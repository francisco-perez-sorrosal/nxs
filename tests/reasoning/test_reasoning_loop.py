"""Tests for AdaptiveReasoningLoop."""

import pytest

from nxs.application.conversation import Conversation
from nxs.application.reasoning.analyzer import QueryComplexityAnalyzer
from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.evaluator import Evaluator
from nxs.application.reasoning.planner import Planner
from nxs.application.reasoning.synthesizer import Synthesizer
from nxs.application.reasoning.types import ExecutionStrategy
from nxs.application.reasoning_loop import AdaptiveReasoningLoop
from nxs.application.tool_registry import ToolRegistry


@pytest.mark.asyncio
async def test_direct_execution_no_escalation(
    mock_claude, mock_complexity_response, mock_quality_response
):
    """Test simple query that completes with DIRECT strategy."""
    # Setup
    llm = mock_claude(response_generator=lambda q: "Direct response: 4")
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()

    # Create reasoning components with mocked responses
    analyzer_llm = mock_claude(response_generator=mock_complexity_response)
    analyzer = QueryComplexityAnalyzer(analyzer_llm, config)

    planner = Planner(llm, config)

    evaluator_llm = mock_claude(response_generator=mock_quality_response)
    evaluator = Evaluator(evaluator_llm, config)

    synthesizer = Synthesizer(llm, config)

    # Track callbacks
    callback_log = []

    callbacks = {
        "on_analysis_start": lambda: callback_log.append("analysis_start"),
        "on_analysis_complete": lambda c: callback_log.append(f"analysis:{c.complexity_level.value}"),
        "on_strategy_selected": lambda s, r: callback_log.append(f"strategy:{s.value}"),
        "on_quality_check_start": lambda: callback_log.append("quality_check_start"),
        "on_quality_check_complete": lambda e: callback_log.append(f"quality:{e.confidence:.2f}"),
        "on_final_response": lambda s, a, q, e: callback_log.append(f"final:{s.value}:{a}"),
    }

    # Create adaptive loop
    adaptive_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=config,
        callbacks=callbacks,
    )

    # Execute
    result = await adaptive_loop.run("What is 2+2?", use_streaming=False)

    # Verify
    assert result is not None
    assert len(result) > 0
    assert "4" in result or "Direct response" in result

    # Verify callback sequence
    assert "analysis_start" in callback_log
    assert any("analysis:simple" in log for log in callback_log)
    assert any("strategy:direct" in log for log in callback_log)
    assert "quality_check_start" in callback_log
    assert any("quality:" in log for log in callback_log)
    assert any("final:direct" in log for log in callback_log)


@pytest.mark.asyncio
async def test_escalation_direct_to_light(mock_claude, mock_complexity_response):
    """Test escalation from DIRECT to LIGHT when quality is insufficient."""
    # Setup with responses that show escalation
    response_count = [0]

    def response_generator(query):
        response_count[0] += 1
        # Handle both string and list inputs
        query_str = query if isinstance(query, str) else str(query)
        if "complexity" in query_str.lower() or "user query" in query_str.lower():
            # Complexity analysis
            return mock_complexity_response(query)
        elif "quality assessment" in query_str.lower():
            # Quality evaluation
            if response_count[0] <= 3:
                # First attempt - insufficient quality
                return """**Quality Assessment:** INSUFFICIENT

**Confidence Score:** 0.35

**Reasoning:**
Response is too brief and lacks depth.

**Missing Aspects:**
- Technical details
- Examples"""
            else:
                # Second attempt - sufficient quality
                return """**Quality Assessment:** SUFFICIENT

**Confidence Score:** 0.85

**Reasoning:**
Response now has appropriate depth and detail."""
        else:
            # Regular response
            if response_count[0] <= 2:
                return "Brief answer"
            else:
                return "Comprehensive detailed answer with examples"

    llm = mock_claude(response_generator=response_generator)
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()

    # Create components
    analyzer = QueryComplexityAnalyzer(llm, config)
    planner = Planner(llm, config)
    evaluator = Evaluator(llm, config)
    synthesizer = Synthesizer(llm, config)

    # Track escalation
    escalations = []

    callbacks = {
        "on_auto_escalation": lambda from_s, to_s, r, c: escalations.append(
            {"from": from_s.value, "to": to_s.value, "confidence": c}
        ),
    }

    adaptive_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=config,
        callbacks=callbacks,
    )

    # Execute
    result = await adaptive_loop.run("Explain X", use_streaming=False)

    # Verify escalation happened
    assert len(escalations) >= 1
    assert escalations[0]["from"] == "direct"
    assert escalations[0]["to"] == "light_planning"
    assert result is not None


