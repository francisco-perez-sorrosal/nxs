"""
Orchestrator that coordinates completion strategies.
"""

from __future__ import annotations

from collections.abc import Sequence

from textual_autocomplete import DropdownItem, TargetState

from nxs.logger import get_logger

from .strategy import CompletionRequest, CompletionStrategy

logger = get_logger("autocomplete.orchestrator")


class CompletionOrchestrator:
    """Selects the first strategy able to serve the current request."""

    def __init__(self, strategies: Sequence[CompletionStrategy]) -> None:
        self._strategies = list(strategies)

    def get_completions(self, state: TargetState) -> list[DropdownItem]:
        request = CompletionRequest(state)
        for strategy in self._strategies:
            try:
                if strategy.can_handle(request):
                    logger.debug("Strategy %s selected for completion", strategy.__class__.__name__)
                    return strategy.get_candidates(request)
            except Exception:
                logger.exception(
                    "Completion strategy %s failed",
                    strategy.__class__.__name__,
                )
        logger.debug("No completion strategy matched current input")
        return []
