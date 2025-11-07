"""
MCP client with OAuth support.

Connects to an MCP server with OAuth.
"""

import asyncio
import json
import os
from mcp import types
import typer
import webbrowser
from datetime import timedelta
from typing import Any, Callable, Optional
from pydantic import AnyUrl

from mcp.types import CallToolResult
from mcp.client.auth import OAuthClientProvider
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientMetadata

from nxs.logger import get_logger
from nxs.mcp_client.auth import oauth_context
from nxs.mcp_client.connection import ConnectionManager, ConnectionStatus


class MCPAuthClient:
    """MCP Auth Client with OAuth support."""

    def __init__(
        self,
        server_url: str,
        transport_type: str = "streamable_http",
        on_status_change: Optional[Callable[[ConnectionStatus], None]] = None,
        on_reconnect_progress: Optional[Callable[[int, int, float], None]] = None,
    ):
        self.server_url = server_url
        self.transport_type = transport_type
        self._use_auth = False

        # Use ConnectionManager for all connection management
        self._connection_manager = ConnectionManager(
            on_status_change=on_status_change,
            on_reconnect_progress=on_reconnect_progress,
        )

    @property
    def connection_status(self) -> ConnectionStatus:
        """Get current connection status."""
        return self._connection_manager.status

    @property
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        return self._connection_manager.is_connected

    @property
    def session(self) -> ClientSession | None:
        """Get current session."""
        return self._connection_manager.session

    @property
    def reconnect_info(self) -> dict[str, Any]:
        """
        Get reconnection progress information.

        Returns:
            Dictionary with reconnection info:
            - attempts: Current attempt number
            - max_attempts: Maximum reconnection attempts
            - next_retry_delay: Seconds until next retry (if reconnecting)
            - error_message: Error message if status is ERROR
        """
        return self._connection_manager.reconnect_info

    async def connect(self, use_auth: bool = False):
        """
        Connect to MCP server and keep connection alive in background.

        This method returns once the session is ready but doesn't block.
        The connection is maintained in a background task, allowing external
        code to use the session via self.session.

        Args:
            use_auth: Whether to use OAuth authentication
        """
        self._use_auth = use_auth
        print(f"🔗 Attempting to connect to {self.server_url}...")
        logger.info(f"🔗 Starting non-blocking connection to {self.server_url}")
        logger.info(f"🔗 Transport type: {self.transport_type}")

        # Check transport type
        if self.transport_type == "sse":
            raise ValueError("SSE transport is not supported")

        print("📡 Opening StreamableHTTP transport connection...")

        # Use ConnectionManager to handle connection
        await self._connection_manager.connect(self._connection_function)

        logger.info(f"✅ Connection ready, returning control to caller")
        print(f"✅ Connection established! Session is ready for use.\n")

    async def _connection_function(self, stop_event: asyncio.Event) -> None:
        """
        Establish and maintain connection with the MCP server.

        This function is called by ConnectionManager and should:
        1. Establish the connection (with or without auth)
        2. Initialize the session
        3. Set the session on ConnectionManager
        4. Wait for stop_event before cleaning up

        Args:
            stop_event: Event to signal when to stop and clean up
        """
        logger.info(f"Connection function starting (auth={self._use_auth})")

        if self._use_auth:
            logger.info("Using OAuth context")
            async with oauth_context(self.server_url) as oauth_provider:
                async with streamablehttp_client(
                    url=self.server_url,
                    auth=oauth_provider,
                    timeout=timedelta(seconds=60),
                ) as (read_stream, write_stream, get_session_id):
                    logger.info("StreamableHTTP transport connected (with auth)")
                    await self._setup_session(read_stream, write_stream, get_session_id, stop_event)
        else:
            logger.info("No OAuth context")
            async with streamablehttp_client(
                url=self.server_url,
                auth=None,
                timeout=timedelta(seconds=60),
            ) as (read_stream, write_stream, get_session_id):
                logger.info("StreamableHTTP transport connected (no auth)")
                await self._setup_session(read_stream, write_stream, get_session_id, stop_event)

        logger.info("Connection function exiting (connection lost or stopped)")

    async def _setup_session(self, read_stream, write_stream, get_session_id, stop_event: asyncio.Event):
        """Initialize session and keep it alive until stop signal or connection loss."""
        print("🤝 Initializing MCP session...")
        logger.info("Creating ClientSession")

        async with ClientSession(read_stream, write_stream) as session:
            print("⚡ Starting session initialization...")
            logger.info("Calling session.initialize()")

            try:
                await session.initialize()
                logger.info("Session initialization completed successfully")
                print("✨ Session initialization complete!")
            except Exception as e:
                logger.error(f"Session initialization failed: {e}")
                raise

            # Set session on ConnectionManager (this will mark ready and set status to CONNECTED)
            self._connection_manager.set_session(session)
            print(f"\n✅ Connected to MCP server at {self.server_url}")
            logger.info(f"Full connection established to {self.server_url}")

            if get_session_id:
                session_id = get_session_id()
                if session_id:
                    print(f"Session ID: {session_id}")
                    logger.info(f"Session ID: {session_id}")

            # Keep session alive until stop signal or connection loss
            logger.info("Session active, waiting for stop signal or connection loss...")
            await stop_event.wait()

            logger.info("Stop signal received, cleaning up session...")

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    async def list_tools(self) -> list[types.Tool]:
        """List available tools from the server."""
        try:
            if not self.session:
                logger.warning("⚠️  Cannot list tools: session is None (connection may have failed)")
                return []
            result = await self.session.list_tools()
            if hasattr(result, "tools") and result.tools:
                return result.tools
            return []
        except Exception as e:
            logger.error(f"❌ Failed to list tools: {e}")
            return []  # Return empty list instead of raising - allow app to continue

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> types.CallToolResult | None:
        """Call a specific tool."""
        try:
            if not self.session:
                logger.warning(f"⚠️  Cannot call tool '{tool_name}': session is None (connection may have failed)")
                return None
            logger.info(f"Arguments: {arguments} {type(arguments)}")
            result = await self.session.call_tool(tool_name, arguments or {})
            print(f"\n🔧 Tool '{tool_name}' result:")
            if hasattr(result, "content"):
                for content in result.content:
                    if content.type == "text":
                        print(content.text)
                    else:
                        print(content)
            else:
                print(result)
            return result
        except Exception as e:
            logger.error(f"❌ Failed to call tool '{tool_name}': {e}")
            return None  # Return None instead of raising - allow app to continue

    # -------------------------------------------------------------------------
    # Prompts
    # -------------------------------------------------------------------------

    async def list_prompts(self) -> list[types.Prompt]:
        """List available prompts from the server."""
        try:
            if not self.session:
                logger.warning("⚠️  Cannot list prompts: session is None (connection may have failed)")
                return []
            result = await self.session.list_prompts()
            return result.prompts if result else []
        except Exception as e:
            logger.error(f"❌ Failed to list prompts: {e}")
            return []  # Return empty list instead of raising - allow app to continue
        
    async def get_prompt(self, prompt_name: str, args: dict[str, str]) -> list[types.PromptMessage]:
        """Get a prompt with the given arguments."""
        try:
            if not self.session:
                logger.warning(f"⚠️  Cannot get prompt '{prompt_name}': session is None (connection may have failed)")
                return []
            result = await self.session.get_prompt(prompt_name, args)
            return result.messages if result else []
        except Exception as e:
            logger.error(f"❌ Failed to get prompt '{prompt_name}': {e}")
            return []  # Return empty list instead of raising - allow app to continue

    # -------------------------------------------------------------------------
    # Resources
    # -------------------------------------------------------------------------

    async def list_resources(self) -> list[types.Resource]:
        """List available resources from the server."""
        try:
            if not self.session:
                logger.warning("⚠️  Cannot list resources: session is None (connection may have failed)")
                return []
            result = await self.session.list_resources()
            return result.resources if result else []
        except Exception as e:
            logger.error(f"❌ Failed to list resources: {e}")
            return []  # Return empty list instead of raising - allow app to continue


    async def read_resource(self, uri: str) -> Any:
        """Read a resource by URI."""
        try:
            if not self.session:
                logger.warning(f"⚠️  Cannot read resource '{uri}': session is None (connection may have failed)")
                return None
            result = await self.session.read_resource(AnyUrl(uri))
            resource = result.contents[0]

            if isinstance(resource, types.TextResourceContents):
                if resource.mimeType == "application/json":
                    return json.loads(resource.text)

                return resource.text
            return None
        except Exception as e:
            logger.error(f"❌ Failed to read resource '{uri}': {e}")
            return None  # Return None instead of raising - allow app to continue

    # -------------------------------------------------------------------------
    # Main Interactive Loop !!!
    # -------------------------------------------------------------------------

    async def interactive_loop(self):
        """Run interactive command loop."""
        print("\n🎯 Interactive MCP Client")
        print("Commands:")
        print("  list - List available tools")
        print("  call <tool_name> [args] - Call a tool")
        print("  quit - Exit the client")
        print()

        while True:
            try:
                command = input("mcp> ").strip()

                if not command:
                    continue

                match command:
                    case "quit":
                        break

                    case "resources":
                        await self.list_resources()

                    case "list":
                        await self.list_tools()

                    case cmd if cmd.startswith("call "):
                        parts = cmd.split(maxsplit=2)
                        tool_name = parts[1] if len(parts) > 1 else ""

                        if not tool_name:
                            print("❌ Please specify a tool name")
                            continue

                        # Parse arguments (simple JSON-like format)
                        arguments = {}
                        if len(parts) > 2:
                            import json
                            logger.info(f"🔍 Parsing arguments: {parts[2]}")
                            try:
                                arguments = json.loads(parts[2])
                            except json.JSONDecodeError:
                                print("❌ Invalid arguments format (expected JSON)")
                                continue

                        await self.call_tool(tool_name, arguments)

                    case _:
                        print("❌ Unknown command. Try 'list', 'call <tool_name>', or 'quit'")

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except EOFError:
                break

    async def retry_connection(self, use_auth: bool = False) -> None:
        """
        Manually retry connection after ERROR status.

        This resets the reconnection state and attempts to reconnect.

        Args:
            use_auth: Whether to use OAuth authentication
        """
        self._use_auth = use_auth
        await self._connection_manager.retry_connection(self._connection_function)

    async def disconnect(self):
        """
        Disconnect from the MCP server and clean up resources.

        This signals the background connection task to stop and waits for it to complete.
        """
        logger.info("Disconnect requested")
        print("\n🛑 Disconnecting from server...")

        await self._connection_manager.disconnect()

        print("👋 Disconnected successfully!")
        logger.info("Disconnect complete")

    async def run_interactive(self):
        """
        Run the interactive command loop.

        This is optional - call this method if you want to use the interactive CLI.
        Otherwise, just use the session directly via self.session.

        Raises:
            RuntimeError: If not connected to server
        """
        if not self.session:
            raise RuntimeError("Not connected to server. Call connect() first.")

        logger.info(f"🎮 Starting interactive mode")
        await self.interactive_loop()

