"""Argument parsing package for command arguments."""

from nxs.application.parsers.base import ArgumentParser
from nxs.application.parsers.positional import PositionalArgumentParser
from nxs.application.parsers.key_value import KeyValueArgumentParser
from nxs.application.parsers.schema_adapter import SchemaAdapter
from nxs.application.parsers.composite import CompositeArgumentParser
from nxs.application.parsers.defaults import (
    is_valid_default_value,
    clean_default_value,
)
from nxs.application.parsers.utils import (
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
    "is_valid_default_value",
    "clean_default_value",
    "ParsedArgument",
    "parse_command_arguments",
    "extract_last_argument",
    "is_inside_quotes",
    "extract_value_part",
    "is_complete_quoted_argument",
    "extract_provided_arg_names",
]
