"""
Resource completion strategy for ``@`` triggers.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from textual_autocomplete import DropdownItem

from nxs.logger import get_logger

from .strategy import CompletionRequest, CompletionStrategy

logger = get_logger("autocomplete.resource")


class ResourceCompletionStrategy(CompletionStrategy):
    """Produces resource candidates when the user types ``@``."""

    def __init__(self, resource_provider: Callable[[], Sequence[str]]) -> None:
        self._resource_provider = resource_provider

    def can_handle(self, request: CompletionRequest) -> bool:
        text_before_cursor = request.text[: request.cursor_position]
        return "@" in text_before_cursor

    def get_candidates(self, request: CompletionRequest) -> list[DropdownItem]:
        text_before_cursor = request.text[: request.cursor_position]
        last_at = text_before_cursor.rfind("@")
        if last_at == -1:
            return []

        query = text_before_cursor[last_at + 1 :].lower()
        resources = list(self._resource_provider())
        logger.debug(
            "ResourceCompletionStrategy triggered (query=%r, total_resources=%d)",
            query,
            len(resources),
        )

        if query:
            filtered = [res for res in resources if query in res.lower()]
        else:
            filtered = resources

        logger.debug("ResourceCompletionStrategy returning %d matches", len(filtered))
        return [DropdownItem(main=resource, prefix="📄") for resource in filtered]

