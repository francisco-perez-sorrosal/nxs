# Local Tools Guide

This guide explains how to add local Python functions as tools in the NXS application using the `LocalToolProvider`.

## Overview

The `LocalToolProvider` allows you to convert any Python function into a tool that Claude can use, without needing to create an MCP server. It automatically:

- Extracts function name, description, and parameters
- Converts type hints to JSON Schema
- Parses docstrings for parameter descriptions
- Handles tool execution and error management

## Quick Start

### 1. Create a Tool Function

Create a function in `src/nxs/tools/` with type hints and a docstring:

```python
# src/nxs/tools/calculator.py

def add_numbers(a: int, b: int) -> dict:
    """Add two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        Dictionary with the sum
    """
    return {"result": a + b, "operation": "addition"}
```

### 2. Export the Function

Add it to `src/nxs/tools/__init__.py`:

```python
from nxs.tools.weather import get_weather
from nxs.tools.calculator import add_numbers

__all__ = ["get_weather", "add_numbers"]
```

### 3. Register with ToolRegistry

In your application code (e.g., `main.py`):

```python
from nxs.application.local_tool_provider import LocalToolProvider
from nxs.application.tool_registry import ToolRegistry
from nxs.tools import get_weather, add_numbers

# Create registry
registry = ToolRegistry(enable_caching=True)

# Register local tools
local_provider = LocalToolProvider([get_weather, add_numbers])
registry.register_provider(local_provider)

# Tools are now available to Claude
tools = await registry.get_tool_definitions_for_api()
```

## Writing Tool Functions

### Function Requirements

1. **Type hints**: All parameters must have type hints
2. **Docstring**: Must include description and Args section
3. **Return type**: Preferably `dict` or `str` for easy serialization

### Supported Types

The `LocalToolProvider` supports these Python types:

| Python Type | JSON Schema Type |
|-------------|------------------|
| `str` | `string` |
| `int` | `integer` |
| `float` | `number` |
| `bool` | `boolean` |
| `dict` | `object` |
| `list` | `array` |
| `Optional[T]` | Type T (not required) |
| `List[T]` | `array` with item type |
| `Dict[K, V]` | `object` |

### Docstring Format

Use Google-style or NumPy-style docstrings:

```python
def my_tool(param1: str, param2: int, optional: bool = False) -> dict:
    """Short description of what the tool does.

    Longer description can go here if needed.

    Args:
        param1: Description of param1
        param2: Description of param2
        optional: Description of optional parameter

    Returns:
        Description of return value
    """
    # Implementation
    pass
```

The `Args:` section is parsed to extract parameter descriptions.

### Example Functions

#### Simple Calculation Tool

```python
def calculate_percentage(value: float, percentage: float) -> dict:
    """Calculate percentage of a value.

    Args:
        value: The base value
        percentage: The percentage to calculate (e.g., 20 for 20%)
    """
    result = value * (percentage / 100)
    return {
        "value": value,
        "percentage": percentage,
        "result": result
    }
```

#### API Integration Tool

```python
import requests

def search_wikipedia(query: str, limit: int = 5) -> dict:
    """Search Wikipedia for articles.

    Args:
        query: Search term
        limit: Maximum number of results to return
    """
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "opensearch",
        "search": query,
        "limit": limit,
        "format": "json"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return {
            "status": "success",
            "query": query,
            "results": data[1],  # Article titles
            "descriptions": data[2],  # Descriptions
            "urls": data[3]  # URLs
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

#### File Operations Tool

```python
import json
from pathlib import Path

