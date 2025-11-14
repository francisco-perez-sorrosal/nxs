"""Application service for unified artifact management.

This service aggregates artifacts from all sources (MCP servers, local tools)
and provides them in a consistent format using Pydantic models.
"""

from typing import TYPE_CHECKING

from nxs.domain.artifacts import (
    Tool,
    Resource,
    Prompt,
    ArtifactCollection,
    ArtifactSource,
)
from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.application.artifact_manager import ArtifactManager
    from nxs.application.tool_registry import ToolRegistry
    from nxs.application.tool_state import ToolStateManager

logger = get_logger(__name__)


class ArtifactService:
    """Service for managing and aggregating artifacts from all sources.

    This service provides a unified interface for accessing tools, resources,
    and prompts from both MCP servers and local sources.
    """

    def __init__(
        self,
        artifact_manager: "ArtifactManager",
        tool_registry: "ToolRegistry | None" = None,
        tool_state_manager: "ToolStateManager | None" = None,
    ):
        """Initialize the artifact service.

        Args:
            artifact_manager: Manager for MCP artifacts
            tool_registry: Registry for all tools (MCP + local)
            tool_state_manager: Manager for tool enabled/disabled state
        """
        self.artifact_manager = artifact_manager
        self.tool_registry = tool_registry
        self.tool_state_manager = tool_state_manager

    async def get_all_artifacts(self) -> dict[str, ArtifactCollection]:
        """Get all artifacts from all sources.

        Returns:
            Dictionary mapping source IDs to ArtifactCollections
        """
        collections = {}

        # Get MCP server artifacts
        mcp_collections = await self._get_mcp_artifacts()
        collections.update(mcp_collections)

        # Get local tools
        local_collection = await self._get_local_tools()
        if local_collection and local_collection.tools:
            collections["Local Tools"] = local_collection

        return collections

    async def _get_mcp_artifacts(self) -> dict[str, ArtifactCollection]:
        """Get artifacts from all MCP servers.

        Returns:
            Dictionary mapping server names to ArtifactCollections
        """
        collections = {}

        try:
            # Get raw artifact data from MCP servers
            servers_data = await self.artifact_manager.get_all_servers_artifacts()

            for server_name, artifacts in servers_data.items():
                # Convert to Pydantic models
                tools = []
                for tool_data in artifacts.get("tools", []):
                    if isinstance(tool_data, dict) and "name" in tool_data:
                        tool = Tool(
                            name=tool_data["name"],
                            description=tool_data.get("description"),
                            source=ArtifactSource.MCP,
                            source_id=server_name,
                            enabled=self._is_tool_enabled(tool_data["name"]),
                            input_schema=tool_data.get("inputSchema"),
                        )
                        tools.append(tool)

                resources = []
                for resource_data in artifacts.get("resources", []):
                    # Handle both dict and string formats
                    if isinstance(resource_data, dict):
                        # Handle case where "name" contains the URI (from repository format)
                        # vs case where "uri" and "name" are separate fields
                        uri = resource_data.get("uri") or resource_data.get("name", "")
                        name = resource_data.get("name", "")
                        # If name wasn't provided separately, extract from URI
                        if not name or name == uri:
                            name = uri.split("/")[-1] if uri and "/" in uri else uri
                        description = resource_data.get("description")
                    elif isinstance(resource_data, str):
                        uri = resource_data
                        name = uri.split("/")[-1] if uri and "/" in uri else uri
                        description = None
                    else:
                        continue

                    if uri:
                        resource = Resource(
                            uri=uri,
                            name=name,
                            description=description,
                            source_id=server_name,
                        )
                        resources.append(resource)
                        logger.debug(
                            f"Added resource for {server_name}: uri={uri!r}, name={name!r}"
                        )

                prompts = []
                for prompt_data in artifacts.get("prompts", []):
                    if isinstance(prompt_data, dict) and "name" in prompt_data:
                        prompt = Prompt(
                            name=prompt_data["name"],
                            description=prompt_data.get("description"),
                            source_id=server_name,
                            arguments=prompt_data.get("arguments"),
                        )
                        prompts.append(prompt)

                # Create collection
                collection = ArtifactCollection(
                    source_id=server_name,
                    source=ArtifactSource.MCP,
                    tools=tools,
                    resources=resources,
                    prompts=prompts,
                )
                collections[server_name] = collection

        except Exception as e:
            logger.error(f"Error getting MCP artifacts: {e}", exc_info=True)

        return collections

    async def _get_local_tools(self) -> ArtifactCollection | None:
        """Get local tools from the tool registry.

        Returns:
            ArtifactCollection with local tools or None if not available
        """
        if not self.tool_registry:
            return None

        try:
            tools = []

            # Get all tool definitions from non-MCP providers
            for provider_name in self.tool_registry.get_provider_names():
                if provider_name == "mcp":
                    # Skip MCP tools, they're handled separately
                    continue

                provider = self.tool_registry._providers.get(provider_name)
                if provider:
                    provider_tools = await provider.get_tool_definitions()

                    for tool_def in provider_tools:
                        tool = Tool(
                            name=tool_def["name"],
                            description=tool_def.get("description"),
                            source=ArtifactSource.LOCAL,
                            source_id="local",
                            enabled=self._is_tool_enabled(tool_def["name"]),
                            input_schema=tool_def.get("input_schema"),
                        )
                        tools.append(tool)

            if not tools:
                return None

            return ArtifactCollection(
                source_id="Local Tools",
                source=ArtifactSource.LOCAL,
                tools=tools,
                resources=[],
                prompts=[],
            )

        except Exception as e:
            logger.error(f"Error getting local tools: {e}", exc_info=True)
            return None

    def _is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a tool is enabled.

        Args:
            tool_name: Name of the tool

        Returns:
            True if enabled, False otherwise
        """
        if not self.tool_state_manager:
            return True
        return self.tool_state_manager.is_enabled(tool_name)

    async def get_display_data(self) -> dict[str, dict[str, list[dict[str, str | None | bool]]]]:
        """Get all artifacts formatted for display in the UI.

        Returns:
            Dictionary mapping source IDs to display dictionaries
        """
        collections = await self.get_all_artifacts()
        return {
            source_id: collection.to_display_dict()
            for source_id, collection in collections.items()
        }
