#!/usr/bin/env python3
"""Test script for LocalToolProvider.

This script demonstrates how to use LocalToolProvider to convert
Python functions into tools that can be used with the ToolRegistry.
"""

import asyncio
import json
from nxs.application.local_tool_provider import LocalToolProvider
from nxs.tools import get_weather


async def main():
    """Test LocalToolProvider functionality."""
    print("=" * 60)
    print("Testing LocalToolProvider")
    print("=" * 60)

    # 1. Create provider with weather function
    print("\n1. Creating LocalToolProvider with get_weather function...")
    provider = LocalToolProvider([get_weather])
    print(f"   Provider name: {provider.provider_name}")
    print(f"   Function count: {provider.get_function_count()}")
    print(f"   Function names: {provider.get_function_names()}")

    # 2. Get tool definitions
    print("\n2. Getting tool definitions...")
    tool_defs = await provider.get_tool_definitions()
    print(f"   Number of tools: {len(tool_defs)}")
    print("\n   Tool definition:")
    print(json.dumps(tool_defs[0], indent=2))

    # 3. Test tool execution
    print("\n3. Testing tool execution...")

    # Test 1: Valid request
    print("\n   Test 1: Valid weather request for San Francisco")
    try:
        result = await provider.execute_tool(
            "get_weather",
            {
                "location": "San Francisco",
                "date": "2025-11-15",
                "unit": "F"
            }
        )
        print(f"   Result: {result}")

        # Parse and pretty print the result
        result_dict = json.loads(result)
        if result_dict.get("status") == "success":
            print(f"   ✓ Success!")
            print(f"     Location: {result_dict['location']}")
            print(f"     Date: {result_dict['date']}")
            print(f"     Temperature: {result_dict['temperature']['min']}°{result_dict['unit']} - {result_dict['temperature']['max']}°{result_dict['unit']}")
            print(f"     Condition: {result_dict['condition']}")
        else:
            print(f"   ✗ Error: {result_dict.get('error_message')}")
    except Exception as e:
        print(f"   ✗ Exception: {e}")

    # Test 2: Invalid date format
    print("\n   Test 2: Invalid date format")
    try:
        result = await provider.execute_tool(
            "get_weather",
            {
                "location": "New York",
                "date": "2025-15-11",  # Invalid format
                "unit": "C"
            }
        )
        result_dict = json.loads(result)
        if result_dict.get("status") == "error":
            print(f"   ✓ Error handled correctly: {result_dict['error_message']}")
        else:
            print(f"   ✗ Should have returned error")
    except Exception as e:
        print(f"   ✗ Exception: {e}")

    # Test 3: Invalid tool name
    print("\n   Test 3: Invalid tool name")
    try:
        result = await provider.execute_tool(
            "nonexistent_tool",
            {}
        )
        print(f"   ✗ Should have raised KeyError")
    except KeyError as e:
        print(f"   ✓ KeyError raised correctly: {e}")
    except Exception as e:
        print(f"   ✗ Unexpected exception: {e}")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