app = typer.Typer()
logger = get_logger("mcp_client")

@app.command()
def main(
    server_url: str = typer.Option(os.getenv("MCP_SERVER_URL", "http://localhost:8000"), "--server-url", help="MCP server URL"),
    transport_type: str = typer.Option(os.getenv("MCP_TRANSPORT_TYPE", "streamable_http"), "--transport-type", help="MCP transport type"),
    use_auth: bool = typer.Option(os.getenv("MCP_USE_AUTH", "false").lower() == "true", "--use-auth", help="Use OAuth authentication"),
):
    """
    MCP Client CLI - Connect to an MCP server and run interactive commands.

    The client now supports both interactive mode (default) and programmatic access.
    """
    server_url = f"{server_url}/mcp" if transport_type == "streamable_http" else f"{server_url}"

    logger.info(f"🚀 MCP Client")
    logger.info(f"Connecting to: {server_url}")
    logger.info(f"Transport type: {transport_type}")
    logger.info(f"Use OAuth authentication: {use_auth}")

    async def run():
        client = MCPAuthClient(server_url, transport_type)
        try:
            # Connect (non-blocking, returns when session is ready)
            await client.connect(use_auth)

            # Run interactive loop (blocks here)
            await client.run_interactive()
            
            await client.call_tool("run", {"code": "print(1+1)", "session_id": None})

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            logger.info(f"⚠️  User interrupt")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            logger.error(f"❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Always clean up
            await client.disconnect()

    asyncio.run(run())

if __name__ == "__main__":
    app()