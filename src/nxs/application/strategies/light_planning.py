"""Light planning execution strategy.

Quick planning with 1-2 iterations and minimal overhead.
Good for medium-complexity queries.
"""

from typing import Callable

from nxs.application.progress_tracker import ResearchProgressTracker
from nxs.application.reasoning.planner import Planner
from nxs.application.reasoning.synthesizer import Synthesizer
from nxs.application.reasoning.types import ComplexityAnalysis, ExecutionStrategy
from nxs.application.strategies.base import ExecutionStrategy as BaseExecutionStrategy
from nxs.application.strategies.utils import (
    build_plan_context,
    build_subtask_query,
    call_callback,
)
from nxs.application.tool_registry import ToolRegistry
from nxs.logger import get_logger

logger = get_logger("light_planning_strategy")


class LightPlanningStrategy(BaseExecutionStrategy):
    """Light planning execution strategy for medium-complexity queries.

    This strategy performs quick task decomposition and executes 1-2 planning
    iterations with minimal overhead, suitable for queries that benefit from
    some structure but don't require deep reasoning.

    Characteristics:
    - Quick task analysis and decomposition
    - Limited to 1-2 execution iterations
    - Simple synthesis without filtering
    - Skips already completed steps (caching)
    - Falls back to direct execution if no plan generated
    - Avoids re-executing tools when results exist in conversation

    Use Cases:
    - Multi-part questions with clear structure
    - Queries requiring 2-3 tool calls
    - Research tasks with known scope
    - Escalated from direct execution

    Example:
        >>> strategy = LightPlanningStrategy(
        ...     planner=planner,
        ...     synthesizer=synthesizer,
        ...     tool_registry=registry,
        ...     execute_with_tracking=loop._execute_with_tool_tracking,
        ...     get_conversation_history=loop.conversation.get_messages
        ... )
        >>> result = await strategy.execute(query, complexity, tracker, callbacks)
    """

    def __init__(
        self,
        planner: Planner,
        synthesizer: Synthesizer,
        tool_registry: ToolRegistry,
        execute_with_tracking: Callable,
        get_conversation_history: Callable | None = None,
    ):
        """Initialize light planning strategy.

        Args:
            planner: Planner for task decomposition and subtask generation
            synthesizer: Synthesizer for combining subtask results
            tool_registry: ToolRegistry for tool discovery and availability
            execute_with_tracking: Async callable that executes queries with tool tracking.
                Signature: async (query, tracker, use_streaming, callbacks) -> str
                This handles the actual LLM execution with tool call interception.
            get_conversation_history: Optional callable to get conversation messages
                for context-aware planning (avoids re-execution of tools).
        """
        self.planner = planner
        self.synthesizer = synthesizer
        self.tool_registry = tool_registry
        self.execute_with_tracking = execute_with_tracking
        self.get_conversation_history = get_conversation_history

    async def execute(
        self,
        query: str,
        complexity: ComplexityAnalysis,
        tracker: ResearchProgressTracker,
        callbacks: dict[str, Callable],
    ) -> str:
        """Execute query using light planning strategy (1-2 iterations).

        This method performs quick task decomposition, executes subtasks,
        and synthesizes results with minimal overhead.

        Workflow:
        1. Generate or refine execution plan with tracker context
        2. Check if plan has subtasks (fallback to direct if empty)
        3. Execute plan steps (max 1-2 iterations):
           - Skip already completed steps (caching)
           - Build subtask query with tracker context
           - Execute with tool tracking
           - Update tracker with findings
        4. Synthesize results (simple combination)

        Args:
            query: User's query string
            complexity: Complexity analysis with estimated iterations
            tracker: ResearchProgressTracker with execution history and plan
            callbacks: Callback dictionary for status updates:
                - "on_light_planning": Start of light planning
                - "on_planning_complete": Plan generated
                - "on_iteration": Iteration progress
                - "on_step_progress": Step status changes

        Returns:
            Synthesized response combining all subtask results
            (buffered, not yet quality-checked)

        Note:
            Falls back to direct execution if:
            - No subtasks generated
            - No plan in tracker
            - No results accumulated
        """
        logger.info("Light planning execution")
        await call_callback(callbacks, "on_light_planning")

        # Get conversation history to avoid re-execution of tools
        conversation_history = None
        if self.get_conversation_history:
            conversation_history = self.get_conversation_history()

        # Generate or refine plan with full tracker context and conversation history
        plan_context = build_plan_context(
            complexity=complexity,
            tool_names=self.tool_registry.get_tool_names(),
            tracker=tracker,
            mode="light",
            conversation_history=conversation_history,
        )

        plan = await self.planner.generate_plan(query, context=plan_context)
        tracker.set_plan(plan, ExecutionStrategy.LIGHT_PLANNING)

        await call_callback(callbacks, "on_planning_complete", plan, "light")

        # If no subtasks were generated, fall back to direct execution
        if not plan.subtasks or len(plan.subtasks) == 0:
            logger.warning("No subtasks generated, falling back to direct execution")
            return await self.execute_with_tracking(
                query,
                tracker=tracker,
                use_streaming=False,
                callbacks={
                    k: v for k, v in callbacks.items() if k not in ["on_stream_chunk"]
                },
            )

        # Limit iterations for light planning
        max_iters = min(2, complexity.estimated_iterations or 2)

        accumulated_results = []

        # Execute plan steps with tracker integration
        if not tracker.plan:
            logger.warning("No plan in tracker, falling back to direct execution")
            return await self.execute_with_tracking(
                query,
                tracker=tracker,
                use_streaming=False,
                callbacks={
                    k: v for k, v in callbacks.items() if k not in ["on_stream_chunk"]
                },
            )

        for iteration in range(max_iters):
            if iteration >= len(tracker.plan.steps):
                break

            step = tracker.plan.steps[iteration]

            # Skip already completed steps
            if step.status == "completed":
                logger.debug(f"Skipping completed step: {step.description}")
                accumulated_results.append(
                    f"[Cached] {step.description}: {'; '.join(step.findings)}"
                )
                continue

            # Update step status
            tracker.update_step_status(step.id, "in_progress")

            # Notify step progress for real-time display
            await call_callback(
                callbacks, "on_step_progress", step.id, "in_progress", step.description
            )

            logger.debug(f"Light iteration {iteration + 1}/{max_iters}")

            await call_callback(
                callbacks,
                "on_iteration",
                iteration + 1,
                max_iters,
                step.description,
            )

            # Build subtask query with tracker context
            subtask_query = build_subtask_query(step, tracker)

            # Use execute_with_tracking
            result = await self.execute_with_tracking(
                subtask_query,
                tracker=tracker,
                use_streaming=False,
                callbacks={
                    k: v for k, v in callbacks.items() if k not in ["on_stream_chunk"]
                },
            )

            accumulated_results.append(
                {"query": step.description, "result": result, "iteration": iteration}
            )

            # Mark step as completed with findings
            tracker.update_step_status(step.id, "completed", findings=[result])

            # Notify step completion for real-time display
            await call_callback(
                callbacks, "on_step_progress", step.id, "completed", step.description
            )

            plan.subtasks.pop(0) if plan.subtasks else None

        # Simple synthesis (no filtering, just combine)
        if len(accumulated_results) == 0:
            logger.warning("No results accumulated, returning original query execution")
            return await self.execute_with_tracking(
                query,
                tracker=tracker,
                use_streaming=False,
                callbacks={
                    k: v for k, v in callbacks.items() if k not in ["on_stream_chunk"]
                },
            )
        elif len(accumulated_results) == 1:
            return accumulated_results[0]["result"]
        else:
            # Quick synthesis without filtering
            return await self.synthesizer.synthesize(query, accumulated_results)