@pytest.mark.asyncio
async def test_forced_strategy_direct(
    mock_claude, mock_complexity_response, mock_quality_response
):
    """Test forcing DIRECT strategy for testing/debugging."""
    llm = mock_claude(response_generator=lambda q: "Forced direct response")
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()

    analyzer = QueryComplexityAnalyzer(
        mock_claude(response_generator=mock_complexity_response), config
    )
    planner = Planner(llm, config)
    evaluator = Evaluator(
        mock_claude(response_generator=mock_quality_response), config
    )
    synthesizer = Synthesizer(llm, config)

    # Force DIRECT strategy
    adaptive_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=config,
        force_strategy=ExecutionStrategy.DIRECT,
    )

    result = await adaptive_loop.run("Any query", use_streaming=False)

    assert result is not None
    # Analyzer shouldn't be called when strategy is forced
    assert analyzer.llm.call_count == 0


@pytest.mark.asyncio
async def test_light_planning_execution(
    mock_claude, mock_complexity_response, mock_planning_response, mock_quality_response
):
    """Test light planning execution path."""

    def response_generator(query):
        query_str = query if isinstance(query, str) else str(query)
        if "complexity" in query_str.lower():
            # Return MEDIUM complexity for light planning
            return """**Complexity Level:** MEDIUM

**Recommended Strategy:** LIGHT_PLANNING

**Estimated Iterations:** 2

**Confidence:** 0.85

**Reasoning:**
Medium complexity query needs light planning.

**Analysis Flags:**
- Requires Research: Yes
- Requires Synthesis: Yes
- Multi-Part Query: Yes
- Tool Count Estimate: 2"""
        elif "quality assessment" in query_str.lower():
            return mock_quality_response(query)
        elif any(
            keyword in query_str.lower() for keyword in ["plan", "priority", "subtask"]
        ):
            return mock_planning_response
        else:
            return "Response to subtask"

    llm = mock_claude(response_generator=response_generator)
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()

    analyzer = QueryComplexityAnalyzer(llm, config)
    planner = Planner(llm, config)
    evaluator = Evaluator(llm, config)
    synthesizer = Synthesizer(llm, config)

    callbacks = {
        "on_light_planning": lambda: None,
        "on_planning_complete": lambda p: None,
    }

    adaptive_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=config,
        callbacks=callbacks,
    )

    result = await adaptive_loop.run("Medium complexity query", use_streaming=False)

    assert result is not None
    assert len(result) > 0


@pytest.mark.asyncio
async def test_deep_reasoning_execution(mock_claude, mock_planning_response):
    """Test deep reasoning execution path."""

    def response_generator(query):
        query_str = query if isinstance(query, str) else str(query)
        if "complexity" in query_str.lower():
            # Return COMPLEX for deep reasoning
            return """**Complexity Level:** COMPLEX

**Recommended Strategy:** DEEP_REASONING

**Estimated Iterations:** 3

**Confidence:** 0.90

**Reasoning:**
Complex query requires deep reasoning.

**Analysis Flags:**
- Requires Research: Yes
- Requires Synthesis: Yes
- Multi-Part Query: Yes
- Tool Count Estimate: 5"""
        elif "quality assessment" in query_str.lower():
            return """**Quality Assessment:** SUFFICIENT

**Confidence Score:** 0.88

**Reasoning:**
Comprehensive answer with good depth."""
        elif "completeness assessment" in query_str.lower():
            return """## Completeness Assessment
COMPLETE

All aspects addressed.

## Confidence Score
0.90"""
        elif any(
            keyword in query_str.lower() for keyword in ["plan", "priority", "subtask"]
        ):
            return mock_planning_response
        else:
            return "Detailed response to subtask"

    llm = mock_claude(response_generator=response_generator)
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()

    analyzer = QueryComplexityAnalyzer(llm, config)
    planner = Planner(llm, config)
    evaluator = Evaluator(llm, config)
    synthesizer = Synthesizer(llm, config)

    callbacks = {
        "on_deep_reasoning": lambda: None,
        "on_iteration": lambda c, t, s: None,
        "on_evaluation": lambda: None,
        "on_synthesis": lambda: None,
    }

    adaptive_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=config,
        callbacks=callbacks,
    )

    result = await adaptive_loop.run("Complex research query", use_streaming=False)

    assert result is not None
    assert len(result) > 0


