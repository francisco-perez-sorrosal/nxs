"""Deep reasoning execution strategy.

Full reasoning cycle with iterative execution and evaluation.
Good for complex research queries.
"""

from typing import Callable

from nxs.application.progress_tracker import PlanStep, ResearchProgressTracker
from nxs.application.reasoning.evaluator import Evaluator
from nxs.application.reasoning.planner import Planner
from nxs.application.reasoning.synthesizer import Synthesizer
from nxs.application.reasoning.types import ComplexityAnalysis, ExecutionStrategy, SubTask
from nxs.application.strategies.base import ExecutionStrategy as BaseExecutionStrategy
from nxs.application.strategies.utils import (
    build_plan_context,
    build_subtask_query_with_full_context,
    call_callback,
)
from nxs.application.tool_registry import ToolRegistry
from nxs.logger import get_logger

logger = get_logger("deep_reasoning_strategy")


class DeepReasoningStrategy(BaseExecutionStrategy):
    """Deep reasoning execution strategy for complex research queries.

    This strategy implements a full reasoning cycle with comprehensive planning,
    iterative execution, evaluation at each step, and sophisticated synthesis.
    It's designed for complex queries requiring multi-step research and analysis.

    Characteristics:
    - Comprehensive planning with full context
    - Iterative execution with per-step evaluation
    - Dynamic plan adjustment based on gaps
    - Result filtering before synthesis
    - Maximum robustness and quality

    Use Cases:
    - Complex research questions
    - Multi-faceted analysis tasks
    - Queries requiring >3 tool calls
    - Tasks with unknown scope
    - Escalated from light planning
    - Final escalation attempt

    Example:
        >>> strategy = DeepReasoningStrategy(
        ...     planner=planner,
        ...     evaluator=evaluator,
        ...     synthesizer=synthesizer,
        ...     tool_registry=registry,
        ...     execute_with_tracking=loop._execute_with_tool_tracking,
        ...     max_iterations=3
        ... )
        >>> result = await strategy.execute(query, complexity, tracker, callbacks)
    """

    def __init__(
        self,
        planner: Planner,
        evaluator: Evaluator,
        synthesizer: Synthesizer,
        tool_registry: ToolRegistry,
        execute_with_tracking: Callable,
        max_iterations: int = 3,
    ):
        """Initialize deep reasoning strategy.

        Args:
            planner: Planner for comprehensive task decomposition
            evaluator: Evaluator for completeness and quality assessment
            synthesizer: Synthesizer for filtering and combining results
            tool_registry: ToolRegistry for tool discovery and availability
            execute_with_tracking: Async callable that executes queries with tool tracking.
                Signature: async (query, tracker, use_streaming, callbacks) -> str
                This handles the actual LLM execution with tool call interception.
            max_iterations: Maximum iterations for deep reasoning (default 3).
                Actual iterations may be fewer if evaluation determines completion.
        """
        self.planner = planner
        self.evaluator = evaluator
        self.synthesizer = synthesizer
        self.tool_registry = tool_registry
        self.execute_with_tracking = execute_with_tracking
        self.max_iterations = max_iterations

    async def execute(
        self,
        query: str,
        complexity: ComplexityAnalysis,
        tracker: ResearchProgressTracker,
        callbacks: dict[str, Callable],
    ) -> str:
        """Execute query using deep reasoning strategy (full cycle).

        This method performs comprehensive planning, iterative execution with
        evaluation, dynamic plan adjustment, and sophisticated synthesis.

        Workflow:
        1. Planning Phase:
           - Generate comprehensive plan with full tracker context
           - Include previous attempts, knowledge gaps, completed steps
           - Set or refine plan in tracker
        2. Iterative Execution Phase (up to max_iterations):
           - Find next pending step
           - Execute step with full context
           - Evaluate completeness after each iteration
           - Identify knowledge gaps and missing information
           - Add dynamic steps if needed
           - Early exit if evaluation confirms completion
        3. Synthesis Phase:
           - Filter results for relevance
           - Generate final comprehensive answer

        Args:
            query: User's query string
            complexity: Complexity analysis with estimated iterations
            tracker: ResearchProgressTracker with execution history and plan
            callbacks: Callback dictionary for status updates:
                - "on_deep_reasoning": Start of deep reasoning
                - "on_planning": Start of planning phase
                - "on_planning_complete": Plan generated
                - "on_iteration": Iteration progress
                - "on_step_progress": Step status changes
                - "on_evaluation": Evaluation start
                - "on_synthesis": Synthesis start

        Returns:
            Synthesized final answer combining all results
            (buffered, not yet quality-checked)

        Note:
            This is the most expensive strategy but provides the highest
            quality results for complex queries. It's the final escalation
            level with no further fallback.
        """
        logger.info("Deep reasoning execution")
        await call_callback(callbacks, "on_deep_reasoning")

        # Phase 1: Planning (full detail)
        logger.info(f"Phase 1: Planning for query: {query[:100]}")
        await call_callback(callbacks, "on_planning")

        # Generate comprehensive plan with full tracker context
        plan_context = build_plan_context(
            complexity=complexity,
            tool_names=self.tool_registry.get_tool_names(),
            tracker=tracker,
            mode="deep",
        )

        plan = await self.planner.generate_plan(query, context=plan_context)
        plan.complexity_analysis = complexity
        logger.info(f"Generated plan with {len(plan.subtasks)} subtasks")

        # Set or refine plan in tracker
        if tracker.plan is None:
            tracker.set_plan(plan, ExecutionStrategy.DEEP_REASONING)
        else:
            # Refine existing plan
            tracker.set_plan(plan, ExecutionStrategy.DEEP_REASONING)

        await call_callback(callbacks, "on_planning_complete", plan, "deep")

        # Phase 2: Iterative execution and evaluation
        accumulated_results = []
        executed_queries = []

        # Use tracker plan steps instead of plan.subtasks
        if not tracker.plan:
            logger.error("No plan in tracker for deep reasoning")
            return "Error: No plan available for deep reasoning execution"

        max_iterations = min(self.max_iterations, len(tracker.plan.steps))

        for iteration in range(max_iterations):
            logger.info(f"Phase 2: Iteration {iteration + 1}/{max_iterations}")

            # Find next pending step from tracker
            pending_steps = tracker.plan.get_pending_steps()
            if not pending_steps:
                break

            step = pending_steps[0]
            tracker.update_step_status(step.id, "in_progress")

            # Notify step progress for real-time display
            await call_callback(
                callbacks, "on_step_progress", step.id, "in_progress", step.description
            )

            subtask_query = step.description
            await call_callback(
                callbacks,
                "on_iteration",
                iteration + 1,
                max_iterations,
                subtask_query,
            )

            # Execute step with full context
            subtask_query_with_context = build_subtask_query_with_full_context(
                step, tracker
            )

            logger.debug(f"Executing subtask: {subtask_query}")

            # Use execute_with_tracking
            result = await self.execute_with_tracking(
                subtask_query_with_context,
                tracker=tracker,
                use_streaming=False,
                callbacks={
                    k: v for k, v in callbacks.items() if k not in ["on_stream_chunk"]
                },
            )

            accumulated_results.append(
                {
                    "query": subtask_query,
                    "result": result,
                    "iteration": iteration,
                }
            )
            executed_queries.append(subtask_query)

            # Mark step as completed
            tracker.update_step_status(step.id, "completed", findings=[result])

            # Notify step completion for real-time display
            await call_callback(
                callbacks, "on_step_progress", step.id, "completed", step.description
            )

            # Phase 3: Evaluation
            logger.info("Phase 3: Evaluating completeness")
            await call_callback(callbacks, "on_evaluation")

            evaluation = await self.evaluator.evaluate(
                query=query, results=accumulated_results, current_plan=plan
            )

            logger.info(
                f"Evaluation: complete={evaluation.is_complete}, "
                f"confidence={evaluation.confidence:.2f}"
            )

            # Store evaluation insights in tracker
            tracker.insights.add_from_evaluation(evaluation)

            # Check if we're done
            if evaluation.is_complete:
                logger.info("Query fully answered, proceeding to synthesis")
                break

            # Phase 4: Plan adjustment if needed
            if evaluation.additional_queries and iteration < max_iterations - 1:
                logger.info(
                    f"Adding {len(evaluation.additional_queries)} additional queries"
                )
                # Add dynamic steps to tracker plan
                if tracker.plan:
                    for additional_query in evaluation.additional_queries:
                        if additional_query not in executed_queries:
                            new_step = PlanStep(
                                id=f"step_dynamic_{iteration}_{len(tracker.plan.steps)}",
                                description=additional_query,
                                status="pending",
                                started_at=None,
                                completed_at=None,
                                findings=[],
                                tools_used=[],
                                depends_on=[step.id],
                                spawned_from=step.id,
                            )
                            tracker.plan.add_dynamic_step(new_step, step.id)
                        # Also add to plan.subtasks for backward compatibility
                        plan.subtasks.append(
                            SubTask(query=additional_query, priority=1)
                        )

        # Phase 5: Synthesis
        logger.info("Phase 5: Synthesizing final answer")
        await call_callback(callbacks, "on_synthesis")

        # Filter results first
        filtered_results = await self.synthesizer.filter_results(
            query, accumulated_results
        )

        # Generate final answer
        final_answer = await self.synthesizer.synthesize(query, filtered_results)

        logger.info(f"Deep reasoning complete: {len(final_answer)} chars generated")

        return final_answer
