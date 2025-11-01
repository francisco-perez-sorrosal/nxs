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
from typing import Any
from pydantic import AnyUrl

from mcp.types import CallToolResult
from mcp.client.auth import OAuthClientProvider
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientMetadata

from nxs.logger import get_logger
from nxs.mcp_client.auth import oauth_context


class MCPAuthClient:
    """MCP Auth Client with OAuth support."""

    def __init__(self, server_url: str, transport_type: str = "streamable_http"):
        self.server_url = server_url
        self.transport_type = transport_type
        self.session: ClientSession | None = None

        # Lifecycle management for background connection
        self._connection_task: asyncio.Task | None = None  # Background task keeping connection alive
        self._stop_event: asyncio.Event | None = None      # Event to signal shutdown
        self._ready_event: asyncio.Event | None = None     # Event to signal session is ready

    async def connect(self, use_auth: bool = False):
        """
        Connect to MCP server and keep connection alive in background.

        This method returns once the session is ready but doesn't block.
        The connection is maintained in a background task, allowing external
        code to use the session via self.session.

        Args:
            use_auth: Whether to use OAuth authentication
        """
        print(f"🔗 Attempting to connect to {self.server_url}...")
        logger.info(f"🔗 Starting non-blocking connection to {self.server_url}")
        logger.info(f"🔗 Transport type: {self.transport_type}")

        # Check transport type
        if self.transport_type == "sse":
            raise ValueError("SSE transport is not supported")

        # Create events for lifecycle coordination
        self._stop_event = asyncio.Event()
        self._ready_event = asyncio.Event()

        # Start background task to maintain connection
        logger.info(f"🚀 Starting background connection maintenance task")
        self._connection_task = asyncio.create_task(self._maintain_connection(use_auth))

        # Wait for session to be ready
        logger.info(f"⏳ Waiting for session to be ready...")
        print("📡 Opening StreamableHTTP transport connection...")

        try:
            await self._ready_event.wait()
            logger.info(f"✅ Connection ready, returning control to caller")
            print(f"✅ Connection established! Session is ready for use.\n")
        except Exception as e:
            logger.error(f"❌ Failed to establish connection: {e}")
            # Clean up if connection failed
            if self._connection_task:
                self._connection_task.cancel()
                try:
                    await self._connection_task
                except asyncio.CancelledError:
                    pass
            raise

    async def _maintain_connection(self, use_auth: bool):
        """Background task that maintains the connection by keeping all context managers alive."""
        try:
            logger.info(f"🔄 Starting connection maintenance task (auth={use_auth})")

            if use_auth:
                logger.info(f"🔐 Using OAuth context")
                async with oauth_context(self.server_url) as oauth_provider:
                    async with streamablehttp_client(
                        url=self.server_url,
                        auth=oauth_provider,
                        timeout=timedelta(seconds=60),
                    ) as (read_stream, write_stream, get_session_id):
                        logger.info(f"✅ StreamableHTTP transport connected (with auth)")
                        await self._setup_session(read_stream, write_stream, get_session_id)
            else:
                logger.info(f"🔓 No OAuth context")
                async with streamablehttp_client(
                    url=self.server_url,
                    auth=None,
                    timeout=timedelta(seconds=60),
                ) as (read_stream, write_stream, get_session_id):
                    logger.info(f"✅ StreamableHTTP transport connected (no auth)")
                    await self._setup_session(read_stream, write_stream, get_session_id)

        except Exception as e:
            logger.error(f"❌ Connection maintenance task failed: {e}")
            # If ready event wasn't set yet, set it so connect() doesn't hang
            if self._ready_event and not self._ready_event.is_set():
                self._ready_event.set()
            raise
        finally:
            logger.info(f"🧹 Connection maintenance task exiting")
            self.session = None

    async def _setup_session(self, read_stream, write_stream, get_session_id):
        """Initialize session and keep it alive until stop signal."""
        print("🤝 Initializing MCP session...")
        logger.info(f"🤝 Creating ClientSession")

        async with ClientSession(read_stream, write_stream) as session:
            self.session = session
            print("⚡ Starting session initialization...")
            logger.info(f"⚡ Calling session.initialize()")

            try:
                await session.initialize()
                logger.info(f"✅ Session initialization completed successfully")
                print("✨ Session initialization complete!")
            except Exception as e:
                logger.error(f"❌ Session initialization failed: {e}")
                raise

            print(f"\n✅ Connected to MCP server at {self.server_url}")
            logger.info(f"✅ Full connection established to {self.server_url}")

            if get_session_id:
                session_id = get_session_id()
                if session_id:
                    print(f"Session ID: {session_id}")
                    logger.info(f"📋 Session ID: {session_id}")

            # Signal that session is ready for use
            if self._ready_event:
                self._ready_event.set()
                logger.info(f"✅ Session ready - signaled ready event")

            # Keep session alive until stop signal
            logger.info(f"⏳ Session active, waiting for stop signal...")
            if self._stop_event:
                await self._stop_event.wait()

            logger.info(f"🛑 Stop signal received, cleaning up session...")

    async def _run_session(self, read_stream, write_stream, get_session_id):
        """Run the MCP session with the given streams."""
        print("🤝 Initializing MCP session...")
        logger.info(f"🤝 Creating ClientSession")
        async with ClientSession(read_stream, write_stream) as session:
            self.session = session
            print("⚡ Starting session initialization...")
            logger.info(f"⚡ Calling session.initialize() - this may trigger OAuth if needed")
            try:
                await session.initialize()
                logger.info(f"✅ Session initialization completed successfully")
                print("✨ Session initialization complete!")
            except Exception as e:
                logger.error(f"❌ Session initialization failed: {e}")
                raise

            print(f"\n✅ Connected to MCP server at {self.server_url}")
            logger.info(f"✅ Full connection established to {self.server_url}")
            if get_session_id:
                session_id = get_session_id()
                if session_id:
                    print(f"Session ID: {session_id}")
                    logger.info(f"📋 Session ID: {session_id}")

            # Run interactive loop
            logger.info(f"🎮 Starting interactive loop")
            await self.interactive_loop()

    def _check_session_or_raise(self):
        if not self.session:
            raise RuntimeError("❌ Not connected to server")

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    async def list_tools(self) -> list[types.Tool]:
        """List available tools from the server."""
        try:
            self._check_session_or_raise()
            result = await self.session.list_tools()
            if hasattr(result, "tools") and result.tools:
                return result.tools
            return []
        except Exception as e:
            print(f"❌ Failed to list tools: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> types.CallToolResult | None:
        """Call a specific tool."""

        try:
            self._check_session_or_raise()
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
        except Exception as e:
            print(f"❌ Failed to call tool '{tool_name}': {e}")

    # -------------------------------------------------------------------------
    # Prompts
    # -------------------------------------------------------------------------

    async def list_prompts(self) -> list[types.Prompt]:
        try:
            self._check_session_or_raise()
            result = await self.session.list_prompts() if self.session else None
            return result.prompts if result else []
        except Exception as e:
            print(f"❌ Failed to list prompts: {e}")
            return []
        
    async def get_prompt(self, prompt_name: str, args: dict[str, str]) -> list[types.PromptMessage]:
        try:
            self._check_session_or_raise()
            result = await self.session.get_prompt(prompt_name, args) if self.session else None
            return result.messages if result else []
        except Exception as e:
            print(f"❌ Failed to get prompt: {e}")
            return []

    # -------------------------------------------------------------------------
    # Resources
    # -------------------------------------------------------------------------

    async def list_resources(self) -> list[types.Resource]:
        try:
            self._check_session_or_raise()
            result = await self.session.list_resources()
            return result.resources
        except Exception as e:
            print(f"❌ Failed to list resources: {e}")
            return []


    async def read_resource(self, uri: str) -> Any:
        try:
            self._check_session_or_raise()
            result = await self.session.read_resource(AnyUrl(uri))
            resource = result.contents[0]

            if isinstance(resource, types.TextResourceContents):
                if resource.mimeType == "application/json":
                    return json.loads(resource.text)

                return resource.text
        except Exception as e:
            print(f"❌ Failed to read resource: {e}")
            return None

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

    async def disconnect(self):
        """
        Disconnect from the MCP server and clean up resources.

        This signals the background connection task to stop and waits for it to complete.
        """
        logger.info(f"🛑 Disconnect requested")
        print("\n🛑 Disconnecting from server...")

        if self._stop_event:
            # Signal background task to stop
            self._stop_event.set()
            logger.info(f"📤 Stop event set, waiting for connection task to finish")

        if self._connection_task:
            try:
                # Wait for background task to complete
                await self._connection_task
                logger.info(f"✅ Connection task completed")
            except Exception as e:
                logger.error(f"⚠️  Error during disconnect: {e}")

        # Clean up
        self.session = None
        self._connection_task = None
        self._stop_event = None
        self._ready_event = None

        print("👋 Disconnected successfully!")
        logger.info(f"👋 Disconnect complete")

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