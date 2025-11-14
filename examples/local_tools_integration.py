#!/usr/bin/env python3
"""Example: Integrating LocalToolProvider with NXS application.

This example demonstrates how to add local Python functions as tools
to the NXS application alongside MCP tools.

To integrate local tools into your application:

1. Define your tool functions in the nxs.tools package (or any module)
2. Create a LocalToolProvider with your functions
3. Register the provider with the ToolRegistry
4. The tools will be automatically available to Claude

Steps to integrate into main.py:

    from nxs.application.local_tool_provider import LocalToolProvider
    from nxs.application.tool_registry import ToolRegistry
    from nxs.tools import get_weather

    # Create tool registry
    registry = ToolRegistry(enable_caching=True)

    # Register MCP provider (existing)
    mcp_provider = MCPToolProvider(mcp_clients)
    registry.register_provider(mcp_provider)

    # Register local tools provider (new)
    local_provider = LocalToolProvider([get_weather])
    registry.register_provider(local_provider)

    # Tools from both providers are now available
    tools = await registry.get_tool_definitions_for_api()

"""

import asyncio
from nxs.application.local_tool_provider import LocalToolProvider
from nxs.application.tool_registry import ToolRegistry
from nxs.tools import get_weather


async def main():
    """Demonstrate local tools integration with ToolRegistry."""
    print("=" * 60)
    print("Local Tools Integration Example")
    print("=" * 60)

    # 1. Create ToolRegistry
    print("\n1. Creating ToolRegistry...")
    registry = ToolRegistry(enable_caching=True)

    # 2. Create and register LocalToolProvider
    print("\n2. Registering LocalToolProvider with weather tool...")
    local_provider = LocalToolProvider([get_weather])
    registry.register_provider(local_provider)

    print(f"   Registered providers: {registry.get_provider_names()}")
    print(f"   Provider count: {registry.get_provider_count()}")

    # 3. Get all tool definitions
    print("\n3. Getting all tool definitions...")
    tools = await registry.get_tool_definitions_for_api()
    print(f"   Total tools available: {len(tools)}")
    print(f"   Tool names: {registry.get_tool_names()}")

    # 4. Execute a tool through the registry
    print("\n4. Executing weather tool through ToolRegistry...")
    result = await registry.execute_tool(
        "get_weather",
        {
            "location": "New York",
            "date": "2025-11-20",
            "unit": "F"
        }
    )
    print(f"   Result:\n{result}")

    # 5. Show tool schema
    print("\n5. Getting tool schema...")
    schema = await registry.get_tool_schema("get_weather")
    if schema:
        print(f"   Tool name: {schema['name']}")
        print(f"   Description: {schema['description'][:100]}...")
        print(f"   Parameters: {list(schema['input_schema']['properties'].keys())}")
        print(f"   Required: {schema['input_schema'].get('required', [])}")

    print("\n" + "=" * 60)
    print("Integration example completed!")
    print("=" * 60)

    print("\n" + "=" * 60)
    print("How to add more local tools:")
    print("=" * 60)
    print("""
1. Create a new function in nxs/tools/ (e.g., calculator.py):

    def add_numbers(a: int, b: int) -> dict:
        '''Add two numbers together.

        Args:
            a: First number
            b: Second number
        '''
        return {"result": a + b}

2. Import it in nxs/tools/__init__.py:

    from nxs.tools.calculator import add_numbers
    __all__ = ["get_weather", "add_numbers"]

3. Register it with LocalToolProvider:

    from nxs.tools import get_weather, add_numbers
    local_provider = LocalToolProvider([get_weather, add_numbers])

That's it! The tool will be automatically available to nsx.
""")


if __name__ == "__main__":
    asyncio.run(main())
