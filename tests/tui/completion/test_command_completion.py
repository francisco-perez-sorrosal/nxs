from types import SimpleNamespace

from textual_autocomplete import TargetState

from nxs.tui.completion.command_completion import CommandCompletionStrategy
from nxs.tui.completion.strategy import CompletionRequest


class StubPromptService:
    def __init__(self, schemas: dict[str, tuple[object, str]] | None = None):
        self._schemas = schemas or {}

    def get_cached_schema(self, command: str):
        return self._schemas.get(command)


def make_state(text: str, cursor: int | None = None) -> TargetState:
    if cursor is None:
        cursor = len(text)
    return TargetState(text=text, cursor_position=cursor)


def test_command_strategy_filters_matches() -> None:
    prompt = SimpleNamespace(
        arguments={
            "properties": {"foo": {"default": "bar"}},
            "required": [],
        }
    )
    service = StubPromptService({"run": (prompt, "server")})
    strategy = CommandCompletionStrategy(lambda: ["run", "list"], service)

    request = CompletionRequest(make_state("/r"))
    assert strategy.can_handle(request)

    candidates = strategy.get_candidates(request)
    assert any("run (foo=bar)" == candidate.main for candidate in candidates)


def test_command_strategy_ignores_known_command_with_args() -> None:
    service = StubPromptService()
    strategy = CommandCompletionStrategy(lambda: ["run"], service)

    request = CompletionRequest(make_state("/run arg"))
    assert not strategy.can_handle(request)

