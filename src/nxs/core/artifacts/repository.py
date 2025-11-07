"""Repository for fetching artifacts from MCP clients."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Mapping

from mcp.types import Prompt, Resource, Tool

from nxs.core.protocols import MCPClient
from nxs.logger import get_logger

from .cache import ArtifactCollection


logger = get_logger("artifact_repository")


class ArtifactRepository:
    """Fetch artifacts (resources, prompts, tools) from MCP clients."""

    def __init__(
        self,
        clients_provider: Callable[[], Mapping[str, MCPClient]],
    ) -> None:
        self._clients_provider = clients_provider

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def _connected_clients(self) -> Mapping[str, MCPClient]:
        return {
            name: client
            for name, client in self._clients_provider().items()
            if client.is_connected
        }

    # ------------------------------------------------------------------
    # Artifact fetch methods
    # ------------------------------------------------------------------
    async def get_resources(self) -> dict[str, list[str]]:
        """Return mapping of server name to resource URIs."""
        all_resource_ids: dict[str, list[str]] = {}

        for server_name, client in self._connected_clients().items():
            try:
                logger.debug("Listing resources from %s", server_name)
                resource_list: list[Resource] = await client.list_resources()
                all_resource_ids[server_name] = [str(resource.uri) for resource in resource_list]
            except Exception as err:
                logger.error("Failed to list resources from %s: %s", server_name, err)
                all_resource_ids[server_name] = []

        return all_resource_ids

    async def get_prompts(self) -> list[Prompt]:
        """Return prompts from all connected servers."""
        prompts: list[Prompt] = []

        for server_name, client in self._connected_clients().items():
            try:
                logger.debug("Listing prompts from %s", server_name)
                prompts.extend(await client.list_prompts())
            except Exception as err:
                logger.error("Failed to list prompts from %s: %s", server_name, err)

        return prompts

    async def get_tools(self) -> list[Tool]:
        """Return tools from all connected servers."""
        tools: list[Tool] = []

        for server_name, client in self._connected_clients().items():
            try:
                logger.debug("Listing tools from %s", server_name)
                result = await client.list_tools()
                if isinstance(result, list):
                    tools.extend(result)
                else:
                    logger.warning(
                        "Unexpected return type from list_tools() on %s: %s",
                        server_name,
                        type(result),
                    )
            except Exception as err:
                logger.error("Failed to list tools from %s: %s", server_name, err)

        return tools

    async def get_resource_list(self) -> list[str]:
        """Return flattened list of resource URIs."""
        resources = await self.get_resources()
        flattened: list[str] = []
        for uris in resources.values():
            flattened.extend(uris)
        return flattened

    async def get_command_names(self) -> list[str]:
        """Return list of prompt command names."""
        prompts = await self.get_prompts()
        return [prompt.name for prompt in prompts]

    async def find_prompt(self, prompt_name: str) -> tuple[Prompt, str] | None:
        """Find a prompt by name across all servers."""
        for server_name, client in self._connected_clients().items():
            try:
                prompts = await client.list_prompts()
                for prompt in prompts:
                    if prompt.name == prompt_name:
                        return prompt, server_name
            except Exception as err:
                logger.error(
                    "Failed to search prompts in %s: %s",
                    server_name,
                    err,
                )
        return None

    async def get_server_artifacts(
        self,
        server_name: str,
        retry_on_empty: bool = False,
        timeout: float | None = None,
    ) -> ArtifactCollection:
        """
        Fetch all artifact categories for a server.

        Args:
            server_name: Name of the server
            retry_on_empty: If True, retry if result is empty
            timeout: Optional timeout in seconds for the fetch operation

        Returns:
            Dictionary with keys "tools", "prompts", "resources"
        """
        artifacts: ArtifactCollection = {
            "tools": [],
            "prompts": [],
            "resources": [],
        }

        client = self._clients_provider().get(server_name)
        if not client:
            logger.warning("Server %s not found when fetching artifacts", server_name)
            return artifacts

        if not client.is_connected:
            logger.debug("Server %s is not connected, skipping artifact fetch", server_name)
            return artifacts

        # Wrap fetch operations with timeout if specified
        async def _fetch_all():
            # Tools
            tools = await self._fetch_with_retry(
                client.list_tools,
                server_name,
                "tools",
                retry_on_empty=retry_on_empty,
            )
            artifacts["tools"] = [
                {"name": tool.name, "description": tool.description}
                for tool in tools
            ]

            # Prompts
            prompts = await self._fetch_with_retry(
                client.list_prompts,
                server_name,
                "prompts",
                retry_on_empty=retry_on_empty,
            )
            artifacts["prompts"] = [
                {"name": prompt.name, "description": prompt.description}
                for prompt in prompts
            ]

            # Resources
            resources = await self._fetch_with_retry(
                client.list_resources,
                server_name,
                "resources",
                retry_on_empty=retry_on_empty,
            )
            artifacts["resources"] = [
                {
                    "name": str(resource.uri),
                    "description": (
                        resource.description
                        if hasattr(resource, "description") and resource.description
                        else resource.name
                        if hasattr(resource, "name") and resource.name
                        else None
                    ),
                }
                for resource in resources
            ]

        try:
            if timeout is not None:
                await asyncio.wait_for(_fetch_all(), timeout=timeout)
            else:
                await _fetch_all()
        except asyncio.TimeoutError:
            logger.warning("Timeout fetching artifacts for %s", server_name)
            return artifacts  # Return empty artifacts on timeout
        except Exception as err:
            logger.error("Error fetching artifacts for %s: %s", server_name, err)
            return artifacts  # Return empty artifacts on error

        logger.debug(
            "Fetched artifacts for %s: %d tools, %d prompts, %d resources",
            server_name,
            len(artifacts["tools"]),
            len(artifacts["prompts"]),
            len(artifacts["resources"]),
        )

        return artifacts

    async def get_all_servers_artifacts(
        self,
        timeout: float | None = None,
    ) -> dict[str, ArtifactCollection]:
        """
        Fetch artifacts for all servers.

        Args:
            timeout: Optional timeout in seconds for the entire operation

        Returns:
            Dictionary mapping server names to their artifacts
        """
        async def _fetch_all_servers():
            results: dict[str, ArtifactCollection] = {}
            for server_name in self._clients_provider().keys():
                results[server_name] = await self.get_server_artifacts(server_name)
            return results

        try:
            if timeout is not None:
                return await asyncio.wait_for(_fetch_all_servers(), timeout=timeout)
            else:
                return await _fetch_all_servers()
        except asyncio.TimeoutError:
            logger.warning("Timeout fetching artifacts for all servers")
            # Return empty artifacts for all servers
            return {
                server_name: {"tools": [], "prompts": [], "resources": []}
                for server_name in self._clients_provider().keys()
            }

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------
    async def _fetch_with_retry(
        self,
        fetch_func: Callable[[], Awaitable[list]],
        server_name: str,
        artifact_type: str,
        *,
        retry_on_empty: bool = False,
        max_retries: int = 2,
        retry_delay: float = 0.5,
    ) -> list:
        for attempt in range(max_retries + 1):
            try:
                result = await fetch_func()
                if result or not retry_on_empty or attempt == max_retries:
                    return result or []

                if attempt < max_retries:
                    logger.debug(
                        "Empty %s for %s (attempt %d), retrying in %.1fs",
                        artifact_type,
                        server_name,
                        attempt + 1,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
            except Exception as err:
                if attempt < max_retries:
                    logger.debug(
                        "Error fetching %s for %s (attempt %d): %s; retrying in %.1fs",
                        artifact_type,
                        server_name,
                        attempt + 1,
                        err,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.warning(
                        "Failed to fetch %s for %s after %d attempts: %s",
                        artifact_type,
                        server_name,
                        max_retries + 1,
                        err,
                    )
                    raise

        return []
