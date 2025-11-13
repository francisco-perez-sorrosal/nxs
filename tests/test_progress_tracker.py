"""Tests for ResearchProgressTracker."""

from datetime import datetime

import pytest

from nxs.application.progress_tracker import (
    AccumulatedInsights,
    ExecutionAttempt,
    PlanStep,
    ResearchPlanSkeleton,
    ResearchProgressTracker,
    ToolExecution,
)
from nxs.application.reasoning.types import (
    ComplexityAnalysis,
    ComplexityLevel,
    EvaluationResult,
    ExecutionStrategy,
    ResearchPlan,
    SubTask,
)


@pytest.fixture
def sample_complexity():
    """Sample complexity analysis for testing."""
    return ComplexityAnalysis(
        complexity_level=ComplexityLevel.MEDIUM,
        reasoning_required=True,
        recommended_strategy=ExecutionStrategy.LIGHT_PLANNING,
        rationale="Test query requires planning",
        estimated_iterations=2,
        confidence=0.85,
    )


@pytest.fixture
def sample_plan():
    """Sample research plan for testing."""
    return ResearchPlan(
        original_query="Test query",
        subtasks=[
            SubTask(query="Step 1: Research", priority=1),
            SubTask(query="Step 2: Analyze", priority=2),
            SubTask(query="Step 3: Synthesize", priority=3),
        ],
        max_iterations=3,
        estimated_complexity="medium",
    )


@pytest.fixture
def tracker(sample_complexity):
    """Create a fresh tracker for testing."""
    return ResearchProgressTracker("Test query", sample_complexity)


class TestExecutionManagement:
    """Tests for execution attempt management."""

    def test_start_attempt(self, tracker):
        """Test starting a new execution attempt."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)

        assert tracker.current_strategy == ExecutionStrategy.DIRECT
        assert tracker.current_attempt is not None
        assert tracker.current_attempt.strategy == ExecutionStrategy.DIRECT
        assert tracker.current_attempt.status == "in_progress"
        assert tracker.current_attempt.started_at is not None
        assert len(tracker.attempts) == 1

    def test_multiple_attempts(self, tracker):
        """Test multiple execution attempts."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.end_attempt("Quality sufficient", "Response 1", None, 0.8)
        tracker.start_attempt(ExecutionStrategy.LIGHT_PLANNING)

        assert len(tracker.attempts) == 2
        assert tracker.attempts[0].strategy == ExecutionStrategy.DIRECT
        assert tracker.attempts[1].strategy == ExecutionStrategy.LIGHT_PLANNING
        assert tracker.current_attempt.strategy == ExecutionStrategy.LIGHT_PLANNING

    def test_end_attempt_success(self, tracker):
        """Test ending an attempt with success."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        evaluation = EvaluationResult(
            is_complete=True,
            confidence=0.85,
            reasoning="Good response",
            additional_queries=[],
            missing_aspects=[],
        )
        tracker.end_attempt("Quality sufficient", "Response text", evaluation, 0.85)

        assert tracker.current_attempt.status == "completed"
        assert tracker.current_attempt.response == "Response text"
        assert tracker.current_attempt.quality_score == 0.85
        assert tracker.current_attempt.completed_at is not None
        assert tracker.current_attempt.evaluation == evaluation

    def test_end_attempt_escalation(self, tracker):
        """Test ending an attempt with escalation."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        evaluation = EvaluationResult(
            is_complete=False,
            confidence=0.4,
            reasoning="Insufficient quality",
            additional_queries=["Need more research"],
            missing_aspects=["Missing context"],
        )
        tracker.end_attempt("Escalated due to low quality", "Response text", evaluation, 0.4)

        assert tracker.current_attempt.status == "escalated"
        assert tracker.current_attempt.quality_score == 0.4
        # Check that insights were extracted
        assert "Missing context" in tracker.insights.knowledge_gaps
        assert "Insufficient quality" in tracker.insights.quality_feedback

    def test_end_attempt_without_current(self, tracker):
        """Test ending attempt when no current attempt exists."""
        # Should not raise, just log warning
        tracker.end_attempt("Test", "Response", None, 0.5)
        assert len(tracker.attempts) == 0


