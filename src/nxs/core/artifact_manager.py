"""ArtifactManager - Facade for MCP artifact access and connection lifecycle."""

from __future__ import annotations

from typing import Optional

from mcp.types import Prompt, Tool

from nxs.core.artifacts import (
    ArtifactCache,
    ArtifactChangeDetector,
    ArtifactCollection,
    ArtifactRepository,
)
from nxs.core.cache import Cache
from nxs.core.events import ArtifactsFetched, EventBus
from nxs.core.mcp_config import MCPServersConfig, load_mcp_config
from nxs.core.protocols import MCPClient
from nxs.logger import get_logger
from nxs.mcp_client.client import ConnectionStatus, MCPAuthClient

logger = get_logger("artifact_manager")


class ArtifactManager:
    """Facade that coordinates connections, artifact fetching, and caching."""

    def __init__(
        self,
        config: Optional[MCPServersConfig] = None,
        event_bus: Optional[EventBus] = None,
        artifacts_cache: Optional[Cache[str, ArtifactCollection]] = None,
        *,
        artifact_repository: Optional[ArtifactRepository] = None,
        artifact_cache_service: Optional[ArtifactCache] = None,
        change_detector: Optional[ArtifactChangeDetector] = None,
    ):
        """
        Initialize the ArtifactManager.

        Args:
            config: MCP servers configuration. If None, loads from default location.
            event_bus: Optional EventBus instance for publishing events. If provided,
                      events will be published for connection status changes, reconnection
                      progress, and artifact fetches. If None, events are not published.
            artifacts_cache: Optional Cache instance for caching artifacts. If None, a
                            MemoryCache will be created. This allows injecting different
                            cache implementations (e.g., TTLCache for expiration).
        """
        self.config = config or load_mcp_config()
        self.event_bus = event_bus
        self.mcp_clients: dict[str, MCPClient] = {}
        self._server_statuses: dict[str, ConnectionStatus] = {}
        self._server_last_check: dict[str, float] = {}

        clients_provider = lambda: self.mcp_clients
        self._artifact_repository = artifact_repository or ArtifactRepository(
            clients_provider=clients_provider
        )
        self._artifact_cache = artifact_cache_service or ArtifactCache(
            cache=artifacts_cache
        )
        self._change_detector = change_detector or ArtifactChangeDetector(
            self._artifact_cache
        )

    async def initialize(self, use_auth: bool = False) -> None:
        """Initialize and connect to all configured MCP servers."""
        logger.info("Initializing ArtifactManager")
        for server_name, client in self._create_clients():
            try:
                await client.connect(use_auth=use_auth)
                logger.info("Successfully connected to %s", server_name)
            except Exception as err:
                logger.error("Failed to connect to %s: %s", server_name, err)
                self._handle_status_change(
                    status=ConnectionStatus.ERROR,
                    server_name=server_name,
                )

        logger.info(
            "ArtifactManager initialized with %d client(s)",
            len(self.mcp_clients),
        )

    def _create_clients(self) -> list[tuple[str, MCPAuthClient]]:
        """Instantiate MCPAuthClient objects for all configured servers."""
        clients: list[tuple[str, MCPAuthClient]] = []

        for server_name, server in self._iter_remote_servers():
            url = server.remote_url()
            if not url:
                logger.warning("Remote server URL not set for %s, skipping", server_name)
                continue

            logger.info("Connecting to remote MCP server: %s", server_name)

            client = MCPAuthClient(
                url,
                on_status_change=lambda status, name=server_name: self._handle_status_change(
                    status=status,
                    server_name=name,
                ),
                on_reconnect_progress=lambda attempts, max_attempts, delay, name=server_name: self._handle_reconnect_progress(
                    attempts=attempts,
                    max_attempts=max_attempts,
                    next_retry_delay=delay,
                    server_name=name,
                ),
            )

            self.mcp_clients[server_name] = client
            self._server_statuses.setdefault(server_name, ConnectionStatus.DISCONNECTED)
            self._server_last_check.setdefault(server_name, 0.0)
            clients.append((server_name, client))

        return clients

    async def get_resources(self) -> dict[str, list[str]]:
        """
        Get all resources from all connected MCP servers.

        Returns:
            Dictionary mapping server names to lists of resource URIs.
            Format: {server_name: [resource_uri1, resource_uri2, ...]}

        Example:
            {
                "synx_mcp_fps": ["mcp://synx_mcp_fps/document1.md", ...],
                "fps_cv_mcp": ["mcp://fps_cv_mcp/image1.jpg", ...]
            }
        """
        resources = await self._artifact_repository.get_resources()
        logger.info(
            "Retrieved resources from %d server(s): %d total resource(s)",
            len(resources),
            sum(len(uris) for uris in resources.values()),
        )
        return resources

    async def get_prompts(self) -> list[Prompt]:
        """
        Get all prompts from all connected MCP servers.

        Returns:
            List of Prompt objects from all servers.

        Example:
            [
                Prompt(name="analyze_document", description="...", ...),
                Prompt(name="summarize_document", description="...", ...),
                ...
            ]
        """
        prompts = await self._artifact_repository.get_prompts()
        logger.info("Retrieved %d prompt(s) from all servers", len(prompts))
        return prompts

    async def get_tools(self) -> list[Tool]:
        """
        Get all tools from all connected MCP servers.

        Returns:
            List of Tool objects from all servers. These are used by
            CommandControlAgent/AgentLoop for Claude tool-use requests.

        Example:
            [
                Tool(name="read_file", description="...", inputSchema={...}),
                Tool(name="write_file", description="...", inputSchema={...}),
                ...
            ]
        """
        tools = await self._artifact_repository.get_tools()
        logger.info("Retrieved %d tool(s) from all servers", len(tools))
        return tools

    async def get_resource_list(self) -> list[str]:
        """
        Get all resources from all connected MCP servers as a flattened list.

        Returns:
            Flat list of resource URIs from all servers. This is the format
            expected by NexusApp for auto-completion.

        Example:
            [
                "mcp://synx_mcp_fps/document1.md",
                "mcp://synx_mcp_fps/document2.md",
                "mcp://fps_cv_mcp/image1.jpg",
                ...
            ]
        """
        resources_dict = await self.get_resources()
        # Flatten the dict into a single list
        resources = []
        for server_name, resource_uris in resources_dict.items():
            resources.extend(resource_uris)
        logger.debug(f"Flattened {len(resources)} resources from {len(resources_dict)} server(s)")
        return resources

    async def get_command_names(self) -> list[str]:
        """
        Get all command names from all connected MCP servers.

        Returns:
            Flat list of command names from all prompts. This is the format
            expected by NexusApp for auto-completion.

        Example:
            [
                "analyze_document",
                "summarize_document",
                "format_document",
                ...
            ]
        """
        command_names = await self._artifact_repository.get_command_names()
        logger.debug("Extracted %d command names", len(command_names))
        return command_names

    async def find_prompt(self, prompt_name: str) -> tuple[Prompt, str] | None:
        """
        Find a prompt by name across all MCP servers.

        Args:
            prompt_name: Name of the prompt to find

        Returns:
            Tuple of (Prompt, server_name) if found, None otherwise.
            This allows calling get_prompt on the correct server.
        """
        result = await self._artifact_repository.find_prompt(prompt_name)
        if result:
            prompt, server = result
            logger.debug("Found prompt '%s' in server '%s'", prompt_name, server)
        else:
            logger.warning("Prompt '%s' not found in any MCP server", prompt_name)
        return result

    @property
    def clients(self) -> dict[str, MCPClient]:
        """
        Get the dictionary of MCP clients.

        Returns:
            Dictionary mapping server names to MCP client instances.
            This is used by CommandControlAgent/AgentLoop to execute tools.
        """
        return dict(self.mcp_clients)

    def get_server_statuses(self) -> dict[str, ConnectionStatus]:
        """
        Get the connection status for all servers.

        Returns:
            Dictionary mapping server names to their connection status.
        """
        return self._server_statuses.copy()

    def get_server_last_check(self, server_name: str) -> float:
        """
        Get the last check time for a server.

        Args:
            server_name: Name of the server

        Returns:
            Unix timestamp of last check, or 0 if never checked
        """
        return self._server_last_check.get(server_name, 0.0)

    def update_server_last_check(self, server_name: str, timestamp: float | None = None) -> None:
        """
        Update the last check time for a server.

        Args:
            server_name: Name of the server
            timestamp: Unix timestamp. If None, uses current time
        """
        if timestamp is None:
            import time

            timestamp = time.time()
        self._server_last_check[server_name] = timestamp

    def get_cached_artifacts(self, server_name: str) -> ArtifactCollection | None:
        """
        Get cached artifacts for a server.

        Args:
            server_name: Name of the server

        Returns:
            Cached artifacts dict or None if not cached. Returns a copy to prevent
            external modification of cached data.
        """
        return self._artifact_cache.get(server_name)

    def cache_artifacts(self, server_name: str, artifacts: ArtifactCollection) -> None:
        """
        Cache artifacts for a server.

        Args:
            server_name: Name of the server
            artifacts: Artifacts dict with keys "tools", "prompts", "resources"
        """
        self._artifact_cache.set(server_name, artifacts)

    def clear_artifacts_cache(self, server_name: str | None = None) -> None:
        """
        Clear artifacts cache for a server or all servers.

        Args:
            server_name: Name of the server. If None, clears all cache
        """
        self._artifact_cache.clear(server_name)

    def have_artifacts_changed(
        self,
        server_name: str,
        new_artifacts: ArtifactCollection,
    ) -> bool:
        """
        Check if artifacts have changed compared to cache.

        This method uses the cache's has_changed method, which compares the
        new artifacts against the cached value.

        Args:
            server_name: Name of the server
            new_artifacts: New artifacts dict to compare

        Returns:
            True if artifacts have changed, False otherwise
        """
        return self._change_detector.has_changed(server_name, new_artifacts)

    async def get_server_artifacts(
        self,
        server_name: str,
        retry_on_empty: bool = False,
        timeout: float | None = None,
    ) -> ArtifactCollection:
        """
        Get artifacts (tools, prompts, resources) for a specific server.

        Args:
            server_name: Name of the server
            retry_on_empty: If True, retry fetching if results are empty
            timeout: Optional timeout in seconds for the fetch operation

        Returns:
            Dictionary with keys "tools", "prompts", "resources", each containing a list of dicts
            with "name" and "description" keys
        """
        artifacts = await self._artifact_repository.get_server_artifacts(
            server_name,
            retry_on_empty=retry_on_empty,
            timeout=timeout,
        )

        self.update_server_last_check(server_name)

        changed = self.have_artifacts_changed(server_name, artifacts)
        self.cache_artifacts(server_name, artifacts)

        if self.event_bus:
            try:
                self.event_bus.publish(
                    ArtifactsFetched(
                        server_name=server_name,
                        artifacts=artifacts,
                        changed=changed,
                    )
                )
            except Exception as err:
                logger.error(
                    "Error publishing ArtifactsFetched event for %s: %s",
                    server_name,
                    err,
                )

        return artifacts

    async def get_all_servers_artifacts(
        self,
        timeout: float | None = None,
    ) -> dict[str, ArtifactCollection]:
        """
        Get artifacts for all servers.

        Args:
            timeout: Optional timeout in seconds for the entire operation

        Returns:
            Dictionary mapping server names to their artifacts dict
        """
        return await self._artifact_repository.get_all_servers_artifacts(timeout=timeout)

    async def cleanup(self) -> None:
        """
        Clean up all MCP client connections.

        This should be called when the ArtifactManager is no longer needed,
        typically during application shutdown.
        """
        logger.info("Cleaning up ArtifactManager connections")

        for server_name, client in list(self.mcp_clients.items()):
            try:
                if hasattr(client, "disconnect"):
                    await client.disconnect()
            except Exception as err:
                logger.error("Error disconnecting from %s: %s", server_name, err)

        self.mcp_clients.clear()
        self._server_statuses.clear()
        self._server_last_check.clear()
        self._artifact_cache.clear()
        logger.info("ArtifactManager cleanup complete")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _iter_remote_servers(self):
        """Yield configured remote servers."""
        from nxs.core.mcp_config import get_all_server_names, get_server_config

        for server_name in get_all_server_names(self.config):
            server = get_server_config(server_name, self.config)
            if server and server.is_remote():
                yield server_name, server

    def _handle_status_change(self, status: ConnectionStatus, server_name: str) -> None:
        """Handle connection status change for a specific server."""
        previous_status = self._server_statuses.get(server_name)
        self._server_statuses[server_name] = status

        if self.event_bus:
            try:
                from nxs.core.events import ConnectionStatusChanged

                self.event_bus.publish(
                    ConnectionStatusChanged(
                        server_name=server_name,
                        status=status,
                        previous_status=previous_status,
                    )
                )
            except Exception as err:
                logger.error(
                    "Error publishing ConnectionStatusChanged for %s: %s",
                    server_name,
                    err,
                )

    def _handle_reconnect_progress(
        self,
        attempts: int,
        max_attempts: int,
        next_retry_delay: float,
        server_name: str,
    ) -> None:
        """Handle reconnection progress events for a specific server."""
        if self.event_bus:
            try:
                from nxs.core.events import ReconnectProgress

                self.event_bus.publish(
                    ReconnectProgress(
                        server_name=server_name,
                        attempts=attempts,
                        max_attempts=max_attempts,
                        next_retry_delay=next_retry_delay,
                    )
                )
            except Exception as err:
                logger.error(
                    "Error publishing ReconnectProgress for %s: %s",
                    server_name,
                    err,
                )

