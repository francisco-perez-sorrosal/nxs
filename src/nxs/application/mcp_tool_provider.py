"""MCP tool provider for ToolRegistry.

This module provides MCPToolProvider, a ToolProvider implementation that
aggregates tools from multiple MCP clients and routes execution to the
appropriate client.

This bridges the existing MCP infrastructure with the new ToolRegistry
architecture, allowing MCP tools to be used alongside other tool sources.
"""

import json
from typing import Any, Mapping

from mcp.types import TextContent

from nxs.domain.protocols import MCPClient
from nxs.logger import get_logger

logger = get_logger(__name__)


class MCPToolProvider:
    """Tool provider for MCP servers.

    Wraps multiple MCPClient instances and exposes their tools through
    the ToolProvider protocol. Handles:
    - Tool aggregation from multiple MCP clients
    - Tool execution routing to correct client
    - Error handling for disconnected clients
    - Tool name collision detection

    Example:
        >>> clients = {"server1": client1, "server2": client2}
        >>> provider = MCPToolProvider(clients)
        >>> registry.register_provider(provider)
    """

    def __init__(self, clients: Mapping[str, MCPClient]):
        """Initialize MCP tool provider.

        Args:
            clients: Mapping of server_name -> MCPClient instances.
                Tools from all clients will be aggregated.
        """
        self._clients = clients
        self._tool_to_client: dict[str, str] = {}  # tool_name -> server_name

        logger.debug(f"MCPToolProvider initialized with {len(clients)} clients")

    @property
    def provider_name(self) -> str:
        """Return provider name for logging and identification."""
        return "mcp"

    async def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions from all MCP clients.

        Aggregates tools from all MCP clients. Tool names must be unique
        across all clients.

        Returns:
            List of tool definition dictionaries in Anthropic format.
        """
        all_tools: list[dict[str, Any]] = []
        self._tool_to_client.clear()

        for server_name, client in self._clients.items():
            try:
                # Get tools from this client (returns list of Tool Pydantic models)
                client_tools = await client.list_tools()

                for tool in client_tools:
                    tool_name = tool.name

                    # Check for tool name collisions
                    if tool_name in self._tool_to_client:
                        logger.warning(
                            f"Duplicate tool '{tool_name}' from MCP server "
                            f"'{server_name}', already provided by "
                            f"'{self._tool_to_client[tool_name]}'. Skipping."
                        )
                        continue

                    # Convert Tool model to dict format for Anthropic API
                    tool_dict = {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema,
                    }
                    all_tools.append(tool_dict)
                    self._tool_to_client[tool_name] = server_name

                logger.debug(
                    f"Retrieved {len(client_tools)} tools from MCP server '{server_name}'"
                )

            except Exception as e:
                logger.error(
                    f"Error fetching tools from MCP server '{server_name}': {e}",
                    exc_info=True,
                )
                # Continue with other clients even if one fails

        logger.info(
            f"MCPToolProvider: Retrieved {len(all_tools)} tools from "
            f"{len(self._clients)} MCP clients"
        )

        return all_tools

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """Execute a tool by routing to the appropriate MCP client.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments dictionary.

        Returns:
            Tool execution result as string.

        Raises:
            KeyError: If tool_name is not found in any MCP client.
            Exception: If tool execution fails.
        """
        # Find which client provides this tool
        server_name = self._tool_to_client.get(tool_name)
        if server_name is None:
            raise KeyError(
                f"Tool '{tool_name}' not found in any MCP client. "
                f"Available tools: {list(self._tool_to_client.keys())}"
            )

        client = self._clients[server_name]

        logger.debug(
            f"Executing MCP tool '{tool_name}' on server '{server_name}'"
        )

        try:
            # Execute tool via MCP client (returns CallToolResult or None)
            result = await client.call_tool(tool_name, arguments)

            if not result:
                logger.warning(f"MCP tool '{tool_name}' returned no result")
                return ""

            # Extract text content from CallToolResult
            items = result.content
            content_list = [
                item.text for item in items if isinstance(item, TextContent)
            ]

            # Return JSON-formatted result for consistency
            result_str = json.dumps(content_list)

            logger.debug(
                f"MCP tool '{tool_name}' executed successfully on '{server_name}': "
                f"{len(result_str)} chars returned"
            )

            return result_str

        except Exception as e:
            logger.error(
                f"MCP tool '{tool_name}' execution failed on '{server_name}': {e}",
                exc_info=True,
            )
            raise

    def get_client_count(self) -> int:
        """Get the number of MCP clients.

        Returns:
            Count of MCP clients managed by this provider.
        """
        return len(self._clients)

    def get_server_names(self) -> list[str]:
        """Get names of all MCP servers.

        Returns:
            List of server names.
        """
        return list(self._clients.keys())
