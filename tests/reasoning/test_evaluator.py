"""Tests for Evaluator."""

import pytest

from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.evaluator import Evaluator
from nxs.application.reasoning.types import ResearchPlan, SubTask


@pytest.mark.asyncio
async def test_evaluator_research_incomplete(
    mock_claude, mock_evaluation_response_incomplete
):
    """Test research evaluation when results are incomplete."""
    llm = mock_claude(responses=[mock_evaluation_response_incomplete])
    evaluator = Evaluator(llm, ReasoningConfig())

    results = [
        {"query": "What is X?", "result": "X is a thing"},
    ]
    plan = ResearchPlan(
        original_query="Comprehensive analysis of X",
        subtasks=[SubTask(query="More research needed", priority=1)],
    )

    result = await evaluator.evaluate("Comprehensive analysis of X", results, plan)

    assert result.is_complete is False
    assert result.confidence < 0.8
    assert len(result.missing_aspects) > 0
    assert len(result.additional_queries) > 0


@pytest.mark.asyncio
async def test_evaluator_research_complete(mock_claude, mock_evaluation_response_complete):
    """Test research evaluation when results are complete."""
    llm = mock_claude(responses=[mock_evaluation_response_complete])
    evaluator = Evaluator(llm, ReasoningConfig())

    results = [
        {"query": "What is X?", "result": "Comprehensive answer about X"},
        {"query": "Historical context", "result": "Historical details"},
        {"query": "Current trends", "result": "Trend analysis"},
    ]
    plan = ResearchPlan(
        original_query="Comprehensive analysis of X",
        subtasks=[],  # No remaining subtasks
    )

    result = await evaluator.evaluate("Comprehensive analysis of X", results, plan)

    assert result.is_complete is True
    assert result.confidence >= 0.9
    assert len(result.additional_queries) == 0


@pytest.mark.asyncio
async def test_evaluator_response_quality_sufficient(mock_claude):
    """Test that high-quality responses pass evaluation."""
    llm = mock_claude(
        responses=[
            """**Quality Assessment:** SUFFICIENT

**Confidence Score:** 0.85

**Reasoning:**
The response comprehensively answers the query with appropriate depth and accuracy.

**Missing Aspects:**
None

**Key Questions:**
All questions adequately addressed."""
        ]
    )
    evaluator = Evaluator(llm, ReasoningConfig())

    result = await evaluator.evaluate_response_quality(
        query="What is quantum computing?",
        response="Quantum computing is a type of computation that harnesses quantum phenomena...",
        strategy_used="DIRECT",
        expected_complexity=None,
    )

    assert result.is_complete is True
    assert result.confidence >= 0.8
    assert len(result.missing_aspects) == 0


@pytest.mark.asyncio
async def test_evaluator_response_quality_insufficient(mock_claude):
    """Test that low-quality responses trigger escalation."""
    llm = mock_claude(
        responses=[
            """**Quality Assessment:** INSUFFICIENT

**Confidence Score:** 0.35

**Reasoning:**
The response is too superficial and lacks key technical concepts.

**Missing Aspects:**
- Lacks technical depth
- Missing key concepts
- No examples provided

**Escalation Recommendation:**
Recommend LIGHT_PLANNING for more thorough response."""
        ]
    )
    evaluator = Evaluator(llm, ReasoningConfig())

    result = await evaluator.evaluate_response_quality(
        query="Explain quantum computing in detail",
        response="It's a type of computer.",
        strategy_used="DIRECT",
        expected_complexity=None,
    )

    assert result.is_complete is False
    assert result.confidence < 0.5
    assert len(result.missing_aspects) > 0


@pytest.mark.asyncio
async def test_evaluator_handles_empty_results(mock_claude):
    """Test evaluator handles empty results gracefully."""
    llm = mock_claude(responses=["## Completeness Assessment\nNo results\n\n## Confidence Score\n0.0"])
    evaluator = Evaluator(llm, ReasoningConfig())

    plan = ResearchPlan(original_query="Test", subtasks=[])
    result = await evaluator.evaluate("Test query", [], plan)

    assert result is not None
    assert result.is_complete is False or result.confidence <= 0.5


@pytest.mark.asyncio
async def test_evaluator_error_handling_research(mock_claude):
    """Test evaluator handles errors in research evaluation."""

    async def failing_create_message(*args, **kwargs):
        raise Exception("API Error")

    llm = mock_claude()
    llm.create_message = failing_create_message

    evaluator = Evaluator(llm, ReasoningConfig())
    plan = ResearchPlan(original_query="Test", subtasks=[])

    # Should not raise
    result = await evaluator.evaluate("Test", [], plan)

    assert result is not None
    assert result.confidence <= 0.5  # Fallback behavior


@pytest.mark.asyncio
async def test_evaluator_error_handling_quality(mock_claude):
    """Test evaluator handles errors in quality evaluation."""

    async def failing_create_message(*args, **kwargs):
        raise Exception("API Error")

    llm = mock_claude()
    llm.create_message = failing_create_message

    evaluator = Evaluator(llm, ReasoningConfig())

    # Should not raise - fallback to accepting response
    result = await evaluator.evaluate_response_quality(
        query="Test",
        response="Response",
        strategy_used="DIRECT",
        expected_complexity=None,
    )

    assert result is not None
    assert result.is_complete is True  # Fallback accepts to avoid loops


@pytest.mark.asyncio
async def test_evaluator_formats_results_correctly(mock_claude, mock_evaluation_response_complete):
    """Test that evaluator formats results for prompt correctly."""
    llm = mock_claude(responses=[mock_evaluation_response_complete])
    evaluator = Evaluator(llm, ReasoningConfig())

    results = [
        {"query": "Q1", "result": "A" * 1000},  # Long result
        {"query": "Q2", "result": "Short"},
    ]
    plan = ResearchPlan(original_query="Test", subtasks=[])

    await evaluator.evaluate("Test", results, plan)

    # Verify results were formatted and truncated
    assert llm.call_count == 1
    prompt = llm.calls[0]["query"]
    assert "Q1" in prompt
    assert "Q2" in prompt

