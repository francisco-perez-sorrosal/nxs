"""Base execution strategy interface.

This module defines the base interface for all execution strategies
used in the AdaptiveReasoningLoop.
"""

from abc import ABC, abstractmethod
from typing import Callable

from nxs.application.progress_tracker import ResearchProgressTracker
from nxs.application.reasoning.types import ComplexityAnalysis


class ExecutionStrategy(ABC):
    """Base interface for execution strategies.

    Each strategy implements a different approach to query execution:
    - Direct: Fast-path with no planning
    - Light Planning: Quick planning with 1-2 iterations
    - Deep Reasoning: Full reasoning cycle with evaluation
    """

    @abstractmethod
    async def execute(
        self,
        query: str,
        complexity: ComplexityAnalysis,
        tracker: ResearchProgressTracker,
        callbacks: dict[str, Callable],
    ) -> str:
        """Execute the strategy.

        Args:
            query: User query
            complexity: Complexity analysis
            tracker: ResearchProgressTracker instance
            callbacks: Callback dictionary

        Returns:
            Response text (buffered, not yet quality-checked)
        """
        pass
