"""
Strategy interfaces for autocomplete completions.

These abstractions make it possible to decompose the behaviour of the
autocomplete widget into focused, testable components.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from textual_autocomplete import DropdownItem, TargetState


@dataclass(slots=True)
class CompletionRequest:
    """Snapshot of the target input state used by completion strategies."""

    state: TargetState

    @property
    def text(self) -> str:
        """Current input text for convenience."""
        return self.state.text

    @property
    def cursor_position(self) -> int:
        """Cursor position convenience accessor."""
        return self.state.cursor_position


class CompletionStrategy(Protocol):
    """Contract implemented by all autocomplete strategies."""

    def can_handle(self, request: CompletionRequest) -> bool:
        """Return ``True`` when this strategy should produce candidates."""

        ...

    def get_candidates(self, request: CompletionRequest) -> list[DropdownItem]:
        """Return dropdown items for the current state."""

        ...