class TestToolTracking:
    """Tests for tool execution tracking."""

    def test_log_tool_execution_success(self, tracker):
        """Test logging a successful tool execution."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.log_tool_execution(
            "web_search",
            {"query": "test"},
            success=True,
            result="Search results",
            execution_time_ms=150.5,
        )

        assert len(tracker.tool_executions) == 1
        exec_record = tracker.tool_executions[0]
        assert exec_record.tool_name == "web_search"
        assert exec_record.success is True
        assert exec_record.result == "Search results"
        assert exec_record.execution_time_ms == 150.5
        assert exec_record.result_hash != ""

        # Check cache
        assert exec_record.result_hash in tracker._tool_result_cache
        assert tracker._tool_result_cache[exec_record.result_hash] == "Search results"

    def test_log_tool_execution_failure(self, tracker):
        """Test logging a failed tool execution."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.log_tool_execution(
            "web_search",
            {"query": "test"},
            success=False,
            error="Timeout error",
            execution_time_ms=5000.0,
        )

        assert len(tracker.tool_executions) == 1
        exec_record = tracker.tool_executions[0]
        assert exec_record.success is False
        assert exec_record.error == "Timeout error"
        assert "web_search" in tracker.insights.failed_tool_attempts

    def test_should_execute_tool_cache_hit(self, tracker):
        """Test tool caching - should not execute if cached."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.log_tool_execution(
            "web_search",
            {"query": "test"},
            success=True,
            result="Cached result",
        )

        should_execute, cached_result = tracker.should_execute_tool("web_search", {"query": "test"})

        assert should_execute is False
        assert cached_result == "Cached result"

    def test_should_execute_tool_cache_miss(self, tracker):
        """Test tool caching - should execute if not cached."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)

        should_execute, cached_result = tracker.should_execute_tool("web_search", {"query": "new"})

        assert should_execute is True
        assert cached_result is None

    def test_should_execute_tool_different_args(self, tracker):
        """Test that different arguments are not cached together."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.log_tool_execution(
            "web_search",
            {"query": "test1"},
            success=True,
            result="Result 1",
        )

        should_execute, cached_result = tracker.should_execute_tool("web_search", {"query": "test2"})

        assert should_execute is True  # Different args, should execute
        assert cached_result is None

    def test_tool_hash_deterministic(self, tracker):
        """Test that tool argument hashing is deterministic."""
        hash1 = tracker._hash_arguments("tool", {"a": 1, "b": 2})
        hash2 = tracker._hash_arguments("tool", {"b": 2, "a": 1})  # Different order

        assert hash1 == hash2  # Should be same regardless of dict order


class TestPlanManagement:
    """Tests for research plan management."""

    def test_set_plan_initial(self, tracker, sample_plan):
        """Test setting initial plan."""
        tracker.set_plan(sample_plan, ExecutionStrategy.LIGHT_PLANNING)

        assert tracker.plan is not None
        assert tracker.plan.created_by == ExecutionStrategy.LIGHT_PLANNING
        assert len(tracker.plan.steps) == 3
        assert tracker.plan.steps[0].description == "Step 1: Research"
        assert tracker.plan.steps[0].status == "pending"

    def test_set_plan_refinement(self, tracker, sample_plan):
        """Test refining an existing plan."""
        tracker.set_plan(sample_plan, ExecutionStrategy.LIGHT_PLANNING)
        initial_revision = tracker.plan.revision_count

        # Create new plan with additional step
        new_plan = ResearchPlan(
            original_query="Test query",
            subtasks=[
                SubTask(query="Step 1: Research", priority=1),
                SubTask(query="Step 2: Analyze", priority=2),
                SubTask(query="Step 3: Synthesize", priority=3),
                SubTask(query="Step 4: New step", priority=4),
            ],
        )
        tracker.set_plan(new_plan, ExecutionStrategy.DEEP_REASONING)

        assert tracker.plan.revision_count == initial_revision + 1
        assert len(tracker.plan.steps) == 4  # Should have new step

    def test_update_step_status(self, tracker, sample_plan):
        """Test updating step status."""
        tracker.set_plan(sample_plan, ExecutionStrategy.LIGHT_PLANNING)
        step_id = tracker.plan.steps[0].id

        tracker.update_step_status(step_id, "in_progress")
        assert tracker.plan.steps[0].status == "in_progress"
        assert tracker.plan.steps[0].started_at is not None
        assert tracker.plan.current_step_id == step_id

        tracker.update_step_status(step_id, "completed", findings=["Finding 1", "Finding 2"])
        assert tracker.plan.steps[0].status == "completed"
        assert tracker.plan.steps[0].completed_at is not None
        assert len(tracker.plan.steps[0].findings) == 2

    def test_plan_get_completed_steps(self, tracker, sample_plan):
        """Test getting completed steps from plan."""
        tracker.set_plan(sample_plan, ExecutionStrategy.LIGHT_PLANNING)

        # Complete first step
        tracker.update_step_status(tracker.plan.steps[0].id, "completed")

        completed = tracker.plan.get_completed_steps()
        assert len(completed) == 1
        assert completed[0].id == tracker.plan.steps[0].id

    def test_plan_get_pending_steps(self, tracker, sample_plan):
        """Test getting pending steps from plan."""
        tracker.set_plan(sample_plan, ExecutionStrategy.LIGHT_PLANNING)

        # Complete first step
        tracker.update_step_status(tracker.plan.steps[0].id, "completed")

        pending = tracker.plan.get_pending_steps()
        assert len(pending) == 2  # Two remaining steps

    def test_plan_add_dynamic_step(self, tracker, sample_plan):
        """Test adding dynamic step during execution."""
        tracker.set_plan(sample_plan, ExecutionStrategy.LIGHT_PLANNING)
        initial_count = len(tracker.plan.steps)

        new_step = PlanStep(
            id="step_dynamic_1",
            description="Dynamic step",
            status="pending",
        )
        tracker.plan.add_dynamic_step(new_step, tracker.plan.steps[0].id)

        assert len(tracker.plan.steps) == initial_count + 1
        assert tracker.plan.steps[1].id == "step_dynamic_1"


class TestSerialization:
    """Tests for serialization methods."""

    def test_to_context_text_minimal(self, tracker):
        """Test context text with minimal data."""
        context = tracker.to_context_text(ExecutionStrategy.DIRECT)

        assert "Test query" in context
        assert "MEDIUM" in context
        assert "DIRECT" in context

    def test_to_context_text_with_attempts(self, tracker):
        """Test context text with execution attempts."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        evaluation = EvaluationResult(
            is_complete=False,
            confidence=0.4,
            reasoning="Needs more depth",
            missing_aspects=["Context A", "Context B"],
        )
        tracker.end_attempt("Escalated", "Response", evaluation, 0.4)
        tracker.start_attempt(ExecutionStrategy.LIGHT_PLANNING)

        context = tracker.to_context_text(ExecutionStrategy.LIGHT_PLANNING)

        assert "Previous Execution Attempts" in context
        assert "DIRECT" in context
        assert "Needs more depth" in context
        assert "Context A" in context

    def test_to_context_text_with_plan(self, tracker, sample_plan):
        """Test context text with research plan."""
        tracker.set_plan(sample_plan, ExecutionStrategy.LIGHT_PLANNING)
        tracker.update_step_status(tracker.plan.steps[0].id, "completed", findings=["Finding 1"])

        context = tracker.to_context_text(ExecutionStrategy.LIGHT_PLANNING)

        assert "Research Plan Progress" in context
        assert "1/3 steps completed" in context
        assert "Completed Steps" in context
        assert "Pending Steps" in context
        assert "Step 1: Research" in context

    def test_to_context_text_with_tools(self, tracker):
        """Test context text with tool executions."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.log_tool_execution("web_search", {"query": "test"}, success=True, result="Results")
        tracker.log_tool_execution("calculator", {"op": "add"}, success=False, error="Error")

        context = tracker.to_context_text(ExecutionStrategy.DIRECT)

        assert "Tool Execution History" in context
        assert "web_search" in context
        assert "calculator" in context
        assert "Successful Tool Executions" in context
        assert "Failed Tool Executions" in context

    def test_to_compact_context(self, tracker, sample_plan):
        """Test compact context serialization."""
        tracker.set_plan(sample_plan, ExecutionStrategy.LIGHT_PLANNING)
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.log_tool_execution("web_search", {"query": "test"}, success=True, result="Results")
        tracker.insights.knowledge_gaps = ["Gap 1", "Gap 2", "Gap 3"]

        compact = tracker.to_compact_context()

        assert "Progress:" in compact
        assert "tool calls" in compact
        assert "steps done" in compact
        assert "Gap 1" in compact
        assert len(compact) < 500  # Should be compact

    def test_to_dict(self, tracker, sample_plan):
        """Test dictionary serialization."""
        tracker.set_plan(sample_plan, ExecutionStrategy.LIGHT_PLANNING)
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.log_tool_execution("web_search", {"query": "test"}, success=True, result="Results")

        data = tracker.to_dict()

        assert data["query"] == "Test query"
        assert "complexity" in data
        assert "attempts" in data
        assert "tool_executions" in data
        assert "plan" in data
        assert "insights" in data
        assert len(data["attempts"]) == 1
        assert len(data["tool_executions"]) == 1

    def test_from_dict(self, tracker, sample_plan):
        """Test dictionary deserialization."""
        tracker.set_plan(sample_plan, ExecutionStrategy.LIGHT_PLANNING)
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.log_tool_execution("web_search", {"query": "test"}, success=True, result="Results")
        tracker.end_attempt("Done", "Response", None, 0.8)

        data = tracker.to_dict()
        restored = ResearchProgressTracker.from_dict(data)

        assert restored.query == tracker.query
        assert restored.complexity.complexity_level == tracker.complexity.complexity_level
        assert len(restored.attempts) == 1
        assert len(restored.tool_executions) == 1
        assert restored.plan is not None
        assert len(restored.plan.steps) == 3

    def test_from_dict_round_trip(self, tracker):
        """Test round-trip serialization preserves data."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        evaluation = EvaluationResult(
            is_complete=True,
            confidence=0.85,
            reasoning="Good",
            missing_aspects=[],
        )
        tracker.end_attempt("Success", "Response", evaluation, 0.85)
        tracker.log_tool_execution("tool1", {"arg": 1}, success=True, result="Result")

        data = tracker.to_dict()
        restored = ResearchProgressTracker.from_dict(data)

        assert restored.attempts[0].strategy == ExecutionStrategy.DIRECT
        assert restored.attempts[0].quality_score == 0.85
        assert restored.tool_executions[0].tool_name == "tool1"
        # Check cache was restored
        assert len(restored._tool_result_cache) == 1


