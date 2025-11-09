"""MCP client protocol."""

from typing import Protocol, Any
from mcp.types import Tool, Prompt, Resource, PromptMessage, CallToolResult

__all__ = ["MCPClient"]


class MCPClient(Protocol):
    """Protocol for MCP client operations.

    This protocol defines the interface that any MCP client must implement.
    It allows code to work with any client implementation (MCPAuthClient,
    mock clients for testing, etc.) without being tightly coupled to a
    specific concrete class.
    """

    @property
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        ...

    async def list_tools(self) -> list[Tool]:
        """List available tools from the server.

        Returns:
            List of Tool objects available from the MCP server.
        """
        ...

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> CallToolResult | None:
        """Call a specific tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Optional dictionary of arguments for the tool

        Returns:
            CallToolResult if successful, None otherwise
        """
        ...

    async def list_prompts(self) -> list[Prompt]:
        """List available prompts from the server.

        Returns:
            List of Prompt objects available from the MCP server.
        """
        ...

    async def get_prompt(self, prompt_name: str, args: dict[str, str]) -> list[PromptMessage]:
        """Get a prompt with the given arguments.

        Args:
            prompt_name: Name of the prompt to retrieve
            args: Dictionary of arguments for the prompt

        Returns:
            List of PromptMessage objects
        """
        ...

    async def list_resources(self) -> list[Resource]:
        """List available resources from the server.

        Returns:
            List of Resource objects available from the MCP server.
        """
        ...

    async def read_resource(self, uri: str) -> Any:
        """Read a resource by URI.

        Args:
            uri: URI of the resource to read

        Returns:
            Resource contents (parsed based on content type) or None if failed
        """
        ...
