"""Tool registry with pluggable tool providers.

This module provides a unified interface for managing tools from multiple sources
(MCP servers, built-in tools, custom tools) through the ToolProvider protocol.

Key features:
- ToolProvider protocol for extensible tool sources
- Tool registration and discovery from multiple providers
- Tool execution routing to appropriate provider
- Cache control support for tool definitions
- Separation of tool concerns from agent orchestration

Architecture:
    ToolRegistry (central hub)
        ↓
    ToolProvider (protocol)
        ↓
    Concrete providers: MCPToolProvider, CustomToolProvider, etc.
"""

import asyncio
from typing import Any, Protocol

from anthropic.types import ToolParam

from nxs.logger import get_logger

logger = get_logger(__name__)


class ToolProvider(Protocol):
    """Protocol for tool providers.

    Tool providers abstract different sources of tools (MCP servers,
    built-in tools, custom integrations, etc.) behind a uniform interface.

    Implementations must provide:
    - Tool discovery: get_tool_definitions()
    - Tool execution: execute_tool()
    - Provider identification: provider_name property

    Example:
        class CustomToolProvider:
            @property
            def provider_name(self) -> str:
                return "custom"

            async def get_tool_definitions(self) -> list[dict[str, Any]]:
                return [
                    {
                        "name": "my_tool",
                        "description": "Does something useful",
                        "input_schema": {...}
                    }
                ]

            async def execute_tool(self, tool_name: str, arguments: dict) -> str:
                # Execute tool and return result
                return "Tool result"
    """

    @property
    def provider_name(self) -> str:
        """Return the name of this tool provider.

        Used for logging, debugging, and tool routing.
        """
        ...

    async def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get all tool definitions from this provider.

        Returns:
            List of tool definition dictionaries compatible with
            Anthropic's tool format:
            [
                {
                    "name": "tool_name",
                    "description": "What the tool does",
                    "input_schema": {
                        "type": "object",
                        "properties": {...},
                        "required": [...]
                    }
                },
                ...
            ]
        """
        ...

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """Execute a tool with given arguments.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments as dictionary.

        Returns:
            Tool execution result as string.

        Raises:
            KeyError: If tool_name is not found in this provider.
            Exception: If tool execution fails.
        """
        ...


class ToolRegistry:
    """Central registry for managing tools from multiple providers.

    The ToolRegistry acts as a facade over multiple ToolProvider instances,
    providing:
    - Unified tool discovery across all providers
    - Tool execution routing to the correct provider
    - Cache control application for Anthropic API
    - Provider lifecycle management

    Example:
        >>> registry = ToolRegistry(enable_caching=True)
        >>> registry.register_provider(mcp_provider)
        >>> registry.register_provider(custom_provider)
        >>>
        >>> # Get all tools for Claude API
        >>> tools = await registry.get_tool_definitions_for_api()
        >>>
        >>> # Execute a tool (registry routes to correct provider)
        >>> result = await registry.execute_tool("search", {"query": "test"})
    """

    def __init__(self, enable_caching: bool = True):
        """Initialize the tool registry.

        Args:
            enable_caching: Whether to apply cache_control markers to
                tool definitions. Enables 90% cost reduction on tool
                definitions which are stable across conversation.
        """
        self._providers: dict[str, ToolProvider] = {}
        self._tool_to_provider: dict[str, str] = {}  # tool_name -> provider_name
        self._enable_caching = enable_caching
        self._cache_dirty = True  # Track if tool cache needs refresh

        logger.debug(f"ToolRegistry initialized: caching={enable_caching}")

    def register_provider(self, provider: ToolProvider) -> None:
        """Register a tool provider.

        Multiple providers can be registered. Tool names must be unique
        across all providers.

        Args:
            provider: ToolProvider instance to register.

        Raises:
            ValueError: If provider_name is already registered.

        Example:
            >>> registry.register_provider(MCPToolProvider(clients))
            >>> registry.register_provider(CustomToolProvider())
        """
        provider_name = provider.provider_name

        if provider_name in self._providers:
            raise ValueError(f"Provider '{provider_name}' is already registered")

        self._providers[provider_name] = provider
        self._cache_dirty = True

        logger.info(f"Registered tool provider: {provider_name}")

    def unregister_provider(self, provider_name: str) -> None:
        """Unregister a tool provider.

        Args:
            provider_name: Name of provider to unregister.

        Raises:
            KeyError: If provider_name is not registered.
        """
        if provider_name not in self._providers:
            raise KeyError(f"Provider '{provider_name}' not found")

        del self._providers[provider_name]

        # Clean up tool routing table
        self._tool_to_provider = {
            tool: prov
            for tool, prov in self._tool_to_provider.items()
            if prov != provider_name
        }
        self._cache_dirty = True

        logger.info(f"Unregistered tool provider: {provider_name}")

    async def get_tool_definitions_for_api(self) -> list[ToolParam]:
        """Get all tool definitions formatted for Anthropic API.

        Aggregates tools from all registered providers and applies
        cache control if enabled.

        Returns:
            List of ToolParam dictionaries ready for Anthropic API,
            with cache_control markers applied to the last tool if
            caching is enabled.

        Example:
            >>> tools = await registry.get_tool_definitions_for_api()
            >>> response = await claude.create_message(
            ...     messages=messages,
            ...     tools=tools
            ... )
        """
        # Gather tools from all providers
        all_tools: list[dict[str, Any]] = []
        self._tool_to_provider.clear()

        # Gather tools concurrently from all providers
        provider_names = list(self._providers.keys())
        provider_results = await asyncio.gather(
            *[
                self._providers[name].get_tool_definitions()
                for name in provider_names
            ],
            return_exceptions=True,
        )

        # Process results and build routing table
        for provider_name, result in zip(provider_names, provider_results):
            if isinstance(result, Exception):
                logger.error(
                    f"Error fetching tools from {provider_name}: {result}",
                    exc_info=result,
                )
                continue

            for tool in result:
                tool_name = tool["name"]

                # Check for duplicate tool names
                if tool_name in self._tool_to_provider:
                    logger.warning(
                        f"Duplicate tool '{tool_name}' from {provider_name}, "
                        f"already provided by {self._tool_to_provider[tool_name]}"
                    )
                    continue

                all_tools.append(tool)
                self._tool_to_provider[tool_name] = provider_name

        # Apply cache control to last tool if caching enabled
        if self._enable_caching and all_tools:
            # Cache the last tool for cost optimization
            # Tools are stable across conversation (unlike messages)
            all_tools[-1]["cache_control"] = {"type": "ephemeral"}

            logger.debug(
                f"Applied cache control to last tool: {all_tools[-1]['name']}"
            )

        self._cache_dirty = False
        logger.debug(f"Retrieved {len(all_tools)} tools from {len(self._providers)} providers")

        # Type cast: all_tools are properly formatted ToolParam dicts
        return all_tools  # type: ignore[return-value]

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """Execute a tool by routing to the appropriate provider.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments dictionary.

        Returns:
            Tool execution result as string.

        Raises:
            KeyError: If tool_name is not found in any provider.
            Exception: If tool execution fails.

        Example:
            >>> result = await registry.execute_tool(
            ...     "search",
            ...     {"query": "anthropic"}
            ... )
        """
        # Refresh tool routing if cache is dirty
        if self._cache_dirty:
            await self.get_tool_definitions_for_api()

        # Find provider for this tool
        provider_name = self._tool_to_provider.get(tool_name)
        if provider_name is None:
            raise KeyError(
                f"Tool '{tool_name}' not found in any registered provider. "
                f"Available tools: {list(self._tool_to_provider.keys())}"
            )

        provider = self._providers[provider_name]

        logger.debug(
            f"Executing tool '{tool_name}' via provider '{provider_name}'"
        )

        try:
            result = await provider.execute_tool(tool_name, arguments)
            logger.debug(
                f"Tool '{tool_name}' executed successfully: "
                f"{len(result)} chars returned"
            )
            return result
        except Exception as e:
            logger.error(
                f"Tool '{tool_name}' execution failed via {provider_name}: {e}",
                exc_info=True,
            )
            raise

    def get_tool_count(self) -> int:
        """Get the total number of registered tools.

        Returns:
            Count of unique tools across all providers.
        """
        return len(self._tool_to_provider)

    def get_provider_count(self) -> int:
        """Get the number of registered providers.

        Returns:
            Count of registered providers.
        """
        return len(self._providers)

    def get_provider_names(self) -> list[str]:
        """Get names of all registered providers.

        Returns:
            List of provider names.
        """
        return list(self._providers.keys())

    def get_tool_names(self) -> list[str]:
        """Get names of all registered tools.

        Returns:
            List of tool names across all providers.
        """
        return list(self._tool_to_provider.keys())

    async def refresh_tools(self) -> None:
        """Force a refresh of tool definitions from all providers.

        Useful when providers may have updated their available tools.
        """
        self._cache_dirty = True
        await self.get_tool_definitions_for_api()
        logger.info("Tool definitions refreshed from all providers")
