"""
RefreshService for managing MCP panel refresh operations.

This service encapsulates the logic for scheduling and coordinating
refresh operations, including task management and debouncing.
"""

import asyncio
import time
from typing import TYPE_CHECKING, Callable

from nxs.application.artifact_manager import ArtifactManager
from nxs.logger import get_logger

if TYPE_CHECKING:
    from ..widgets.mcp_panel import MCPPanel

logger = get_logger("refresh_service")


class RefreshService:
    """
    Service for coordinating MCP panel refresh operations.

    This class handles:
    - Task scheduling and cancellation to prevent accumulation
    - Refresh orchestration with locking to prevent simultaneous operations
    - Single server vs. full refresh logic
    - Cache comparison and updating
    - Status display coordination
    """

    # Default timeout for artifact fetching (in seconds)
    DEFAULT_TIMEOUT = 30.0

    def __init__(self, artifact_manager: ArtifactManager, mcp_panel_getter: Callable[[], "MCPPanel"]):
        """
        Initialize the RefreshService.

        Args:
            artifact_manager: The ArtifactManager instance
            mcp_panel_getter: Function to get the MCP panel widget
        """
        self.artifact_manager = artifact_manager
        self.mcp_panel_getter = mcp_panel_getter

        # Task management
        self._refresh_tasks: set[asyncio.Task] = set()
        self._refresh_lock = asyncio.Lock()
        self._server_last_check: dict[str, float] = {}

    def get_server_last_check(self, server_name: str) -> float:
        """Return the last artifact check timestamp for a server."""
        return self._server_last_check.get(server_name, 0.0)

    def update_server_last_check(self, server_name: str, timestamp: float | None = None) -> None:
        """Record the last artifact check time for a server."""
        if timestamp is None:
            timestamp = time.time()
        self._server_last_check[server_name] = timestamp

    def get_all_last_checks(self) -> dict[str, float]:
        """Expose a copy of the last-check timestamps."""
        return dict(self._server_last_check)

    def schedule_refresh(
        self, server_name: str | None = None, retry_on_empty: bool = False, delay: float = 0.0
    ) -> None:
        """
        Schedule a refresh operation, cancelling any previous refresh tasks.

        This prevents accumulation of refresh tasks that can cause unresponsiveness.

        Args:
            server_name: Optional specific server name to refresh
            retry_on_empty: If True, retry fetching artifacts if they come back empty
            delay: Delay in seconds before starting the refresh
        """
        # Cancel all previous refresh tasks to prevent accumulation
        self.cancel_pending_refreshes()

        # Create new refresh task
        task = asyncio.create_task(self.refresh(server_name=server_name, retry_on_empty=retry_on_empty, delay=delay))

        # Track the task
        self._refresh_tasks.add(task)

        # Clean up task when done
        task.add_done_callback(self._refresh_tasks.discard)

    def cancel_pending_refreshes(self) -> None:
        """Cancel all active refresh tasks to prevent accumulation."""
        for task in list(self._refresh_tasks):
            if not task.done():
                try:
                    task.cancel()
                except Exception as e:
                    logger.debug(f"Error cancelling refresh task: {e}")
        self._refresh_tasks.clear()

    async def refresh(self, server_name: str | None = None, retry_on_empty: bool = False, delay: float = 0.0) -> None:
        """
        Refresh the MCP panel with current server data and statuses.

        This method uses a lock to prevent simultaneous refresh operations.

        Args:
            server_name: Optional specific server name to refresh
            retry_on_empty: If True, retry fetching artifacts if they come back empty
            delay: Delay in seconds before starting the refresh
        """
        # Apply delay if specified (used when status changes to CONNECTED)
        if delay > 0:
            await asyncio.sleep(delay)

        # Use lock to prevent simultaneous refresh operations
        async with self._refresh_lock:
            try:
                if server_name is not None:
                    await self._refresh_single_server(server_name, retry_on_empty)
                else:
                    await self._refresh_all_servers()
            except asyncio.TimeoutError:
                logger.warning(f"Timeout refreshing MCP panel for {server_name or 'all servers'}")
                if server_name:
                    self._set_fetch_status(server_name, "[red]✗ Timeout[/]")
            except Exception as e:
                logger.error(f"Error refreshing MCP panel: {e}")
                if server_name:
                    self._set_fetch_status(server_name, f"[red]✗ Error: {str(e)[:30]}...[/]")

    async def _refresh_single_server(self, server_name: str, retry_on_empty: bool) -> None:
        """
        Refresh a single server, preserving data for other servers.

        Args:
            server_name: Name of the server to refresh
            retry_on_empty: If True, retry if result is empty
        """
        mcp_panel = self.mcp_panel_getter()
        mcp_panel.set_fetch_status(server_name, "[dim]Fetching artifacts...[/]")

        # Fetch artifacts for the target server with timeout
        artifacts = await self.artifact_manager.get_server_artifacts(
            server_name,
            retry_on_empty=retry_on_empty,
            timeout=self.DEFAULT_TIMEOUT,
        )
        self.update_server_last_check(server_name)

        # Get all servers data (cached or empty for others)
        servers_data = self._get_all_cached_or_empty()
        servers_data[server_name] = artifacts

        # Check if artifacts changed
        if self.artifact_manager.have_artifacts_changed(server_name, artifacts):
            # Cache the new artifacts
            self.artifact_manager.cache_artifacts(server_name, artifacts)

            # Show success status
            total_artifacts = self._count_artifacts(artifacts)
            if total_artifacts > 0:
                mcp_panel.set_fetch_status(server_name, f"[green]✓ {total_artifacts} artifact(s)[/]")
                # Clear status after 2 seconds
                asyncio.create_task(self._clear_fetch_status_after_delay(server_name, 2.0))
            else:
                mcp_panel.set_fetch_status(server_name, "[dim]No artifacts[/]")

            # Update display with all server data
            await self._update_panel_display(mcp_panel, servers_data)
            logger.debug(f"Artifacts changed for {server_name}, refreshed panel")
        else:
            # Cache even if unchanged
            self.artifact_manager.cache_artifacts(server_name, artifacts)
            # Clear "Fetching artifacts..." status
            mcp_panel.clear_fetch_status(server_name)
            logger.debug(f"Artifacts unchanged for {server_name}, preserved widgets")

    async def _refresh_all_servers(self) -> None:
        """Refresh all servers."""
        # Fetch artifacts for all servers with timeout
        servers_data = await self.artifact_manager.get_all_servers_artifacts(timeout=60.0)

        # Cache all artifacts
        for name, artifacts in servers_data.items():
            self.artifact_manager.cache_artifacts(name, artifacts)
            self.update_server_last_check(name)

        # Update panel
        mcp_panel = self.mcp_panel_getter()
        await self._update_panel_display(mcp_panel, servers_data)
        logger.debug(f"Refreshed MCP panel with {len(servers_data)} server(s)")

    async def _update_panel_display(
        self, mcp_panel: "MCPPanel", servers_data: dict[str, dict[str, list[dict[str, str | None]]]]
    ) -> None:
        """
        Update the MCP panel display with server data and statuses.

        Args:
            mcp_panel: The MCP panel widget
            servers_data: Dictionary mapping server names to their artifacts
        """
        # Get server statuses and last check times
        server_statuses = self.artifact_manager.get_server_statuses()

        server_names = set(servers_data.keys()) if servers_data else set(server_statuses.keys())
        server_last_check = {server_name: self.get_server_last_check(server_name) for server_name in server_names}

        logger.debug(f"Updating panel: {len(servers_data)} servers in data, " f"{len(server_statuses)} in statuses")
        mcp_panel.update_servers(servers_data, server_statuses, server_last_check)

    async def _clear_fetch_status_after_delay(self, server_name: str, delay: float) -> None:
        """
        Clear the fetch status for a server after a delay.

        Args:
            server_name: Name of the server
            delay: Delay in seconds before clearing status
        """
        await asyncio.sleep(delay)
        try:
            mcp_panel = self.mcp_panel_getter()
            mcp_panel.clear_fetch_status(server_name)
        except Exception as e:
            logger.debug(f"Error clearing fetch status for {server_name}: {e}")

    def _set_fetch_status(self, server_name: str, status: str) -> None:
        """
        Set the fetch status for a server.

        Args:
            server_name: Name of the server
            status: Status message to display
        """
        try:
            mcp_panel = self.mcp_panel_getter()
            mcp_panel.set_fetch_status(server_name, status)
        except Exception as e:
            logger.debug(f"Error setting fetch status for {server_name}: {e}")

    def _get_all_cached_or_empty(self) -> dict[str, dict[str, list]]:
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
            self._server_last_check.setdefault(server_name, 0.0)

        return servers_data

    def _count_artifacts(self, artifacts: dict[str, list]) -> int:
        """
        Count total number of artifacts.

        Args:
            artifacts: Dictionary with "tools", "prompts", "resources" keys

        Returns:
            Total number of artifacts
        """
        return len(artifacts.get("tools", [])) + len(artifacts.get("prompts", [])) + len(artifacts.get("resources", []))
