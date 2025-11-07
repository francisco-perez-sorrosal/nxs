from textual_autocomplete import TargetState, DropdownItem

from nxs.tui.completion.resource_completion import ResourceCompletionStrategy
from nxs.tui.completion.strategy import CompletionRequest


def make_state(text: str, cursor: int | None = None) -> TargetState:
    if cursor is None:
        cursor = len(text)
    return TargetState(text=text, cursor_position=cursor)


def test_resource_strategy_detects_at_trigger() -> None:
    strategy = ResourceCompletionStrategy(lambda: ["Docs/Intro.md", "Summary.txt"])
    request = CompletionRequest(make_state("See @Sum"))

    assert strategy.can_handle(request)

    candidates = strategy.get_candidates(request)
    assert {item.main for item in candidates} == {"Summary.txt"}


def test_resource_strategy_returns_all_when_no_query() -> None:
    strategy = ResourceCompletionStrategy(lambda: ["A", "B"])
    request = CompletionRequest(make_state("Read @"))

    candidates = strategy.get_candidates(request)
    assert len(candidates) == 2
    assert all(isinstance(item, DropdownItem) for item in candidates)

