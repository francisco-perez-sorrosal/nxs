"""
Strategy-based autocomplete overlay for the Nexus input widget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Sequence

from textual_autocomplete import AutoComplete, DropdownItem, TargetState

from nxs.application.suggestions import ArgumentSuggestionGenerator
from nxs.logger import get_logger
from nxs.presentation.widgets.input_field import NexusInput

from nxs.presentation.completion import (
    ArgumentCompletionStrategy,
    CommandCompletionStrategy,
    CompletionApplier,
    CompletionOrchestrator,
    ResourceCompletionStrategy,
    SchemaCacheMapping,
    compute_search_string,
    should_show_dropdown as helper_should_show_dropdown,
)

if TYPE_CHECKING:
    from nxs.presentation.services.prompt_service import PromptService

logger = get_logger("nexus_input")


class NexusAutoComplete(AutoComplete):
    """Overlay providing @resource, /command and argument completions."""

    def __init__(self, input_widget: NexusInput, prompt_service: "PromptService"):
        logger.info(
            "Initializing NexusAutoComplete (resources=%d, commands=%d)",
            len(input_widget.resources),
            len(input_widget.commands),
        )

        self.input_widget = input_widget
        self.prompt_service = prompt_service

        schema_mapping = SchemaCacheMapping(prompt_service)
        self._argument_generator = ArgumentSuggestionGenerator(schema_mapping)

        command_provider: Callable[[], Sequence[str]] = lambda: self.input_widget.commands
        resource_provider: Callable[[], Sequence[str]] = lambda: self.input_widget.resources

        self._orchestrator = CompletionOrchestrator(
            [
                ArgumentCompletionStrategy(
                    command_provider, prompt_service, self._argument_generator
                ),
                CommandCompletionStrategy(command_provider, prompt_service),
                ResourceCompletionStrategy(resource_provider),
            ]
        )
        self._applier = CompletionApplier(prompt_service)

        super().__init__(
            target=input_widget,
            candidates=self._collect_candidates,
            prevent_default_enter=True,
        )

    def on_mount(self) -> None:
        logger.info(
            "NexusAutoComplete mounted (target=%s, type=%s)",
            self.target,
            type(self.target),
        )

    def _collect_candidates(self, state: TargetState) -> list[DropdownItem]:
        candidates = self._orchestrator.get_completions(state)
        logger.debug("Collected %d completion candidates", len(candidates))
        return candidates

    def get_matches(
        self,
        target_state: TargetState,
        candidates: list[DropdownItem],
        search_string: str,
    ) -> list[DropdownItem]:
        """
        Show all argument suggestions when the search string is empty.
        """
        if candidates and hasattr(candidates[0], "prefix"):
            prefix = str(candidates[0].prefix or "")
            if prefix and ("[R]" in prefix or "[O]" in prefix):
                if not search_string.strip():
                    logger.debug(
                        "Emitting %d argument suggestions without filtering",
                        len(candidates),
                    )
                    return candidates

        return super().get_matches(target_state, candidates, search_string)

    def get_search_string(self, target_state: TargetState) -> str:
        search = compute_search_string(
            target_state.text,
            target_state.cursor_position,
        )
        logger.debug("Derived search string=%r", search)
        return search

    def apply_completion(self, value: str, state: TargetState) -> None:
        result = self._applier.apply(value, state)
        self.target.value = result.text
        self.target.cursor_position = result.cursor
        logger.info("Applied completion; new cursor=%d", result.cursor)

    def should_show_dropdown(self, _search_string: str) -> bool:
        text_before_cursor = self.target.value[: self.target.cursor_position]
        decision = helper_should_show_dropdown(text_before_cursor)
        logger.debug("Dropdown visibility=%s for text=%r", decision, text_before_cursor)
        return decision

