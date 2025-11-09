from types import SimpleNamespace

from textual_autocomplete import TargetState

from nxs.presentation.completion.applier import (
    CompletionApplier,
    compute_search_string,
    should_show_dropdown,
)


class StubPromptService:
    def __init__(self, schemas: dict[str, tuple[object, str]] | None = None):
        self._schemas = schemas or {}

    def get_cached_schema(self, command: str):
        return self._schemas.get(command)


def make_state(text: str, cursor: int | None = None) -> TargetState:
    if cursor is None:
        cursor = len(text)
    return TargetState(text=text, cursor_position=cursor)


def test_apply_resource_completion_adds_value() -> None:
    applier = CompletionApplier(StubPromptService())
    state = make_state("Read @")

    result = applier.apply("docs/guide.md", state)

    assert result.text == "Read @docs/guide.md "
    assert result.cursor == len("Read @docs/guide.md ")


def test_apply_command_completion_expands_arguments() -> None:
    prompt = SimpleNamespace(
        arguments={
            "properties": {
                "topic": {"default": "overview"},
                "audience": {},
            },
            "required": ["audience"],
        }
    )
    applier = CompletionApplier(StubPromptService({"run": (prompt, "server")}))  # type: ignore[arg-type]
    state = make_state("/")

    result = applier.apply("run (topic=overview)", state)

    assert result.text.replace(" ", "").startswith("/run")
    assert "topic=overview" in result.text
    assert "audience=<required>" in result.text


def test_apply_argument_suggestion_inserts_assignment() -> None:
    applier = CompletionApplier(StubPromptService())
    state = make_state("/run ")

    result = applier.apply("audience=<required>", state)

    assert result.text.startswith('/run audience="')


def test_compute_search_string_handles_resource_trigger() -> None:
    text = "see @doc"
    search = compute_search_string(text, cursor_position=len(text))
    assert search == "doc"


def test_should_show_dropdown_with_command_arguments() -> None:
    visible = should_show_dropdown("/run ")
    assert visible is True
