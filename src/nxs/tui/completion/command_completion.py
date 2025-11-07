"""
Command completion strategy for ``/`` triggers.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from textual_autocomplete import DropdownItem

from nxs.logger import get_logger
from nxs.tui.services.prompt_service import PromptService

from .strategy import CompletionRequest, CompletionStrategy
from .prompt_utils import get_command_arguments_with_defaults

logger = get_logger("autocomplete.command")


class CommandCompletionStrategy(CompletionStrategy):
    """Provides command suggestions when the user types ``/``."""

    def __init__(
        self,
        command_provider: Callable[[], Sequence[str]],
        prompt_service: PromptService,
    ) -> None:
        self._command_provider = command_provider
        self._prompt_service = prompt_service

    def can_handle(self, request: CompletionRequest) -> bool:
        text_before_cursor = request.text[: request.cursor_position]
        if not text_before_cursor.startswith("/"):
            return False

        command_text = text_before_cursor[1:]
        if not command_text:
            return True

        if " " not in command_text:
            return True

        # When a space is present we only handle the request if the
        # command is not recognised (so argument completion can take over).
        typed_command = command_text.split(" ", 1)[0]
        available_commands = set(self._command_provider())
        return typed_command not in available_commands

    def get_candidates(self, request: CompletionRequest) -> list[DropdownItem]:
        commands = list(self._command_provider())
        text_before_cursor = request.text[: request.cursor_position]
        command_text = text_before_cursor[1:]
        search_part = command_text.split(" ", 1)[0] if command_text else ""
        prefix = search_part.lower()

        if prefix:
            filtered = [
                cmd
                for cmd in commands
                if prefix in cmd.lower() or cmd.lower().startswith(prefix)
            ]
        else:
            filtered = commands

        logger.debug(
            "CommandCompletionStrategy triggered (prefix=%r, matches=%d)",
            prefix,
            len(filtered),
        )

        items: list[DropdownItem] = []
        for command in filtered:
            display = self._format_command_display(command)
            items.append(DropdownItem(main=display, prefix="⚡"))

        return items

    def _format_command_display(self, command: str) -> str:
        arg_info = get_command_arguments_with_defaults(self._prompt_service, command)
        if arg_info:
            logger.debug("Command '%s' has defaulted args: %s", command, arg_info)
            return f"{command} ({arg_info})"
        logger.debug("Command '%s' has no defaulted args", command)
        return command

