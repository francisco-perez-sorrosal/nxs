"""Execution strategies for the Adaptive Reasoning Loop.

This package contains the strategy pattern implementation for different
execution approaches:
- DirectExecutionStrategy: Fast-path with no planning
- LightPlanningStrategy: Quick planning with 1-2 iterations
- DeepReasoningStrategy: Full reasoning cycle with evaluation
"""

from nxs.application.strategies.base import ExecutionStrategy
from nxs.application.strategies.deep_reasoning import DeepReasoningStrategy
from nxs.application.strategies.direct import DirectExecutionStrategy
from nxs.application.strategies.light_planning import LightPlanningStrategy

__all__ = [
    "ExecutionStrategy",
    "DirectExecutionStrategy",
    "LightPlanningStrategy",
    "DeepReasoningStrategy",
]
