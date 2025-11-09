"""ConnectionManager - Manages MCP client lifecycle and connection status."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Dict, Optional
from types import MappingProxyType

from nxs.application.mcp_config import MCPServersConfig, load_mcp_config
from nxs.domain.protocols import MCPClient, ClientProvider
from nxs.domain.events import (
    ConnectionStatusChanged,
    EventBus,
    ReconnectProgress,
)
from nxs.domain.types import ConnectionStatus
from nxs.logger import get_logger

logger = get_logger("connection_manager")


class ConnectionManager:
    """
    Manages MCP client lifecycle and connection status.

    Responsibilities:
    - Create MCP clients from configuration
    - Connect/disconnect clients
    - Track connection status
    - Publish connection events
    """

    def __init__(
        self,
        config: Optional[MCPServersConfig] = None,
        event_bus: Optional[EventBus] = None,
        client_provider: Optional[ClientProvider] = None,
    ):
        """
        Initialize the ConnectionManager.

        Args:
            config: MCP server configuration (loads from default if None)
            event_bus: Event bus for publishing connection events
            client_provider: Factory for creating MCP clients (uses default if None)
        """
        self._config = config or load_mcp_config()
        self.event_bus = event_bus or EventBus()

        # Pragmatic fallback: import concrete implementation only when needed
        if client_provider is None:
            from nxs.infrastructure.mcp.factory import ClientFactory
            client_provider = ClientFactory()  # type: ignore[assignment]
        self._client_factory: ClientProvider = client_provider

        self._clients: Dict[str, MCPClient] = {}
        self._previous_statuses: Dict[str, ConnectionStatus] = {}

    async def initialize(self, use_auth: bool = False) -> None:
        """
        Create and connect MCP clients for all configured servers.

        Args:
            use_auth: Whether to use OAuth authentication for remote servers
        """
        logger.info("Initializing ConnectionManager")

        created_clients = self._client_factory.create_clients(
            self._config.mcpServers,
            status_callback=self._handle_status_change,
            progress_callback=self._handle_reconnect_progress,
        )

        self._clients.update(created_clients)
        logger.info("Prepared %d MCP client(s)", len(created_clients))

        for server_name, client in created_clients.items():
            try:
                await client.connect(use_auth=use_auth)
                logger.info("Successfully connected to %s", server_name)
            except Exception as err:  # pragma: no cover - defensive logging
                logger.error("Failed to connect to %s: %s", server_name, err)
                self._handle_status_change(server_name, ConnectionStatus.ERROR)

    async def cleanup(self) -> None:
        """Disconnect all clients and clear state."""
        if not self._clients:
            return

        logger.info("Cleaning up %d MCP client(s)", len(self._clients))
        tasks = []
        for server_name, client in list(self._clients.items()):
            disconnect = getattr(client, "disconnect", None)
            if callable(disconnect):
                tasks.append(self._disconnect_client(server_name, disconnect))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._clients.clear()
        logger.info("ConnectionManager cleanup complete")

    async def _disconnect_client(self, server_name: str, disconnect_callable) -> None:
        """
        Disconnect a single client.

        Args:
            server_name: Name of the server
            disconnect_callable: Async disconnect function
        """
        try:
            await disconnect_callable()
        except Exception as err:  # pragma: no cover - defensive logging
            logger.error("Error disconnecting from %s: %s", server_name, err)

    @property
    def clients(self) -> Mapping[str, MCPClient]:
        """
        Return a read-only mapping of configured MCP clients.

        Returns:
            Immutable mapping of server name to MCPClient
        """
        return MappingProxyType(self._clients)

    def get_server_statuses(self) -> dict[str, ConnectionStatus]:
        """
        Get connection status for all servers.

        Returns:
            Dictionary mapping server name to connection status
        """
        statuses: dict[str, ConnectionStatus] = {}
        for server_name, client in self._clients.items():
            status = getattr(client, "connection_status", None)
            if isinstance(status, ConnectionStatus):
                statuses[server_name] = status
        return statuses

    def _handle_status_change(
        self,
        server_name: str,
        status: ConnectionStatus,
    ) -> None:
        """
        Handle connection status change and publish event.

        Args:
            server_name: Name of the server
            status: New connection status
        """
        if not self.event_bus:
            return

        previous_status = self._previous_statuses.get(server_name)
        try:
            self.event_bus.publish(
                ConnectionStatusChanged(
                    server_name=server_name,
                    status=status,
                    previous_status=previous_status,
                )
            )
        except Exception as err:  # pragma: no cover - defensive logging
            logger.error(
                "Error publishing ConnectionStatusChanged for %s: %s",
                server_name,
                err,
            )
        else:
            self._previous_statuses[server_name] = status

    def _handle_reconnect_progress(
        self,
        server_name: str,
        attempts: int,
        max_attempts: int,
        next_retry_delay: float,
    ) -> None:
        """
        Handle reconnection progress and publish event.

        Args:
            server_name: Name of the server
            attempts: Current attempt number
            max_attempts: Maximum number of attempts
            next_retry_delay: Delay before next retry in seconds
        """
        if not self.event_bus:
            return
        try:
            self.event_bus.publish(
                ReconnectProgress(
                    server_name=server_name,
                    attempts=attempts,
                    max_attempts=max_attempts,
                    next_retry_delay=next_retry_delay,
                )
            )
        except Exception as err:  # pragma: no cover - defensive logging
            logger.error(
                "Error publishing ReconnectProgress for %s: %s",
                server_name,
                err,
            )
