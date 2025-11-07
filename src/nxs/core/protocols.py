"""Core protocols for type hints and abstractions.

This module defines protocols (structural types) that describe the contracts
that various components in the system must satisfy. Using protocols allows for
better type safety, easier testing with mocks, and clearer documentation of
expected interfaces.
"""

from typing import Protocol, Any, TypeVar
from mcp.types import Tool, Prompt, Resource, PromptMessage, CallToolResult

# Re-export ArgumentParser from parsers for central protocol access
from nxs.core.parsers.base import ArgumentParser

__all__ = [
    "MCPClient",
    "ArgumentParser",
    "Cache",
]


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
    
    async def call_tool(
        self, 
        tool_name: str, 
        arguments: dict[str, Any] | None = None
    ) -> CallToolResult | None:
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
    
    async def get_prompt(
        self, 
        prompt_name: str, 
        args: dict[str, str]
    ) -> list[PromptMessage]:
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


# Type variables for generic Cache protocol
# Note: Invariant (default) is correct for Cache since we both read and write
K = TypeVar("K", contravariant=False)
V = TypeVar("V", contravariant=False)


class Cache(Protocol[K, V]):
    """Protocol for caching implementations.
    
    This protocol defines a simple caching interface that can be implemented
    by various caching strategies (in-memory, TTL-based, LRU, etc.).
    
    Type Parameters:
        K: The key type
        V: The value type
    """
    
    def get(self, key: K) -> V | None:
        """Get a value from the cache.
        
        Args:
            key: The cache key
            
        Returns:
            The cached value if found, None otherwise
        """
        ...
    
    def set(self, key: K, value: V) -> None:
        """Set a value in the cache.
        
        Args:
            key: The cache key
            value: The value to cache
        """
        ...
    
    def clear(self, key: K | None = None) -> None:
        """Clear cache entries.
        
        Args:
            key: If provided, clear only this key. If None, clear all entries.
        """
        ...

