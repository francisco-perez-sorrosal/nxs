import webbrowser
from contextlib import asynccontextmanager

from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata

from nxs.logger import get_logger
from nxs.mcp_client.callback import CallbackServer
from nxs.mcp_client.storage import InMemoryTokenStorage

logger = get_logger("mcp_client_auth")


client_metadata_dict = {
    "client_name": "Nexus MCP Client",
    "redirect_uris": ["http://localhost:3030/callback"],
    "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"],
    "token_endpoint_auth_method": "none",  # Public client with PKCE
}

def _create_redirect_handler():
    """Create a redirect handler that opens the URL in a browser."""
    async def redirect_handler(authorization_url: str) -> None:
        """Default redirect handler that opens the URL in a browser."""
        print(f"Opening browser for authorization: {authorization_url}")
        logger.info(f"🌐 redirect_handler: OAuth flow triggered, opening browser")
        logger.info(f"🌐 redirect_handler: Authorization URL: {authorization_url[:100]}...")
        webbrowser.open(authorization_url)
    return redirect_handler


def _create_callback_handler(callback_server: CallbackServer):
    """Create a callback handler that uses the provided callback server."""
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
    return callback_handler


@asynccontextmanager
async def oauth_context(server_url: str):
    """
    Context manager for OAuth authentication that manages callback server lifecycle.

    Usage:
        async with oauth_context(server_url) as oauth_provider:
            async with streamablehttp_client(..., auth=oauth_provider) as streams:
                # Use authenticated connection
    """
    # Create and start callback server
    callback_server = CallbackServer(port=3030)
    callback_server.start()
    logger.info(f"🔐 Started OAuth context with callback server")

    try:
        # Create OAuth provider with handlers that use the callback server
        storage = InMemoryTokenStorage()
        logger.info(f"📦 Creating OAuthClientProvider for {server_url.replace('/mcp', '')}")

        oauth_provider = OAuthClientProvider(
            server_url=server_url.replace("/mcp", ""),
            client_metadata=OAuthClientMetadata.model_validate(client_metadata_dict),
            storage=storage,
            redirect_handler=_create_redirect_handler(),
            callback_handler=_create_callback_handler(callback_server),
        )

        yield oauth_provider

    finally:
        # Clean up callback server
        logger.info(f"🧹 Stopping callback server")
        callback_server.stop()
