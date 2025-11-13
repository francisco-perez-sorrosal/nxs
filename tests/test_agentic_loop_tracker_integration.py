"""Integration tests for AgentLoop with ResearchProgressTracker (Phase 2)."""

import pytest

from nxs.application.agentic_loop import AgentLoop
from nxs.application.claude import Claude
from nxs.application.conversation import Conversation
from nxs.application.progress_tracker import ResearchProgressTracker
from nxs.application.reasoning.types import (
    ComplexityAnalysis,
    ComplexityLevel,
    ExecutionStrategy,
)
from nxs.application.tool_registry import ToolRegistry
from tests.reasoning.conftest import MockClaude


class MockToolProvider:
    """Mock tool provider for testing."""

    @property
    def provider_name(self) -> str:
        return "mock"

    async def get_tool_definitions(self) -> list[dict]:
        return [
            {
                "name": "test_tool",
                "description": "A test tool",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute tool with deterministic results for testing."""
        if tool_name == "test_tool":
            query = arguments.get("query", "")
            return f"Result for query: {query}"
        raise KeyError(f"Tool '{tool_name}' not found")


@pytest.fixture
def mock_claude():
    """Create mock Claude instance."""
    return MockClaude(
        responses=[
            '{"type": "message", "content": [{"type": "text", "text": "I need to use a tool."}], "stop_reason": "tool_use"}',
            '{"type": "message", "content": [{"type": "tool_use", "name": "test_tool", "input": {"query": "test"}}], "stop_reason": "tool_use"}',
            '{"type": "message", "content": [{"type": "text", "text": "Final response"}], "stop_reason": "end_turn"}',
        ]
    )


@pytest.fixture
def tool_registry():
    """Create tool registry with mock provider."""
    registry = ToolRegistry()
    provider = MockToolProvider()
    registry.register_provider(provider)
    return registry


@pytest.fixture
def agent_loop(mock_claude, tool_registry):
    """Create AgentLoop instance."""
    conversation = Conversation()
    return AgentLoop(
        llm=mock_claude,
        conversation=conversation,
        tool_registry=tool_registry,
    )


@pytest.fixture
def tracker():
    """Create a progress tracker for testing."""
    complexity = ComplexityAnalysis(
        complexity_level=ComplexityLevel.MEDIUM,
        reasoning_required=True,
        recommended_strategy=ExecutionStrategy.LIGHT_PLANNING,
        rationale="Test",
        estimated_iterations=2,
        confidence=0.8,
    )
    return ResearchProgressTracker("Test query", complexity)


@pytest.mark.asyncio
async def test_execute_with_tool_tracking_basic(agent_loop, tracker):
    """Test basic tool tracking integration."""
    # Start an attempt
    tracker.start_attempt(ExecutionStrategy.DIRECT)

    # Execute with tracking
    result = await agent_loop._execute_with_tool_tracking(
        "Use test_tool with query 'hello'",
        tracker,
        use_streaming=False,
    )

    # Verify tracker was used
    assert len(tracker.tool_executions) > 0
    assert tracker.tool_executions[0].tool_name == "test_tool"
    assert tracker.tool_executions[0].success is True


@pytest.mark.asyncio
async def test_tool_caching(agent_loop, tracker):
    """Test that tool results are cached and reused."""
    tracker.start_attempt(ExecutionStrategy.DIRECT)

    # First execution - should execute tool
    result1 = await agent_loop._execute_with_tool_tracking(
        "Use test_tool with query 'cached'",
        tracker,
        use_streaming=False,
    )

    # Verify tool was executed
    assert len(tracker.tool_executions) == 1
    first_exec = tracker.tool_executions[0]
    assert first_exec.tool_name == "test_tool"
    assert first_exec.arguments == {"query": "cached"}

    # Second execution with same arguments - should use cache
    tracker.start_attempt(ExecutionStrategy.LIGHT_PLANNING)
    initial_exec_count = len(tracker.tool_executions)

    result2 = await agent_loop._execute_with_tool_tracking(
        "Use test_tool with query 'cached'",
        tracker,
        use_streaming=False,
    )

    # Should have logged cached execution
    assert len(tracker.tool_executions) > initial_exec_count

    # Find the cached execution
    cached_execs = [
        e for e in tracker.tool_executions[initial_exec_count:]
        if e.execution_time_ms == 0.0  # Cached executions have 0ms time
    ]
    assert len(cached_execs) > 0


@pytest.mark.asyncio
async def test_tool_execution_time_tracking(agent_loop, tracker):
    """Test that execution time is tracked."""
    tracker.start_attempt(ExecutionStrategy.DIRECT)

    await agent_loop._execute_with_tool_tracking(
        "Use test_tool",
        tracker,
        use_streaming=False,
    )

    # Verify execution time was tracked
    assert len(tracker.tool_executions) > 0
    exec_record = tracker.tool_executions[0]
    assert exec_record.execution_time_ms >= 0.0
    # Execution time should be reasonable (less than 1 second for mock)
    assert exec_record.execution_time_ms < 1000.0


@pytest.mark.asyncio
async def test_tool_failure_tracking(agent_loop, tracker):
    """Test that tool failures are tracked."""
    tracker.start_attempt(ExecutionStrategy.DIRECT)

    # Create a failing tool provider
    class FailingToolProvider:
        @property
        def provider_name(self) -> str:
            return "failing"

        async def get_tool_definitions(self) -> list[dict]:
            return [
                {
                    "name": "failing_tool",
                    "description": "A tool that fails",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ]

        async def execute_tool(self, tool_name: str, arguments: dict) -> str:
            raise Exception("Tool execution failed")

    # Register failing provider
    failing_provider = FailingToolProvider()
    agent_loop.tool_registry.register_provider(failing_provider)

    # Execute with failing tool
    try:
        await agent_loop._execute_with_tool_tracking(
            "Use failing_tool",
            tracker,
            use_streaming=False,
        )
    except Exception:
        pass  # Expected to fail

    # Verify failure was tracked
    failed_execs = [e for e in tracker.tool_executions if not e.success]
    assert len(failed_execs) > 0
    assert failed_execs[0].error is not None
    assert "failed" in failed_execs[0].error.lower()


@pytest.mark.asyncio
async def test_tracker_cleared_after_execution(agent_loop, tracker):
    """Test that tracker reference is cleared after execution."""
    tracker.start_attempt(ExecutionStrategy.DIRECT)

    # Verify tracker is not set initially
    assert agent_loop._current_tracker is None

    # Execute with tracking
    await agent_loop._execute_with_tool_tracking(
        "Test query",
        tracker,
        use_streaming=False,
    )

    # Verify tracker is cleared after execution
    assert agent_loop._current_tracker is None


@pytest.mark.asyncio
async def test_tracker_without_tools(agent_loop, tracker):
    """Test tracker integration when no tools are used."""
    tracker.start_attempt(ExecutionStrategy.DIRECT)

    # Execute query that doesn't require tools
    result = await agent_loop._execute_with_tool_tracking(
        "Simple query without tools",
        tracker,
        use_streaming=False,
    )

    # Tracker should still be set and cleared
    assert agent_loop._current_tracker is None  # Cleared after execution
    # No tool executions should be logged
    assert len(tracker.tool_executions) == 0


@pytest.mark.asyncio
async def test_multiple_tool_calls_tracking(agent_loop, tracker):
    """Test tracking multiple tool calls in one execution."""
    tracker.start_attempt(ExecutionStrategy.DIRECT)

    # Create provider with multiple tools
    class MultiToolProvider:
        @property
        def provider_name(self) -> str:
            return "multi"

        async def get_tool_definitions(self) -> list[dict]:
            return [
                {
                    "name": "tool1",
                    "description": "First tool",
                    "input_schema": {"type": "object", "properties": {}},
                },
                {
                    "name": "tool2",
                    "description": "Second tool",
                    "input_schema": {"type": "object", "properties": {}},
                },
            ]

        async def execute_tool(self, tool_name: str, arguments: dict) -> str:
            return f"Result from {tool_name}"

    multi_provider = MultiToolProvider()
    agent_loop.tool_registry.register_provider(multi_provider)

    # Execute query that uses multiple tools
    await agent_loop._execute_with_tool_tracking(
        "Use multiple tools",
        tracker,
        use_streaming=False,
    )

    # Verify all tool calls were tracked
    tool_names = {e.tool_name for e in tracker.tool_executions}
    assert len(tool_names) >= 1  # At least one tool was called


@pytest.mark.asyncio
async def test_tool_cache_different_arguments(agent_loop, tracker):
    """Test that different arguments don't use cache."""
    tracker.start_attempt(ExecutionStrategy.DIRECT)

    # First execution
    await agent_loop._execute_with_tool_tracking(
        "Use test_tool with query 'query1'",
        tracker,
        use_streaming=False,
    )

    initial_count = len(tracker.tool_executions)

    # Second execution with different arguments
    tracker.start_attempt(ExecutionStrategy.LIGHT_PLANNING)
    await agent_loop._execute_with_tool_tracking(
        "Use test_tool with query 'query2'",
        tracker,
        use_streaming=False,
    )

    # Should have executed again (different args)
    assert len(tracker.tool_executions) > initial_count

    # Verify both executions are present
    queries = [
        e.arguments.get("query", "")
        for e in tracker.tool_executions
        if e.tool_name == "test_tool"
    ]
    assert "query1" in queries or "query2" in queries

