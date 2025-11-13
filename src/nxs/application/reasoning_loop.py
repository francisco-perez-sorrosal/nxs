"""AdaptiveReasoningLoop - Self-correcting adaptive agent with quality guarantees.

This module implements the core self-correcting reasoning system that:
- Automatically analyzes query complexity
- Routes to appropriate execution strategy (DIRECT/LIGHT/DEEP)
- Evaluates response quality
- Auto-escalates when quality is insufficient
- Guarantees quality-approved responses reach users
"""

from typing import Any, Callable, Optional

from nxs.application.agentic_loop import AgentLoop
from nxs.application.approval import ApprovalManager, ApprovalType, create_approval_request
from nxs.application.claude import Claude
from nxs.application.conversation import Conversation
from nxs.application.progress_tracker import ResearchProgressTracker
from nxs.application.reasoning.analyzer import QueryComplexityAnalyzer
from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.evaluator import Evaluator
from nxs.application.reasoning.planner import Planner
from nxs.application.reasoning.synthesizer import Synthesizer
from nxs.application.reasoning.types import (
    ComplexityAnalysis,
    ComplexityLevel,
    EvaluationResult,
    ExecutionStrategy,
    SubTask,
)
from nxs.application.tool_registry import ToolRegistry
from nxs.logger import get_logger

logger = get_logger("adaptive_reasoning_loop")


async def _call_callback(callbacks: dict, key: str, *args):
    """Helper to call callbacks that may be sync or async.

    Args:
        callbacks: Callback dictionary
        key: Callback key
        *args: Arguments to pass to callback
    """
    if key in callbacks:
        result = callbacks[key](*args)
        # Handle both async and sync callbacks
        if hasattr(result, "__await__"):
            await result


