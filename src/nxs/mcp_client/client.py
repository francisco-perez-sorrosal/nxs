"""
MCP client with OAuth support.

Connects to an MCP server with OAuth.
"""

import asyncio
import os
import typer
import webbrowser
from datetime import timedelta
from typing import Any

from mcp.client.auth import OAuthClientProvider
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientMetadata

from nxs.logger import get_logger
from nxs.mcp_client.storage import InMemoryTokenStorage
from nxs.mcp_client.callback import CallbackServer


class AuthClient:
    """MCP Auth Client with OAuth support."""

    def __init__(self, server_url: str, transport_type: str = "streamable_http"):
        self.server_url = server_url
        self.transport_type = transport_type
        self.session: ClientSession | None = None

    async def connect(self, use_auth: bool = False):
        print(f"🔗 Attempting to connect to {self.server_url}...")
        logger.info(f"🔗 Starting connection to {self.server_url}")
        logger.info(f"🔗 Transport type: {self.transport_type}")

        callback_server = None
        try:
            callback_server = CallbackServer(port=3030)
            callback_server.start()

            async def callback_handler() -> tuple[str, str | None]:
                """Wait for OAuth callback and return auth code and state."""
                # CRITICAL: Reset callback server state before each OAuth flow
                # This prevents returning stale auth codes from previous flows
                logger.info(f"🔄 callback_handler: Resetting callback server state for fresh OAuth flow")
                callback_server.reset()

                print("⏳ Waiting for authorization callback...")
                logger.info(f"⏳ callback_handler: Waiting for OAuth callback...")
                auth_code = callback_server.wait_for_callback(timeout=300)
                state = callback_server.get_state()
                print(f"🔑 Authorization code: {auth_code}, CB server state: {state}")
                logger.info(f"🔑 callback_handler: Received auth code (prefix: {auth_code[:15]}...), state: {state}")
                logger.info(f"🔄 callback_handler: Returning auth code to SDK for token exchange")
                return auth_code, state

            client_metadata_dict = {
                "client_name": "Nexus MCP Client",
                "redirect_uris": ["http://localhost:3030/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",  # Public client with PKCE
            }

            async def _default_redirect_handler(authorization_url: str) -> None:
                """Default redirect handler that opens the URL in a browser."""
                print(f"Opening browser for authorization: {authorization_url}")
                logger.info(f"🌐 redirect_handler: OAuth flow triggered, opening browser")
                logger.info(f"🌐 redirect_handler: Authorization URL: {authorization_url[:100]}...")
                webbrowser.open(authorization_url)

            # Create transport with auth handler based on transport type
            if self.transport_type == "sse":
                raise ValueError("SSE transport is not supported")
            else:
                print("📡 Opening StreamableHTTP transport connection with auth...")
                logger.info(f"🔗 Opening StreamableHTTP transport with OAuth")
                logger.info(f"📝 Note: OAuth may be triggered on first unauthorized request")

                # Let the SDK handle OAuth naturally - it will trigger on first 401
                if use_auth:
                    # Create OAuth authentication handler using the new interface
                    storage = InMemoryTokenStorage()
                    logger.info(f"📦 Creating OAuthClientProvider for {self.server_url.replace('/mcp', '')}")

                    oauth_auth = OAuthClientProvider(
                        server_url=self.server_url.replace("/mcp", ""),
                        client_metadata=OAuthClientMetadata.model_validate(client_metadata_dict),
                        storage=storage,
                        redirect_handler=_default_redirect_handler,
                        callback_handler=callback_handler,
                    )
                else:
                    logger.warning(f"🔐 No OAuth authentication required for {self.server_url}")
                    oauth_auth = None

                async with streamablehttp_client(
                    url=self.server_url,
                    auth=oauth_auth,  # SDK will trigger OAuth on first 401 and retry
                    timeout=timedelta(seconds=60),
                ) as (read_stream, write_stream, get_session_id):
                    logger.info(f"✅ StreamableHTTP transport connected, starting session")
                    await self._run_session(read_stream, write_stream, get_session_id)

        except Exception as e:
            logger.error(f"❌ Connection failed with error: {e}")
            print(f"❌ Failed to connect: {e}")
            import traceback

            traceback.print_exc()
        finally:
            # Clean up callback server
            if callback_server:
                logger.info(f"🧹 Stopping callback server")
                callback_server.stop()

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

    async def list_tools(self):
        """List available tools from the server."""
        if not self.session:
            print("❌ Not connected to server")
            return

        try:
            result = await self.session.list_tools()
            if hasattr(result, "tools") and result.tools:
                print("\n📋 Available tools:")
                for i, tool in enumerate(result.tools, 1):
                    print(f"{i}. {tool.name}")
                    if tool.description:
                        print(f"   Description: {tool.description}")
                    print()
            else:
                print("No tools available")
        except Exception as e:
            print(f"❌ Failed to list tools: {e}")

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None):
        """Call a specific tool."""
        if not self.session:
            print("❌ Not connected to server")
            return

        try:
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

                if command == "quit":
                    break

                elif command == "list":
                    await self.list_tools()

                elif command.startswith("call "):
                    parts = command.split(maxsplit=2)
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

                else:
                    print("❌ Unknown command. Try 'list', 'call <tool_name>', or 'quit'")

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except EOFError:
                break

app = typer.Typer()
logger = get_logger("mcp_client")

@app.command()
def main(
    server_url: str = typer.Option(os.getenv("MCP_SERVER_URL", "http://localhost:8000"), "--server-url", help="MCP server URL"),
    transport_type: str = typer.Option(os.getenv("MCP_TRANSPORT_TYPE", "streamable_http"), "--transport-type", help="MCP transport type"),
    use_auth: bool = typer.Option(os.getenv("MCP_USE_AUTH", "false").lower() == "true", "--use-auth", help="Use OAuth authentication"),
):
    server_url = f"{server_url}/mcp" if transport_type == "streamable_http" else f"{server_url}"

    logger.info(f"🚀 MCP Client")
    logger.info(f"Connecting to: {server_url}")
    logger.info(f"Transport type: {transport_type}")
    logger.info(f"Use OAuth authentication: {use_auth}")

    client = AuthClient(server_url, transport_type)
    asyncio.run(client.connect(use_auth))

if __name__ == "__main__":
    app()