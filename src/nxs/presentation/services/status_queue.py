"""
StatusQueue - Manages asynchronous status updates for the status panel.

This module provides a queue-based system for updating the status panel
without blocking the UI, allowing users to scroll while status updates are processed.

Implementation:
    Uses AsyncQueueProcessor for background processing, eliminating code
    duplication with QueryQueue and establishing a reusable pattern.
"""

from collections import namedtuple
from typing import Callable

from nxs.logger import get_logger
from nxs.presentation.services.queue_processor import AsyncQueueProcessor

logger = get_logger("status_queue")

# Status update item for the queue
StatusUpdate = namedtuple("StatusUpdate", ["update_type", "args", "kwargs"])


class StatusQueue:
    """
    Manages asynchronous status updates for the status panel.

    Status updates are queued and processed in the background, ensuring
    the UI remains responsive and scrollable during updates.

    This class wraps AsyncQueueProcessor with a StatusPanel-specific API,
    providing methods like add_tool_call(), add_info_message(), etc.
    """

    def __init__(self, status_panel_getter: Callable):
        """
        Initialize the StatusQueue.

        Args:
            status_panel_getter: Function that returns the StatusPanel widget instance
        """
        self._status_panel_getter = status_panel_getter

        # Define processor function that applies status updates to the panel
        def apply_status_update(update: StatusUpdate) -> None:
            """Apply a status update to the status panel."""
            try:
                status_panel = self._status_panel_getter()
                if status_panel is None:
                    logger.warning("StatusPanel not available, skipping update")
                    return
            except Exception as e:
                logger.error(f"Error getting status panel: {e}")
                return

            # Apply the update by calling the appropriate method on the panel
            method_name = update.update_type
            if hasattr(status_panel, method_name):
                try:
                    method = getattr(status_panel, method_name)
                    method(*update.args, **update.kwargs)
                except Exception as e:
                    logger.error(f"Error applying status update {method_name}: {e}")
            else:
                logger.warning(f"StatusPanel has no method: {method_name}")

        # Create the underlying queue processor
        self._processor = AsyncQueueProcessor[StatusUpdate](
            processor=apply_status_update,
            name="StatusQueue",
        )

    async def start(self) -> None:
        """
        Start the status update worker task.

        This begins processing status updates from the queue asynchronously.
        """
        await self._processor.start()

    async def stop(self) -> None:
        """
        Stop the status update worker task and wait for it to finish.
        """
        await self._processor.stop()

    async def add_tool_call(self, name: str, params: dict) -> None:
        """Queue a tool call status update."""
        await self._processor.enqueue(StatusUpdate("add_tool_call", (name, params), {}))

    async def add_tool_result(self, tool_name: str, result: str, success: bool = True) -> None:
        """Queue a tool result status update."""
        await self._processor.enqueue(StatusUpdate("add_tool_result", (tool_name, result, success), {}))

    async def add_info_message(self, message: str) -> None:
        """Queue an info message status update."""
        await self._processor.enqueue(StatusUpdate("add_info_message", (message,), {}))

    async def add_error_message(self, message: str) -> None:
        """Queue an error message status update."""
        await self._processor.enqueue(StatusUpdate("add_error_message", (message,), {}))

    async def add_success_message(self, message: str) -> None:
        """Queue a success message status update."""
        await self._processor.enqueue(StatusUpdate("add_success_message", (message,), {}))

    async def add_table(self, title: str, data: dict) -> None:
        """Queue a table status update."""
        await self._processor.enqueue(StatusUpdate("add_table", (title, data), {}))

    async def add_divider(self) -> None:
        """Queue a divider status update."""
        await self._processor.enqueue(StatusUpdate("add_divider", (), {}))

    @property
    def is_running(self) -> bool:
        """Check if the StatusQueue is running."""
        return self._processor.is_running

    @property
    def queue_size(self) -> int:
        """Get the current number of pending status updates in the queue."""
        return self._processor.queue_size
