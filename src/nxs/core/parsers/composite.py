"""Composite argument parser that combines multiple parsing strategies."""

from typing import Any
from nxs.core.parsers.positional import PositionalArgumentParser
from nxs.core.parsers.key_value import KeyValueArgumentParser
from nxs.core.parsers.schema_adapter import SchemaAdapter, SchemaInfo
from nxs.logger import get_logger

logger = get_logger("parsers")


class CompositeArgumentParser:
    """
    Composite parser that uses multiple parsing strategies.
    
    Automatically selects the appropriate parser based on query format:
    - Key-value format (key=value) -> KeyValueArgumentParser
    - Positional format (space-separated) -> PositionalArgumentParser
    """
    
    def __init__(self):
        self.key_value_parser = KeyValueArgumentParser()
        self.positional_parser = PositionalArgumentParser()
        self.schema_adapter = SchemaAdapter()
    
    def parse(
        self,
        query_remaining: str,
        arg_names: list[str],
        schema_dict: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        """
        Parse arguments using the appropriate parser strategy.
        
        Args:
            query_remaining: The query string after the command name
            arg_names: List of valid argument names from the schema
            schema_dict: Complete schema dictionary with defaults, required flags, etc.
            
        Returns:
            Dictionary of parsed arguments
        """
        # Select parser based on format
        if '=' in query_remaining:
            # Use key-value parser
            return self.key_value_parser.parse(query_remaining, arg_names, schema_dict)
        else:
            # Use positional parser
            return self.positional_parser.parse(query_remaining, arg_names, schema_dict)
    
    def normalize_schema(self, schema: Any, command_name: str) -> SchemaInfo | None:
        """
        Normalize schema using SchemaAdapter.
        
        Args:
            schema: The schema object
            command_name: Command name for logging
            
        Returns:
            SchemaInfo with normalized schema data, or None if schema is invalid
        """
        return self.schema_adapter.normalize(schema, command_name)
    
    def apply_defaults(
        self,
        args: dict[str, str],
        schema_dict: dict[str, dict[str, Any]],
        command_name: str,
    ) -> dict[str, str]:
        """
        Apply default values for optional arguments that weren't provided.
        
        Args:
            args: Parsed arguments dictionary
            schema_dict: Schema dictionary with defaults
            command_name: Command name for logging
            
        Returns:
            Arguments dictionary with defaults applied
        """
        for arg_name, arg_info in schema_dict.items():
            if arg_name not in args:
                if 'default' in arg_info and arg_info['default'] is not None:
                    # Apply default value
                    args[arg_name] = arg_info['default']
                    logger.debug(f"Applied default value for '{arg_name}': {arg_info['default']}")
        
        return args
    
    def validate_arguments(
        self,
        args: dict[str, str],
        required_args: list[str],
        schema_dict: dict[str, dict[str, Any]],
        command_name: str,
    ) -> None:
        """
        Validate parsed arguments against schema.
        
        Args:
            args: Parsed arguments dictionary
            required_args: List of required argument names
            schema_dict: Schema dictionary for validation
            command_name: Command name for logging
        """
        # Validate required arguments
        missing = [arg for arg in required_args if arg not in args]
        if missing:
            logger.warning(f"Missing required arguments for prompt '{command_name}': {missing}")
            # For now, we'll still proceed but log the warning
        
        # Validate provided arguments against schema
        invalid_args = []
        for arg_name, arg_value in args.items():
            if arg_name not in schema_dict:
                invalid_args.append(arg_name)
                logger.warning(f"Unknown argument '{arg_name}' for prompt '{command_name}'")
            else:
                # Validate type if schema provides type information
                self._validate_argument_type(
                    arg_name=arg_name,
                    arg_value=arg_value,
                    schema_info=schema_dict[arg_name],
                    command_name=command_name,
                )

        if invalid_args:
            logger.warning(f"Invalid arguments provided for prompt '{command_name}': {invalid_args}")

    def _validate_argument_type(
        self,
        arg_name: str,
        arg_value: str,
        schema_info: dict[str, Any],
        command_name: str,
    ) -> None:
        """
        Validate argument value type against schema.

        Args:
            arg_name: Argument name
            arg_value: Argument value (as string from user input)
            schema_info: Schema information for this argument
            command_name: Command name for logging
        """
        expected_type = schema_info.get('type', 'string')

        # Basic type validation - values come as strings from user input
        # We validate format rather than coercing types
        if expected_type == 'number' or expected_type == 'integer':
            try:
                if expected_type == 'integer':
                    int(arg_value)
                else:
                    float(arg_value)
            except ValueError:
                logger.warning(
                    f"Argument '{arg_name}' for prompt '{command_name}' expects type '{expected_type}', "
                    f"but got non-numeric value: '{arg_value}'"
                )
        elif expected_type == 'boolean':
            # Accept common boolean representations
            if arg_value.lower() not in ('true', 'false', '1', '0', 'yes', 'no'):
                logger.warning(
                    f"Argument '{arg_name}' for prompt '{command_name}' expects boolean, "
                    f"but got: '{arg_value}' (expected: true/false/yes/no/1/0)"
                )
        # For 'string' or any other type, accept as-is since input is already string

