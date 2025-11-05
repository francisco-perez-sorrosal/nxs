"""ArtifactManager - Manages MCP artifacts (resources, prompts, tools).

The ArtifactManager is responsible for:
- Loading and connecting to MCP servers from configuration
- Providing access to resources (for NexusApp)
- Providing access to prompts (for NexusApp)
- Providing access to tools (for CommandControlAgent/AgentLoop)
- Managing the lifecycle of MCP client connections
"""

import asyncio
import time
from contextlib import AsyncExitStack
from typing import Optional, Callable

from mcp.types import Prompt, Tool, Resource

from nxs.core.mcp_config import (
    MCPServersConfig,
    get_all_server_names,
    get_server_config,
    load_mcp_config,
)
from nxs.mcp_client.client import MCPAuthClient, ConnectionStatus
from nxs.logger import get_logger

logger = get_logger("artifact_manager")


class ArtifactManager:
    """Manages artifacts from MCP servers: resources, prompts, and tools."""

    def __init__(
        self,
        config: Optional[MCPServersConfig] = None,
        on_status_change: Optional[Callable[[str, ConnectionStatus], None]] = None,
    ):
        """
        Initialize the ArtifactManager.

        Args:
            config: MCP servers configuration. If None, loads from default location.
            on_status_change: Optional callback called when connection status changes.
                             Receives (server_name, status) as arguments.
        """
        self.config = config or load_mcp_config()
        self.mcp_clients: dict[str, MCPAuthClient] = {}
        self._exit_stack: Optional[AsyncExitStack] = None
        self.on_status_change = on_status_change
        self._server_statuses: dict[str, ConnectionStatus] = {}
        # Track last check time for each server
        self._server_last_check: dict[str, float] = {}
        # Cache artifacts for each server to avoid unnecessary fetches
        self._artifacts_cache: dict[str, dict[str, list[str]]] = {}

    async def initialize(self, use_auth: bool = False) -> None:
        """
        Initialize and connect to all MCP servers.

        This method loads all remote MCP servers from configuration and
        establishes connections to them.

        Args:
            use_auth: Whether to use OAuth authentication for remote servers
        """
        logger.info("Initializing ArtifactManager")
        logger.info(f"Loading {len(self.config.mcpServers)} MCP server(s) from configuration")

        self._exit_stack = AsyncExitStack()

        for server_name in get_all_server_names(self.config):
            server = get_server_config(server_name, self.config)
            if server and server.is_remote():
                url = server.remote_url()
                if url:
                    logger.info(f"Connecting to remote MCP server: {server_name} at {url}")
                    
                    # Create status change callback for this server
                    def make_status_callback(name: str):
                        def status_callback(status: ConnectionStatus):
                            self._server_statuses[name] = status
                            if self.on_status_change:
                                try:
                                    self.on_status_change(name, status)
                                except Exception as e:
                                    logger.error(f"Error in status change callback for {name}: {e}")
                        return status_callback
                    
                    mcp_client = MCPAuthClient(
                        url,
                        on_status_change=make_status_callback(server_name)
                    )
                    self.mcp_clients[server_name] = mcp_client
                    self._server_statuses[server_name] = ConnectionStatus.DISCONNECTED

                    try:
                        await mcp_client.connect(use_auth=use_auth)
                        logger.info(f"Successfully connected to {server_name}")
                    except Exception as e:
                        logger.error(f"Failed to connect to {server_name}: {e}")
                        self._server_statuses[server_name] = ConnectionStatus.ERROR
                        # Continue with other servers even if one fails
                else:
                    logger.warning(
                        f"Remote server URL is not set for {server_name}, skipping"
                    )
            else:
                logger.debug(f"Skipping non-remote server: {server_name}")

        logger.info(
            f"ArtifactManager initialized with {len(self.mcp_clients)} connected client(s)"
        )

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
        all_resource_ids: dict[str, list[str]] = {}

        for mcp_name, mcp_client in self.mcp_clients.items():
            try:
                logger.debug(f"Listing resources from {mcp_name}")
                resource_list: list[Resource] = await mcp_client.list_resources()
                # list_resources() returns a list of Resource objects
                if isinstance(resource_list, list):
                    all_resource_ids[mcp_name] = [str(r.uri) for r in resource_list]
                    logger.debug(
                        f"Found {len(resource_list)} resource(s) from {mcp_name}"
                    )
                else:
                    logger.warning(
                        f"Unexpected return type from list_resources(): {type(resource_list)}"
                    )
                    all_resource_ids[mcp_name] = []
            except Exception as e:
                logger.error(f"Failed to list resources from {mcp_name}: {e}")
                all_resource_ids[mcp_name] = []

        logger.info(
            f"Retrieved resources from {len(all_resource_ids)} server(s): "
            f"{sum(len(uris) for uris in all_resource_ids.values())} total resource(s)"
        )
        return all_resource_ids

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
        all_prompts: list[Prompt] = []

        for mcp_name, mcp_client in self.mcp_clients.items():
            try:
                logger.debug(f"Listing prompts from {mcp_name}")
                prompts = await mcp_client.list_prompts()
                all_prompts.extend(prompts)
                logger.debug(f"Found {len(prompts)} prompt(s) from {mcp_name}")
            except Exception as e:
                logger.error(f"Failed to list prompts from {mcp_name}: {e}")

        logger.info(f"Retrieved {len(all_prompts)} prompt(s) from all servers")
        return all_prompts

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
        all_tools: list[Tool] = []

        for mcp_name, mcp_client in self.mcp_clients.items():
            try:
                logger.debug(f"Listing tools from {mcp_name}")
                tools = await mcp_client.list_tools()
                # list_tools() returns a list of Tool objects directly
                if isinstance(tools, list):
                    all_tools.extend(tools)
                    logger.debug(f"Found {len(tools)} tool(s) from {mcp_name}")
                else:
                    logger.warning(
                        f"Unexpected return type from list_tools(): {type(tools)}"
                    )
            except Exception as e:
                logger.error(f"Failed to list tools from {mcp_name}: {e}")

        logger.info(f"Retrieved {len(all_tools)} tool(s) from all servers")
        return all_tools

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
        prompts = await self.get_prompts()
        command_names = [p.name for p in prompts]
        logger.debug(f"Extracted {len(command_names)} command names from {len(prompts)} prompt(s)")
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
        for mcp_name, mcp_client in self.mcp_clients.items():
            try:
                prompts = await mcp_client.list_prompts()
                for prompt in prompts:
                    if prompt.name == prompt_name:
                        logger.debug(f"Found prompt '{prompt_name}' in server '{mcp_name}'")
                        return (prompt, mcp_name)
            except Exception as e:
                logger.error(f"Failed to search prompts in {mcp_name}: {e}")
        
        logger.warning(f"Prompt '{prompt_name}' not found in any MCP server")
        return None

    @property
    def clients(self) -> dict[str, MCPAuthClient]:
        """
        Get the dictionary of MCP clients.

        Returns:
            Dictionary mapping server names to AuthClient instances.
            This is used by CommandControlAgent/AgentLoop to execute tools.
        """
        return self.mcp_clients

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
        return self._server_last_check.get(server_name, 0)

    def update_server_last_check(self, server_name: str, timestamp: float | None = None) -> None:
        """
        Update the last check time for a server.

        Args:
            server_name: Name of the server
            timestamp: Unix timestamp. If None, uses current time
        """
        if timestamp is None:
            timestamp = time.time()
        self._server_last_check[server_name] = timestamp

    def get_cached_artifacts(self, server_name: str) -> dict[str, list[str]] | None:
        """
        Get cached artifacts for a server.

        Args:
            server_name: Name of the server

        Returns:
            Cached artifacts dict or None if not cached
        """
        return self._artifacts_cache.get(server_name)

    def cache_artifacts(self, server_name: str, artifacts: dict[str, list[str]]) -> None:
        """
        Cache artifacts for a server.

        Args:
            server_name: Name of the server
            artifacts: Artifacts dict with keys "tools", "prompts", "resources"
        """
        self._artifacts_cache[server_name] = artifacts.copy()

    def clear_artifacts_cache(self, server_name: str | None = None) -> None:
        """
        Clear artifacts cache for a server or all servers.

        Args:
            server_name: Name of the server. If None, clears all cache
        """
        if server_name is None:
            self._artifacts_cache.clear()
        else:
            self._artifacts_cache.pop(server_name, None)

    def have_artifacts_changed(self, server_name: str, new_artifacts: dict[str, list[str]]) -> bool:
        """
        Check if artifacts have changed compared to cache.

        Args:
            server_name: Name of the server
            new_artifacts: New artifacts dict to compare

        Returns:
            True if artifacts have changed, False otherwise
        """
        cached = self._artifacts_cache.get(server_name)
        if cached is None:
            return True

        # Compare artifact counts
        new_total = (
            len(new_artifacts.get("tools", [])) +
            len(new_artifacts.get("prompts", [])) +
            len(new_artifacts.get("resources", []))
        )
        cached_total = (
            len(cached.get("tools", [])) +
            len(cached.get("prompts", [])) +
            len(cached.get("resources", []))
        )

        # Check if going from 0 to >0 or >0 to 0
        if (cached_total == 0 and new_total > 0) or (cached_total > 0 and new_total == 0):
            return True

        # Compare actual content
        return new_artifacts != cached

    async def _fetch_with_retry(
        self,
        fetch_func: Callable,
        server_name: str,
        artifact_type: str,
        retry_on_empty: bool = False,
        max_retries: int = 2,
        retry_delay: float = 0.5
    ) -> list:
        """
        Fetch artifacts with retry logic for reconnection scenarios.

        Args:
            fetch_func: Async function to fetch artifacts (list_tools, list_prompts, list_resources)
            server_name: Name of the server (for logging)
            artifact_type: Type of artifact being fetched (for logging)
            retry_on_empty: If True, retry if result is empty
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds

        Returns:
            List of artifacts (tools, prompts, or resources)
        """
        for attempt in range(max_retries + 1):
            try:
                result = await fetch_func()
                if result or not retry_on_empty or attempt == max_retries:
                    return result or []

                # If result is empty and we should retry, wait and try again
                if attempt < max_retries:
                    logger.debug(
                        f"Empty {artifact_type} for {server_name} (attempt {attempt + 1}), "
                        f"retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
            except Exception as e:
                if attempt < max_retries:
                    logger.debug(
                        f"Error fetching {artifact_type} for {server_name} (attempt {attempt + 1}): {e}, "
                        f"retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.warning(f"Failed to fetch {artifact_type} for {server_name} after {max_retries + 1} attempts: {e}")
                    raise

        return []

    async def get_server_artifacts(
        self,
        server_name: str,
        retry_on_empty: bool = False
    ) -> dict[str, list[str]]:
        """
        Get artifacts (tools, prompts, resources) for a specific server.

        Args:
            server_name: Name of the server
            retry_on_empty: If True, retry fetching if results are empty

        Returns:
            Dictionary with keys "tools", "prompts", "resources", each containing a list of names/URIs
        """
        artifacts: dict[str, list[str]] = {
            "tools": [],
            "prompts": [],
            "resources": []
        }

        client = self.mcp_clients.get(server_name)
        if not client:
            logger.warning(f"Server {server_name} not found in clients")
            return artifacts

        # Update last check time
        self.update_server_last_check(server_name)

        # Only fetch if connected
        if not client.is_connected:
            logger.debug(f"Server {server_name} is not connected, skipping artifact fetch")
            return artifacts

        try:
            # Fetch tools with retry
            tools = await self._fetch_with_retry(
                client.list_tools,
                server_name,
                "tools",
                retry_on_empty=retry_on_empty
            )
            if tools:
                artifacts["tools"] = [tool.name for tool in tools]

            # Fetch prompts with retry
            prompts = await self._fetch_with_retry(
                client.list_prompts,
                server_name,
                "prompts",
                retry_on_empty=retry_on_empty
            )
            if prompts:
                artifacts["prompts"] = [prompt.name for prompt in prompts]

            # Fetch resources with retry
            resources = await self._fetch_with_retry(
                client.list_resources,
                server_name,
                "resources",
                retry_on_empty=retry_on_empty
            )
            if resources:
                artifacts["resources"] = [str(resource.uri) for resource in resources]

            logger.debug(
                f"Fetched artifacts for {server_name}: "
                f"{len(artifacts['tools'])} tools, "
                f"{len(artifacts['prompts'])} prompts, "
                f"{len(artifacts['resources'])} resources"
            )

        except Exception as e:
            logger.error(f"Failed to fetch artifacts for {server_name}: {e}")

        return artifacts

    async def get_all_servers_artifacts(self) -> dict[str, dict[str, list[str]]]:
        """
        Get artifacts for all servers.

        Returns:
            Dictionary mapping server names to their artifacts dict
        """
        all_artifacts: dict[str, dict[str, list[str]]] = {}

        for server_name in self.mcp_clients.keys():
            artifacts = await self.get_server_artifacts(server_name)
            all_artifacts[server_name] = artifacts

        return all_artifacts

    async def cleanup(self) -> None:
        """
        Clean up all MCP client connections.

        This should be called when the ArtifactManager is no longer needed,
        typically during application shutdown.
        """
        logger.info("Cleaning up ArtifactManager connections")

        for mcp_name, mcp_client in self.mcp_clients.items():
            try:
                logger.debug(f"Disconnecting from {mcp_name}")
                await mcp_client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting from {mcp_name}: {e}")

        self.mcp_clients.clear()

        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.error(f"Error closing exit stack: {e}")

        logger.info("ArtifactManager cleanup complete")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()

