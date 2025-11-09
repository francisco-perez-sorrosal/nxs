"""ArtifactManager - facade for MCP artifact access and caching."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Optional

from mcp.types import Prompt, Tool

from copy import deepcopy

from nxs.application.artifacts import (
    ArtifactCollection,
    ArtifactRepository,
)
from nxs.application.connection_manager import MCPConnectionManager
from nxs.application.mcp_config import MCPServersConfig
from nxs.domain.protocols import Cache, MCPClient, ClientProvider
from nxs.domain.events import ArtifactsFetched, EventBus
from nxs.domain.types import ConnectionStatus
from nxs.logger import get_logger

logger = get_logger("artifact_manager")


class ArtifactManager:
    """
    High-level facade for MCP artifact access and caching.

    Focuses on artifact retrieval and caching. Connection lifecycle
    is delegated to MCPConnectionManager.
    """

    def __init__(
        self,
        connection_manager: Optional[MCPConnectionManager] = None,
        event_bus: Optional[EventBus] = None,
        artifacts_cache: Optional[Cache[str, ArtifactCollection]] = None,
        *,
        artifact_repository: Optional[ArtifactRepository] = None,
        # Legacy parameters for backward compatibility
        config: Optional[MCPServersConfig] = None,
        client_provider: Optional[ClientProvider] = None,
    ):
        """
        Initialize the ArtifactManager.

        Args:
            connection_manager: MCPConnectionManager instance (creates new if None)
            event_bus: Event bus for publishing artifact events
            artifacts_cache: Cache for storing artifacts
            artifact_repository: Repository for fetching artifacts
            config: Legacy parameter - used only if connection_manager is None
            client_provider: Legacy parameter - used only if connection_manager is None
        """
        # Create or use provided MCPConnectionManager
        if connection_manager is None:
            connection_manager = MCPConnectionManager(
                config=config,
                event_bus=event_bus,
                client_provider=client_provider,
            )
        self._connection_manager = connection_manager
        self.event_bus = event_bus or connection_manager.event_bus

        # Artifact management components
        from nxs.infrastructure.cache import MemoryCache

        clients_provider = lambda: self._connection_manager.clients
        self._artifact_repository = artifact_repository or ArtifactRepository(clients_provider=clients_provider)
        self._cache: Cache[str, ArtifactCollection] = artifacts_cache or MemoryCache()

    # --------------------------------------------------------------------- #
    # Lifecycle (delegated to MCPConnectionManager)
    # --------------------------------------------------------------------- #
    async def initialize(self, use_auth: bool = False) -> None:
        """
        Initialize MCP connections.

        Delegates to MCPConnectionManager for connection lifecycle.

        Args:
            use_auth: Whether to use OAuth authentication for remote servers
        """
        logger.info("Initializing ArtifactManager")
        await self._connection_manager.initialize(use_auth=use_auth)

    async def cleanup(self) -> None:
        """
        Cleanup resources.

        Delegates connection cleanup to MCPConnectionManager and clears artifact cache.
        """
        await self._connection_manager.cleanup()
        self._cache.clear()
        logger.info("ArtifactManager cleanup complete")

    async def __aenter__(self) -> "ArtifactManager":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.cleanup()

    # --------------------------------------------------------------------- #
    # Client access (delegated to MCPConnectionManager)
    # --------------------------------------------------------------------- #
    @property
    def clients(self) -> Mapping[str, MCPClient]:
        """
        Return a read-only mapping of configured MCP clients.

        Delegates to MCPConnectionManager.

        Returns:
            Immutable mapping of server name to MCPClient
        """
        return self._connection_manager.clients

    def get_server_statuses(self) -> dict[str, ConnectionStatus]:
        """
        Get connection status for all servers.

        Delegates to MCPConnectionManager.

        Returns:
            Dictionary mapping server name to connection status
        """
        return self._connection_manager.get_server_statuses()

    # --------------------------------------------------------------------- #
    # Artifact access
    # --------------------------------------------------------------------- #
    async def get_resources(self) -> dict[str, list[str]]:
        """Get resources grouped by server."""
        resources = await self._artifact_repository.get_resources()
        logger.info(
            "Retrieved resources from %d server(s): %d resource(s) total",
            len(resources),
            sum(len(uris) for uris in resources.values()),
        )
        return resources

    async def get_prompts(self) -> list[Prompt]:
        """Get prompts from all connected servers."""
        prompts = await self._artifact_repository.get_prompts()
        logger.info("Retrieved %d prompt(s) from all servers", len(prompts))
        return prompts

    async def get_tools(self) -> list[Tool]:
        """Get tools from all connected servers."""
        tools = await self._artifact_repository.get_tools()
        logger.info("Retrieved %d tool(s) from all servers", len(tools))
        return tools

    async def get_resource_list(self) -> list[str]:
        """Return flattened list of all resource URIs."""
        resources = await self.get_resources()
        flattened: list[str] = []
        for uris in resources.values():
            flattened.extend(uris)
        logger.debug("Flattened %d resources into single list", len(flattened))
        return flattened

    async def get_command_names(self) -> list[str]:
        """Return flattened list of command (prompt) names."""
        command_names = await self._artifact_repository.get_command_names()
        logger.debug("Extracted %d command name(s)", len(command_names))
        return command_names

    async def find_prompt(self, prompt_name: str) -> tuple[Prompt, str] | None:
        """Locate a prompt across all servers."""
        result = await self._artifact_repository.find_prompt(prompt_name)
        if result:
            prompt, server = result
            logger.debug("Found prompt '%s' in server '%s'", prompt_name, server)
        else:
            logger.warning("Prompt '%s' not found in any MCP server", prompt_name)
        return result

    # --------------------------------------------------------------------- #
    # Artifact caching helpers
    # --------------------------------------------------------------------- #
    def get_cached_artifacts(self, server_name: str) -> ArtifactCollection | None:
        """Get cached artifacts for a server (returns deep copy for safety)."""
        cached = self._cache.get(server_name)
        return deepcopy(cached) if cached is not None else None

    def cache_artifacts(self, server_name: str, artifacts: ArtifactCollection) -> None:
        """Store artifacts for a server (stores deep copy to prevent mutations)."""
        self._cache.set(server_name, deepcopy(artifacts))

    def clear_artifacts_cache(self, server_name: str | None = None) -> None:
        """Clear cache for a single server or all servers."""
        if server_name is None:
            self._cache.clear()
        else:
            self._cache.delete(server_name)

    def have_artifacts_changed(
        self,
        server_name: str,
        new_artifacts: ArtifactCollection,
    ) -> bool:
        """Check if artifacts differ from cached values."""
        return self._cache.has_changed(server_name, new_artifacts)

    async def get_server_artifacts(
        self,
        server_name: str,
        retry_on_empty: bool = False,
        timeout: float | None = None,
    ) -> ArtifactCollection:
        """Fetch artifacts for a specific server and publish change events."""
        artifacts = await self._artifact_repository.get_server_artifacts(
            server_name,
            retry_on_empty=retry_on_empty,
            timeout=timeout,
        )

        changed = self.have_artifacts_changed(server_name, artifacts)
        self.cache_artifacts(server_name, artifacts)

        self._publish_artifacts_fetched(server_name, artifacts, changed)
        return artifacts

    async def get_all_servers_artifacts(
        self,
        timeout: float | None = None,
    ) -> dict[str, ArtifactCollection]:
        """Fetch artifacts for all servers."""
        return await self._artifact_repository.get_all_servers_artifacts(timeout=timeout)

    # --------------------------------------------------------------------- #
    # Event publishing
    # --------------------------------------------------------------------- #
    def _publish_artifacts_fetched(
        self,
        server_name: str,
        artifacts: ArtifactCollection,
        changed: bool,
    ) -> None:
        """
        Publish ArtifactsFetched event.

        Args:
            server_name: Name of the server
            artifacts: Fetched artifacts
            changed: Whether artifacts have changed
        """
        if not self.event_bus:
            return
        try:
            self.event_bus.publish(
                ArtifactsFetched(
                    server_name=server_name,
                    artifacts=artifacts,
                    changed=changed,
                )
            )
        except Exception as err:  # pragma: no cover - defensive logging
            logger.error(
                "Error publishing ArtifactsFetched for %s: %s",
                server_name,
                err,
            )