class TestAccumulatedInsights:
    """Tests for accumulated insights."""

    def test_add_from_evaluation(self):
        """Test extracting insights from evaluation."""
        insights = AccumulatedInsights()
        evaluation = EvaluationResult(
            is_complete=False,
            confidence=0.5,
            reasoning="Missing information",
            missing_aspects=["Gap 1", "Gap 2"],
            additional_queries=["Query 1", "Query 2"],
        )

        insights.add_from_evaluation(evaluation)

        assert "Gap 1" in insights.knowledge_gaps
        assert "Gap 2" in insights.knowledge_gaps
        assert "Missing information" in insights.quality_feedback
        assert "Query 1" in insights.recommended_improvements
        assert "Query 2" in insights.recommended_improvements


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_tracker_context(self, tracker):
        """Test context generation with empty tracker."""
        context = tracker.to_context_text(ExecutionStrategy.DIRECT)
        assert len(context) > 0
        assert "Test query" in context

    def test_tracker_no_plan(self, tracker):
        """Test tracker operations without a plan."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.update_step_status("nonexistent", "completed")  # Should not crash

        assert tracker.plan is None

    def test_tracker_no_tools(self, tracker):
        """Test tracker with no tool executions."""
        context = tracker.to_context_text(ExecutionStrategy.DIRECT)
        assert "Tool Execution History" not in context or "0" in context

    def test_multiple_tool_calls_same_tool(self, tracker):
        """Test multiple calls to same tool with different results."""
        tracker.start_attempt(ExecutionStrategy.DIRECT)
        tracker.log_tool_execution("web_search", {"query": "test1"}, success=True, result="Result 1")
        tracker.log_tool_execution("web_search", {"query": "test2"}, success=True, result="Result 2")

        assert len(tracker.tool_executions) == 2
        assert len(tracker._tool_result_cache) == 2  # Different args, different cache entries

    def test_tool_execution_without_current_attempt(self, tracker):
        """Test logging tool execution without current attempt."""
        # Should not crash, but may not update current_attempt
        tracker.log_tool_execution("web_search", {"query": "test"}, success=True, result="Result")

        assert len(tracker.tool_executions) == 1
        assert tracker.tool_executions[0].strategy == ExecutionStrategy.DIRECT  # Default

