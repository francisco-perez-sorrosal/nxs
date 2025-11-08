"""Resource-related operations for MCP sessions."""

from __future__ import annotations

import json
from typing import Any, Optional

from mcp import types
from pydantic import AnyUrl

from .base import OperationBase, SessionGetter


class ResourcesOperations(OperationBase):
    """Encapsulates resource discovery and retrieval operations."""

    def __init__(self, session_getter: SessionGetter) -> None:
        super().__init__(session_getter, logger_name="mcp_client.operations.resources")

    async def list_resources(self) -> list[types.Resource]:
        """Return the resources exposed by the connected server."""
        session = self._session_or_warn("list resources")
        if session is None:
            return []

        try:
            result = await session.list_resources()
        except Exception as exc:  # pragma: no cover - logged for observability
            self.logger.error("Failed to list resources: %s", exc)
            return []

        resources = getattr(result, "resources", None)
        return list(resources or [])

    async def read_resource(self, uri: str) -> Optional[Any]:
        """Read and return the resource payload at the provided URI."""
        session = self._session_or_warn(f"read resource '{uri}'")
        if session is None:
            return None

        try:
            result = await session.read_resource(AnyUrl(uri))
        except Exception as exc:  # pragma: no cover - logged for observability
            self.logger.error("Failed to read resource '%s': %s", uri, exc)
            return None

        contents = getattr(result, "contents", None)
        if not contents:
            return None

        resource = contents[0]
        if isinstance(resource, types.TextResourceContents):
            if resource.mimeType == "application/json":
                try:
                    return json.loads(resource.text)
                except json.JSONDecodeError as exc:  # pragma: no cover
                    self.logger.error("Invalid JSON in resource '%s': %s", uri, exc)
                    return None
            return resource.text

        return None

