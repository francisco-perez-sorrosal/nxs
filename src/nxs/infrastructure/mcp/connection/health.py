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
    """Monitors connection health and detects failures.

    This checker serves dual purposes:
    1. Keep-alive: Sends periodic requests to keep serverless backends active
    2. Health monitoring: Detects connection failures and triggers reconnection
    """

    def __init__(
        self,
        check_interval: float = 10.0,
        timeout: float = 5.0,
        keep_alive_enabled: bool = True,
        failure_threshold: int = 2,
        health_check_operation: str = "list_tools",
    ):
        """
        Initialize health checker.

        Args:
            check_interval: Seconds between health checks (default: 10s for serverless)
            timeout: Timeout for health check operations (seconds)
            keep_alive_enabled: If True, proactively sends requests to keep server alive
            failure_threshold: Number of consecutive failures before marking unhealthy
            health_check_operation: MCP operation to use for health checks (list_tools, list_prompts, list_resources)
        """
        self._check_interval = check_interval
        self._timeout = timeout
        self._keep_alive_enabled = keep_alive_enabled
        self._failure_threshold = failure_threshold
        self._health_check_operation = health_check_operation
        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._consecutive_failures = 0

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
        self._consecutive_failures = 0
        self._task = asyncio.create_task(self._health_check_loop(get_session, on_unhealthy, stop_event))
        mode = "keep-alive + health monitoring" if self._keep_alive_enabled else "health monitoring only"
        logger.info(f"Health checker started (interval={self._check_interval}s, mode={mode}, operation={self._health_check_operation})")

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
        self._consecutive_failures = 0
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

                if is_healthy:
                    # Reset failure counter on successful check
                    if self._consecutive_failures > 0:
                        logger.info(f"Connection recovered after {self._consecutive_failures} failure(s)")
                    self._consecutive_failures = 0
                else:
                    # Increment failure counter
                    self._consecutive_failures += 1
                    logger.warning(f"Health check failed ({self._consecutive_failures}/{self._failure_threshold})")

                    # Only trigger unhealthy callback after threshold is reached
                    if self._consecutive_failures >= self._failure_threshold:
                        logger.warning(f"Connection unhealthy after {self._consecutive_failures} consecutive failures, triggering callback")
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
            logger.debug("Health check: Session is None")
            return False

        try:
            # Execute the configured health check operation
            operation = getattr(session, self._health_check_operation, None)
            if operation is None:
                logger.error(f"Invalid health check operation: {self._health_check_operation}")
                # Fallback to list_tools
                operation = session.list_tools

            await asyncio.wait_for(operation(), timeout=self._timeout)

            # Log differently based on mode
            if self._keep_alive_enabled:
                logger.debug(f"Health check passed (keep-alive ping sent via {self._health_check_operation})")
            else:
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
