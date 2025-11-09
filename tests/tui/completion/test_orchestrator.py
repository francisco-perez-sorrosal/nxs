from textual_autocomplete import DropdownItem, TargetState

from nxs.presentation.completion.orchestrator import CompletionOrchestrator
from nxs.presentation.completion.strategy import CompletionRequest, CompletionStrategy


class StubStrategy(CompletionStrategy):
    def __init__(self, name: str, match: bool, result: list[str]):
        self.name = name
        self._match = match
        self._result = result
        self.calls = 0

    def can_handle(self, request: CompletionRequest) -> bool:
        self.calls += 1
        return self._match

    def get_candidates(self, request: CompletionRequest) -> list[DropdownItem]:
        return [DropdownItem(main=value) for value in self._result]


def test_orchestrator_selects_first_matching_strategy() -> None:
    strategies = [
        StubStrategy("A", match=False, result=[]),
        StubStrategy("B", match=True, result=["hit"]),
        StubStrategy("C", match=True, result=["miss"]),
    ]
    orchestrator = CompletionOrchestrator(strategies)

    state = TargetState(text="/", cursor_position=1)
    candidates = orchestrator.get_completions(state)

    assert [candidate.main for candidate in candidates] == ["hit"]
    assert strategies[0].calls == 1
    assert strategies[1].calls == 1
    assert strategies[2].calls == 0
