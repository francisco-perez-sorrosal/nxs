from mcp.client.auth import TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from nxs.logger import get_logger

logger = get_logger("mcp_client_store")


class InMemoryTokenStorage(TokenStorage):
    """Simple in-memory token storage implementation."""

    def __init__(self):
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None
        logger.info("🔐 Initialized InMemoryTokenStorage")

    async def get_tokens(self) -> OAuthToken | None:
        import traceback

        # Log the call stack to see WHO is calling get_tokens - DEBUG LOG
        stack = "".join(traceback.format_stack()[-4:-1])  # Get last 3 stack frames
        if self._tokens:
            # Log token info without exposing full token - DEBUG LOG
            logger.info(
                f"📤 get_tokens() CALLED - Returning token (prefix: {self._tokens.access_token[:10] if self._tokens.access_token else 'None'}...)"
            )
            logger.info(f"   Token type: {self._tokens.token_type if hasattr(self._tokens, 'token_type') else 'N/A'}")
            logger.info(
                f"   Expires in: {self._tokens.expires_in if hasattr(self._tokens, 'expires_in') else 'N/A'} seconds"
            )
            if hasattr(self._tokens, "scope"):
                logger.info(f"   Scope: {self._tokens.scope}")
            logger.debug(f"   Call stack:\n{stack}")
        else:
            logger.warning(f"📤 get_tokens() CALLED - No tokens stored yet!")  # DEBUG LOG
            logger.debug(f"   Call stack:\n{stack}")
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        # Log token storage without exposing full token - DEBUG LOG
        logger.info(f"📥 set_tokens() called - Storing new token")
        logger.info(f"   Access token prefix: {tokens.access_token[:10] if tokens.access_token else 'None'}...")
        logger.info(f"   Token type: {tokens.token_type if hasattr(tokens, 'token_type') else 'N/A'}")
        logger.info(f"   Expires in: {tokens.expires_in if hasattr(tokens, 'expires_in') else 'N/A'} seconds")
        if hasattr(tokens, "scope"):
            logger.info(f"   Scope: {tokens.scope}")
        if hasattr(tokens, "refresh_token") and tokens.refresh_token:
            logger.info(f"   Has refresh token: Yes (prefix: {tokens.refresh_token[:10]}...)")
        self._tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        if self._client_info:
            logger.info(
                f"📤 get_client_info() called - Returning client info (client_id: {self._client_info.client_id if hasattr(self._client_info, 'client_id') else 'N/A'})"
            )  # DEBUG LOG
        else:
            logger.warning("📤 get_client_info() called - No client info stored yet!")  # DEBUG LOG
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        logger.info(f"📥 set_client_info() called - Storing client info")  # DEBUG LOG
        logger.info(f"   Client ID: {client_info.client_id if hasattr(client_info, 'client_id') else 'N/A'}")
        if hasattr(client_info, "client_secret") and client_info.client_secret:
            logger.info(f"   Has client secret: Yes (length: {len(client_info.client_secret)})")
        self._client_info = client_info
