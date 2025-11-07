"""
ConnectionHandler for handling connection-related events.

This handler processes:
- ConnectionStatusChanged events
- ReconnectProgress events
- Updates MCP panel and manages refresh coordination
"""

import time
from typing import TYPE_CHECKING, Callable

from nxs.core.events import ConnectionStatusChanged, ReconnectProgress
from nxs.mcp_client.client import ConnectionStatus
from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.core.artifact_manager import ArtifactManager
    from nxs.tui.services.mcp_refresher import MCPRefresher
    from nxs.tui.widgets.mcp_panel import MCPPanel

logger = get_logger("connection_handler")


class ConnectionHandler:
    """
    Handles connection-related events.
    
    This handler processes connection status changes and reconnection
    progress events, updating the MCP panel and coordinating refreshes.
    """

    def __init__(
        self,
        artifact_manager: "ArtifactManager",
        mcp_panel_getter: Callable[[], "MCPPanel"],
        mcp_refresher: "MCPRefresher",
        reconnect_progress_debounce_interval: float = 1.0,
    ):
        """
        Initialize the ConnectionHandler.

        Args:
            artifact_manager: The ArtifactManager instance
            mcp_panel_getter: Function to get the MCP panel widget
            mcp_refresher: MCPRefresher service for coordinating refreshes
            reconnect_progress_debounce_interval: Minimum seconds between reconnect progress updates
        """
        self.artifact_manager = artifact_manager
        self.mcp_panel_getter = mcp_panel_getter
        self.mcp_refresher = mcp_refresher
        self._reconnect_progress_debounce_interval = reconnect_progress_debounce_interval
        self._last_reconnect_progress_update: dict[str, float] = {}

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
                        len(cached.get("tools", []))
                        + len(cached.get("prompts", []))
                        + len(cached.get("resources", []))
                    )
                    if total_cached > 0:
                        # Already connected with artifacts, don't refresh unnecessarily
                        logger.debug(
                            f"Server {server_name} already connected with {total_cached} artifact(s), "
                            "skipping refresh"
                        )
                        # Still update reconnect info to clear any stale progress
                        try:
                            mcp_panel = self.mcp_panel_getter()
                            if client:
                                # reconnect_info is implementation-specific, not in protocol
                                reconnect_info = client.reconnect_info  # type: ignore[attr-defined]
                                mcp_panel.update_reconnect_info(server_name, reconnect_info)
                                self.mcp_refresher.schedule_refresh()
                        except Exception:
                            pass
                        return
        except Exception:
            pass  # Continue with refresh if check fails

        # Update MCP panel status
        try:
            mcp_panel = self.mcp_panel_getter()
            mcp_panel.update_server_status(server_name, status)

            # Update reconnect info from client
            client = self.artifact_manager.clients.get(server_name)
            if client:
                # reconnect_info is implementation-specific, not in protocol
                reconnect_info = client.reconnect_info  # type: ignore[attr-defined]
                mcp_panel.update_reconnect_info(server_name, reconnect_info)

            # Update last check time when status changes
            self.artifact_manager.update_server_last_check(server_name)

            # Refresh the panel with current data
            # For CONNECTED status, add a small delay to ensure session is fully ready
            # This is especially important during reconnection when artifacts need to be re-fetched
            if status == ConnectionStatus.CONNECTED:
                # Delay refresh slightly to ensure session is ready after initialization
                self.mcp_refresher.schedule_refresh(server_name=server_name, delay=0.5)
            elif status == ConnectionStatus.DISCONNECTED:
                # Clear fetch status and artifacts cache when disconnected
                mcp_panel.clear_fetch_status(server_name)
                self.artifact_manager.clear_artifacts_cache(server_name)
                # Refresh panel immediately to show artifacts are gone
                self.mcp_refresher.schedule_refresh()
            else:
                # For other statuses (CONNECTING, RECONNECTING, ERROR), refresh immediately
                self.mcp_refresher.schedule_refresh()
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
            client = self.artifact_manager.clients.get(server_name)
            if client:
                # reconnect_info is implementation-specific, not in protocol
                reconnect_info = client.reconnect_info  # type: ignore[attr-defined]
                mcp_panel.update_reconnect_info(server_name, reconnect_info)
                # Schedule refresh with task management to prevent accumulation
                self.mcp_refresher.schedule_refresh()
        except Exception as e:
            logger.debug(f"Error updating reconnect progress for {server_name}: {e}")

