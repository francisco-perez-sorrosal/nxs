"""
Argument completion strategy for command arguments.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from textual_autocomplete import DropdownItem

from nxs.application.suggestions import ArgumentSuggestionGenerator
from nxs.logger import get_logger
from nxs.presentation.services.prompt_service import PromptService

from .strategy import CompletionRequest, CompletionStrategy

logger = get_logger("autocomplete.argument")


class ArgumentCompletionStrategy(CompletionStrategy):
    """Suggests arguments once a valid command has been entered."""

    def __init__(
        self,
        command_provider: Callable[[], Sequence[str]],
        prompt_service: PromptService,
        suggestion_generator: ArgumentSuggestionGenerator,
    ) -> None:
        self._command_provider = command_provider
        self._prompt_service = prompt_service
        self._suggestion_generator = suggestion_generator

    def can_handle(self, request: CompletionRequest) -> bool:
        text_before_cursor = request.text[: request.cursor_position]
        if not text_before_cursor.startswith("/"):
            return False

        if " " not in text_before_cursor:
            return False

        command_part = text_before_cursor[1:].split(" ", 1)[0]
        available_commands = set(self._command_provider())
        if command_part not in available_commands:
            return False

        has_schema = self._prompt_service.get_cached_schema(command_part) is not None
        logger.debug(
            "ArgumentCompletionStrategy command=%r has_schema=%s",
            command_part,
            has_schema,
        )
        return has_schema

    def get_candidates(self, request: CompletionRequest) -> list[DropdownItem]:
        text_before_cursor = request.text[: request.cursor_position]
        command_part, remaining = self._split_command(text_before_cursor)
        if command_part is None:
            return []

        suggestions = self._suggestion_generator.generate_suggestions(command_part, remaining)
        logger.debug(
            "ArgumentCompletionStrategy returning %d suggestions for command %r",
            len(suggestions),
            command_part,
        )

        if not suggestions:
            cached_schema = self._prompt_service.get_cached_schema(command_part)
            if cached_schema is None:
                logger.warning(
                    "Command '%s' missing schema cache during argument completion",
                    command_part,
                )
        return suggestions

    def _split_command(self, text_before_cursor: str) -> tuple[str | None, str]:
        stripped = text_before_cursor[1:].strip()
        if not stripped:
            return None, ""

        if " " in stripped:
            command, remainder = stripped.split(" ", 1)
        else:
            command, remainder = stripped, ""

        return command, remainder
