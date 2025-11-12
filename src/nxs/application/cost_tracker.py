"""Cost tracker for accumulating token usage and costs.

This module provides a lightweight tracker for monitoring cumulative
token usage and costs across a conversation session.
"""

from dataclasses import dataclass, field
from typing import Optional

from nxs.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CostSummary:
    """Summary of session costs and token usage."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    round_count: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost": self.total_cost,
            "round_count": self.round_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CostSummary":
        """Create from dictionary."""
        return cls(
            total_input_tokens=data.get("total_input_tokens", 0),
            total_output_tokens=data.get("total_output_tokens", 0),
            total_cost=data.get("total_cost", 0.0),
            round_count=data.get("round_count", 0),
        )


class CostTracker:
    """Track cumulative token usage and costs.

    Thread-safe accumulation of token counts and costs across
    multiple conversation rounds. Lightweight and efficient.
    """

    def __init__(self, initial_summary: Optional[CostSummary] = None):
        """Initialize the cost tracker.

        Args:
            initial_summary: Optional initial summary (for restoring from persistence)
        """
        self._summary = initial_summary or CostSummary()
        logger.debug(
            f"CostTracker initialized: "
            f"{self._summary.total_input_tokens} input, "
            f"{self._summary.total_output_tokens} output tokens, "
            f"${self._summary.total_cost:.6f} total cost"
        )

    def add_usage(
        self, input_tokens: int, output_tokens: int, cost: float
    ) -> None:
        """Add token usage and cost for a conversation round.

        Args:
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens used
            cost: Cost in USD for this usage
        """
        self._summary.total_input_tokens += input_tokens
        self._summary.total_output_tokens += output_tokens
        self._summary.total_cost += cost
        self._summary.round_count += 1

        logger.debug(
            f"Added usage: +{input_tokens} input, +{output_tokens} output tokens, "
            f"+${cost:.6f} cost. "
            f"Session totals: {self._summary.total_input_tokens} input, "
            f"{self._summary.total_output_tokens} output, "
            f"${self._summary.total_cost:.6f} total"
        )

    def get_total(self) -> CostSummary:
        """Get current total usage and cost summary.

        Returns:
            CostSummary with cumulative totals
        """
        return self._summary

    def reset(self) -> None:
        """Reset all counters to zero."""
        logger.info("Resetting session cost tracker")
        self._summary = CostSummary()

    def to_dict(self) -> dict:
        """Serialize tracker state to dictionary.

        Returns:
            Dictionary representation for persistence
        """
        return self._summary.to_dict()

    @classmethod
    def from_dict(cls, data: dict) -> "CostTracker":
        """Create tracker from serialized data.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored CostTracker instance
        """
        summary = CostSummary.from_dict(data)
        return cls(initial_summary=summary)

