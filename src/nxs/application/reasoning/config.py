"""Configuration for reasoning components."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ReasoningConfig:
    """Configuration for reasoning components."""

    # Iteration control
    max_iterations: int = 3
    min_confidence: float = 0.7

    # Complexity thresholds (for automatic routing)
    simple_threshold: float = 0.3  # Below this = SIMPLE
    complex_threshold: float = 0.7  # Above this = COMPLEX, between = MEDIUM

    # Quality thresholds (for self-correction)
    min_quality_direct: float = 0.6  # Minimum quality for DIRECT responses
    min_quality_light: float = 0.7  # Minimum quality for LIGHT responses
    min_quality_deep: float = 0.5  # Accept lower for DEEP (final attempt)

    # Model selection (can use different models for different phases)
    analysis_model: str = "claude-3-5-haiku-20241022"  # Fast, cheap for complexity analysis
    planning_model: str = "claude-3-5-sonnet-20241022"
    evaluation_model: str = "claude-3-5-sonnet-20241022"
    synthesis_model: str = "claude-3-5-sonnet-20241022"

    # Caching
    enable_caching: bool = True

    # Performance tuning
    max_subtasks: int = 5
    min_subtasks: int = 1
    parallel_execution: bool = False  # Future feature

    # Analysis caching
    cache_analysis: bool = True  # Cache similar queries
    analysis_cache_ttl: int = 3600  # 1 hour

    # Strategy overrides (for testing/debugging)
    force_strategy: Optional[str] = None  # "direct", "light", "deep", or None

    # Logging
    debug_mode: bool = False

