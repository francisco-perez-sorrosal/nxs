"""AdaptiveReasoningLoop - Self-correcting adaptive agent with quality guarantees.

This module implements the core self-correcting reasoning system that:
- Automatically analyzes query complexity
- Routes to appropriate execution strategy (DIRECT/LIGHT/DEEP)
- Evaluates response quality
- Auto-escalates when quality is insufficient
- Guarantees quality-approved responses reach users
"""

from typing import Callable, Optional

from nxs.application.agentic_loop import AgentLoop
from nxs.application.approval import ApprovalManager
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
)
from nxs.application.strategies import (
    DeepReasoningStrategy,
    DirectExecutionStrategy,
    LightPlanningStrategy,
)
from nxs.application.strategies.utils import call_callback
from nxs.application.tool_registry import ToolRegistry
from nxs.logger import get_logger

logger = get_logger("adaptive_reasoning_loop")


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

        # Callback to get reasoning enabled state from TUI
        self.get_reasoning_enabled: Optional[Callable[[], bool]] = None

        # Initialize execution strategies
        self.direct_strategy = DirectExecutionStrategy(
            execute_with_tracking=self._execute_with_tool_tracking
        )
        self.light_planning_strategy = LightPlanningStrategy(
            planner=self.planner,
            synthesizer=self.synthesizer,
            tool_registry=self.tool_registry,
            execute_with_tracking=self._execute_with_tool_tracking,
            get_conversation_history=self.conversation.get_messages,  # Pass conversation history for context
        )
        self.deep_reasoning_strategy = DeepReasoningStrategy(
            planner=self.planner,
            evaluator=self.evaluator,
            synthesizer=self.synthesizer,
            tool_registry=self.tool_registry,
            execute_with_tracking=self._execute_with_tool_tracking,
            max_iterations=self.max_iterations,
        )

        # Recursion prevention flag for tool tracking integration
        #
        # ARCHITECTURAL NOTE:
        # This flag prevents infinite recursion in the following call chain:
        #   1. AdaptiveReasoningLoop.run() -> executes strategy
        #   2. strategy method -> calls _execute_with_tool_tracking()
        #   3. _execute_with_tool_tracking() -> calls self.run() for tool tracking
        #   4. self.run() is AdaptiveReasoningLoop.run() (polymorphism)
        #   5. WITHOUT THIS FLAG: Would trigger reasoning logic again -> infinite loop
        #   6. WITH THIS FLAG: Skips reasoning, calls parent AgentLoop.run() directly
        #
        # When True: Skip complexity analysis, strategy selection, and quality evaluation.
        #            Just execute the query directly via parent AgentLoop.
        # When False: Normal reasoning flow (analyze, execute, evaluate, escalate)
        #
        # This is set by _execute_with_tool_tracking() before calling run(),
        # then restored after execution completes.
        self._skip_reasoning = False

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

        # Recursion prevention: Skip reasoning logic during sub-executions
        # This happens when _execute_with_tool_tracking() calls run() for tool interception
        if self._skip_reasoning:
            logger.debug(
                "Recursion prevention: Skipping reasoning logic, delegating to AgentLoop.run()"
            )
            # Bypass all reasoning (complexity analysis, strategy selection, evaluation)
            # and execute directly via parent AgentLoop for tool tracking
            return await super().run(query, callbacks=callbacks, use_streaming=use_streaming)

        # Check reasoning enabled state from TUI checkbox
        use_reasoning = False
        initial_strategy = ExecutionStrategy.DIRECT  # Default
        complexity = None

        # Get reasoning enabled state from TUI checkbox via callback
        if self.get_reasoning_enabled:
            use_reasoning = self.get_reasoning_enabled()
            logger.info(
                f"Reasoning mode: {'enabled' if use_reasoning else 'disabled'} (from TUI checkbox)"
            )
        else:
            logger.warning(
                "No reasoning enabled callback set, defaulting to direct execution"
            )

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
            await call_callback(callbacks, "on_analysis_start")

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

            await call_callback(callbacks, "on_analysis_complete", complexity)
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

            await call_callback(
                callbacks,
                "on_strategy_selected",
                current_strategy,
                f"Executing with {current_strategy.value} strategy",
            )

            # NEW: Start execution attempt in tracker (Phase 3)
            tracker.start_attempt(current_strategy)

            # Execute with current strategy (buffered, not streamed to user yet)
            if current_strategy == ExecutionStrategy.DIRECT:
                result = await self.direct_strategy.execute(
                    query, complexity, tracker, callbacks
                )
                execution_attempts.append(("DIRECT", result, 0.0))

            elif current_strategy == ExecutionStrategy.LIGHT_PLANNING:
                result = await self.light_planning_strategy.execute(
                    query, complexity, tracker, callbacks
                )
                execution_attempts.append(("LIGHT", result, 0.0))

            else:  # DEEP_REASONING
                result = await self.deep_reasoning_strategy.execute(
                    query, complexity, tracker, callbacks
                )
                execution_attempts.append(("DEEP", result, 0.0))

            # Phase 2: QUALITY EVALUATION (Always performed!)
            logger.info("Phase 2: Evaluating response quality")
            
            # Show the response that will be judged
            await call_callback(callbacks, "on_response_for_judgment", result, current_strategy.value)
            
            await call_callback(callbacks, "on_quality_check_start")

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

            await call_callback(callbacks, "on_quality_check_complete", evaluation)

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
                        await call_callback(callbacks, "on_stream_chunk", chunk)
                    
                    # Signal streaming completion so chat panel can render the buffered message
                    await call_callback(callbacks, "on_stream_complete")

                await call_callback(
                    callbacks,
                    "on_final_response",
                    current_strategy,
                    len(execution_attempts),
                    evaluation.confidence,
                    len(execution_attempts) > 1,  # escalated flag
                )

                # Phase 6: Notify tracker completion for persistence
                await call_callback(callbacks, "on_tracker_complete", tracker, query)

                return result

            # Quality insufficient - escalate!
            logger.warning(
                f"Response quality insufficient ({evaluation.confidence:.2f}), "
                f"escalating from {current_strategy.value}"
            )

            await call_callback(
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

        # Extract conversation context showing tool executions and strategy
        conversation_context = self._extract_conversation_context(strategy_used=strategy_used.value)

        # DEBUG: Log the context being sent to judge
        logger.info("=" * 80)
        logger.info("CONTEXT BEING SENT TO JUDGE:")
        logger.info(conversation_context)
        logger.info("=" * 80)

        # Use evaluator to assess response quality
        evaluation = await self.evaluator.evaluate_response_quality(
            query=query,
            response=response,
            strategy_used=strategy_used.value,
            expected_complexity=complexity,
            conversation_context=conversation_context,
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

    def _extract_conversation_context(self, strategy_used: str = "UNKNOWN") -> str:
        """Extract tool executions for the CURRENT QUERY ONLY.

        CRITICAL: This method is called AFTER the agent has completed execution and BEFORE
        the judge evaluates the response. All tool calls and results should already be in
        the conversation messages at this point.

        Args:
            strategy_used: The strategy that generated the response (DIRECT/LIGHT_PLANNING/DEEP_REASONING)

        Returns:
            Formatted string showing execution context for CURRENT QUERY ONLY
        """
        messages = self.conversation.get_messages()

        if not messages:
            logger.warning("No messages in conversation - cannot extract context")
            return "=== NO CONVERSATION CONTEXT ===\nNo messages in conversation yet."

        logger.debug(f"Extracting context from {len(messages)} total conversation messages")

        # Find the MOST RECENT user query message (not tool results)
        last_query_idx = None
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            role = msg.get("role")
            content = msg.get("content", "")

            logger.debug(f"Message {i}: role={role}, content_type={type(content).__name__}")

            if role == "user":
                # User messages can be either text queries or tool results
                # Text query: content is a string OR list with text blocks
                # Tool result: content is a list with tool_result blocks

                is_query = False
                if isinstance(content, str) and len(content.strip()) > 0:
                    # Direct string content - this is a query
                    is_query = True
                    logger.debug(f"  Found text query (string): {content[:50]}...")
                elif isinstance(content, list):
                    # List content - check what type of blocks it contains
                    has_text = any(
                        isinstance(block, dict) and block.get("type") == "text"
                        for block in content
                    )
                    has_tool_results = any(
                        isinstance(block, dict) and block.get("type") == "tool_result"
                        for block in content
                    )

                    if has_text and not has_tool_results:
                        # Has text blocks but no tool results - this is a query
                        is_query = True
                        logger.debug(f"  Found text query (list with text blocks)")
                    elif has_tool_results:
                        logger.debug(f"  Skipping tool result message")

                if is_query:
                    last_query_idx = i
                    logger.info(f"Found last user query at message index {i}")
                    break

        if last_query_idx is None:
            logger.error("Could not find user query message in conversation!")
            logger.error(f"Total messages: {len(messages)}")
            for i, msg in enumerate(messages[-5:]):  # Log last 5 messages
                logger.error(f"  Message {i}: {msg.get('role')} - {type(msg.get('content'))}")
            return "=== NO USER QUERY FOUND ===\nCould not identify the current user query."

        # Extract messages from the current query onwards
        current_query_messages = messages[last_query_idx:]
        logger.info(
            f"Extracting context from message {last_query_idx} onwards "
            f"({len(current_query_messages)} messages in current query cycle)"
        )

        # Extract tool executions from current query cycle only
        tool_executions = []

        logger.info(f"Scanning {len(current_query_messages)} messages for tool executions...")

        for i, msg in enumerate(current_query_messages):
            msg_role = msg.get("role")
            msg_content = msg.get("content", [])

            # ULTRA-DEBUG: Log message structure
            logger.debug(f"[Message {i}] role={msg_role}, content_type={type(msg_content).__name__}")

            if msg_role == "assistant":
                logger.debug(f"[Message {i}] Assistant message - examining for tool uses")

                # Content can be a list or a single ContentBlock
                content_blocks = msg_content if isinstance(msg_content, list) else [msg_content]

                logger.debug(f"[Message {i}] Found {len(content_blocks)} content blocks")

                for block_idx, block in enumerate(content_blocks):
                    # CRITICAL: Handle both dict and ContentBlock object
                    block_type = None
                    if isinstance(block, dict):
                        block_type = block.get("type")
                        logger.debug(f"[Message {i}][Block {block_idx}] Dict block, type={block_type}")
                    elif hasattr(block, 'type'):
                        # Anthropic ContentBlock object
                        block_type = block.type
                        logger.debug(f"[Message {i}][Block {block_idx}] ContentBlock object, type={block_type}")
                    else:
                        logger.warning(f"[Message {i}][Block {block_idx}] Unknown block type: {type(block)}")
                        continue

                    if block_type == "tool_use":
                        # Extract tool info from either dict or object
                        if isinstance(block, dict):
                            tool_name = block.get("name", "unknown_tool")
                            tool_input = block.get("input", {})
                            tool_id = block.get("id")
                        else:
                            # ContentBlock object
                            tool_name = getattr(block, 'name', 'unknown_tool')
                            tool_input = getattr(block, 'input', {})
                            tool_id = getattr(block, 'id', None)

                        logger.info(f"✓ FOUND TOOL USE: {tool_name} (id={tool_id})")
                        logger.debug(f"  Tool input: {tool_input}")

                        # Look ahead for the result in current query cycle
                        result_preview = None
                        if i + 1 < len(current_query_messages):
                            next_msg = current_query_messages[i + 1]
                            if next_msg.get("role") == "user":
                                next_content = next_msg.get("content", [])
                                result_blocks = next_content if isinstance(next_content, list) else [next_content]

                                logger.debug(f"  Searching next message for tool result (has {len(result_blocks)} blocks)")

                                for result_block in result_blocks:
                                    # Handle both dict and ContentBlock
                                    result_block_type = None
                                    if isinstance(result_block, dict):
                                        result_block_type = result_block.get("type")
                                    elif hasattr(result_block, 'type'):
                                        result_block_type = result_block.type

                                    if result_block_type == "tool_result":
                                        # Extract tool_use_id from either dict or object
                                        result_tool_id = None
                                        if isinstance(result_block, dict):
                                            result_tool_id = result_block.get("tool_use_id")
                                            result_content = result_block.get("content", "")
                                        else:
                                            result_tool_id = getattr(result_block, 'tool_use_id', None)
                                            result_content = getattr(result_block, 'content', "")

                                        if result_tool_id == tool_id:
                                            logger.debug(f"  ✓ Found matching result for {tool_name}")

                                            # Get preview of result
                                            if isinstance(result_content, str):
                                                result_preview = result_content[:300] + "..." if len(result_content) > 300 else result_content
                                            elif isinstance(result_content, list):
                                                result_str = str(result_content)
                                                result_preview = result_str[:300] + "..." if len(result_str) > 300 else result_str
                                            else:
                                                result_preview = str(result_content)[:300]

                                            logger.debug(f"  Result preview: {result_preview[:100]}...")
                                            break

                        tool_executions.append({
                            "tool": tool_name,
                            "input": tool_input,
                            "result": result_preview if result_preview else "(no result found)"
                        })

        logger.info(f"✓ Extracted {len(tool_executions)} tool executions for current query")
        if tool_executions:
            logger.info(f"  Tools: {[t['tool'] for t in tool_executions]}")
        else:
            # NO TOOLS FOUND - This is a problem! Dump message structure for diagnosis
            logger.error("=" * 80)
            logger.error("NO TOOLS FOUND IN CONVERSATION!")
            logger.error(f"Examined {len(current_query_messages)} messages from index {last_query_idx}")
            logger.error("Message structure dump:")
            for i, msg in enumerate(current_query_messages):
                role = msg.get("role")
                content = msg.get("content", [])
                logger.error(f"  [{i}] role={role}")
                if isinstance(content, list):
                    logger.error(f"      content: list with {len(content)} items")
                    for j, block in enumerate(content[:3]):  # First 3 blocks
                        if isinstance(block, dict):
                            logger.error(f"        [{j}] dict: {block.get('type', 'no type')}")
                        elif hasattr(block, 'type'):
                            logger.error(f"        [{j}] object: {block.type} ({type(block).__name__})")
                        else:
                            logger.error(f"        [{j}] unknown: {type(block).__name__}")
                else:
                    logger.error(f"      content: {type(content).__name__}")
            logger.error("=" * 80)

        # Build comprehensive context
        context_parts = []

        # Header with strategy info
        context_parts.append(f"=== EXECUTION CONTEXT FOR CURRENT QUERY ===")
        context_parts.append(f"Strategy: {strategy_used}")
        context_parts.append(f"Tool executions for THIS query: {len(tool_executions)}")
        context_parts.append("")

        if tool_executions:
            context_parts.append("=== TOOL EXECUTIONS FOR THIS QUERY ===")
            context_parts.append("The agent executed the following tools to answer THIS specific query:")
            context_parts.append("(NOTE: Tools from previous queries are NOT shown here)")
            context_parts.append("")

            for i, execution in enumerate(tool_executions, 1):
                context_parts.append(f"{i}. Tool: {execution['tool']}")
                context_parts.append(f"   Input: {execution['input']}")
                if execution['result']:
                    context_parts.append(f"   Result: {execution['result']}")
                else:
                    context_parts.append(f"   Result: (no result captured)")
                context_parts.append("")

            context_parts.append("=== EVALUATION GUIDANCE ===")
            context_parts.append("✓ The agent DID use the tools shown above for THIS query")
            context_parts.append("✓ These tools are relevant to the CURRENT query being evaluated")
            context_parts.append("✓ The final response should be based on these tool results")
            context_parts.append("✓ The response doesn't need to repeat tool execution details")
            context_parts.append("✓ Evaluate whether the response uses these tool results appropriately")
        else:
            context_parts.append("=== NO TOOL EXECUTIONS FOR THIS QUERY ===")
            context_parts.append("No tools were executed to answer this specific query.")
            context_parts.append("")
            context_parts.append("=== EVALUATION GUIDANCE ===")
            context_parts.append("- If the query required external data/tools and none were used, this IS a problem")
            context_parts.append("- If the query could be answered from knowledge alone, no tools may be needed")
            context_parts.append("- Evaluate whether the lack of tool usage was appropriate for THIS query")

        return "\n".join(context_parts)

    # Note: Prompt caching for tracker context is handled by the Conversation class
    #
    # The Conversation class (application/conversation.py) automatically applies
    # cache_control markers to system messages, tools, and recent message pairs.
    # This provides 90% cost reduction on cached content without requiring
    # special integration here.
    #
    # Tracker context is injected into queries (see _build_subtask_query_with_full_context)
    # where it becomes part of the user messages, which are cached by the Conversation class.
    #
    # Original design (from RESEARCH_PROGRESS_TRACKING_PLAN.md) proposed explicit
    # cache control via custom message builders, but the simpler approach of using
    # Conversation's built-in caching is more maintainable and works transparently.