def read_json_file(file_path: str) -> dict:
    """Read and parse a JSON file.

    Args:
        file_path: Path to the JSON file
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {"status": "error", "message": "File not found"}

        with open(path, "r") as f:
            data = json.load(f)

        return {
            "status": "success",
            "file_path": str(path),
            "data": data
        }
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

## Integration with NXS Application

### Modifying main.py

Here's how to integrate local tools into the main NXS application:

```python
# In src/nxs/main.py

from nxs.application.local_tool_provider import LocalToolProvider
from nxs.application.mcp_tool_provider import MCPToolProvider
from nxs.application.tool_registry import ToolRegistry
from nxs.tools import get_weather  # Import your tools

async def create_tool_registry(mcp_clients) -> ToolRegistry:
    """Create and configure the tool registry with all providers."""

    # Create registry
    registry = ToolRegistry(enable_caching=True)

    # Register MCP tools (existing functionality)
    if mcp_clients:
        mcp_provider = MCPToolProvider(mcp_clients)
        registry.register_provider(mcp_provider)

    # Register local tools (new functionality)
    local_tools = [get_weather]  # Add all your local tools here
    if local_tools:
        local_provider = LocalToolProvider(local_tools)
        registry.register_provider(local_provider)

    return registry

# Use the registry in your agent/application
async def main():
    # ... existing setup ...

    # Create registry with both MCP and local tools
    registry = await create_tool_registry(mcp_clients)

    # Get all tools for Claude
    tools = await registry.get_tool_definitions_for_api()

    # ... rest of application ...
```

## Best Practices

### 1. Error Handling

Always handle errors gracefully and return informative error messages:

```python
def my_tool(param: str) -> dict:
    """My tool description.

    Args:
        param: Parameter description
    """
    try:
        # Your logic here
        result = some_operation(param)
        return {"status": "success", "result": result}
    except ValueError as e:
        return {"status": "error", "message": f"Invalid input: {e}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

### 2. Return Structured Data

Return dictionaries with consistent structure:

```python
# Good: Structured response
{
    "status": "success",
    "data": {...},
    "metadata": {...}
}

# Also good: Direct data when simple
{
    "result": 42,
    "unit": "meters"
}
```

### 3. Input Validation

Validate inputs and provide clear error messages:

```python
def my_tool(value: int, mode: str = "default") -> dict:
    """Tool with validation."""

    # Validate value range
    if value < 0 or value > 100:
        return {
            "status": "error",
            "message": "Value must be between 0 and 100"
        }

    # Validate mode
    valid_modes = ["default", "advanced"]
    if mode not in valid_modes:
        return {
            "status": "error",
            "message": f"Mode must be one of: {valid_modes}"
        }

    # Process...
    return {"status": "success", "result": ...}
```

### 4. Documentation

Write clear, comprehensive docstrings:

```python
def my_tool(param1: str, param2: int) -> dict:
    """Brief one-line description.

    More detailed explanation of what the tool does,
    how it works, and any important considerations.

    Args:
        param1: Clear description of param1, including:
            - Valid values or format
            - Examples if helpful
        param2: Clear description of param2

    Returns:
        Description of return format:
            {
                "status": "success" | "error",
                "result": ...,
                "message": "..." (only on error)
            }
    """
```

### 5. Timeouts for External Calls

Always set timeouts for network requests:

```python
import requests

def api_tool(query: str) -> dict:
    """Tool that calls external API."""
    try:
        response = requests.get(
            "https://api.example.com/search",
            params={"q": query},
            timeout=10  # Always set timeout!
        )
        return {"status": "success", "data": response.json()}
    except requests.Timeout:
        return {"status": "error", "message": "Request timed out"}
    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}
```

## Testing Tools

### Unit Testing

Create tests in `tests/test_local_tools.py`:

```python
import pytest
from nxs.tools.calculator import add_numbers

def test_add_numbers():
    result = add_numbers(5, 3)
    assert result["result"] == 8
    assert result["operation"] == "addition"

def test_add_numbers_negative():
    result = add_numbers(-5, 3)
    assert result["result"] == -2
```

### Integration Testing

Test with the LocalToolProvider:

```python
import pytest
from nxs.application.local_tool_provider import LocalToolProvider
from nxs.tools import get_weather

@pytest.mark.asyncio
async def test_weather_tool_integration():
    provider = LocalToolProvider([get_weather])

    # Get tool definitions
    tools = await provider.get_tool_definitions()
    assert len(tools) == 1
    assert tools[0]["name"] == "get_weather"

    # Execute tool
    result = await provider.execute_tool(
        "get_weather",
        {"location": "New York", "date": "2025-11-20", "unit": "C"}
    )
    assert "status" in result
```

## Troubleshooting

### Tool Not Found

If your tool isn't available:

1. Check it's exported in `__init__.py`
2. Verify it's passed to `LocalToolProvider([...])`
3. Ensure the provider is registered with the registry

### Type Conversion Errors

If you see type conversion warnings:

1. Add explicit type hints to all parameters
2. Use standard types (str, int, float, bool, dict, list)
3. For complex types, use `dict` or `str` and document the format

### Execution Errors

If tool execution fails:

1. Check function signature matches the arguments
2. Verify all required parameters are provided
3. Look at logs in `nexus.log` for detailed error info

## Advanced Usage

### Custom Type Conversion

For complex types, you can extend `LocalToolProvider._type_to_json_schema()`:

```python
class CustomLocalToolProvider(LocalToolProvider):
    def _type_to_json_schema(self, python_type):
        # Handle custom types
        if python_type == MyCustomType:
            return {"type": "string", "format": "custom"}
        return super()._type_to_json_schema(python_type)
```

### Async Tools

The `execute_tool` method is async, but it calls sync functions. For async functions:

```python
import asyncio

def my_async_tool(param: str) -> dict:
    """Tool that needs async operations."""

    async def _async_impl():
        # Async operations
        await asyncio.sleep(1)
        return {"result": "done"}

    # Run async code in sync function
    return asyncio.run(_async_impl())
```

Or modify `LocalToolProvider.execute_tool()` to handle async functions using `inspect.iscoroutinefunction()`.

## Examples

See the following examples for more details:

- `test_local_tools.py` - Basic testing example
- `examples/local_tools_integration.py` - Full integration example
- `src/nxs/tools/weather.py` - Complete weather tool implementation

## Summary

The `LocalToolProvider` makes it easy to add custom functionality to Claude by converting Python functions into tools. Key points:

1. ✅ Write functions with type hints and docstrings
2. ✅ Export them from the `tools` package
3. ✅ Register with `LocalToolProvider([...])`
4. ✅ Tools automatically available to Claude

No MCP server needed - just write Python functions!
