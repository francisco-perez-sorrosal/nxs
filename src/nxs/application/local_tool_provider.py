"""Local Python function tool provider for ToolRegistry.

This module provides LocalToolProvider, a ToolProvider implementation that
converts Python callable functions into tools compatible with the Anthropic
API format.

This allows you to easily expose local Python functions as tools that can be
called by Claude, without needing to create an MCP server.
"""

import inspect
import json
import re
from typing import Any, Callable, Union, get_args, get_origin

from nxs.logger import get_logger

logger = get_logger(__name__)


class LocalToolProvider:
    """Tool provider for local Python functions.

    Converts Python callable functions into Anthropic-compatible tool
    definitions by introspecting function signatures, type hints, and
    docstrings.

    Features:
    - Automatic schema generation from type hints
    - Docstring parsing for descriptions
    - Required vs optional parameter detection
    - Type conversion and validation
    - Error handling with informative messages

    Example:
        >>> def greet(name: str, greeting: str = "Hello") -> str:
        ...     '''Greet someone.
        ...     Args:
        ...         name: Person's name
        ...         greeting: Greeting phrase
        ...     '''
        ...     return f"{greeting}, {name}!"
        >>>
        >>> provider = LocalToolProvider([greet])
        >>> registry.register_provider(provider)
    """

    def __init__(self, functions: list[Callable[..., Any]]):
        """Initialize local tool provider.

        Args:
            functions: List of Python callable functions to expose as tools.
                Each function should have:
                - Type hints for all parameters
                - A docstring describing the function and its arguments
                - A return type (preferably dict or str)
        """
        self._functions: dict[str, Callable[..., Any]] = {}
        self._tool_definitions: list[dict[str, Any]] = []

        for func in functions:
            tool_def = self._create_tool_definition(func)
            self._tool_definitions.append(tool_def)
            self._functions[tool_def["name"]] = func

        logger.debug(
            f"LocalToolProvider initialized with {len(functions)} functions"
        )

    @property
    def provider_name(self) -> str:
        """Return provider name for logging and identification."""
        return "local"

    async def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions for all registered functions.

        Returns:
            List of tool definition dictionaries in Anthropic format.
        """
        return self._tool_definitions

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """Execute a local function with given arguments.

        Args:
            tool_name: Name of the function to execute.
            arguments: Function arguments as dictionary.

        Returns:
            Function execution result as string.

        Raises:
            KeyError: If tool_name is not found.
            Exception: If function execution fails.
        """
        func = self._functions.get(tool_name)
        if func is None:
            raise KeyError(
                f"Function '{tool_name}' not found in local provider. "
                f"Available tools: {list(self._functions.keys())}"
            )

        logger.debug(f"Executing local function '{tool_name}' with args: {arguments}")

        try:
            # Execute the function
            result = func(**arguments)

            # Convert result to string
            if isinstance(result, str):
                result_str = result
            elif isinstance(result, dict):
                result_str = json.dumps(result, indent=2)
            else:
                result_str = str(result)

            logger.debug(
                f"Local function '{tool_name}' executed successfully: "
                f"{len(result_str)} chars returned"
            )

            return result_str

        except Exception as e:
            logger.error(
                f"Local function '{tool_name}' execution failed: {e}",
                exc_info=True,
            )
            raise

    def _create_tool_definition(self, func: Callable[..., Any]) -> dict[str, Any]:
        """Create an Anthropic-compatible tool definition from a function.

        Args:
            func: Python callable function.

        Returns:
            Tool definition dictionary with name, description, and input_schema.
        """
        # Get function name
        func_name = func.__name__

        # Get function signature
        sig = inspect.signature(func)

        # Parse docstring for description and parameter docs
        docstring = inspect.getdoc(func) or ""
        description, param_docs = self._parse_docstring(docstring)

        # Build input schema from parameters
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            # Skip self and cls parameters
            if param_name in ("self", "cls"):
                continue

            # Get parameter type hint
            param_type = param.annotation
            if param_type is inspect.Parameter.empty:
                logger.warning(
                    f"Parameter '{param_name}' in function '{func_name}' "
                    f"has no type hint. Defaulting to 'string'."
                )
                param_type = str

            # Convert Python type to JSON Schema
            param_schema = self._type_to_json_schema(param_type)

            # Add parameter description from docstring
            if param_name in param_docs:
                param_schema["description"] = param_docs[param_name]

            properties[param_name] = param_schema

            # Mark as required if no default value
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        # Build complete input schema
        input_schema = {
            "type": "object",
            "properties": properties,
        }

        if required:
            input_schema["required"] = required

        tool_def = {
            "name": func_name,
            "description": description or f"Execute {func_name} function",
            "input_schema": input_schema,
        }

        logger.debug(f"Created tool definition for function '{func_name}'")

        return tool_def

    def _parse_docstring(self, docstring: str) -> tuple[str, dict[str, str]]:
        """Parse docstring to extract description and parameter docs.

        Supports Google-style and NumPy-style docstrings.

        Args:
            docstring: Function docstring.

        Returns:
            Tuple of (description, param_docs) where param_docs is a dict
            mapping parameter names to their descriptions.
        """
        if not docstring:
            return "", {}

        # Split into lines
        lines = docstring.split("\n")

        # Find the Args: or Parameters: section
        description_lines = []
        param_lines = []
        in_args_section = False

        for line in lines:
            stripped = line.strip()

            # Check for Args/Parameters section
            if re.match(r"^(Args|Arguments|Parameters):", stripped):
                in_args_section = True
                continue

            # Check for end of Args section (new section or empty line after args)
            if in_args_section and re.match(r"^(Returns?|Raises?|Yields?|Examples?|Notes?):", stripped):
                in_args_section = False
                continue

            if in_args_section:
                param_lines.append(line)
            elif not in_args_section and stripped:
                description_lines.append(line)

        # Extract description (first paragraph)
        description = "\n".join(description_lines).strip()
        if description:
            # Take only the first paragraph
            description = description.split("\n\n")[0]

        # Parse parameter docs
        param_docs: dict[str, str] = {}
        current_param = None
        current_desc_lines = []

        for line in param_lines:
            # Check for parameter definition: "param_name: description" or "param_name (type): description"
            match = re.match(r"^\s*(\w+)(?:\s*\([^)]+\))?\s*:\s*(.+)$", line)
            if match:
                # Save previous parameter if any
                if current_param and current_desc_lines:
                    param_docs[current_param] = " ".join(current_desc_lines).strip()

                # Start new parameter
                current_param = match.group(1)
                current_desc_lines = [match.group(2)]
            elif current_param and line.strip():
                # Continuation of current parameter description
                current_desc_lines.append(line.strip())

        # Save last parameter
        if current_param and current_desc_lines:
            param_docs[current_param] = " ".join(current_desc_lines).strip()

        return description, param_docs

    def _type_to_json_schema(self, python_type: Any) -> dict[str, Any]:
        """Convert Python type hint to JSON Schema format.

        Args:
            python_type: Python type annotation.

        Returns:
            JSON Schema dictionary for the type.
        """
        # Handle basic types
        type_mapping = {
            str: {"type": "string"},
            int: {"type": "integer"},
            float: {"type": "number"},
            bool: {"type": "boolean"},
            dict: {"type": "object"},
            list: {"type": "array"},
        }

        if python_type in type_mapping:
            return type_mapping[python_type]

        # Handle Optional types (Union[X, None])
        origin = get_origin(python_type)
        args = get_args(python_type)

        if origin is type(None):
            return {"type": "null"}

        # Handle Union types (including Optional)
        # Check if origin is Union (works for Union and Optional types)
        try:
            from types import UnionType
            is_union = origin is Union or isinstance(python_type, UnionType)
        except ImportError:
            # Python < 3.10 doesn't have UnionType
            is_union = origin is Union

        if is_union:
            # For Optional[X] (Union[X, None]), return schema for X
            non_none_types = [arg for arg in args if arg is not type(None)]
            if len(non_none_types) == 1:
                return self._type_to_json_schema(non_none_types[0])
            # For complex unions, default to string
            logger.warning(f"Complex Union type {python_type} not fully supported. Defaulting to string.")
            return {"type": "string"}

        # Handle List[X]
        if origin is list:
            if args:
                item_schema = self._type_to_json_schema(args[0])
                return {"type": "array", "items": item_schema}
            return {"type": "array"}

        # Handle Dict[K, V]
        if origin is dict:
            return {"type": "object"}

        # Default to string for unknown types
        logger.warning(f"Unknown type {python_type}. Defaulting to string.")
        return {"type": "string"}

    def get_function_count(self) -> int:
        """Get the number of registered functions.

        Returns:
            Count of local functions managed by this provider.
        """
        return len(self._functions)

    def get_function_names(self) -> list[str]:
        """Get names of all registered functions.

        Returns:
            List of function names.
        """
        return list(self._functions.keys())
