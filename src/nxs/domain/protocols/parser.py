"""Argument parser protocol."""

from typing import Protocol, Any

__all__ = ["ArgumentParser"]


class ArgumentParser(Protocol):
    """Protocol for argument parsers.

    This protocol defines the interface for parsing command arguments
    from query strings according to a schema.
    """

    def parse(
        self,
        query_remaining: str,
        arg_names: list[str],
        schema_dict: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        """Parse arguments from query string.

        Args:
            query_remaining: The query string after the command name (e.g., "arg1 arg2" or "key=value")
            arg_names: List of valid argument names from the schema
            schema_dict: Complete schema dictionary with defaults, required flags, etc.

        Returns:
            Dictionary of parsed arguments (key: argument name, value: parsed value)
        """
        ...