class AdaptiveReasoningLoop(AgentLoop):
    """Self-correcting adaptive agent loop with quality feedback.

    Key Innovations:
    1. Automatically analyzes query complexity and adapts execution
    2. ALWAYS evaluates responses - even for "simple" queries
    3. Self-corrects: If simple execution produces poor result, automatically escalates
    4. Guarantees quality: No response sent without passing evaluation
    5. Buffers responses during evaluation (quality-first delivery)

    Execution Flow (ALL paths include buffering + evaluation):
    1. DIRECT → Execute & Buffer → Evaluate → (Pass: Return | Fail: Escalate to LIGHT)
    2. LIGHT → Plan → Execute & Buffer → Evaluate → (Pass: Return | Fail: Escalate to DEEP)
    3. DEEP → Full reasoning → Buffer → Evaluate → Return (no further escalation)

    Message Management:
    - User query added to conversation once at start
    - Execution attempts buffered (NOT added to conversation during attempts)
    - Only final quality-approved response added to conversation
    - Failed attempts logged for debugging but not persisted in conversation

    Self-Correction Example:
    - Query: "What is quantum computing?"
    - Initial: Classified as SIMPLE
    - Execute: Quick response via AgentLoop (buffered, not returned)
    - Evaluate: "Response is superficial, lacks key concepts" (confidence: 0.4)
    - Auto-escalate: Discard buffer, re-execute as LIGHT with research (buffered)
    - Re-evaluate: "Now comprehensive and accurate" (confidence: 0.85)
    - Return: Final quality-checked response
    - Persist: Add approved response to conversation history

    This ensures fast execution when possible, but NEVER sacrifices quality.
    Maintains backward compatibility - intelligently adds overhead only when needed.
    """

    def __init__(
        self,
        llm: Claude,
        conversation: Conversation,
        tool_registry: ToolRegistry,
        analyzer: QueryComplexityAnalyzer,
        planner: Planner,
        evaluator: Evaluator,
        synthesizer: Synthesizer,
        max_iterations: int = 3,
        config: Optional[ReasoningConfig] = None,
        callbacks: Optional[dict] = None,
        force_strategy: Optional[ExecutionStrategy] = None,
        approval_manager: Optional[ApprovalManager] = None,
    ):
        """Initialize adaptive reasoning loop.

        Args:
            llm: Claude instance for API calls
            conversation: Conversation instance for state management
            tool_registry: ToolRegistry for tool discovery and execution
            analyzer: QueryComplexityAnalyzer for complexity analysis
            planner: Planner for task decomposition
            evaluator: Evaluator for quality assessment
            synthesizer: Synthesizer for result combination
            max_iterations: Maximum iterations for deep reasoning (default 3)
            config: ReasoningConfig for thresholds and settings
            callbacks: Optional callbacks for TUI integration
            force_strategy: Override strategy for testing/debugging (None = auto)
            approval_manager: Optional ApprovalManager for query analysis approval
        """
        super().__init__(llm, conversation, tool_registry, callbacks)

        self.analyzer = analyzer
        self.planner = planner
        self.evaluator = evaluator
        self.synthesizer = synthesizer
        self.max_iterations = max_iterations
        self.config = config or ReasoningConfig()
        self.force_strategy = force_strategy
        self.approval_manager = approval_manager

        logger.info(
            f"AdaptiveReasoningLoop initialized: max_iterations={max_iterations}, "
            f"force_strategy={force_strategy}"
        )
    
    def set_reasoning_cost_callback(
        self, on_usage: Optional[Callable[[dict, float], None]]
    ) -> None:
        """Set cost tracking callback for all reasoning components.
        
        Args:
            on_usage: Callback function (usage dict, cost) -> None
        """
        self.analyzer.on_usage = on_usage
        self.planner.on_usage = on_usage
        self.evaluator.on_usage = on_usage
        self.synthesizer.on_usage = on_usage
        logger.debug("Reasoning cost callback set on all reasoning components")

    async def run(
        self,
        query: str,
        use_streaming: bool = True,
        callbacks: Optional[dict[str, Callable]] = None,
    ) -> str:
        """Run with adaptive execution strategy based on query complexity.

        Self-Correcting Adaptive Process:
        0. Analysis Phase: Determine initial query complexity
        1. Strategy Selection: Choose execution path
        2. Execute: Run chosen strategy (buffered, not streamed yet)
        3. Evaluate: ALWAYS evaluate response quality
        4. Self-Correct: If quality insufficient, escalate and retry
        5. Return: Only return quality-approved responses

        ALL execution paths include quality evaluation:
        - DIRECT: Fast execution → Evaluate → (Good: Return | Poor: → LIGHT)
        - LIGHT: Light planning → Evaluate → (Good: Return | Poor: → DEEP)
        - DEEP: Full reasoning → Evaluate → Return (final attempt)

        Args:
            query: User's query/message
            use_streaming: Whether to use streaming (default True)
            callbacks: Optional callback overrides

        Returns:
            Quality-approved final answer
        """
        callbacks = callbacks or self.callbacks

        # Human-in-the-Loop: Simple choice - execute directly or use reasoning
        use_reasoning = False
        initial_strategy = ExecutionStrategy.DIRECT  # Default
        complexity = None

        if (
            self.approval_manager
            and self.approval_manager.config.require_query_analysis_approval
        ):
            logger.info("Requesting execution mode from user")

            # Build approval request details - simple binary choice
            approval_details = {
                "mode": "execution_choice",  # Signal this is a simple mode choice
                "options": ["Execute Directly (fast)", "Analyze & Use Reasoning (automatic)"]
            }

            request = create_approval_request(
                approval_type=ApprovalType.QUERY_ANALYSIS,
                title="Choose Execution Mode",
                details=approval_details,
            )

            response = await self.approval_manager.request_approval(request)

            if not response.approved:
                logger.info("Execution mode selection cancelled by user")
                return "Query cancelled by user."

            # Check which mode user selected
            use_reasoning = response.metadata.get("use_reasoning", False)
            logger.info(f"User selected: {'Reasoning mode' if use_reasoning else 'Direct execution'}")

        # Phase 0: COMPLEXITY ANALYSIS (only if user selected reasoning mode or forced)
        if self.force_strategy:
            logger.warning(f"Forcing strategy: {self.force_strategy.value}")
            initial_strategy = self.force_strategy
            complexity = ComplexityAnalysis(
                complexity_level=ComplexityLevel.COMPLEX,
                reasoning_required=True,
                recommended_strategy=self.force_strategy,
                rationale="Forced by configuration",
                estimated_iterations=self.max_iterations,
                confidence=1.0,
            )
        elif use_reasoning:
            # User wants reasoning - run analyzer to determine complexity and strategy
            logger.info("Running complexity analysis for reasoning mode")
            await _call_callback(callbacks, "on_analysis_start")

            # Get available tools for analysis
            tool_names = self.tool_registry.get_tool_names()

            complexity = await self.analyzer.analyze(
                query=query,
                available_tools=tool_names,
                conversation_context={},  # Could pass recent messages
            )

            # Analyzer chooses between LIGHT_PLANNING and DEEP_REASONING
            initial_strategy = complexity.recommended_strategy

            logger.info(
                f"Complexity Analysis: level={complexity.complexity_level.value}, "
                f"recommended_strategy={initial_strategy.value}, "
                f"iterations={complexity.estimated_iterations}"
            )

            await _call_callback(callbacks, "on_analysis_complete", complexity)
        else:
            # Direct execution - skip analyzer
            logger.info("Using DIRECT execution - skipping complexity analysis")
            initial_strategy = ExecutionStrategy.DIRECT
            complexity = ComplexityAnalysis(
                complexity_level=ComplexityLevel.SIMPLE,
                reasoning_required=False,
                recommended_strategy=ExecutionStrategy.DIRECT,
                rationale="User selected direct execution",
                estimated_iterations=1,
                confidence=1.0,
            )

        # NEW: Initialize progress tracker (Phase 3)
        tracker = ResearchProgressTracker(query, complexity)
        logger.debug("Initialized ResearchProgressTracker for query execution")

        # Phase 1: ADAPTIVE EXECUTION WITH SELF-CORRECTION
        # Try execution strategies in order: DIRECT → LIGHT → DEEP
        # Escalate automatically if evaluation fails

        current_strategy = initial_strategy
        execution_attempts: list[tuple[str, str, float]] = []  # (strategy, response, quality)

        while True:
            logger.info(f"Attempting strategy: {current_strategy.value}")

            await _call_callback(
                callbacks,
                "on_strategy_selected",
                current_strategy,
                f"Executing with {current_strategy.value} strategy",
            )

            # NEW: Start execution attempt in tracker (Phase 3)
            tracker.start_attempt(current_strategy)

            # Execute with current strategy (buffered, not streamed to user yet)
            if current_strategy == ExecutionStrategy.DIRECT:
                result = await self._execute_direct(query, complexity, tracker, callbacks)
                execution_attempts.append(("DIRECT", result, 0.0))

            elif current_strategy == ExecutionStrategy.LIGHT_PLANNING:
                result = await self._execute_light_planning(
                    query, complexity, tracker, callbacks
                )
                execution_attempts.append(("LIGHT", result, 0.0))

            else:  # DEEP_REASONING
                result = await self._execute_deep_reasoning(
                    query, complexity, tracker, callbacks
                )
                execution_attempts.append(("DEEP", result, 0.0))

            # Phase 2: QUALITY EVALUATION (Always performed!)
            logger.info("Phase 2: Evaluating response quality")
            
            # Show the response that will be judged
            await _call_callback(callbacks, "on_response_for_judgment", result, current_strategy.value)
            
            await _call_callback(callbacks, "on_quality_check_start")

            evaluation = await self._evaluate_response_quality(
                query=query,
                response=result,
                strategy_used=current_strategy,
                complexity=complexity,
            )

            # Update quality score in attempts
            execution_attempts[-1] = (
                execution_attempts[-1][0],
                execution_attempts[-1][1],
                evaluation.confidence,
            )

            logger.info(
                f"Quality evaluation: sufficient={evaluation.is_complete}, "
                f"confidence={evaluation.confidence:.2f}"
            )

            await _call_callback(callbacks, "on_quality_check_complete", evaluation)

            # NEW: Record attempt outcome in tracker (Phase 3)
            outcome = (
                "Quality sufficient"
                if evaluation.is_complete
                else "Escalated due to low quality"
            )
            tracker.end_attempt(
                outcome=outcome,
                response=result,
                evaluation=evaluation,
                quality_score=evaluation.confidence,
            )

            # Phase 3: SELF-CORRECTION DECISION
            if (
                evaluation.is_complete
                or current_strategy == ExecutionStrategy.DEEP_REASONING
            ):
                # Either quality is good, or we've tried the deepest strategy
                logger.info(
                    f"Returning response: strategy={current_strategy.value}, "
                    f"attempts={len(execution_attempts)}, "
                    f"quality={evaluation.confidence:.2f}"
                )

                # Now stream the approved response to user
                if use_streaming and "on_stream_chunk" in callbacks:
                    # Stream the buffered response
                    for i in range(0, len(result), 20):
                        chunk = result[i : i + 20]
                        await _call_callback(callbacks, "on_stream_chunk", chunk)
                    
                    # Signal streaming completion so chat panel can render the buffered message
                    await _call_callback(callbacks, "on_stream_complete")

                await _call_callback(
                    callbacks,
                    "on_final_response",
                    current_strategy,
                    len(execution_attempts),
                    evaluation.confidence,
                    len(execution_attempts) > 1,  # escalated flag
                )

                return result

            # Quality insufficient - escalate!
            logger.warning(
                f"Response quality insufficient ({evaluation.confidence:.2f}), "
                f"escalating from {current_strategy.value}"
            )

            await _call_callback(
                callbacks,
                "on_auto_escalation",
                current_strategy,
                self._get_next_strategy(current_strategy),
                evaluation.reasoning,
                evaluation.confidence,
            )

            # Escalate to next strategy level
            current_strategy = self._get_next_strategy(current_strategy)
            logger.info(f"Auto-escalating to: {current_strategy.value}")

    def _get_next_strategy(self, current: ExecutionStrategy) -> ExecutionStrategy:
        """Get next strategy level for escalation.

        Args:
            current: Current execution strategy

        Returns:
            Next strategy level (escalated)
        """
        if current == ExecutionStrategy.DIRECT:
            return ExecutionStrategy.LIGHT_PLANNING
        elif current == ExecutionStrategy.LIGHT_PLANNING:
            return ExecutionStrategy.DEEP_REASONING
        else:
            # Already at DEEP, return same (shouldn't reach here)
            return ExecutionStrategy.DEEP_REASONING

    async def _execute_direct(
        self,
        query: str,
        complexity: ComplexityAnalysis,
        tracker: ResearchProgressTracker,
        callbacks: dict,
    ) -> str:
        """Execute with direct strategy (fast-path).

        Modified for Phase 3:
        - Adds compact context if this is an escalation
        - Uses _execute_with_tool_tracking() for tool interception

        Fast execution:
        - No planning overhead
        - Direct AgentLoop execution
        - Good for simple, straightforward queries

        Args:
            query: User query
            complexity: Complexity analysis
            tracker: ResearchProgressTracker instance
            callbacks: Callback dictionary

        Returns:
            Response text (buffered, not yet quality-checked)
        """
        logger.info("Direct execution (fast-path)")
        await _call_callback(callbacks, "on_direct_execution")

        # NEW: Add tracker context if this is an escalation (Phase 3)
        if len(tracker.attempts) > 1:
            # This is a retry after failed attempt
            context_text = tracker.to_compact_context()
            enhanced_query = f"{query}\n\n[Previous attempt context: {context_text}]"
            logger.debug("Added compact tracker context to DIRECT execution")
        else:
            enhanced_query = query

        # NEW: Use _execute_with_tool_tracking() for tool interception (Phase 3)
        result = await self._execute_with_tool_tracking(
            enhanced_query,
            tracker=tracker,
            use_streaming=False,
            callbacks={
                k: v
                for k, v in callbacks.items()
                if k not in ["on_stream_chunk"]  # Suppress streaming
            },
        )

        logger.info(f"Direct execution complete: {len(result)} chars")
        return result

    async def _execute_light_planning(
        self,
        query: str,
        complexity: ComplexityAnalysis,
        tracker: ResearchProgressTracker,
        callbacks: dict,
    ) -> str:
        """Execute with light planning (1-2 iterations, minimal overhead).

        Modified for Phase 3:
        - Uses plan skeleton from tracker
        - Tracks step progress
        - Skips completed steps
        - Uses _execute_with_tool_tracking() for tool interception

        Light planning:
        - Quick analysis of query parts
        - Execute 1-2 steps
        - No deep evaluation/synthesis
        - Good for medium-complexity queries

        Args:
            query: User query
            complexity: Complexity analysis
            tracker: ResearchProgressTracker instance
            callbacks: Callback dictionary

        Returns:
            Synthesized response (buffered, not yet quality-checked)
        """
        logger.info("Light planning execution")
        await _call_callback(callbacks, "on_light_planning")

        # NEW: Generate or refine plan with tracker context (Phase 3)
        if tracker.plan is None:
            # First planning attempt
            plan = await self.planner.generate_plan(
                query, context={"complexity": complexity, "mode": "light"}
            )
            tracker.set_plan(plan, ExecutionStrategy.LIGHT_PLANNING)
        else:
            # Refine existing plan based on gaps
            plan_context = {
                "mode": "light",
                "complexity": complexity,
                "previous_attempts": len(tracker.attempts),
                "knowledge_gaps": tracker.insights.knowledge_gaps,
                "completed_steps": [
                    s.description for s in tracker.plan.get_completed_steps()
                ],
            }
            plan = await self.planner.generate_plan(query, context=plan_context)
            tracker.set_plan(plan, ExecutionStrategy.LIGHT_PLANNING)

        await _call_callback(callbacks, "on_planning_complete", len(plan.subtasks), "light")

        # If no subtasks were generated, fall back to direct execution
        if not plan.subtasks or len(plan.subtasks) == 0:
            logger.warning("No subtasks generated, falling back to direct execution")
            return await self._execute_with_tool_tracking(
                query,
                tracker=tracker,
                use_streaming=False,
                callbacks={k: v for k, v in callbacks.items() if k not in ["on_stream_chunk"]},
            )

        # Limit iterations for light planning
        max_iters = min(2, complexity.estimated_iterations or 2)

        accumulated_results = []

        # NEW: Execute plan steps with tracker integration (Phase 3)
        if not tracker.plan:
            logger.warning("No plan in tracker, falling back to direct execution")
            return await self._execute_with_tool_tracking(
                query,
                tracker=tracker,
                use_streaming=False,
                callbacks={k: v for k, v in callbacks.items() if k not in ["on_stream_chunk"]},
            )

        for iteration in range(max_iters):
            if iteration >= len(tracker.plan.steps):
                break

            step = tracker.plan.steps[iteration]

            # NEW: Skip already completed steps (Phase 3)
            if step.status == "completed":
                logger.debug(f"Skipping completed step: {step.description}")
                accumulated_results.append(
                    f"[Cached] {step.description}: {'; '.join(step.findings)}"
                )
                continue

            # NEW: Update step status (Phase 3)
            tracker.update_step_status(step.id, "in_progress")

            logger.debug(f"Light iteration {iteration + 1}/{max_iters}")

            await _call_callback(
                callbacks,
                "on_iteration",
                iteration + 1,
                max_iters,
                step.description,
            )

            # NEW: Build subtask query with tracker context (Phase 3)
            subtask_query = self._build_subtask_query(step, tracker)

            # NEW: Use _execute_with_tool_tracking() (Phase 3)
            result = await self._execute_with_tool_tracking(
                subtask_query,
                tracker=tracker,
                use_streaming=False,
                callbacks={k: v for k, v in callbacks.items() if k not in ["on_stream_chunk"]},
            )

            accumulated_results.append(
                {"query": step.description, "result": result, "iteration": iteration}
            )

            # NEW: Mark step as completed with findings (Phase 3)
            tracker.update_step_status(step.id, "completed", findings=[result])

            plan.subtasks.pop(0) if plan.subtasks else None

        # Simple synthesis (no filtering, just combine)
        if len(accumulated_results) == 0:
            logger.warning("No results accumulated, returning original query execution")
            return await self._execute_with_tool_tracking(
                query,
                tracker=tracker,
                use_streaming=False,
                callbacks={k: v for k, v in callbacks.items() if k not in ["on_stream_chunk"]},
            )
        elif len(accumulated_results) == 1:
            return accumulated_results[0]["result"]
        else:
            # Quick synthesis without filtering
            return await self.synthesizer.synthesize(query, accumulated_results)

    async def _execute_deep_reasoning(
        self,
        query: str,
        complexity: ComplexityAnalysis,
        tracker: ResearchProgressTracker,
        callbacks: dict,
    ) -> str:
        """Execute with full reasoning cycle (original ReasoningLoop logic).

        Modified for Phase 3:
        - Uses plan skeleton from tracker
        - Full context integration for escalations
        - Tracks step progress and adds dynamic steps
        - Uses _execute_with_tool_tracking() for tool interception

        Deep reasoning:
        - Full planning phase
        - Iterative execution with evaluation
        - Gap identification and additional queries
        - Result filtering and synthesis
        - Good for complex research queries

        Args:
            query: User query
            complexity: Complexity analysis
            tracker: ResearchProgressTracker instance
            callbacks: Callback dictionary

        Returns:
            Synthesized final answer (buffered, not yet quality-checked)
        """
        logger.info("Deep reasoning execution")
        await _call_callback(callbacks, "on_deep_reasoning")

        # Phase 1: Planning (full detail)
        logger.info(f"Phase 1: Planning for query: {query[:100]}")
        await _call_callback(callbacks, "on_planning")

        # NEW: Generate comprehensive plan with tracker context (Phase 3)
        plan_context = {
            "mode": "deep",
            "complexity": complexity,
            "available_tools": self.tool_registry.get_tool_names(),
        }

        # NEW: Add previous attempt context if escalated (Phase 3)
        if len(tracker.attempts) > 1:
            plan_context["previous_attempts"] = [
                {
                    "strategy": a.strategy.value,
                    "quality": a.quality_score,
                    "evaluation": a.evaluation.reasoning if a.evaluation else None,
                }
                for a in tracker.attempts[:-1]  # Exclude current
            ]
            plan_context["knowledge_gaps"] = tracker.insights.knowledge_gaps
            plan_context["completed_steps"] = (
                [s.description for s in tracker.plan.get_completed_steps()]
                if tracker.plan
                else []
            )

        plan = await self.planner.generate_plan(query, context=plan_context)
        plan.complexity_analysis = complexity
        logger.info(f"Generated plan with {len(plan.subtasks)} subtasks")

        # NEW: Set or refine plan in tracker (Phase 3)
        if tracker.plan is None:
            tracker.set_plan(plan, ExecutionStrategy.DEEP_REASONING)
        else:
            # Refine existing plan
            tracker.set_plan(plan, ExecutionStrategy.DEEP_REASONING)

        await _call_callback(callbacks, "on_planning_complete", len(plan.subtasks), "deep")

        # Phase 2: Iterative execution and evaluation
        accumulated_results = []
        executed_queries = []

        # NEW: Use tracker plan steps instead of plan.subtasks (Phase 3)
        if not tracker.plan:
            logger.error("No plan in tracker for deep reasoning")
            return "Error: No plan available for deep reasoning execution"

        max_iterations = min(self.max_iterations, len(tracker.plan.steps))

        for iteration in range(max_iterations):
            logger.info(f"Phase 2: Iteration {iteration + 1}/{max_iterations}")

            # NEW: Find next pending step from tracker (Phase 3)
            pending_steps = tracker.plan.get_pending_steps()
            if not pending_steps:
                break

            step = pending_steps[0]
            tracker.update_step_status(step.id, "in_progress")

            subtask_query = step.description
            await _call_callback(
                callbacks,
                "on_iteration",
                iteration + 1,
                max_iterations,
                subtask_query,
            )

            # NEW: Execute step with full context (Phase 3)
            subtask_query_with_context = self._build_subtask_query_with_full_context(
                step, tracker
            )

            logger.debug(f"Executing subtask: {subtask_query}")

            # NEW: Use _execute_with_tool_tracking() (Phase 3)
            result = await self._execute_with_tool_tracking(
                subtask_query_with_context,
                tracker=tracker,
                use_streaming=False,
                callbacks={k: v for k, v in callbacks.items() if k not in ["on_stream_chunk"]},
            )

            accumulated_results.append(
                {
                    "query": subtask_query,
                    "result": result,
                    "iteration": iteration,
                }
            )
            executed_queries.append(subtask_query)

            # NEW: Mark step as completed (Phase 3)
            tracker.update_step_status(step.id, "completed", findings=[result])

            # Phase 3: Evaluation
            logger.info("Phase 3: Evaluating completeness")
            await _call_callback(callbacks, "on_evaluation")

            evaluation = await self.evaluator.evaluate(
                query=query, results=accumulated_results, current_plan=plan
            )

            logger.info(
                f"Evaluation: complete={evaluation.is_complete}, "
                f"confidence={evaluation.confidence:.2f}"
            )

            # NEW: Store evaluation insights in tracker (Phase 3)
            tracker.insights.add_from_evaluation(evaluation)

            # Check if we're done
            if evaluation.is_complete:
                logger.info("Query fully answered, proceeding to synthesis")
                break

            # Phase 4: Plan adjustment if needed
            if (
                evaluation.additional_queries
                and iteration < max_iterations - 1
            ):
                logger.info(
                    f"Adding {len(evaluation.additional_queries)} additional queries"
                )
                # NEW: Add dynamic steps to tracker plan (Phase 3)
                if tracker.plan:
                    from nxs.application.progress_tracker import PlanStep

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
        await _call_callback(callbacks, "on_synthesis")

        # Filter results first
        filtered_results = await self.synthesizer.filter_results(
            query, accumulated_results
        )

        # Generate final answer
        final_answer = await self.synthesizer.synthesize(query, filtered_results)

        logger.info(
            f"Deep reasoning complete: {len(final_answer)} chars generated"
        )

        return final_answer

    async def _evaluate_response_quality(
        self,
        query: str,
        response: str,
        strategy_used: ExecutionStrategy,
        complexity: ComplexityAnalysis,
    ) -> EvaluationResult:
        """Evaluate response quality to determine if escalation needed.

        Quality criteria:
        - Completeness: Does it fully answer the query?
        - Accuracy: Is the information correct?
        - Depth: Is it detailed enough for the question?
        - Coherence: Is it well-structured and clear?

        Args:
            query: Original query
            response: Generated response to evaluate
            strategy_used: Which strategy produced this response
            complexity: Initial complexity analysis

        Returns:
            EvaluationResult with:
            - is_complete: True if quality is sufficient
            - confidence: Quality score (0.0 to 1.0)
            - reasoning: Explanation of quality assessment
            - missing_aspects: What's lacking (if insufficient)
        """
        logger.debug(
            f"Evaluating response quality: strategy={strategy_used.value}, "
            f"response_length={len(response)}"
        )

        # Use evaluator to assess response quality
        evaluation = await self.evaluator.evaluate_response_quality(
            query=query,
            response=response,
            strategy_used=strategy_used.value,
            expected_complexity=complexity,
        )

        # Apply minimum confidence threshold based on strategy
        # Higher strategies require higher confidence to avoid escalation
        min_confidence_thresholds = {
            ExecutionStrategy.DIRECT: self.config.min_quality_direct,
            ExecutionStrategy.LIGHT_PLANNING: self.config.min_quality_light,
            ExecutionStrategy.DEEP_REASONING: self.config.min_quality_deep,
        }

        min_confidence = min_confidence_thresholds.get(
            strategy_used, self.config.min_confidence
        )

        # Override is_complete based on confidence threshold
        if evaluation.confidence < min_confidence:
            evaluation.is_complete = False
            logger.debug(
                f"Quality below threshold: {evaluation.confidence:.2f} < {min_confidence}"
            )

        return evaluation

    def _build_subtask_query(
        self, step: Any, tracker: ResearchProgressTracker
    ) -> str:
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

    def _build_subtask_query_with_full_context(
        self, step: Any, tracker: ResearchProgressTracker
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

    def _get_context_for_strategy(
        self, tracker: ResearchProgressTracker, strategy: ExecutionStrategy
    ) -> str:
        """Get appropriate context verbosity for strategy.

        Args:
            tracker: ResearchProgressTracker instance
            strategy: Current execution strategy

        Returns:
            Context text appropriate for the strategy level
        """
        if len(tracker.attempts) == 1:
            # First attempt - minimal context
            return (
                f"Query: {tracker.query}\n"
                f"Complexity: {tracker.complexity.complexity_level.value}"
            )

        if strategy == ExecutionStrategy.DIRECT:
            return tracker.to_compact_context()
        elif strategy == ExecutionStrategy.LIGHT_PLANNING:
            return tracker.to_context_text(strategy)  # Medium detail
        else:  # DEEP_REASONING
            return tracker.to_context_text(strategy)  # Full detail

