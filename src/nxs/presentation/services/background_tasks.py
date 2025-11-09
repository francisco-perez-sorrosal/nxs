"""
BackgroundTaskService - Manages background tasks for the TUI.

This service handles periodic background operations like:
- Artifact refresh checks for connected servers
- Server reconnection retries for ERROR status servers
"""

import asyncio
import time
from typing import TYPE_CHECKING

from nxs.application.artifact_manager import ArtifactManager
from nxs.domain.types import ConnectionStatus
from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.presentation.services.mcp_refresher import RefreshService

logger = get_logger("background_tasks")


class BackgroundTaskService:
    """
    Manages background tasks for the TUI.

    This service runs periodic checks in the background:
    - Checks for connected servers with no artifacts and refreshes them
    - Retries ERROR status servers periodically to allow recovery
    """

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        mcp_refresher: "RefreshService",
    ):
        """
        Initialize the BackgroundTaskService.

        Args:
            artifact_manager: The ArtifactManager instance
            mcp_refresher: RefreshService for managing panel refreshes
        """
        self.artifact_manager = artifact_manager
        self.mcp_refresher = mcp_refresher
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self, mcp_initialized_getter) -> None:
        """
        Start the background task.

        Args:
            mcp_initialized_getter: Callable that returns True when MCP is initialized
        """
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._periodic_artifact_refresh(mcp_initialized_getter))
            logger.info("Background task started")

    async def stop(self) -> None:
        """Stop the background task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Background task stopped")

    async def _periodic_artifact_refresh(self, mcp_initialized_getter) -> None:
        """
        Periodically check for connected servers with no artifacts and refresh them.

        This helps catch cases where artifacts weren't loaded initially but are
        now available, or when reconnection happens but artifacts weren't refreshed.
        Also retries ERROR status servers periodically to allow recovery.

        Runs asynchronously every 30 seconds without blocking the UI.
        Only refreshes if artifacts have changed or if server had no artifacts before.
        """
        await asyncio.sleep(5.0)  # Initial delay before first check

        while self._running and mcp_initialized_getter():
            try:
                # Check all servers asynchronously
                for server_name, client in self.artifact_manager.clients.items():
                    try:
                        # connection_status is implementation-specific, not in protocol
                        status = client.connection_status  # type: ignore[attr-defined]

                        # Handle ERROR status servers - retry connection periodically (every 60 seconds)
                        if status == ConnectionStatus.ERROR:
                            # Check if we should retry (every 60 seconds)
                            last_check = self.mcp_refresher.get_server_last_check(server_name)
                            time_since_check = time.time() - last_check
                            if time_since_check >= 60.0:
                                logger.info(f"Retrying connection for ERROR status server: {server_name}")
                                try:
                                    # retry_connection is implementation-specific, not in protocol
                                    await client.retry_connection(use_auth=False)  # type: ignore[attr-defined]
                                    # Update last check time
                                    self.mcp_refresher.update_server_last_check(server_name)
                                except Exception as e:
                                    logger.debug(f"Error retrying connection for {server_name}: {e}")
                                    # Update last check time even on failure to avoid retrying too frequently
                                    self.mcp_refresher.update_server_last_check(server_name)
                            continue

                        # Handle connected servers - check for artifacts
                        if client.is_connected:
                            logger.debug(f"Periodic refresh check for {server_name}")

                            # Update last check time
                            self.mcp_refresher.update_server_last_check(server_name)

                            # Get cached artifacts
                            cached_artifacts = self.artifact_manager.get_cached_artifacts(server_name)
                            cached_total = 0
                            if cached_artifacts:
                                cached_total = (
                                    len(cached_artifacts.get("tools", []))
                                    + len(cached_artifacts.get("prompts", []))
                                    + len(cached_artifacts.get("resources", []))
                                )

                            # Only fetch if we don't have artifacts cached (to avoid unnecessary work)
                            if cached_total == 0:
                                # Fetch artifacts to see if they're available
                                artifacts = await self.artifact_manager.get_server_artifacts(server_name)
                                total = (
                                    len(artifacts.get("tools", []))
                                    + len(artifacts.get("prompts", []))
                                    + len(artifacts.get("resources", []))
                                )

                                if total > 0:
                                    # Server has artifacts but we didn't have them cached, refresh the panel
                                    logger.info(
                                        f"Found {total} artifact(s) for {server_name} during periodic check (was 0) - refreshing panel"
                                    )
                                    # Cache the artifacts
                                    self.artifact_manager.cache_artifacts(server_name, artifacts)
                                    # Refresh asynchronously without blocking
                                    self.mcp_refresher.schedule_refresh(server_name=server_name)
                            else:
                                # Already have artifacts cached, skip fetching to avoid unnecessary refresh
                                logger.debug(
                                    f"Server {server_name} already has {cached_total} artifact(s) cached, skipping periodic fetch"
                                )
                    except Exception as e:
                        logger.debug(f"Error during periodic refresh check for {server_name}: {e}")

                # Wait 30 seconds before next check (asynchronous sleep)
                await asyncio.sleep(30.0)
            except asyncio.CancelledError:
                logger.info("Periodic artifact refresh task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic artifact refresh: {e}")
                # Wait 30 seconds before retrying (asynchronous sleep)
                await asyncio.sleep(30.0)
