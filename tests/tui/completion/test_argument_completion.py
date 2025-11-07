from types import SimpleNamespace

from textual_autocomplete import TargetState

from nxs.core.suggestions import ArgumentSuggestionGenerator
from nxs.tui.completion.argument_completion import ArgumentCompletionStrategy
from nxs.tui.completion.strategy import CompletionRequest


class StubPromptService:
    def __init__(self, schemas: dict[str, tuple[object, str]]):
        self._schemas = schemas

    def get_cached_schema(self, command: str):
        return self._schemas.get(command)


def make_state(text: str, cursor: int | None = None) -> TargetState:
    if cursor is None:
        cursor = len(text)
    return TargetState(text=text, cursor_position=cursor)


def test_argument_strategy_returns_suggestions() -> None:
    prompt = SimpleNamespace(
        arguments={
            "properties": {"topic": {"default": "report"}},
            "required": [],
        }
    )
    schemas = {"summarize": (prompt, "server")}
    service = StubPromptService(schemas)
    generator = ArgumentSuggestionGenerator(schemas)

    strategy = ArgumentCompletionStrategy(lambda: ["summarize"], service, generator)
    request = CompletionRequest(make_state("/summarize "))

    assert strategy.can_handle(request)

    candidates = strategy.get_candidates(request)
    assert candidates
    assert any(str(candidate.main).startswith("topic=") for candidate in candidates)


def test_argument_strategy_requires_known_command() -> None:
    schemas = {}
    service = StubPromptService(schemas)
    generator = ArgumentSuggestionGenerator(schemas)

    strategy = ArgumentCompletionStrategy(lambda: ["summarize"], service, generator)
    request = CompletionRequest(make_state("/unknown "))

    assert not strategy.can_handle(request)

