"""Test script to verify all callback signatures are correct."""

from src.nxs.presentation.widgets.reasoning_trace_panel import ReasoningTracePanel
from src.nxs.application.reasoning.types import (
    ComplexityAnalysis,
    ComplexityLevel,
    ExecutionStrategy,
    EvaluationResult,
)

# Test all callback signatures match
panel = ReasoningTracePanel()

print("Testing callback signatures...")

# Test 1: on_analysis_start - no args
panel.on_analysis_start()
print("✓ on_analysis_start()")

# Test 2: on_analysis_complete - ComplexityAnalysis arg
complexity = ComplexityAnalysis(
    complexity_level=ComplexityLevel.SIMPLE,
    recommended_strategy=ExecutionStrategy.DIRECT,
    reasoning_required=False,
    rationale="Test",
    estimated_iterations=1,
)
panel.on_analysis_complete(complexity)
print("✓ on_analysis_complete(complexity)")

# Test 3: on_strategy_selected - strategy, reason
panel.on_strategy_selected(ExecutionStrategy.DIRECT, "Test reason")
print("✓ on_strategy_selected(strategy, reason)")

# Test 4: on_planning_start - no args
panel.on_planning_start()
print("✓ on_planning_start()")

# Test 5: on_planning_complete - count, mode
panel.on_planning_complete(3, "light")
print("✓ on_planning_complete(count, mode)")

# Test 6: on_quality_check_start - no args
panel.on_quality_check_start()
print("✓ on_quality_check_start()")

# Test 7: on_quality_check_complete - evaluation
evaluation = EvaluationResult(
    is_complete=True, confidence=0.95, reasoning="Test", missing_aspects=[]
)
panel.on_quality_check_complete(evaluation)
print("✓ on_quality_check_complete(evaluation)")

# Test 8: on_auto_escalation - from, to, reason, confidence
panel.on_auto_escalation(
    ExecutionStrategy.DIRECT, ExecutionStrategy.LIGHT_PLANNING, "Test", 0.85
)
print("✓ on_auto_escalation(from_strategy, to_strategy, reason, confidence)")

# Test 9: on_final_response - strategy, attempts, quality, escalated
panel.on_final_response(ExecutionStrategy.DIRECT, 1, 0.95, False)
print("✓ on_final_response(strategy_used, attempts, final_quality, escalated)")

print("\n✅ All 9 callback signatures are valid and work correctly!")

