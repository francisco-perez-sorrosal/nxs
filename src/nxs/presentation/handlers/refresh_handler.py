"""
RefreshHandler for handling artifact refresh events.

This handler processes:
- ArtifactsFetched events
- Coordinates refresh operations with RefreshService
"""

from typing import TYPE_CHECKING

from nxs.domain.events import ArtifactsFetched
from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.presentation.services.mcp_refresher import RefreshService

logger = get_logger("refresh_handler")


class RefreshHandler:
    """
    Handles artifact refresh events.

    This handler processes ArtifactsFetched events and coordinates
    refresh operations with the RefreshService.
    """

    def __init__(self, mcp_refresher: "RefreshService"):
        """
        Initialize the RefreshHandler.

        Args:
            mcp_refresher: RefreshService for coordinating refreshes
        """
        self.mcp_refresher = mcp_refresher

    def handle_artifacts_fetched(self, event: ArtifactsFetched) -> None:
        """
        Handle artifacts fetched event.

        This method schedules a refresh of the MCP panel if artifacts changed.

        Args:
            event: ArtifactsFetched event
        """
        if event.changed:
            logger.debug(
                f"Artifacts changed for {event.server_name}, scheduling refresh"
            )
            self.mcp_refresher.schedule_refresh(server_name=event.server_name)
        else:
            logger.debug(
                f"Artifacts fetched for {event.server_name} (no changes)"
            )

