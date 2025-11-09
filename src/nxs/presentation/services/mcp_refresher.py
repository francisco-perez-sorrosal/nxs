"""
RefreshService for managing MCP panel refresh operations.

This service encapsulates the logic for scheduling and coordinating
refresh operations, including task management, debouncing, and periodic
background refresh checks.
"""

import asyncio
import time
from typing import TYPE_CHECKING, Callable

from nxs.application.artifact_manager import ArtifactManager
from nxs.domain.events import ArtifactsFetched, ConnectionStatusChanged, ReconnectProgress
from nxs.domain.types import ConnectionStatus
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
    - Periodic background refresh checks for connected servers
    - Automatic reconnection retries for ERROR status servers
    """

    # Default timeout for artifact fetching (in seconds)
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        mcp_panel_getter: Callable[[], "MCPPanel"],
        reconnect_progress_debounce_interval: float = 1.0,
    ):
        """
        Initialize the RefreshService.

        Args:
            artifact_manager: The ArtifactManager instance
            mcp_panel_getter: Function to get the MCP panel widget
            reconnect_progress_debounce_interval: Minimum seconds between reconnect progress updates
        """
        self.artifact_manager = artifact_manager
        self.mcp_panel_getter = mcp_panel_getter

        # Task management
        self._refresh_tasks: set[asyncio.Task] = set()
        self._refresh_lock = asyncio.Lock()
        self._server_last_check: dict[str, float] = {}

        # Background task management
        self._background_task: asyncio.Task | None = None
        self._background_running = False

        # Event handling (merged from ConnectionHandler and RefreshHandler)
        self._reconnect_progress_debounce_interval = reconnect_progress_debounce_interval
        self._last_reconnect_progress_update: dict[str, float] = {}
        self._reconnect_info_cache: dict[str, dict | None] = {}

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

    # -------------------------------------------------------------------------
    # Event handlers (merged from ConnectionHandler and RefreshHandler)
    # -------------------------------------------------------------------------

    def handle_connection_status_changed(self, event: ConnectionStatusChanged) -> None:
        """
        Handle connection status change event.

        This method updates the MCP panel to reflect the new status and
        coordinates refresh operations based on the status change.

        Args:
            event: ConnectionStatusChanged event
        """
        server_name = event.server_name
        status = event.status
        logger.info(f"Connection status changed for {server_name}: {status.value}")

        # Check if this is a real status change (not just setting to already-connected)
        try:
            client = self.artifact_manager.clients.get(server_name)
            if client and status == ConnectionStatus.CONNECTED:
                # Check if already connected and has artifacts
                cached = self.artifact_manager.get_cached_artifacts(server_name)
                if cached and client.is_connected:
                    total_cached = (
                        len(cached.get("tools", [])) + len(cached.get("prompts", [])) + len(cached.get("resources", []))
                    )
                    if total_cached > 0:
                        # Already connected with artifacts, don't refresh unnecessarily
                        logger.debug(
                            f"Server {server_name} already connected with {total_cached} artifact(s), " "skipping refresh"
                        )
                        # Still update reconnect info to clear any stale progress
                        try:
                            mcp_panel = self.mcp_panel_getter()
                            # Get cached reconnect info from events
                            reconnect_info = self._reconnect_info_cache.get(server_name)
                            if reconnect_info:
                                mcp_panel.update_reconnect_info(server_name, reconnect_info)
                            self.schedule_refresh()
                        except Exception:
                            pass
                        return
        except Exception:
            pass  # Continue with refresh if check fails

        # Update MCP panel status
        try:
            mcp_panel = self.mcp_panel_getter()
            mcp_panel.update_server_status(server_name, status)

            # Update reconnect info from cached events
            reconnect_info = self._reconnect_info_cache.get(server_name)
            if reconnect_info:
                mcp_panel.update_reconnect_info(server_name, reconnect_info)

            # Clear reconnect info cache when successfully connected
            if status == ConnectionStatus.CONNECTED:
                self._reconnect_info_cache.pop(server_name, None)

            # Update last check time when status changes
            self.update_server_last_check(server_name)

            # Refresh the panel with current data
            # For CONNECTED status, add a small delay to ensure session is fully ready
            # This is especially important during reconnection when artifacts need to be re-fetched
            if status == ConnectionStatus.CONNECTED:
                # Delay refresh slightly to ensure session is ready after initialization
                self.schedule_refresh(server_name=server_name, delay=0.5)
            elif status == ConnectionStatus.DISCONNECTED:
                # Clear fetch status and artifacts cache when disconnected
                mcp_panel.clear_fetch_status(server_name)
                self.artifact_manager.clear_artifacts_cache(server_name)
                # Refresh panel immediately to show artifacts are gone
                self.schedule_refresh()
            else:
                # For other statuses (CONNECTING, RECONNECTING, ERROR), refresh immediately
                self.schedule_refresh()
        except Exception as e:
            logger.error(f"Error updating MCP panel status: {e}")

    def handle_reconnect_progress(self, event: ReconnectProgress) -> None:
        """
        Handle reconnection progress event.

        This method updates the MCP panel with reconnection progress information.
        Debounced to prevent creating too many refresh tasks.

        Args:
            event: ReconnectProgress event
        """
        server_name = event.server_name
        current_time = time.time()

        # Cache reconnect info from event
        self._reconnect_info_cache[server_name] = {
            "attempts": event.attempts,
            "max_attempts": event.max_attempts,
            "next_retry_delay": event.next_retry_delay,
        }

        # Debounce: only update if enough time has passed since last update for this server
        last_update = self._last_reconnect_progress_update.get(server_name, 0)
        if current_time - last_update < self._reconnect_progress_debounce_interval:
            return  # Skip this update to avoid too many refresh tasks

        self._last_reconnect_progress_update[server_name] = current_time
        logger.debug(
            f"Reconnection progress for {server_name}: attempt {event.attempts}/{event.max_attempts}, "
            f"retry in {event.next_retry_delay:.1f}s"
        )

        try:
            mcp_panel = self.mcp_panel_getter()
            # Get cached reconnect info from events
            reconnect_info = self._reconnect_info_cache.get(server_name)
            if reconnect_info:
                mcp_panel.update_reconnect_info(server_name, reconnect_info)
                # Schedule refresh with task management to prevent accumulation
                self.schedule_refresh()
        except Exception as e:
            logger.debug(f"Error updating reconnect progress for {server_name}: {e}")

    def handle_artifacts_fetched(self, event: ArtifactsFetched) -> None:
        """
        Handle artifacts fetched event.

        This method schedules a refresh of the MCP panel if artifacts changed.

        Args:
            event: ArtifactsFetched event
        """
        if event.changed:
            logger.debug(f"Artifacts changed for {event.server_name}, scheduling refresh")
            self.schedule_refresh(server_name=event.server_name)
        else:
            logger.debug(f"Artifacts fetched for {event.server_name} (no changes)")

    # -------------------------------------------------------------------------
    # Background periodic refresh task (merged from BackgroundTaskService)
    # -------------------------------------------------------------------------

    def start_periodic_refresh(self, mcp_initialized_getter: Callable[[], bool]) -> None:
        """
        Start periodic background refresh task.

        This task runs every 30 seconds and:
        - Checks connected servers for artifacts (if not cached)
        - Retries ERROR status servers every 60 seconds

        Args:
            mcp_initialized_getter: Callable that returns True when MCP is initialized
        """
        if self._background_task is None or self._background_task.done():
            self._background_running = True
            self._background_task = asyncio.create_task(self._periodic_refresh_loop(mcp_initialized_getter))
            logger.info("Periodic background refresh started")

    async def stop_periodic_refresh(self) -> None:
        """Stop the periodic background refresh task."""
        self._background_running = False
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            logger.info("Periodic background refresh stopped")

    async def _periodic_refresh_loop(self, mcp_initialized_getter: Callable[[], bool]) -> None:
        """
        Periodically check for connected servers with no artifacts and refresh them.

        This helps catch cases where artifacts weren't loaded initially but are
        now available, or when reconnection happens but artifacts weren't refreshed.
        Also retries ERROR status servers periodically to allow recovery.

        Runs asynchronously every 30 seconds without blocking the UI.
        Only refreshes if artifacts have changed or if server had no artifacts before.
        """
        await asyncio.sleep(5.0)  # Initial delay before first check

        while self._background_running and mcp_initialized_getter():
            try:
                # Check all servers asynchronously
                for server_name, client in self.artifact_manager.clients.items():
                    try:
                        # connection_status is implementation-specific, not in protocol
                        status = client.connection_status  # type: ignore[attr-defined]

                        # Handle ERROR status servers - retry connection periodically (every 60 seconds)
                        if status == ConnectionStatus.ERROR:
                            # Check if we should retry (every 60 seconds)
                            last_check = self.get_server_last_check(server_name)
                            time_since_check = time.time() - last_check
                            if time_since_check >= 60.0:
                                logger.info(f"Retrying connection for ERROR status server: {server_name}")
                                try:
                                    # retry_connection is implementation-specific, not in protocol
                                    await client.retry_connection(use_auth=False)  # type: ignore[attr-defined]
                                    # Update last check time
                                    self.update_server_last_check(server_name)
                                except Exception as e:
                                    logger.debug(f"Error retrying connection for {server_name}: {e}")
                                    # Update last check time even on failure to avoid retrying too frequently
                                    self.update_server_last_check(server_name)
                            continue

                        # Handle connected servers - check for artifacts
                        if client.is_connected:
                            logger.debug(f"Periodic refresh check for {server_name}")

                            # Update last check time
                            self.update_server_last_check(server_name)

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
                                    self.schedule_refresh(server_name=server_name)
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
                logger.info("Periodic refresh loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic refresh loop: {e}")
                # Wait 30 seconds before retrying (asynchronous sleep)
                await asyncio.sleep(30.0)
