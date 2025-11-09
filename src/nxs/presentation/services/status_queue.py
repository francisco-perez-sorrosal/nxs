"""
StatusQueue - Manages asynchronous status updates for the status panel.

This module provides a queue-based system for updating the status panel
without blocking the UI, allowing users to scroll while status updates are processed.
"""

import asyncio
from collections import namedtuple
from typing import Callable
from nxs.logger import get_logger

logger = get_logger("status_queue")

# Status update item for the queue
StatusUpdate = namedtuple("StatusUpdate", ["update_type", "args", "kwargs"])


class StatusQueue:
    """
    Manages asynchronous status updates for the status panel.

    Status updates are queued and processed in the background, ensuring
    the UI remains responsive and scrollable during updates.
    """

    def __init__(self, status_panel_getter: Callable):
        """
        Initialize the StatusQueue.

        Args:
            status_panel_getter: Function that returns the StatusPanel widget instance
        """
        self._status_panel_getter = status_panel_getter
        self._update_queue: asyncio.Queue[StatusUpdate] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """
        Start the status update worker task.

        This begins processing status updates from the queue asynchronously.
        """
        if self._running:
            logger.warning("StatusQueue already running")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("StatusQueue started")

    async def stop(self) -> None:
        """
        Stop the status update worker task and wait for it to finish.
        """
        if not self._running:
            return

        self._running = False
        logger.info("Stopping StatusQueue...")

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                logger.info("StatusQueue worker task cancelled successfully")

        logger.info("StatusQueue stopped")

    async def add_tool_call(self, name: str, params: dict) -> None:
        """Queue a tool call status update."""
        await self._update_queue.put(StatusUpdate("add_tool_call", (name, params), {}))

    async def add_tool_result(self, tool_name: str, result: str, success: bool = True) -> None:
        """Queue a tool result status update."""
        await self._update_queue.put(StatusUpdate("add_tool_result", (tool_name, result, success), {}))

    async def add_info_message(self, message: str) -> None:
        """Queue an info message status update."""
        await self._update_queue.put(StatusUpdate("add_info_message", (message,), {}))

    async def add_error_message(self, message: str) -> None:
        """Queue an error message status update."""
        await self._update_queue.put(StatusUpdate("add_error_message", (message,), {}))

    async def add_success_message(self, message: str) -> None:
        """Queue a success message status update."""
        await self._update_queue.put(StatusUpdate("add_success_message", (message,), {}))

    async def add_table(self, title: str, data: dict) -> None:
        """Queue a table status update."""
        await self._update_queue.put(StatusUpdate("add_table", (title, data), {}))

    async def add_divider(self) -> None:
        """Queue a divider status update."""
        await self._update_queue.put(StatusUpdate("add_divider", (), {}))

    @property
    def is_running(self) -> bool:
        """Check if the StatusQueue is running."""
        return self._running

    @property
    def queue_size(self) -> int:
        """Get the current number of pending status updates in the queue."""
        return self._update_queue.qsize()

    async def _worker(self) -> None:
        """
        Worker task that processes status updates from the queue asynchronously.

        Updates are applied using call_after_refresh to ensure they don't block
        UI interactions like scrolling.
        """
        logger.info("StatusQueue worker started")

        while self._running:
            try:
                # Wait for an update from the queue (blocks until one is available)
                update = await self._update_queue.get()

                # Get the status panel widget
                try:
                    status_panel = self._status_panel_getter()
                    if status_panel is None:
                        logger.warning("StatusPanel not available, skipping update")
                        self._update_queue.task_done()
                        continue
                except Exception as e:
                    logger.error(f"Error getting status panel: {e}")
                    self._update_queue.task_done()
                    continue

                # Apply the update directly - Textual widgets are safe to update from async contexts
                # The queueing ensures we don't overwhelm the UI thread
                method_name = update.update_type
                if hasattr(status_panel, method_name):
                    method = getattr(status_panel, method_name)
                    try:
                        # Call the method directly - Textual handles async updates gracefully
                        method(*update.args, **update.kwargs)
                    except Exception as e:
                        logger.error(f"Error applying status update {method_name}: {e}")
                else:
                    logger.warning(f"StatusPanel has no method: {method_name}")

                # Mark the update as done
                self._update_queue.task_done()

                # Small delay to allow UI to process other events (like scrolling)
                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                logger.info("StatusQueue worker task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in StatusQueue worker: {e}", exc_info=True)
                try:
                    self._update_queue.task_done()
                except ValueError:
                    pass

        logger.info("StatusQueue worker stopped")
