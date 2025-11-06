"""
ArtifactFetcher service for fetching MCP artifacts with timeout handling.

This service encapsulates the logic for fetching artifacts from MCP servers,
including timeout handling and error recovery.
"""

import asyncio
from typing import TYPE_CHECKING

from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.core.artifact_manager import ArtifactManager

logger = get_logger("artifact_fetcher")


class ArtifactFetcher:
    """
    Service for fetching MCP artifacts with timeout and error handling.

    This class handles:
    - Fetching artifacts from a single server with timeout
    - Fetching artifacts from all servers with timeout
    - Fallback to cached data on timeout
    - Retry logic for empty results
    """

    def __init__(self, artifact_manager: "ArtifactManager", default_timeout: float = 30.0):
        """
        Initialize the ArtifactFetcher.

        Args:
            artifact_manager: The ArtifactManager instance
            default_timeout: Default timeout in seconds for single server fetches
        """
        self.artifact_manager = artifact_manager
        self.default_timeout = default_timeout

    async def fetch_with_timeout(
        self,
        server_name: str,
        retry_on_empty: bool = False,
        timeout: float | None = None
    ) -> dict[str, list[dict[str, str | None]]]:
        """
        Fetch artifacts for a single server with timeout.

        Args:
            server_name: Name of the server
            retry_on_empty: If True, retry if result is empty
            timeout: Timeout in seconds (uses default if None)

        Returns:
            Dictionary with keys "tools", "prompts", "resources"
        """
        timeout = timeout or self.default_timeout

        try:
            artifacts = await asyncio.wait_for(
                self.artifact_manager.get_server_artifacts(
                    server_name,
                    retry_on_empty=retry_on_empty
                ),
                timeout=timeout
            )
            return artifacts
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching artifacts for {server_name}")
            return {"tools": [], "prompts": [], "resources": []}
        except Exception as e:
            logger.error(f"Error fetching artifacts for {server_name}: {e}")
            return {"tools": [], "prompts": [], "resources": []}

    async def fetch_all(
        self,
        timeout: float = 60.0,
        use_cached_on_timeout: bool = True
    ) -> dict[str, dict[str, list[dict[str, str | None]]]]:
        """
        Fetch artifacts for all servers with timeout.

        Args:
            timeout: Timeout in seconds for fetching all servers
            use_cached_on_timeout: If True, fallback to cached data on timeout

        Returns:
            Dictionary mapping server names to their artifacts
        """
        try:
            servers_data = await asyncio.wait_for(
                self.artifact_manager.get_all_servers_artifacts(),
                timeout=timeout
            )

            # Cache all artifacts
            for name, artifacts in servers_data.items():
                self.artifact_manager.cache_artifacts(name, artifacts)

            return servers_data
        except asyncio.TimeoutError:
            logger.warning("Timeout fetching artifacts for all servers")

            if use_cached_on_timeout:
                # Fall back to cached data
                return self._get_all_cached_or_empty()
            else:
                return {}
        except Exception as e:
            logger.error(f"Error fetching artifacts for all servers: {e}")

            if use_cached_on_timeout:
                return self._get_all_cached_or_empty()
            else:
                return {}

    def _get_all_cached_or_empty(self) -> dict[str, dict[str, list[dict[str, str | None]]]]:
        """
        Get cached artifacts for all servers, or empty dicts if not cached.

        Returns:
            Dictionary mapping server names to their cached artifacts
        """
        server_statuses = self.artifact_manager.get_server_statuses()
        servers_data = {}

        for server_name in server_statuses.keys():
            cached = self.artifact_manager.get_cached_artifacts(server_name)
            if cached:
                servers_data[server_name] = cached
            else:
                servers_data[server_name] = {"tools": [], "prompts": [], "resources": []}

        return servers_data

    async def fetch_and_merge(
        self,
        server_name: str,
        retry_on_empty: bool = False,
        timeout: float | None = None
    ) -> dict[str, dict[str, list[dict[str, str | None]]]]:
        """
        Fetch artifacts for a single server and merge with cached data for others.

        This is useful when refreshing a single server while preserving
        existing data for other servers.

        Args:
            server_name: Name of the server to fetch
            retry_on_empty: If True, retry if result is empty
            timeout: Timeout in seconds (uses default if None)

        Returns:
            Dictionary mapping all server names to their artifacts
        """
        # Fetch artifacts for the target server
        artifacts = await self.fetch_with_timeout(server_name, retry_on_empty, timeout)

        # Get cached/empty data for all servers
        servers_data = self._get_all_cached_or_empty()

        # Update with the newly fetched artifacts
        servers_data[server_name] = artifacts

        return servers_data
