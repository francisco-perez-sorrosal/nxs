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
from enum import Enum
from pydantic import AnyUrl

from mcp.types import CallToolResult
from mcp.client.auth import OAuthClientProvider
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientMetadata

from nxs.logger import get_logger
from nxs.mcp_client.auth import oauth_context


class ConnectionStatus(Enum):
    """Connection status enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class MCPAuthClient:
    """MCP Auth Client with OAuth support."""

    def __init__(
        self,
        server_url: str,
        transport_type: str = "streamable_http",
        on_status_change: Optional[Callable[[ConnectionStatus], None]] = None,
    ):
        self.server_url = server_url
        self.transport_type = transport_type
        self.session: ClientSession | None = None
        self.on_status_change = on_status_change
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._use_auth = False

        # Reconnection settings
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 1.0  # Initial delay in seconds
        self._max_reconnect_delay = 60.0  # Maximum delay in seconds
        self._reconnect_backoff_multiplier = 2.0
        self._health_check_interval = 30.0  # Check connection health every 30 seconds
        self._health_check_task: asyncio.Task | None = None

        # Lifecycle management for background connection
        self._connection_task: asyncio.Task | None = None  # Background task keeping connection alive
        self._stop_event: asyncio.Event | None = None      # Event to signal shutdown
        self._ready_event: asyncio.Event | None = None     # Event to signal session is ready

    def _set_status(self, status: ConnectionStatus):
        """Update connection status and notify callback if set."""
        if self._connection_status != status:
            old_status = self._connection_status
            self._connection_status = status
            logger.debug(f"Connection status changed: {old_status.value} -> {status.value}")
            if self.on_status_change:
                try:
                    self.on_status_change(status)
                except Exception as e:
                    logger.error(f"Error in status change callback: {e}")

    @property
    def connection_status(self) -> ConnectionStatus:
        """Get current connection status."""
        return self._connection_status

    @property
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        return self._connection_status == ConnectionStatus.CONNECTED and self.session is not None

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
        self._set_status(ConnectionStatus.CONNECTING)

        # Check transport type
        if self.transport_type == "sse":
            self._set_status(ConnectionStatus.ERROR)
            raise ValueError("SSE transport is not supported")

        # Reset reconnection state
        self._reconnect_attempts = 0

        # Create events for lifecycle coordination
        self._stop_event = asyncio.Event()
        self._ready_event = asyncio.Event()

        # Start background task to maintain connection
        logger.info(f"🚀 Starting background connection maintenance task")
        self._connection_task = asyncio.create_task(self._maintain_connection(use_auth))

        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        # Wait for session to be ready
        logger.info(f"⏳ Waiting for session to be ready...")
        print("📡 Opening StreamableHTTP transport connection...")

        try:
            await self._ready_event.wait()
            logger.info(f"✅ Connection ready, returning control to caller")
            print(f"✅ Connection established! Session is ready for use.\n")
        except Exception as e:
            logger.error(f"❌ Failed to establish connection: {e}")
            self._set_status(ConnectionStatus.ERROR)
            # Clean up if connection failed
            if self._connection_task:
                self._connection_task.cancel()
                try:
                    await self._connection_task
                except asyncio.CancelledError:
                    pass
            if self._health_check_task:
                self._health_check_task.cancel()
            raise

    async def _maintain_connection(self, use_auth: bool):
        """
        Background task that maintains the connection by keeping all context managers alive.
        Implements reconnection logic with exponential backoff.
        
        CRITICAL: This method catches all exceptions to prevent them from blocking the application.
        Connection failures are logged but do not crash the app - the TUI should continue working
        even if MCP connections fail.
        """
        if self._stop_event is None:
            logger.error("❌ Stop event not initialized, cannot maintain connection")
            return
        
        while not self._stop_event.is_set():
            try:
                logger.info(f"🔄 Starting connection maintenance task (auth={use_auth}, attempt={self._reconnect_attempts + 1})")
                self._set_status(ConnectionStatus.CONNECTING if self._reconnect_attempts == 0 else ConnectionStatus.RECONNECTING)

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
                
                # If we get here, the connection was successful and then lost
                # (setup_session exited, which means connection was closed)
                logger.warning(f"⚠️ Connection lost, attempting to reconnect...")
                self._set_status(ConnectionStatus.RECONNECTING)
                self._reconnect_attempts += 1
                
            except asyncio.CancelledError:
                # Task was cancelled - this is expected during shutdown
                logger.info(f"🛑 Connection maintenance task cancelled")
                self._set_status(ConnectionStatus.DISCONNECTED)
                raise  # Re-raise cancellation so asyncio knows task was cancelled
            except Exception as e:
                # Log the error but attempt reconnection
                import traceback
                logger.error(f"❌ Connection maintenance task failed: {e}")
                logger.debug(f"Connection error traceback:\n{traceback.format_exc()}")
                
                # CRITICAL: Always set ready_event even on failure, so connect() doesn't hang
                if self._ready_event and not self._ready_event.is_set():
                    self._ready_event.set()
                    logger.info(f"✅ Set ready_event despite connection failure (non-blocking mode)")
                
                # Check if we should attempt reconnection
                if self._stop_event.is_set():
                    logger.info(f"🛑 Stop event set, not attempting reconnection")
                    self._set_status(ConnectionStatus.DISCONNECTED)
                    break
                
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    logger.error(f"❌ Max reconnection attempts ({self._max_reconnect_attempts}) reached, giving up")
                    self._set_status(ConnectionStatus.ERROR)
                    break
                
                # Attempt reconnection with exponential backoff
                self._reconnect_attempts += 1
                delay = min(
                    self._reconnect_delay * (self._reconnect_backoff_multiplier ** (self._reconnect_attempts - 1)),
                    self._max_reconnect_delay
                )
                logger.info(f"🔄 Reconnecting in {delay:.1f} seconds (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})...")
                self._set_status(ConnectionStatus.RECONNECTING)
                
                # Wait before reconnecting (but check stop_event periodically)
                try:
                    if self._stop_event is not None:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                    else:
                        await asyncio.sleep(delay)
                    # If stop_event was set, break the loop
                    logger.info(f"🛑 Stop event set during reconnect delay")
                    self._set_status(ConnectionStatus.DISCONNECTED)
                    break
                except asyncio.TimeoutError:
                    # Timeout is expected - continue to reconnect
                    pass
            finally:
                # Clean up session if connection was lost
                if self.session:
                    self.session = None
                    logger.info(f"🧹 Session cleaned up")
        
        logger.info(f"🧹 Connection maintenance task exiting")
        self._set_status(ConnectionStatus.DISCONNECTED)

    async def _setup_session(self, read_stream, write_stream, get_session_id):
        """Initialize session and keep it alive until stop signal or connection loss."""
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
                self._set_status(ConnectionStatus.ERROR)
                raise

            # Reset reconnect attempts on successful connection
            self._reconnect_attempts = 0
            self._set_status(ConnectionStatus.CONNECTED)
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

            # Keep session alive until stop signal or connection loss
            logger.info(f"⏳ Session active, waiting for stop signal or connection loss...")
            if self._stop_event:
                await self._stop_event.wait()

            logger.info(f"🛑 Stop signal received, cleaning up session...")
            self._set_status(ConnectionStatus.DISCONNECTED)

    async def _health_check_loop(self):
        """
        Background task that periodically checks connection health.
        If connection is lost, triggers reconnection.
        """
        if self._stop_event is None:
            logger.error("❌ Stop event not initialized, cannot run health check")
            return
        
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(self._health_check_interval)
                
                if self._stop_event.is_set():
                    break
                
                # Check if we have a session and if it's still valid
                if self.session is None:
                    logger.warning(f"⚠️ Health check: Session is None, connection may be lost")
                    if self._connection_status == ConnectionStatus.CONNECTED:
                        logger.warning(f"⚠️ Connection status says CONNECTED but session is None, triggering reconnection")
                        # Trigger reconnection by breaking out of _setup_session
                        # The _maintain_connection loop will handle reconnection
                    continue
                
                # Try to perform a lightweight operation to check connection health
                try:
                    # Use list_tools as a health check - it's lightweight and doesn't require arguments
                    await asyncio.wait_for(self.session.list_tools(), timeout=5.0)
                    logger.debug(f"✅ Health check passed: connection is healthy")
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ Health check timed out, connection may be lost")
                    self.session = None
                    self._set_status(ConnectionStatus.RECONNECTING)
                except Exception as e:
                    logger.warning(f"⚠️ Health check failed: {e}, connection may be lost")
                    self.session = None
                    self._set_status(ConnectionStatus.RECONNECTING)
        except asyncio.CancelledError:
            logger.info(f"🛑 Health check task cancelled")
        except Exception as e:
            logger.error(f"❌ Health check loop error: {e}")

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

    async def disconnect(self):
        """
        Disconnect from the MCP server and clean up resources.

        This signals the background connection task to stop and waits for it to complete.
        """
        logger.info(f"🛑 Disconnect requested")
        print("\n🛑 Disconnecting from server...")
        self._set_status(ConnectionStatus.DISCONNECTED)

        if self._stop_event:
            # Signal background task to stop
            self._stop_event.set()
            logger.info(f"📤 Stop event set, waiting for connection task to finish")

        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"⚠️  Error cancelling health check task: {e}")
            self._health_check_task = None

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