"""Tests for Planner."""

import pytest

from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.planner import Planner


@pytest.mark.asyncio
async def test_planner_simple_query(mock_claude):
    """Test planner with simple single-step query."""
    llm = mock_claude(
        responses=[
            """1. [HIGH PRIORITY] Search for Python definition
   Tools: search

Strategy: Direct search for information."""
        ]
    )
    planner = Planner(llm, ReasoningConfig())

    plan = await planner.generate_plan("What is Python?")

    assert len(plan.subtasks) >= 1
    assert plan.subtasks[0].priority == 1
    assert plan.estimated_complexity in ["low", "medium"]
    assert plan.original_query == "What is Python?"


@pytest.mark.asyncio
async def test_planner_complex_query(mock_claude, mock_planning_response):
    """Test planner with complex multi-step query."""
    llm = mock_claude(responses=[mock_planning_response])
    planner = Planner(llm, ReasoningConfig())

    plan = await planner.generate_plan(
        "Research quantum computing landscape and provide recommendations"
    )

    assert len(plan.subtasks) >= 2
    assert plan.estimated_complexity in ["medium", "high"]
    # Verify priorities are assigned
    assert all(task.priority for task in plan.subtasks)
    # Verify subtasks are sorted by priority
    priorities = [task.priority for task in plan.subtasks]
    assert priorities == sorted(priorities)


@pytest.mark.asyncio
async def test_planner_with_tools(mock_claude, mock_planning_response):
    """Test planner parses tool hints correctly."""
    llm = mock_claude(responses=[mock_planning_response])
    planner = Planner(llm, ReasoningConfig())

    plan = await planner.generate_plan("Test query")

    # Check that some subtasks have tool hints
    has_tools = any(task.tool_hints for task in plan.subtasks)
    assert has_tools


@pytest.mark.asyncio
async def test_planner_light_mode(mock_claude, mock_planning_response):
    """Test planner limits subtasks in light mode."""
    llm = mock_claude(responses=[mock_planning_response])
    config = ReasoningConfig(max_subtasks=5)
    planner = Planner(llm, config)

    plan = await planner.generate_plan("Complex query", context={"mode": "light"})

    # Light mode should limit to 2 subtasks
    assert len(plan.subtasks) <= 2


@pytest.mark.asyncio
async def test_planner_deep_mode(mock_claude, mock_planning_response):
    """Test planner allows more subtasks in deep mode."""
    llm = mock_claude(responses=[mock_planning_response])
    config = ReasoningConfig(max_subtasks=5)
    planner = Planner(llm, config)

    plan = await planner.generate_plan("Complex query", context={"mode": "deep"})

    # Deep mode can have up to max_subtasks
    assert len(plan.subtasks) <= 5


@pytest.mark.asyncio
async def test_planner_error_handling(mock_claude):
    """Test planner handles LLM errors gracefully."""

    async def failing_create_message(*args, **kwargs):
        raise Exception("API Error")

    llm = mock_claude()
    llm.create_message = failing_create_message

    planner = Planner(llm, ReasoningConfig())

    # Should not raise, but return fallback plan
    plan = await planner.generate_plan("Any query")

    assert plan is not None
    assert len(plan.subtasks) == 1  # Fallback: single subtask with original query
    assert plan.subtasks[0].query == "Any query"
    assert plan.estimated_complexity == "low"


@pytest.mark.asyncio
async def test_planner_parses_simple_format(mock_claude):
    """Test planner can parse simple numbered list."""
    llm = mock_claude(
        responses=[
            """Here's the plan:

1. Research the basics
2. Gather examples
3. Synthesize findings

That's the strategy."""
        ]
    )
    planner = Planner(llm, ReasoningConfig())

    plan = await planner.generate_plan("Test")

    assert len(plan.subtasks) >= 2
    assert "basics" in plan.subtasks[0].query.lower()


@pytest.mark.asyncio
async def test_planner_respects_max_subtasks(mock_claude):
    """Test planner respects max_subtasks configuration."""
    # Response with many subtasks
    response = "\n".join([f"{i}. [HIGH PRIORITY] Task {i}\n   Tools: none" for i in range(1, 11)])
    llm = mock_claude(responses=[response])

    config = ReasoningConfig(max_subtasks=3)
    planner = Planner(llm, config)

    plan = await planner.generate_plan("Test", context={"mode": "deep"})

    # Should be limited to 3
    assert len(plan.subtasks) <= 3


@pytest.mark.asyncio
async def test_planner_complexity_estimation(mock_claude):
    """Test planner estimates complexity based on subtask count."""
    llm_low = mock_claude(responses=["1. [HIGH PRIORITY] Single task"])
    planner = Planner(llm_low, ReasoningConfig())

    plan_low = await planner.generate_plan("Simple")
    assert plan_low.estimated_complexity == "low"

    llm_medium = mock_claude(
        responses=[
            """1. [HIGH PRIORITY] Task 1
2. [MEDIUM PRIORITY] Task 2
3. [LOW PRIORITY] Task 3"""
        ]
    )
    planner = Planner(llm_medium, ReasoningConfig())

    plan_medium = await planner.generate_plan("Medium")
    assert plan_medium.estimated_complexity == "medium"

    llm_high = mock_claude(
        responses=["\n".join([f"{i}. [HIGH PRIORITY] Task {i}" for i in range(1, 6)])]
    )
    planner = Planner(llm_high, ReasoningConfig())

    plan_high = await planner.generate_plan("Complex")
    assert plan_high.estimated_complexity == "high"

