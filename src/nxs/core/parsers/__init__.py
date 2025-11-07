"""Argument parsing package for command arguments."""

from nxs.core.parsers.base import ArgumentParser
from nxs.core.parsers.positional import PositionalArgumentParser
from nxs.core.parsers.key_value import KeyValueArgumentParser
from nxs.core.parsers.schema_adapter import SchemaAdapter
from nxs.core.parsers.composite import CompositeArgumentParser
from nxs.core.parsers.utils import (
    ParsedArgument,
    parse_command_arguments,
    extract_last_argument,
    is_inside_quotes,
    extract_value_part,
    is_complete_quoted_argument,
    extract_provided_arg_names,
)

__all__ = [
    "ArgumentParser",
    "PositionalArgumentParser",
    "KeyValueArgumentParser",
    "SchemaAdapter",
    "CompositeArgumentParser",
    "ParsedArgument",
    "parse_command_arguments",
    "extract_last_argument",
    "is_inside_quotes",
    "extract_value_part",
    "is_complete_quoted_argument",
    "extract_provided_arg_names",
]

