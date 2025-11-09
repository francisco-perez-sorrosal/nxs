"""Tool-related operations for MCP sessions."""

from __future__ import annotations

from typing import Any, Optional

from mcp import types

from .base import OperationBase, SessionGetter


class ToolsOperations(OperationBase):
    """Encapsulates tool discovery and invocation operations."""

    def __init__(self, session_getter: SessionGetter) -> None:
        super().__init__(session_getter, logger_name="mcp_client.operations.tools")

    async def list_tools(self) -> list[types.Tool]:
        """Return the list of tools exposed by the connected server."""
        session = self._session_or_warn("list tools")
        if session is None:
            return []

        try:
            result = await session.list_tools()
        except Exception as exc:  # pragma: no cover - logged for observability
            self.logger.error("Failed to list tools: %s", exc)
            return []

        tools = getattr(result, "tools", None)
        return list(tools or [])

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> Optional[types.CallToolResult]:
        """
        Invoke a tool on the connected server.

        Returns:
            The tool result when successful, otherwise ``None``.
        """
        session = self._session_or_warn(f"call tool '{tool_name}'")
        if session is None:
            return None

        try:
            return await session.call_tool(tool_name, arguments or {})
        except Exception as exc:  # pragma: no cover - logged for observability
            self.logger.error("Failed to call tool '%s': %s", tool_name, exc)
            return None
