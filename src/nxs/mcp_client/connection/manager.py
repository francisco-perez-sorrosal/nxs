"""Connection manager that orchestrates connection lifecycle, health, and reconnection."""

import asyncio
from typing import Any, Callable, Optional, Protocol

from nxs.logger import get_logger
from .health import HealthChecker
from .lifecycle import ConnectionLifecycle, ConnectionStatus
from .reconnect import ReconnectionStrategy, ExponentialBackoffStrategy

logger = get_logger("connection.manager")


class SessionProtocol(Protocol):
    """Protocol for MCP session objects."""

    async def list_tools(self):
        """List available tools."""
        ...


class ConnectionManager:
    """
    Orchestrates connection management with lifecycle, health checking, and reconnection.

    This manager coordinates:
    - Connection lifecycle state (connecting, connected, disconnected, etc.)
    - Health monitoring to detect connection failures
    - Automatic reconnection with configurable strategy
    - Callbacks for status changes and reconnection progress
    """

    def __init__(
        self,
        reconnection_strategy: Optional[ReconnectionStrategy] = None,
        health_checker: Optional[HealthChecker] = None,
        lifecycle: Optional[ConnectionLifecycle] = None,
        on_status_change: Optional[Callable[[ConnectionStatus], None]] = None,
        on_reconnect_progress: Optional[Callable[[int, int, float], None]] = None,
    ):
        """
        Initialize connection manager.

        Args:
            reconnection_strategy: Strategy for reconnection backoff (defaults to exponential)
            health_checker: Health checker instance (defaults to 30s interval)
            lifecycle: Lifecycle manager instance (created if not provided)
            on_status_change: Callback invoked when connection status changes
            on_reconnect_progress: Callback invoked during reconnection (attempt, max_attempts, delay)
        """
        self._reconnect_strategy = reconnection_strategy or ExponentialBackoffStrategy()
        self._health_checker = health_checker or HealthChecker()
        self._lifecycle = lifecycle or ConnectionLifecycle(on_status_change=on_status_change)
        self._on_reconnect_progress = on_reconnect_progress

        self._session: Optional[SessionProtocol] = None
        self._connection_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0

    @property
    def status(self) -> ConnectionStatus:
        """Get current connection status."""
        return self._lifecycle.status

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._lifecycle.is_connected and self._session is not None

    @property
    def session(self) -> Optional[SessionProtocol]:
        """Get current session."""
        return self._session

    def set_session(self, session: Any) -> None:
        """
        Set the current session.

        This should be called by the connect_fn when the session is ready.

        Args:
            session: The session to set (typically ClientSession from MCP SDK)
        """
        self._session = session
        if session:
            # Reset reconnect attempts and error on successful connection
            self._reconnect_attempts = 0
            self._lifecycle.set_status(ConnectionStatus.CONNECTED)
            self._lifecycle.mark_ready()
            logger.debug("Session set and connection marked as ready")

    @property
    def reconnect_info(self) -> dict[str, Any]:
        """
        Get reconnection progress information.

        Returns:
            Dictionary with reconnection info:
            - attempts: Current attempt number
            - max_attempts: Maximum reconnection attempts
            - next_retry_delay: Seconds until next retry (if reconnecting)
            - error_message: Error message if status is ERROR
        """
        info = {
            "attempts": self._reconnect_attempts,
            "max_attempts": self._reconnect_strategy.max_attempts,
            "next_retry_delay": None,
            "error_message": self._lifecycle.error_message,
        }

        # Calculate next retry delay if reconnecting
        if self._lifecycle.status == ConnectionStatus.RECONNECTING and self._reconnect_attempts > 0:
            # Only calculate delay if strategy supports it (ExponentialBackoffStrategy)
            if hasattr(self._reconnect_strategy, "calculate_delay"):
                delay = self._reconnect_strategy.calculate_delay(self._reconnect_attempts)
                info["next_retry_delay"] = delay

        return info

    async def connect(
        self,
        connect_fn: Callable[[asyncio.Event], Any],
    ) -> None:
        """
        Establish connection and maintain it with health monitoring and reconnection.

        Args:
            connect_fn: Async function that establishes connection.
                       Receives stop_event as parameter and should run until stop_event is set.
                       Should set self._session when connection is ready.

        Example:
            async def connect_fn(stop_event):
                async with streamablehttp_client(...) as (read, write, get_id):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self._session = session
                        self._lifecycle.mark_ready()
                        await stop_event.wait()
        """
        if self._connection_task and not self._connection_task.done():
            logger.warning("Connection already in progress")
            return

        logger.info("Starting connection")
        self._lifecycle.set_status(ConnectionStatus.CONNECTING)
        self._reconnect_attempts = 0

        # Initialize lifecycle events
        stop_event, _ = self._lifecycle.initialize()

        # Start connection maintenance in background
        self._connection_task = asyncio.create_task(
            self._maintain_connection(connect_fn, stop_event)
        )

        # Start health monitoring
        await self._health_checker.start(
            get_session=lambda: self._session,
            on_unhealthy=self._on_unhealthy,
            stop_event=stop_event,
        )

        # Wait for connection to be ready
        try:
            await self._lifecycle.wait_until_ready()
            logger.info("Connection ready")
        except Exception as e:
            logger.error(f"Failed to establish connection: {e}")
            self._lifecycle.set_status(ConnectionStatus.ERROR)
            await self._cleanup()
            raise

    async def disconnect(self) -> None:
        """Disconnect and clean up resources."""
        logger.info("Disconnecting")
        self._lifecycle.signal_stop()
        self._lifecycle.set_status(ConnectionStatus.DISCONNECTED)

        await self._cleanup()
        logger.info("Disconnected")

    async def retry_connection(self, connect_fn: Callable[[asyncio.Event], Any]) -> None:
        """
        Manually retry connection after ERROR status.

        Args:
            connect_fn: Async function that establishes connection
        """
        if not self._lifecycle.is_error:
            logger.warning(
                f"Cannot retry: status is {self._lifecycle.status.value}, not ERROR"
            )
            return

        logger.info("Manual retry requested")
        self._reconnect_attempts = 0
        self._lifecycle.reset_error()
        await self.connect(connect_fn)

    async def _maintain_connection(
        self,
        connect_fn: Callable[[asyncio.Event], Any],
        stop_event: asyncio.Event,
    ) -> None:
        """
        Background task that maintains connection with reconnection logic.

        Args:
            connect_fn: Async function that establishes and maintains connection
            stop_event: Event to signal stopping
        """
        while not stop_event.is_set():
            try:
                # Update status based on attempt count
                if self._reconnect_attempts == 0:
                    self._lifecycle.set_status(ConnectionStatus.CONNECTING)
                else:
                    self._lifecycle.set_status(ConnectionStatus.RECONNECTING)

                logger.info(
                    f"Connection attempt {self._reconnect_attempts + 1} "
                    f"(max={self._reconnect_strategy.max_attempts})"
                )

                # Execute connection function (passes stop_event)
                await connect_fn(stop_event)

                # If we get here, connection was lost (not an error)
                logger.warning("Connection lost")
                self._session = None
                self._reconnect_attempts += 1

                # Wait before reconnecting
                should_continue = await self._reconnect_strategy.wait_before_retry(
                    attempt=self._reconnect_attempts,
                    on_progress=self._on_reconnect_progress,
                    stop_event=stop_event,
                )

                if not should_continue:
                    logger.info("Stopping reconnection")
                    break

            except asyncio.CancelledError:
                logger.info("Connection task cancelled")
                self._lifecycle.set_status(ConnectionStatus.DISCONNECTED)
                raise

            except Exception as e:
                logger.error(f"Connection error: {e}")

                # Mark ready even on failure (non-blocking mode)
                self._lifecycle.mark_ready()

                if stop_event.is_set():
                    logger.info("Stop requested, not reconnecting")
                    self._lifecycle.set_status(ConnectionStatus.DISCONNECTED)
                    break

                self._reconnect_attempts += 1

                # Check if we should retry
                if not self._reconnect_strategy.should_retry(self._reconnect_attempts):
                    error_msg = (
                        f"Connection failed after {self._reconnect_strategy.max_attempts} attempts"
                    )
                    logger.error(error_msg)
                    self._lifecycle.set_status(ConnectionStatus.ERROR, error_msg)
                    break

                # Wait before retrying
                self._lifecycle.set_status(ConnectionStatus.RECONNECTING)
                should_continue = await self._reconnect_strategy.wait_before_retry(
                    attempt=self._reconnect_attempts,
                    on_progress=self._on_reconnect_progress,
                    stop_event=stop_event,
                )

                if not should_continue:
                    logger.info("Stopping reconnection")
                    break

            finally:
                # Clean up session if connection was lost
                if self._session:
                    logger.debug("Cleaning up session")
                    self._session = None

        logger.info("Connection maintenance task exiting")
        self._lifecycle.set_status(ConnectionStatus.DISCONNECTED)

    def _on_unhealthy(self) -> None:
        """Handle unhealthy connection detected by health checker."""
        logger.warning("Health check detected unhealthy connection")
        self._session = None
        if self._lifecycle.status == ConnectionStatus.CONNECTED:
            self._lifecycle.set_status(ConnectionStatus.RECONNECTING)

    async def _cleanup(self) -> None:
        """Clean up connection resources."""
        # Stop health checker
        await self._health_checker.stop()

        # Cancel connection task
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error during connection task cleanup: {e}")

        self._connection_task = None
        self._session = None
        self._lifecycle.cleanup()
