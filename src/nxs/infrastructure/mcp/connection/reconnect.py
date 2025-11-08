"""Reconnection strategies for MCP client connections."""

import asyncio
from abc import ABC, abstractmethod
from typing import Callable, Optional

from nxs.logger import get_logger

logger = get_logger("connection.reconnect")


class ReconnectionStrategy(ABC):
    """Abstract base class for reconnection strategies."""

    @abstractmethod
    async def wait_before_retry(
        self,
        attempt: int,
        on_progress: Optional[Callable[[int, int, float], None]] = None,
        stop_event: Optional[asyncio.Event] = None,
    ) -> bool:
        """
        Wait before the next reconnection attempt.

        Args:
            attempt: Current attempt number (1-indexed)
            on_progress: Optional callback for progress updates (attempt, max_attempts, remaining_seconds)
            stop_event: Optional event to signal stopping

        Returns:
            True if should continue retrying, False if should stop
        """
        pass

    @abstractmethod
    def should_retry(self, attempt: int) -> bool:
        """Check if reconnection should be attempted."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset the reconnection state."""
        pass

    @property
    @abstractmethod
    def max_attempts(self) -> int:
        """Get maximum number of reconnection attempts."""
        pass


class ExponentialBackoffStrategy(ReconnectionStrategy):
    """Reconnection strategy with exponential backoff."""

    def __init__(
        self,
        max_attempts: int = 10,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_multiplier: float = 2.0,
        progress_update_interval: float = 2.0,
    ):
        """
        Initialize exponential backoff strategy.

        Args:
            max_attempts: Maximum number of reconnection attempts
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            backoff_multiplier: Multiplier for each retry
            progress_update_interval: How often to update progress during wait (seconds)
        """
        self._max_attempts = max_attempts
        self._initial_delay = initial_delay
        self._max_delay = max_delay
        self._backoff_multiplier = backoff_multiplier
        self._progress_update_interval = progress_update_interval

    @property
    def max_attempts(self) -> int:
        """Get maximum number of reconnection attempts."""
        return self._max_attempts

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for the given attempt number.

        Args:
            attempt: Current attempt number (1-indexed)

        Returns:
            Delay in seconds
        """
        if attempt <= 0:
            return self._initial_delay

        delay = self._initial_delay * (self._backoff_multiplier ** (attempt - 1))
        return min(delay, self._max_delay)

    def should_retry(self, attempt: int) -> bool:
        """Check if reconnection should be attempted."""
        return attempt <= self._max_attempts

    async def wait_before_retry(
        self,
        attempt: int,
        on_progress: Optional[Callable[[int, int, float], None]] = None,
        stop_event: Optional[asyncio.Event] = None,
    ) -> bool:
        """
        Wait before the next reconnection attempt with periodic progress updates.

        Args:
            attempt: Current attempt number (1-indexed)
            on_progress: Optional callback for progress updates
            stop_event: Optional event to signal stopping

        Returns:
            True if should continue retrying, False if should stop
        """
        if not self.should_retry(attempt):
            return False

        delay = self.calculate_delay(attempt)
        logger.info(
            f"Waiting {delay:.1f}s before retry (attempt {attempt}/{self._max_attempts})"
        )

        # Notify initial progress
        if on_progress:
            try:
                on_progress(attempt, self._max_attempts, delay)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")

        # Wait with periodic progress updates
        elapsed = 0.0
        while elapsed < delay:
            remaining = delay - elapsed

            # Check if we should stop
            if stop_event and stop_event.is_set():
                logger.info("Stop event set during reconnection delay")
                return False

            # Calculate next sleep duration
            if remaining > self._progress_update_interval:
                sleep_duration = self._progress_update_interval
            else:
                sleep_duration = remaining

            await asyncio.sleep(sleep_duration)
            elapsed += sleep_duration

            # Update progress
            remaining = delay - elapsed
            if remaining > 0:
                logger.debug(
                    f"Reconnection in {remaining:.1f}s (attempt {attempt}/{self._max_attempts})"
                )
                if on_progress:
                    try:
                        on_progress(attempt, self._max_attempts, remaining)
                    except Exception:
                        pass

        # Check one more time if we should stop
        if stop_event and stop_event.is_set():
            logger.info("Stop event set after reconnection delay")
            return False

        return True

    def reset(self) -> None:
        """Reset the reconnection state (no state to reset for stateless strategy)."""
        pass
