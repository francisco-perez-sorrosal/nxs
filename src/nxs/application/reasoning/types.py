"""Type definitions for reasoning system."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ComplexityLevel(Enum):
    """Query complexity levels."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class ExecutionStrategy(Enum):
    """Recommended execution strategies."""

    DIRECT = "direct"  # Fast-path: direct AgentLoop
    LIGHT_PLANNING = "light_planning"  # 1-2 iterations with minimal planning
    DEEP_REASONING = "deep_reasoning"  # Full reasoning with multiple iterations


@dataclass
class ComplexityAnalysis:
    """Result of query complexity analysis."""

    complexity_level: ComplexityLevel
    reasoning_required: bool
    recommended_strategy: ExecutionStrategy
    rationale: str
    estimated_iterations: int = 1
    confidence: float = 0.0

    # Analysis details
    requires_research: bool = False
    requires_synthesis: bool = False
    multi_part_query: bool = False
    tool_count_estimate: int = 0


@dataclass
class SubTask:
    """Individual subtask in a research plan."""

    query: str
    priority: int
    tool_hints: Optional[list[str]] = None
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ResearchPlan:
    """Plan for executing a complex query."""

    original_query: str
    subtasks: list[SubTask]
    max_iterations: int = 3
    estimated_complexity: str = "medium"  # low/medium/high
    complexity_analysis: Optional[ComplexityAnalysis] = None

    @property
    def current_step(self) -> Optional[SubTask]:
        """Get next subtask to execute."""
        return self.subtasks[0] if self.subtasks else None


@dataclass
class EvaluationResult:
    """Result of completeness or quality evaluation."""

    is_complete: bool
    confidence: float
    reasoning: str
    additional_queries: list[str] = field(default_factory=list)
    missing_aspects: list[str] = field(default_factory=list)

