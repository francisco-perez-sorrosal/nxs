"""Shared utilities for execution strategies.

This module contains helper functions used by multiple execution strategies.
"""

from typing import Any

from nxs.application.progress_tracker import ResearchProgressTracker
from nxs.application.reasoning.types import ExecutionStrategy


async def call_callback(callbacks: dict, key: str, *args):
    """Helper to call callbacks that may be sync or async.

    This utility safely invokes callbacks from the callback dictionary,
    handling both synchronous and asynchronous callbacks transparently.

    Args:
        callbacks: Callback dictionary mapping callback names to functions
        key: Callback key to invoke
        *args: Arguments to pass to the callback

    Example:
        >>> await call_callback(callbacks, "on_step_complete", step_id, status)
    """
    if key in callbacks:
        result = callbacks[key](*args)
        # Handle both async and sync callbacks
        if hasattr(result, "__await__"):
            await result


def build_subtask_query(step: Any, tracker: ResearchProgressTracker) -> str:
    """Build query for a subtask incorporating tracker context.

    Args:
        step: PlanStep from tracker plan
        tracker: ResearchProgressTracker instance

    Returns:
        Enhanced query with context from completed steps and knowledge gaps
    """
    base_query = step.description

    # Add context from completed steps
    if tracker.plan:
        completed = tracker.plan.get_completed_steps()
        if completed:
            context_parts = [
                f"- {s.description}: {'; '.join(s.findings)}"
                for s in completed[-3:]
            ]
            context = "\n".join(context_parts)
            base_query = (
                f"{base_query}\n\nRelevant findings from previous steps:\n{context}"
            )

    # Add knowledge gaps to address
    if tracker.insights.knowledge_gaps:
        gaps = "\n".join(f"- {g}" for g in tracker.insights.knowledge_gaps[:3])
        base_query = (
            f"{base_query}\n\nAddress these knowledge gaps if relevant:\n{gaps}"
        )

    return base_query


def build_subtask_query_with_full_context(
    step: Any, tracker: ResearchProgressTracker
) -> str:
    """Build subtask query with comprehensive tracker context.

    Args:
        step: PlanStep from tracker plan
        tracker: ResearchProgressTracker instance

    Returns:
        Enhanced query with full tracker context
    """
    # Use full context serialization
    context_text = tracker.to_context_text(ExecutionStrategy.DEEP_REASONING)

    subtask_query = f"""
{step.description}

{context_text}

Focus on addressing the identified knowledge gaps and building upon completed work.
Avoid redundant tool calls - check the tool execution history above.
"""

    return subtask_query


def build_plan_context(
    complexity: Any,
    tool_names: list[str],
    tracker: ResearchProgressTracker,
    mode: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """Build context dictionary for plan generation.

    Args:
        complexity: Complexity analysis
        tool_names: Available tool names
        tracker: ResearchProgressTracker instance
        mode: Planning mode ("light" or "deep")
        conversation_history: Optional recent conversation messages with tool results

    Returns:
        Context dictionary for planner
    """
    plan_context = {
        "mode": mode,
        "complexity": complexity,
        "available_tools": tool_names,
    }

    # Add tracker context if this is a refinement (plan exists or has previous attempts)
    if tracker.plan is not None or len(tracker.attempts) > 1:
        # Include previous attempts for context
        if len(tracker.attempts) > 1:
            plan_context["previous_attempts"] = [
                {
                    "strategy": a.strategy.value,
                    "quality": a.quality_score,
                    "evaluation": a.evaluation.reasoning if a.evaluation else None,
                }
                for a in tracker.attempts[:-1]  # Exclude current
            ]

        # Include knowledge gaps
        if tracker.insights.knowledge_gaps:
            plan_context["knowledge_gaps"] = tracker.insights.knowledge_gaps

        # Include completed steps if plan exists
        if tracker.plan:
            plan_context["completed_steps"] = [
                s.description for s in tracker.plan.get_completed_steps()
            ]

    # Include recent conversation history to avoid re-execution
    # This allows the planner to see what tools were already called and their results
    if conversation_history:
        # Extract tool calls and results from recent messages
        tool_executions = []
        for msg in conversation_history[-10:]:  # Last 10 messages for context
            if msg.get("role") == "assistant" and "content" in msg:
                # Check for tool use blocks
                for block in msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_executions.append({
                            "tool": block.get("name"),
                            "input": block.get("input"),
                        })
            # Check for tool results
            if msg.get("role") == "user" and "content" in msg:
                for block in msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        # Add result to most recent tool execution
                        if tool_executions:
                            # Add result to last tool execution
                            tool_executions[-1]["result"] = block.get("content", "")[:200]  # Truncate for context

        if tool_executions:
            plan_context["recent_tool_executions"] = tool_executions

    return plan_context
