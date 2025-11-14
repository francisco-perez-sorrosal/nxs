"""Direct execution strategy.

Fast-path execution with no planning overhead.
Good for simple, straightforward queries.
"""

from typing import Callable

from nxs.application.progress_tracker import ResearchProgressTracker
from nxs.application.reasoning.types import ComplexityAnalysis
from nxs.application.strategies.base import ExecutionStrategy as BaseExecutionStrategy
from nxs.application.strategies.utils import call_callback
from nxs.logger import get_logger

logger = get_logger("direct_execution_strategy")


class DirectExecutionStrategy(BaseExecutionStrategy):
    """Direct execution strategy for simple queries (fast-path).

    This strategy provides the fastest execution path with minimal overhead,
    suitable for simple, straightforward queries that don't require planning
    or multi-step reasoning.

    Characteristics:
    - No planning overhead
    - Direct execution via AgentLoop
    - Single-pass processing
    - Adds escalation context for retries

    Use Cases:
    - Simple factual queries
    - Direct API calls
    - Quick lookups
    - Initial attempt before escalation

    Example:
        >>> strategy = DirectExecutionStrategy(execute_with_tracking=loop._execute_with_tool_tracking)
        >>> result = await strategy.execute(query, complexity, tracker, callbacks)
    """

    def __init__(self, execute_with_tracking: Callable):
        """Initialize direct execution strategy.

        Args:
            execute_with_tracking: Async callable that executes queries with tool tracking.
                Signature: async (query, tracker, use_streaming, callbacks) -> str
                This handles the actual LLM execution with tool call interception.
        """
        self.execute_with_tracking = execute_with_tracking

    async def execute(
        self,
        query: str,
        complexity: ComplexityAnalysis,
        tracker: ResearchProgressTracker,
        callbacks: dict[str, Callable],
    ) -> str:
        """Execute query using direct strategy (fast-path).

        This method performs single-pass execution without planning overhead.
        If this is an escalation (retry after failed attempt), it adds compact
        context from previous attempts to help improve the response.

        Workflow:
        1. Check if this is an escalation (multiple attempts exist)
        2. Add previous attempt context if applicable
        3. Execute query with tool tracking
        4. Return buffered result (not yet quality-checked)

        Args:
            query: User's query string
            complexity: Complexity analysis result (not used, kept for API consistency)
            tracker: ResearchProgressTracker tracking execution history and context
            callbacks: Callback dictionary for status updates (e.g., "on_direct_execution")

        Returns:
            Response text (buffered, not yet streamed or quality-checked)

        Note:
            The complexity parameter is not used in direct execution but is
            part of the common interface for all execution strategies.
        """
        logger.info("Direct execution (fast-path)")
        await call_callback(callbacks, "on_direct_execution")

        # Add tracker context if this is an escalation
        if len(tracker.attempts) > 1:
            # This is a retry after failed attempt
            context_text = tracker.to_compact_context()
            enhanced_query = f"{query}\n\n[Previous attempt context: {context_text}]"
            logger.debug("Added compact tracker context to DIRECT execution")
        else:
            enhanced_query = query

        # Use execute_with_tracking for tool interception
        result = await self.execute_with_tracking(
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
