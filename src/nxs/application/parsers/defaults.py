"""Utilities for validating and sanitizing default values."""

from typing import Any


def is_valid_default_value(default: Any) -> bool:
    """
    Check if a default value is valid (not PydanticUndefined or class reference).

    This function filters out sentinel values like PydanticUndefined and class
    references that are not appropriate for display or use as default values.

    Args:
        default: The default value to validate

    Returns:
        True if value is valid for use, False otherwise

    Examples:
        >>> is_valid_default_value("hello")
        True
        >>> is_valid_default_value(None)
        False
        >>> is_valid_default_value("<class 'str'>")
        False
    """
    if default is None:
        return False

    default_str = str(default)

    # Filter out PydanticUndefined sentinel values
    if "Undefined" in default_str or "PydanticUndefined" in default_str:
        return False

    # Filter out class references (e.g., "<class 'str'>")
    if "class" in default_str.lower() and "<" in default_str:
        return False

    return True


def clean_default_value(default: Any) -> Any | None:
    """
    Return the default value if valid, otherwise None.

    This is a convenience wrapper around is_valid_default_value that returns
    the value itself or None, useful for sanitizing default values.

    Args:
        default: The default value to clean

    Returns:
        The original value if valid, None otherwise

    Examples:
        >>> clean_default_value("hello")
        'hello'
        >>> clean_default_value(None)
        None
        >>> clean_default_value("<class 'str'>")
        None
    """
    return default if is_valid_default_value(default) else None
