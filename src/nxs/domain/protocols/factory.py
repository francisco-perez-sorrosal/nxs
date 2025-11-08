"""Client factory protocol."""

from typing import Protocol, Callable
from nxs.domain.protocols.mcp_client import MCPClient
from nxs.domain.types import ConnectionStatus

__all__ = ["ClientProvider"]


class ClientProvider(Protocol):
    """Protocol for creating MCP clients.

    This protocol defines the interface for factories that create
    and configure MCP client instances.
    """

    def create_clients(
        self,
        servers_config: dict,
        status_callback: Callable[[str, ConnectionStatus], None],
        progress_callback: Callable,
    ) -> dict[str, MCPClient]:
        """Create clients for configured servers.

        Args:
            servers_config: Dictionary of server configurations
            status_callback: Callback for connection status changes
            progress_callback: Callback for reconnection progress

        Returns:
            Dictionary mapping server names to MCPClient instances
        """
        ...
