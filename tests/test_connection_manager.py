"""Tests for connection management components."""

import asyncio
import pytest
from nxs.mcp_client.connection import (
    ExponentialBackoffStrategy,
    HealthChecker,
    ConnectionLifecycle,
    ConnectionStatus,
    ConnectionManager,
)


class TestExponentialBackoffStrategy:
    """Tests for ExponentialBackoffStrategy."""

    def test_calculate_delay(self):
        """Test delay calculation with exponential backoff."""
        strategy = ExponentialBackoffStrategy(
            max_attempts=5,
            initial_delay=1.0,
            max_delay=10.0,
            backoff_multiplier=2.0,
        )

        # Test exponential growth
        assert strategy.calculate_delay(1) == 1.0
        assert strategy.calculate_delay(2) == 2.0
        assert strategy.calculate_delay(3) == 4.0
        assert strategy.calculate_delay(4) == 8.0

        # Test max delay cap
        assert strategy.calculate_delay(5) == 10.0
        assert strategy.calculate_delay(10) == 10.0

    def test_should_retry(self):
        """Test retry decision logic."""
        strategy = ExponentialBackoffStrategy(max_attempts=3)

        assert strategy.should_retry(1) is True
        assert strategy.should_retry(2) is True
        assert strategy.should_retry(3) is True
        assert strategy.should_retry(4) is False

    @pytest.mark.asyncio
    async def test_wait_before_retry(self):
        """Test wait with stop event."""
        strategy = ExponentialBackoffStrategy(
            max_attempts=3,
            initial_delay=0.1,  # Short delay for testing
        )
        stop_event = asyncio.Event()

        # Test normal wait
        start = asyncio.get_event_loop().time()
        result = await strategy.wait_before_retry(1, stop_event=stop_event)
        duration = asyncio.get_event_loop().time() - start

        assert result is True
        assert duration >= 0.1  # Should wait at least the delay

    @pytest.mark.asyncio
    async def test_wait_before_retry_stop_event(self):
        """Test wait respects stop event."""
        strategy = ExponentialBackoffStrategy(
            max_attempts=3,
            initial_delay=5.0,  # Long delay
        )
        stop_event = asyncio.Event()

        # Stop immediately
        stop_event.set()

        start = asyncio.get_event_loop().time()
        result = await strategy.wait_before_retry(1, stop_event=stop_event)
        duration = asyncio.get_event_loop().time() - start

        assert result is False
        assert duration < 1.0  # Should return quickly


class TestConnectionLifecycle:
    """Tests for ConnectionLifecycle."""

    def test_initial_state(self):
        """Test initial connection state."""
        lifecycle = ConnectionLifecycle()

        assert lifecycle.status == ConnectionStatus.DISCONNECTED
        assert not lifecycle.is_connected
        assert lifecycle.is_disconnected

    def test_status_change(self):
        """Test status change with callback."""
        statuses = []

        def on_status_change(status: ConnectionStatus):
            statuses.append(status)

        lifecycle = ConnectionLifecycle(on_status_change=on_status_change)

        lifecycle.set_status(ConnectionStatus.CONNECTING)
        assert lifecycle.status == ConnectionStatus.CONNECTING
        assert statuses == [ConnectionStatus.CONNECTING]

        lifecycle.set_status(ConnectionStatus.CONNECTED)
        assert lifecycle.status == ConnectionStatus.CONNECTED
        assert lifecycle.is_connected
        assert statuses == [ConnectionStatus.CONNECTING, ConnectionStatus.CONNECTED]

    def test_error_state(self):
        """Test error state with message."""
        lifecycle = ConnectionLifecycle()

        lifecycle.set_status(ConnectionStatus.ERROR, "Connection failed")

        assert lifecycle.is_error
        assert lifecycle.error_message == "Connection failed"

    @pytest.mark.asyncio
    async def test_ready_event(self):
        """Test ready event signaling."""
        lifecycle = ConnectionLifecycle()
        stop_event, ready_event = lifecycle.initialize()

        # Mark ready in background
        async def mark_ready():
            await asyncio.sleep(0.1)
            lifecycle.mark_ready()

        task = asyncio.create_task(mark_ready())

        # Wait for ready
        await lifecycle.wait_until_ready()
        assert ready_event.is_set()

        await task


class TestHealthChecker:
    """Tests for HealthChecker."""

    class MockSession:
        """Mock session for testing."""

        def __init__(self, should_fail=False):
            self.should_fail = should_fail
            self.check_count = 0

        async def list_tools(self):
            self.check_count += 1
            if self.should_fail:
                raise RuntimeError("Connection lost")
            return []

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        session = self.MockSession()
        checker = HealthChecker(check_interval=0.1, timeout=1.0)
        stop_event = asyncio.Event()
        unhealthy_called = []

        def on_unhealthy():
            unhealthy_called.append(True)

        await checker.start(
            get_session=lambda: session,
            on_unhealthy=on_unhealthy,
            stop_event=stop_event,
        )

        # Wait for a few checks
        await asyncio.sleep(0.3)

        # Stop checker
        await checker.stop()

        # Should have performed checks
        assert session.check_count > 0
        # Should not have called unhealthy callback
        assert len(unhealthy_called) == 0

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check detects failures."""
        session = self.MockSession(should_fail=True)
        checker = HealthChecker(check_interval=0.1, timeout=1.0)
        stop_event = asyncio.Event()
        unhealthy_called = []

        def on_unhealthy():
            unhealthy_called.append(True)

        await checker.start(
            get_session=lambda: session,
            on_unhealthy=on_unhealthy,
            stop_event=stop_event,
        )

        # Wait for a check
        await asyncio.sleep(0.2)

        # Stop checker
        await checker.stop()

        # Should have called unhealthy callback
        assert len(unhealthy_called) > 0


class TestConnectionManager:
    """Tests for ConnectionManager."""

    def test_initial_state(self):
        """Test initial connection manager state."""
        manager = ConnectionManager()

        assert manager.status == ConnectionStatus.DISCONNECTED
        assert not manager.is_connected
        assert manager.session is None

    def test_reconnect_info(self):
        """Test reconnect info structure."""
        manager = ConnectionManager()
        info = manager.reconnect_info

        assert "attempts" in info
        assert "max_attempts" in info
        assert "next_retry_delay" in info
        assert "error_message" in info

    @pytest.mark.asyncio
    async def test_set_session(self):
        """Test setting session."""
        manager = ConnectionManager()

        class MockSession:
            async def list_tools(self):
                return []

        session = MockSession()
        manager.set_session(session)

        assert manager.session == session
        assert manager.status == ConnectionStatus.CONNECTED
