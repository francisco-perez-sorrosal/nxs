"""Health checking for MCP client connections."""

import asyncio
from typing import Callable, Optional, Protocol

from nxs.logger import get_logger

logger = get_logger("connection.health")


class SessionProtocol(Protocol):
    """Protocol for MCP session objects."""

    async def list_tools(self):
        """List available tools."""
        ...


class HealthChecker:
    """Monitors connection health and detects failures."""

    def __init__(
        self,
        check_interval: float = 30.0,
        timeout: float = 5.0,
    ):
        """
        Initialize health checker.

        Args:
            check_interval: Seconds between health checks
            timeout: Timeout for health check operations (seconds)
        """
        self._check_interval = check_interval
        self._timeout = timeout
        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

    async def start(
        self,
        get_session: Callable[[], Optional[SessionProtocol]],
        on_unhealthy: Callable[[], None],
        stop_event: asyncio.Event,
    ) -> None:
        """
        Start health check monitoring.

        Args:
            get_session: Callable that returns the current session or None
            on_unhealthy: Callback to invoke when connection becomes unhealthy
            stop_event: Event to signal stopping
        """
        if self._task and not self._task.done():
            logger.warning("Health checker already running")
            return

        self._stop_event = stop_event
        self._task = asyncio.create_task(
            self._health_check_loop(get_session, on_unhealthy, stop_event)
        )
        logger.info(f"Health checker started (interval={self._check_interval}s)")

    async def stop(self) -> None:
        """Stop health check monitoring."""
        if not self._task:
            return

        logger.info("Stopping health checker")
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error stopping health checker: {e}")

        self._task = None
        self._stop_event = None
        logger.info("Health checker stopped")

    async def _health_check_loop(
        self,
        get_session: Callable[[], Optional[SessionProtocol]],
        on_unhealthy: Callable[[], None],
        stop_event: asyncio.Event,
    ) -> None:
        """
        Background loop that performs periodic health checks.

        Args:
            get_session: Callable that returns the current session or None
            on_unhealthy: Callback to invoke when connection becomes unhealthy
            stop_event: Event to signal stopping
        """
        try:
            while not stop_event.is_set():
                await asyncio.sleep(self._check_interval)

                if stop_event.is_set():
                    break

                # Perform health check
                is_healthy = await self._check_health(get_session)

                if not is_healthy:
                    logger.warning("Connection unhealthy, triggering callback")
                    try:
                        on_unhealthy()
                    except Exception as e:
                        logger.error(f"Error in unhealthy callback: {e}")

        except asyncio.CancelledError:
            logger.info("Health check loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Health check loop error: {e}")

    async def _check_health(
        self,
        get_session: Callable[[], Optional[SessionProtocol]],
    ) -> bool:
        """
        Perform a single health check.

        Args:
            get_session: Callable that returns the current session or None

        Returns:
            True if connection is healthy, False otherwise
        """
        session = get_session()

        if session is None:
            logger.warning("Health check: Session is None")
            return False

        try:
            # Use list_tools as a lightweight health check
            await asyncio.wait_for(session.list_tools(), timeout=self._timeout)
            logger.debug("Health check passed")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Health check timed out after {self._timeout}s")
            return False
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    @property
    def is_running(self) -> bool:
        """Check if health checker is running."""
        return self._task is not None and not self._task.done()