@pytest.mark.asyncio
async def test_quality_thresholds_per_strategy(mock_claude):
    """Test that different strategies have different quality thresholds."""

    def response_generator(query):
        query_str = query if isinstance(query, str) else str(query)
        if "complexity" in query_str.lower():
            return """**Complexity Level:** SIMPLE

**Recommended Strategy:** DIRECT

**Estimated Iterations:** 1

**Confidence:** 0.95"""
        elif "quality assessment" in query_str.lower():
            # Return borderline quality (0.62)
            return """**Quality Assessment:** SUFFICIENT

**Confidence Score:** 0.62

**Reasoning:**
Acceptable but not great."""
        else:
            return "Response"

    llm = mock_claude(response_generator=response_generator)
    conversation = Conversation()
    tool_registry = ToolRegistry()

    # Configure with high threshold for DIRECT to force escalation
    config = ReasoningConfig(min_quality_direct=0.7)

    analyzer = QueryComplexityAnalyzer(llm, config)
    planner = Planner(llm, config)
    evaluator = Evaluator(llm, config)
    synthesizer = Synthesizer(llm, config)

    escalations = []
    callbacks = {
        "on_auto_escalation": lambda from_s, to_s, r, c: escalations.append(True)
    }

    adaptive_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=config,
        callbacks=callbacks,
    )

    await adaptive_loop.run("Query", use_streaming=False)

    # Should escalate because 0.62 < 0.7 (min_quality_direct threshold)
    assert len(escalations) > 0


@pytest.mark.asyncio
async def test_no_escalation_from_deep(mock_claude):
    """Test that DEEP strategy doesn't escalate further."""

    def response_generator(query):
        query_str = query if isinstance(query, str) else str(query)
        if "complexity" in query_str.lower():
            return """**Complexity Level:** COMPLEX

**Recommended Strategy:** DEEP_REASONING

**Estimated Iterations:** 3

**Confidence:** 0.90"""
        elif "quality assessment" in query_str.lower():
            # Return low quality
            return """**Quality Assessment:** INSUFFICIENT

**Confidence Score:** 0.40

**Reasoning:**
Poor quality response."""
        elif "completeness" in query_str.lower():
            return """## Completeness Assessment
COMPLETE

## Confidence Score
0.5"""
        elif "plan" in query_str.lower():
            return """1. [HIGH PRIORITY] Task 1"""
        else:
            return "Poor response"

    llm = mock_claude(response_generator=response_generator)
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()

    analyzer = QueryComplexityAnalyzer(llm, config)
    planner = Planner(llm, config)
    evaluator = Evaluator(llm, config)
    synthesizer = Synthesizer(llm, config)

    escalations = []
    callbacks = {
        "on_auto_escalation": lambda from_s, to_s, r, c: escalations.append(True)
    }

    adaptive_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=config,
        callbacks=callbacks,
    )

    result = await adaptive_loop.run("Query", use_streaming=False)

    # No escalation should occur from DEEP (it's the final strategy)
    assert len(escalations) == 0
    assert result is not None  # Still returns something


@pytest.mark.asyncio
async def test_callback_sequence(mock_claude, mock_complexity_response, mock_quality_response):
    """Test that callbacks are called in correct order."""
    llm = mock_claude(response_generator=lambda q: "Response")
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()

    analyzer = QueryComplexityAnalyzer(
        mock_claude(response_generator=mock_complexity_response), config
    )
    planner = Planner(llm, config)
    evaluator = Evaluator(
        mock_claude(response_generator=mock_quality_response), config
    )
    synthesizer = Synthesizer(llm, config)

    callback_sequence = []

    callbacks = {
        "on_analysis_start": lambda: callback_sequence.append("1_analysis_start"),
        "on_analysis_complete": lambda c: callback_sequence.append("2_analysis_complete"),
        "on_strategy_selected": lambda s, r: callback_sequence.append("3_strategy_selected"),
        "on_direct_execution": lambda: callback_sequence.append("4_direct_execution"),
        "on_quality_check_start": lambda: callback_sequence.append("5_quality_check_start"),
        "on_quality_check_complete": lambda e: callback_sequence.append(
            "6_quality_check_complete"
        ),
        "on_final_response": lambda s, a, q, e: callback_sequence.append("7_final_response"),
    }

    adaptive_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=config,
        callbacks=callbacks,
    )

    await adaptive_loop.run("Query", use_streaming=False)

    # Verify sequence
    expected_order = [
        "1_analysis_start",
        "2_analysis_complete",
        "3_strategy_selected",
        "4_direct_execution",
        "5_quality_check_start",
        "6_quality_check_complete",
        "7_final_response",
    ]

    for expected in expected_order:
        assert expected in callback_sequence

    # Verify order is preserved
    indices = [callback_sequence.index(cb) for cb in expected_order]
    assert indices == sorted(indices)

