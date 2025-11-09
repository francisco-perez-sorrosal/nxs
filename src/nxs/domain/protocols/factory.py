"""Client factory protocol."""

from typing import Protocol, Callable, Optional, Any
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
        configs: dict[str, Any],
        *,
        status_callback: Optional[Callable[[str, ConnectionStatus], None]] = None,
        progress_callback: Optional[Callable[[str, int, int, float], None]] = None,
    ) -> dict[str, MCPClient]:
        """Create clients for configured servers.

        Args:
            configs: Dictionary of server configurations
            status_callback: Optional callback for connection status changes
            progress_callback: Optional callback for reconnection progress

        Returns:
            Dictionary mapping server names to MCPClient instances
        """
        ...
