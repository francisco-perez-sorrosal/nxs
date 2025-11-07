"""
Utilities for applying selected autocomplete values to the input field.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual_autocomplete import TargetState

from nxs.core.parsers.utils import (
    extract_value_part,
    is_inside_quotes,
    parse_command_arguments,
)
from nxs.logger import get_logger
from nxs.tui.services.prompt_service import PromptService

from .prompt_utils import expand_command_with_arguments

logger = get_logger("autocomplete.applier")


@dataclass(slots=True)
class ApplyResult:
    """Result of applying a completion value."""

    text: str
    cursor: int


class CompletionApplier:
    """Encapsulates the logic for injecting completion values into the input."""

    def __init__(self, prompt_service: PromptService) -> None:
        self._prompt_service = prompt_service

    def apply(self, value: str, state: TargetState) -> ApplyResult:
        logger.info("apply: value=%r text=%r cursor=%d", value, state.text, state.cursor_position)

        stripped_value = value.strip()
        is_argument, argument_value = self._detect_argument_suggestion(stripped_value)

        if is_argument and argument_value:
            return self._apply_argument_suggestion(argument_value, state)

        return self._apply_general_completion(stripped_value, state)

    def _detect_argument_suggestion(self, stripped_value: str) -> tuple[bool, str | None]:
        token = stripped_value.split(" ", 1)[0]

        if token.endswith("?"):
            arg_text = token.rstrip("?").strip()
            logger.info("Detected optional argument suggestion: %s", arg_text)
            return True, arg_text

        if "=" in token:
            left, right = token.split("=", 1)
            if left and any(ch.isalnum() or ch in '".@/' for ch in right):
                arg_text = token.strip()
                logger.info("Detected argument suggestion: %s", arg_text)
                return True, arg_text

        return False, None

    def _apply_argument_suggestion(self, arg_text: str, state: TargetState) -> ApplyResult:
        text = state.text
        cursor_pos = state.cursor_position

        text_before_cursor = text[:cursor_pos]
        text_after_cursor = text[cursor_pos:]

        if not text_before_cursor.startswith("/"):
            new_text = f"{text_before_cursor}{arg_text} {text_after_cursor}"
            new_cursor = len(text_before_cursor) + len(arg_text) + 1
            return ApplyResult(text=new_text, cursor=new_cursor)

        command_section = text_before_cursor[1:].strip()
        if " " not in command_section:
            command = command_section
            arg_text = self._ensure_assignment_format(arg_text)
            new_text = f"/{command} {arg_text}{text_after_cursor}"
            new_cursor = len(f"/{command} {arg_text}")
            return ApplyResult(text=new_text, cursor=new_cursor)

        command, existing_args = command_section.split(" ", 1)
        arg_parts = parse_command_arguments(existing_args)

        incomplete_arg_index = self._find_incomplete_argument(arg_parts)
        selected_text = self._ensure_assignment_format(arg_text)

        if incomplete_arg_index is not None:
            complete_prefix = " ".join(arg_parts[:incomplete_arg_index]) if incomplete_arg_index > 0 else ""
            prefix = f"{complete_prefix} " if complete_prefix else ""
            new_args = f"{prefix}{selected_text}".strip()
            new_value = f"/{command} {new_args}{text_after_cursor}"
            new_cursor = len(f"/{command} {new_args}")
            logger.info(
                "Replacing incomplete argument (index=%d) with %s",
                incomplete_arg_index,
                selected_text,
            )
            return ApplyResult(text=new_value, cursor=new_cursor)

        existing_clean = self._close_unterminated_quotes(existing_args.rstrip())
        joined = f"{existing_clean} {selected_text}".strip()
        new_value = f"/{command} {joined}{text_after_cursor}"
        new_cursor = len(f"/{command} {joined}")
        logger.info("Appending new argument %s after existing args", selected_text)
        return ApplyResult(text=new_value, cursor=new_cursor)

    def _apply_general_completion(self, value: str, state: TargetState) -> ApplyResult:
        text = state.text
        cursor_pos = state.cursor_position
        text_before_cursor = text[:cursor_pos]
        text_after_cursor = text[cursor_pos:]

        if " (" in value and value.endswith(")"):
            command_name = value.split(" (", 1)[0]
        else:
            command_name = value

        if "@" in text_before_cursor:
            last_at = text_before_cursor.rfind("@")
            new_text = f"{text[:last_at]}@{command_name} {text_after_cursor}"
            new_cursor = last_at + len(command_name) + 2
            logger.info("Applied resource completion at index %d", last_at)
            return ApplyResult(text=new_text, cursor=new_cursor)

        if text_before_cursor.startswith("/"):
            remainder = text_before_cursor[1:].strip()
            if " " in remainder:
                _, rest = remainder.split(" ", 1)
                new_text = f"/{command_name} {rest}{text_after_cursor}"
                new_cursor = len(f"/{command_name} {rest}")
                return ApplyResult(text=new_text, cursor=new_cursor)

            expanded = expand_command_with_arguments(self._prompt_service, command_name)
            new_text = f"/{expanded} {text_after_cursor}"
            new_cursor = len(expanded) + 2
            logger.info("Expanded command '%s' to '%s'", command_name, expanded)
            return ApplyResult(text=new_text, cursor=new_cursor)

        new_text = f"{text_before_cursor}{command_name}{text_after_cursor}"
        new_cursor = cursor_pos + len(command_name)
        return ApplyResult(text=new_text, cursor=new_cursor)

    def _ensure_assignment_format(self, arg_text: str) -> str:
        if "=" not in arg_text:
            return f"{arg_text}="

        name, value_part = arg_text.split("=", 1)
        if value_part.startswith('"'):
            return arg_text
        if value_part:
            return f'{name}="{value_part}'
        return f"{name}="

    def _find_incomplete_argument(self, arg_parts: list[str]) -> int | None:
        for index in range(len(arg_parts) - 1, -1, -1):
            parsed = extract_value_part(arg_parts[index])
            if not parsed:
                return index

            _, value_part = parsed
            if value_part.startswith('"'):
                if value_part.count('"') >= 2 and value_part.count('"') % 2 == 0:
                    continue
                return None
            if value_part.strip():
                continue
        return None

    def _close_unterminated_quotes(self, existing_text: str) -> str:
        if not existing_text:
            return existing_text

        last_equals = existing_text.rfind("=")
        if last_equals < 0:
            return existing_text

        value_part = existing_text[last_equals + 1 :].strip()
        if not value_part.startswith('"'):
            return existing_text

        if value_part.endswith('"') and value_part.count('"') >= 2:
            return existing_text

        return existing_text + '"'


def should_show_dropdown(text_before_cursor: str) -> bool:
    """Determine whether the dropdown should be visible."""
    if "@" in text_before_cursor:
        last_at = text_before_cursor.rfind("@")
        if " " not in text_before_cursor[last_at:]:
            return True

    if not text_before_cursor.startswith("/"):
        return False

    search = text_before_cursor[1:]
    if " " not in search:
        return True

    parts = search.split(" ", 1)
    arg_text = parts[1] if len(parts) > 1 else ""

    if not arg_text.strip():
        return True

    arg_parts = parse_command_arguments(arg_text)
    if not arg_parts:
        return True

    last_part = arg_parts[-1]
    parsed = extract_value_part(last_part)
    if parsed:
        _, value_part = parsed
        if value_part.startswith('"'):
            if is_inside_quotes(value_part):
                return False
            if value_part.count('"') >= 2 and value_part.endswith('"'):
                return arg_text.rstrip().endswith(" ")
            return False
        if arg_text.rstrip().endswith(" "):
            return True
        if value_part and not value_part.isspace():
            return False
        return True

    return True


def compute_search_string(text: str, cursor_position: int) -> str:
    """Return the substring used for fuzzy matching."""
    text_before_cursor = text[:cursor_position]

    if "@" in text_before_cursor:
        last_at = text_before_cursor.rfind("@")
        return text_before_cursor[last_at + 1 :]

    if not text_before_cursor.startswith("/"):
        return ""

    search_str = text_before_cursor[1:]
    if " " not in search_str:
        return search_str

    arg_text = search_str.split(" ", 1)[1]
    if not arg_text.strip():
        return ""

    arg_parts = parse_command_arguments(arg_text)
    if not arg_parts:
        return ""

    last_part = arg_parts[-1]
    parsed = extract_value_part(last_part)
    if parsed:
        _, value_part = parsed
        if value_part.startswith('"'):
            if is_inside_quotes(value_part):
                return ""
            if value_part.count('"') >= 2 and value_part.endswith('"'):
                return "" if arg_text.rstrip().endswith(" ") else ""
            return ""
        if arg_text.rstrip().endswith(" "):
            return ""
        if value_part and not value_part.isspace():
            return ""
        return value_part

    return last_part

