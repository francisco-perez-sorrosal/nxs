"""Prompt-related operations for MCP sessions."""

from __future__ import annotations

from typing import Any, Optional

from mcp import types

from .base import OperationBase, SessionGetter


class PromptsOperations(OperationBase):
    """Encapsulates prompt discovery and retrieval operations."""

    def __init__(self, session_getter: SessionGetter) -> None:
        super().__init__(session_getter, logger_name="mcp_client.operations.prompts")

    async def list_prompts(self) -> list[types.Prompt]:
        """Return the prompts exposed by the connected server."""
        session = self._session_or_warn("list prompts")
        if session is None:
            return []

        try:
            result = await session.list_prompts()
        except Exception as exc:  # pragma: no cover - logged for observability
            self.logger.error("Failed to list prompts: %s", exc)
            return []

        prompts = getattr(result, "prompts", None)
        return list(prompts or [])

    async def get_prompt(
        self,
        prompt_name: str,
        args: dict[str, Any],
    ) -> list[types.PromptMessage]:
        """Retrieve a prompt with the provided arguments."""
        session = self._session_or_warn(f"get prompt '{prompt_name}'")
        if session is None:
            return []

        try:
            result = await session.get_prompt(prompt_name, args)
        except Exception as exc:  # pragma: no cover - logged for observability
            self.logger.error("Failed to get prompt '%s': %s", prompt_name, exc)
            return []

        messages = getattr(result, "messages", None)
        return list(messages or [])

