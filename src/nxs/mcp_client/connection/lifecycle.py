"""Connection lifecycle management for MCP client."""

import asyncio
from enum import Enum
from typing import Callable, Optional

from nxs.logger import get_logger

logger = get_logger("connection.lifecycle")


class ConnectionStatus(Enum):
    """Connection status enumeration."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class ConnectionLifecycle:
    """Manages connection lifecycle state and events."""

    def __init__(
        self,
        on_status_change: Optional[Callable[[ConnectionStatus], None]] = None,
    ):
        """
        Initialize connection lifecycle manager.

        Args:
            on_status_change: Callback invoked when connection status changes
        """
        self._status = ConnectionStatus.DISCONNECTED
        self._on_status_change = on_status_change
        self._stop_event: Optional[asyncio.Event] = None
        self._ready_event: Optional[asyncio.Event] = None
        self._error_message: Optional[str] = None

    @property
    def status(self) -> ConnectionStatus:
        """Get current connection status."""
        return self._status

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._status == ConnectionStatus.CONNECTED

    @property
    def is_disconnected(self) -> bool:
        """Check if disconnected."""
        return self._status == ConnectionStatus.DISCONNECTED

    @property
    def is_error(self) -> bool:
        """Check if in error state."""
        return self._status == ConnectionStatus.ERROR

    @property
    def error_message(self) -> Optional[str]:
        """Get error message if in ERROR state."""
        return self._error_message

    def set_status(self, status: ConnectionStatus, error_message: Optional[str] = None) -> None:
        """
        Update connection status and notify callback.

        Args:
            status: New connection status
            error_message: Optional error message for ERROR status
        """
        if self._status != status:
            old_status = self._status
            self._status = status
            self._error_message = error_message if status == ConnectionStatus.ERROR else None

            logger.debug(f"Status changed: {old_status.value} -> {status.value}")

            if self._on_status_change:
                try:
                    self._on_status_change(status)
                except Exception as e:
                    logger.error(f"Error in status change callback: {e}")

    def initialize(self) -> tuple[asyncio.Event, asyncio.Event]:
        """
        Initialize lifecycle events for a new connection attempt.

        Returns:
            Tuple of (stop_event, ready_event)
        """
        self._stop_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        self._error_message = None
        logger.debug("Lifecycle events initialized")
        return self._stop_event, self._ready_event

    def mark_ready(self) -> None:
        """Mark connection as ready."""
        if self._ready_event and not self._ready_event.is_set():
            self._ready_event.set()
            logger.debug("Connection marked as ready")

    async def wait_until_ready(self) -> None:
        """Wait until connection is ready."""
        if not self._ready_event:
            raise RuntimeError("Lifecycle not initialized")
        await self._ready_event.wait()

    def signal_stop(self) -> None:
        """Signal that connection should stop."""
        if self._stop_event:
            self._stop_event.set()
            logger.debug("Stop event signaled")

    def is_stop_requested(self) -> bool:
        """Check if stop has been requested."""
        return self._stop_event is not None and self._stop_event.is_set()

    async def wait_for_stop(self) -> None:
        """Wait for stop signal."""
        if not self._stop_event:
            raise RuntimeError("Lifecycle not initialized")
        await self._stop_event.wait()

    def cleanup(self) -> None:
        """Clean up lifecycle state."""
        self._stop_event = None
        self._ready_event = None
        self._error_message = None
        logger.debug("Lifecycle cleaned up")

    def reset_error(self) -> None:
        """Reset error state for retry."""
        self._error_message = None
        if self._status == ConnectionStatus.ERROR:
            self._status = ConnectionStatus.DISCONNECTED
