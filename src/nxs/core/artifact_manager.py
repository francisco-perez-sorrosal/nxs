"""ArtifactManager - facade coordinating MCP clients, artifacts, and caching."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Dict, Optional
from types import MappingProxyType

from mcp.types import Prompt, Tool

from nxs.core.artifacts import (
    ArtifactCache,
    ArtifactChangeDetector,
    ArtifactCollection,
    ArtifactRepository,
)
from nxs.core.cache import Cache
from nxs.core.events import (
    ArtifactsFetched,
    ConnectionStatusChanged,
    EventBus,
    ReconnectProgress,
)
from nxs.core.mcp_config import MCPServersConfig, load_mcp_config
from nxs.core.protocols import MCPClient
from nxs.logger import get_logger
from nxs.mcp_client.client import ConnectionStatus
from nxs.mcp_client.factory import ClientFactory

logger = get_logger("artifact_manager")


class ArtifactManager:
    """High-level facade for MCP artifact access and connection lifecycle."""

    def __init__(
        self,
        config: Optional[MCPServersConfig] = None,
        event_bus: Optional[EventBus] = None,
        artifacts_cache: Optional[Cache[str, ArtifactCollection]] = None,
        *,
        artifact_repository: Optional[ArtifactRepository] = None,
        artifact_cache_service: Optional[ArtifactCache] = None,
        change_detector: Optional[ArtifactChangeDetector] = None,
        client_factory: Optional[ClientFactory] = None,
    ):
        self._config = config or load_mcp_config()
        self.event_bus = event_bus or EventBus()

        self._clients: Dict[str, MCPClient] = {}
        self._client_factory = client_factory or ClientFactory()

        clients_provider = lambda: self._clients
        self._artifact_repository = artifact_repository or ArtifactRepository(
            clients_provider=clients_provider
        )
        self._artifact_cache = artifact_cache_service or ArtifactCache(
            cache=artifacts_cache
        )
        self._change_detector = change_detector or ArtifactChangeDetector(
            self._artifact_cache
        )
        self._previous_statuses: Dict[str, ConnectionStatus] = {}

    # --------------------------------------------------------------------- #
    # Lifecycle
    # --------------------------------------------------------------------- #
    async def initialize(self, use_auth: bool = False) -> None:
        """Instantiate and connect MCP clients for all configured servers."""
        logger.info("Initializing ArtifactManager")

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
        """Disconnect all clients and clear caches."""
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
        self._artifact_cache.clear()
        logger.info("ArtifactManager cleanup complete")

    async def __aenter__(self) -> "ArtifactManager":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup()

    async def _disconnect_client(self, server_name: str, disconnect_callable) -> None:
        try:
            await disconnect_callable()
        except Exception as err:  # pragma: no cover - defensive logging
            logger.error("Error disconnecting from %s: %s", server_name, err)

    # --------------------------------------------------------------------- #
    # Client access
    # --------------------------------------------------------------------- #
    @property
    def clients(self) -> Mapping[str, MCPClient]:
        """Return a read-only mapping of configured MCP clients."""
        return MappingProxyType(self._clients)

    def get_server_statuses(self) -> dict[str, ConnectionStatus]:
        """Derive server connection statuses from the underlying clients."""
        statuses: dict[str, ConnectionStatus] = {}
        for server_name, client in self._clients.items():
            status = getattr(client, "connection_status", None)
            if isinstance(status, ConnectionStatus):
                statuses[server_name] = status
        return statuses

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
        """Get cached artifacts for a server."""
        return self._artifact_cache.get(server_name)

    def cache_artifacts(self, server_name: str, artifacts: ArtifactCollection) -> None:
        """Store artifacts for a server."""
        self._artifact_cache.set(server_name, artifacts)

    def clear_artifacts_cache(self, server_name: str | None = None) -> None:
        """Clear cache for a single server or all servers."""
        self._artifact_cache.clear(server_name)

    def have_artifacts_changed(
        self,
        server_name: str,
        new_artifacts: ArtifactCollection,
    ) -> bool:
        """Check if artifacts differ from cached values."""
        return self._change_detector.has_changed(server_name, new_artifacts)

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

    def _handle_status_change(
        self,
        server_name: str,
        status: ConnectionStatus,
    ) -> None:
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

