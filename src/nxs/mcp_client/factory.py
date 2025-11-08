"""Factory helpers for constructing configured MCP clients."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from nxs.core.mcp_config import MCPServerConfig
from nxs.logger import get_logger
from nxs.mcp_client.client import MCPAuthClient
from nxs.mcp_client.connection import ConnectionManager, ConnectionStatus

logger = get_logger("mcp_client.factory")


class ClientFactory:
    """Create and configure `MCPAuthClient` instances from server configs."""

    def create_client(
        self,
        server_name: str,
        config: MCPServerConfig,
        *,
        status_callback: Optional[Callable[[str, ConnectionStatus], None]] = None,
        progress_callback: Optional[
            Callable[[str, int, int, float], None]
        ] = None,
    ) -> MCPAuthClient | None:
        """
        Create a client for the provided server configuration.

        Args:
            server_name: Name of the server in configuration.
            config: Resolved server configuration.
            status_callback: Optional callback invoked when connection status changes.
            progress_callback: Optional callback invoked during reconnection attempts.

        Returns:
            Configured `MCPAuthClient` instance or `None` if configuration is invalid.
        """
        url = config.remote_url()
        if not config.is_remote() or not url:
            logger.warning(
                "Unsupported MCP server configuration for %s; only remote servers "
                "are currently handled by the ClientFactory.",
                server_name,
            )
            return None

        status_cb = None
        if status_callback is not None:
            def _status_cb(status: ConnectionStatus) -> None:
                status_callback(server_name, status)

            status_cb = _status_cb

        progress_cb = None
        if progress_callback is not None:

            def _progress_cb(attempts: int, max_attempts: int, delay: float) -> None:
                progress_callback(server_name, attempts, max_attempts, delay)

            progress_cb = _progress_cb

        connection_manager = ConnectionManager(
            on_status_change=status_cb,
            on_reconnect_progress=progress_cb,
        )

        client = MCPAuthClient(
            server_url=url,
            connection_manager=connection_manager,
        )

        logger.debug("Created MCPAuthClient for %s", server_name)
        return client

    def create_clients(
        self,
        configs: Dict[str, MCPServerConfig],
        *,
        status_callback: Optional[Callable[[str, ConnectionStatus], None]] = None,
        progress_callback: Optional[
            Callable[[str, int, int, float], None]
        ] = None,
    ) -> Dict[str, MCPAuthClient]:
        """Create MCP clients for all configured servers."""
        clients: Dict[str, MCPAuthClient] = {}
        for server_name, server_config in configs.items():
            client = self.create_client(
                server_name,
                server_config,
                status_callback=status_callback,
                progress_callback=progress_callback,
            )
            if client is not None:
                clients[server_name] = client
        return clients

