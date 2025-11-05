"""
Command Argument Parser - Utilities for parsing command arguments with quote awareness.

This module provides utilities for parsing command-line style arguments that may contain
quoted values with spaces, handling edge cases like incomplete quotes and escaped quotes.
"""

from typing import NamedTuple


class ParsedArgument(NamedTuple):
    """Represents a parsed command argument."""
    name: str
    value: str | None
    is_complete: bool
    is_quoted: bool


def parse_command_arguments(text: str) -> list[str]:
    """
    Parse command arguments while respecting quoted values.
    
    Splits arguments by spaces, but doesn't split on spaces inside quoted values.
    Handles escaped quotes properly.
    
    Args:
        text: Command argument text (e.g., 'arg1="value 1" arg2=value2')
        
    Returns:
        List of argument strings, each may be complete or incomplete
    """
    if not text:
        return []
    
    arg_parts = []
    current_part = ""
    inside_quotes = False
    i = 0
    
    while i < len(text):
        char = text[i]
        
        # Check for escaped quote (not currently used but good to handle)
        if char == '\\' and i + 1 < len(text) and text[i + 1] == '"':
            current_part += char + text[i + 1]
            i += 2
            continue
        
        # Toggle quote state when encountering unescaped quote
        if char == '"':
            inside_quotes = not inside_quotes
            current_part += char
        elif char == ' ' and not inside_quotes:
            # Space outside quotes - end of current argument
            if current_part.strip():
                arg_parts.append(current_part.strip())
            current_part = ""
        else:
            current_part += char
        
        i += 1
    
    # Add the last part (might be incomplete)
    if current_part.strip():
        arg_parts.append(current_part.strip())
    
    return arg_parts


def extract_last_argument(arg_text: str) -> tuple[str, list[str]]:
    """
    Extract the last argument and all complete arguments before it.
    
    Args:
        arg_text: Command argument text
        
    Returns:
        Tuple of (last_part, complete_args_before)
    """
    arg_parts = parse_command_arguments(arg_text)
    
    if not arg_parts:
        return ("", [])
    
    last_part = arg_parts[-1]
    complete_args_before = arg_parts[:-1]
    
    return (last_part, complete_args_before)


def is_inside_quotes(value_part: str) -> bool:
    """
    Check if a value part is inside unclosed quotes.
    
    An odd number of quotes means the quote is not closed.
    
    Args:
        value_part: The value part after the = sign (e.g., '"value' or '"value"')
        
    Returns:
        True if inside unclosed quotes, False otherwise
    """
    if not value_part.startswith('"'):
        return False
    
    # Count quotes - odd number means not closed
    quote_count = value_part.count('"')
    return quote_count % 2 == 1


def extract_value_part(argument: str) -> tuple[str, str] | None:
    """
    Extract argument name and value part from an argument string.
    
    Args:
        argument: Argument string like 'arg_name="value"' or 'arg_name=value'
        
    Returns:
        Tuple of (arg_name, value_part) or None if no = present
    """
    if '=' not in argument:
        return None
    
    eq_pos = argument.rfind('=')
    arg_name = argument[:eq_pos].strip()
    value_part = argument[eq_pos + 1:]
    
    return (arg_name, value_part)


def is_complete_quoted_argument(argument: str) -> bool:
    """
    Check if an argument has a complete quoted value.
    
    Args:
        argument: Argument string like 'arg_name="value"'
        
    Returns:
        True if argument has complete quoted value (even number of quotes, properly closed)
    """
    parsed = extract_value_part(argument)
    if not parsed:
        return False
    
    arg_name, value_part = parsed
    
    if not value_part.startswith('"'):
        return False
    
    # Complete quoted value needs at least 2 quotes (opening and closing) and ends with quote
    quote_count = value_part.count('"')
    return quote_count >= 2 and value_part.endswith('"')


def extract_provided_arg_names(arg_text: str) -> set[str]:
    """
    Extract already-provided argument names from argument text.
    
    Uses quote-aware parsing to correctly handle arguments with spaces in values.
    
    Args:
        arg_text: Command argument text (e.g., 'arg1="value 1" arg2=value2')
        
    Returns:
        Set of argument names that have been provided
    """
    provided_args = set()
    arg_parts = parse_command_arguments(arg_text)
    
    for part in arg_parts:
        parsed = extract_value_part(part)
        if parsed:
            arg_name, value_part = parsed
            # Only count as provided if it's a complete argument
            # For quoted values, check if quote is closed
            if value_part.startswith('"'):
                if not is_inside_quotes(value_part):
                    # Complete quoted argument
                    provided_args.add(arg_name)
            else:
                # Unquoted value - if it's not empty, it's provided
                if value_part.strip():
                    provided_args.add(arg_name)
    
    return provided_args

