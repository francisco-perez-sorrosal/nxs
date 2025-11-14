"""Application service for tool enable/disable state management.

This module provides a centralized service for managing the enabled/disabled
state of tools across the application. It maintains tool state independently
of tool providers, allowing dynamic control over which tools are available
for execution.

Note: This was moved from domain to application layer as it manages
application state rather than core business logic.
"""

from __future__ import annotations

from typing import Set
from nxs.logger import get_logger

logger = get_logger(__name__)


class ToolStateManager:
    """Manages enabled/disabled state for tools.

    Features:
    - Per-tool enable/disable control
    - All tools enabled by default
    - Thread-safe state management
    - Event notification support (future enhancement)

    Example:
        >>> state_mgr = ToolStateManager()
        >>> state_mgr.disable_tool("risky_tool")
        >>> state_mgr.is_enabled("risky_tool")
        False
        >>> state_mgr.enable_tool("risky_tool")
        >>> state_mgr.is_enabled("risky_tool")
        True
    """

    def __init__(self) -> None:
        """Initialize the tool state manager.

        All tools are enabled by default. Disabled tools are tracked
        explicitly in a set.
        """
        self._disabled_tools: Set[str] = set()
        logger.debug("ToolStateManager initialized (all tools enabled by default)")

    def is_enabled(self, tool_name: str) -> bool:
        """Check if a tool is enabled.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is enabled, False if disabled
        """
        return tool_name not in self._disabled_tools

    def enable_tool(self, tool_name: str) -> None:
        """Enable a tool.

        Args:
            tool_name: Name of the tool to enable
        """
        if tool_name in self._disabled_tools:
            self._disabled_tools.remove(tool_name)
            logger.info(f"Tool enabled: {tool_name}")
        else:
            logger.debug(f"Tool already enabled: {tool_name}")

    def disable_tool(self, tool_name: str) -> None:
        """Disable a tool.

        Args:
            tool_name: Name of the tool to disable
        """
        if tool_name not in self._disabled_tools:
            self._disabled_tools.add(tool_name)
            logger.info(f"Tool disabled: {tool_name}")
        else:
            logger.debug(f"Tool already disabled: {tool_name}")

    def toggle_tool(self, tool_name: str) -> bool:
        """Toggle a tool's enabled/disabled state.

        Args:
            tool_name: Name of the tool to toggle

        Returns:
            New state after toggle (True if enabled, False if disabled)
        """
        if self.is_enabled(tool_name):
            self.disable_tool(tool_name)
            return False
        else:
            self.enable_tool(tool_name)
            return True

    def get_disabled_tools(self) -> Set[str]:
        """Get the set of currently disabled tools.

        Returns:
            Set of disabled tool names (copy for safety)
        """
        return self._disabled_tools.copy()

    def enable_all_tools(self) -> None:
        """Enable all tools."""
        count = len(self._disabled_tools)
        self._disabled_tools.clear()
        logger.info(f"All tools enabled ({count} tools were disabled)")

    def disable_all_tools(self) -> None:
        """Disable all tools.

        Note: This will disable all currently known tools and any tools
        added later will be enabled by default. Use with caution.
        """
        # This is intentionally NOT implemented as it's unclear what "all tools" means
        # without knowing the full tool list. Disabled tools are tracked explicitly.
        raise NotImplementedError(
            "disable_all_tools() is not supported. "
            "Disable specific tools individually instead."
        )

    def get_enabled_count(self, total_tools: int) -> int:
        """Get count of enabled tools given total count.

        Args:
            total_tools: Total number of available tools

        Returns:
            Number of enabled tools
        """
        return max(0, total_tools - len(self._disabled_tools))

    def clear(self) -> None:
        """Clear all tool state (enable all tools).

        Useful for resetting state during testing or re-initialization.
        """
        self.enable_all_tools()
