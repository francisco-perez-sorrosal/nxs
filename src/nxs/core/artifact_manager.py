"""ArtifactManager - Manages MCP artifacts (resources, prompts, tools).

The ArtifactManager is responsible for:
- Loading and connecting to MCP servers from configuration
- Providing access to resources (for NexusApp)
- Providing access to prompts (for NexusApp)
- Providing access to tools (for CommandControlAgent/AgentLoop)
- Managing the lifecycle of MCP client connections
"""

from contextlib import AsyncExitStack
from typing import Optional

from mcp.types import Prompt, Tool, Resource

from nxs.core.mcp_config import (
    MCPServersConfig,
    get_all_server_names,
    get_server_config,
    load_mcp_config,
)
from nxs.mcp_client.client import MCPAuthClient
from nxs.logger import get_logger

logger = get_logger("artifact_manager")


class ArtifactManager:
    """Manages artifacts from MCP servers: resources, prompts, and tools."""

    def __init__(self, config: Optional[MCPServersConfig] = None):
        """
        Initialize the ArtifactManager.

        Args:
            config: MCP servers configuration. If None, loads from default location.
        """
        self.config = config or load_mcp_config()
        self.mcp_clients: dict[str, MCPAuthClient] = {}
        self._exit_stack: Optional[AsyncExitStack] = None

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
                    mcp_client = MCPAuthClient(url)
                    self.mcp_clients[server_name] = mcp_client

                    try:
                        await mcp_client.connect(use_auth=use_auth)
                        logger.info(f"Successfully connected to {server_name}")
                    except Exception as e:
                        logger.error(f"Failed to connect to {server_name}: {e}")
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

    @property
    def clients(self) -> dict[str, MCPAuthClient]:
        """
        Get the dictionary of MCP clients.

        Returns:
            Dictionary mapping server names to AuthClient instances.
            This is used by CommandControlAgent/AgentLoop to execute tools.
        """
        return self.mcp_clients

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

