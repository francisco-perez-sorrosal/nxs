"""Base utilities for MCP session operations."""

from __future__ import annotations

from typing import Callable, Optional

from mcp.client.session import ClientSession

from nxs.logger import get_logger

SessionGetter = Callable[[], Optional[ClientSession]]


class OperationBase:
    """Shared helpers for operations that rely on an active MCP session."""

    def __init__(self, session_getter: SessionGetter, logger_name: str) -> None:
        self._session_getter = session_getter
        self._logger = get_logger(logger_name)

    def _session_or_warn(self, action: str) -> Optional[ClientSession]:
        """
        Retrieve the current session or log a warning if unavailable.

        Args:
            action: Description used in warning when session is missing.
        """
        session = self._session_getter()
        if session is None:
            self._logger.warning("Cannot %s: no active MCP session", action)
        return session

    @property
    def logger(self):
        """Expose the configured logger for subclasses."""
        return self._logger
