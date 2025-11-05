"""
Argument Suggestion Generator - Generate autocomplete suggestions for command arguments.

This module handles the generation of argument suggestions from prompt schemas,
formatting them appropriately for display in the autocomplete dropdown.
"""

from typing import Any
from textual_autocomplete import DropdownItem
from nxs.tui.widgets.command_parser import parse_command_arguments, extract_value_part


class ArgumentSuggestionGenerator:
    """
    Generates argument suggestions for command autocompletion.
    
    Handles both dict-based and list-based prompt schemas, formats suggestions
    with appropriate prefixes ([R] for required, [O] for optional), and filters
    out already-provided arguments.
    """
    
    def __init__(self, schema_cache: dict):
        """
        Initialize the generator with a schema cache.
        
        Args:
            schema_cache: Dictionary mapping command names to (prompt, server_name) tuples
        """
        self.schema_cache = schema_cache
    
    def extract_provided_args(self, current_text: str) -> set[str]:
        """
        Extract already-provided argument names from argument text.
        
        Uses quote-aware parsing to correctly handle arguments with spaces in values.
        
        Args:
            current_text: Command argument text (e.g., 'arg1="value 1" arg2=value2')
            
        Returns:
            Set of argument names that have been provided
        """
        provided_args = set()
        arg_parts = parse_command_arguments(current_text)
        
        for part in arg_parts:
            parsed = extract_value_part(part)
            if parsed:
                arg_name, value_part = parsed
                # Only count as provided if it's a complete argument
                # For quoted values, check if quote is closed
                if value_part.startswith('"'):
                    # Count quotes - even number means closed
                    quote_count = value_part.count('"')
                    if quote_count >= 2 and quote_count % 2 == 0:
                        # Complete quoted argument
                        provided_args.add(arg_name)
                else:
                    # Unquoted value - if it's not empty, it's provided
                    if value_part.strip():
                        provided_args.add(arg_name)
        
        return provided_args
    
    def validate_default_value(self, default: Any) -> bool:
        """
        Validate that a default value is acceptable (not PydanticUndefined or class reference).
        
        Args:
            default: The default value to validate
            
        Returns:
            True if value is valid, False otherwise
        """
        if default is None:
            return False
        
        default_str = str(default)
        
        # Filter out PydanticUndefined
        if 'Undefined' in default_str or 'PydanticUndefined' in default_str:
            return False
        
        # Filter out class references (e.g., "<class 'str'>")
        if 'class' in default_str.lower() and '<' in default_str:
            return False
        
        return True
    
    def format_argument_suggestion(
        self,
        arg_name: str,
        default: Any,
        description: str,
        is_required: bool
    ) -> DropdownItem:
        """
        Format a single argument suggestion for the dropdown.
        
        Args:
            arg_name: Name of the argument
            default: Default value (if any)
            description: Description of the argument
            is_required: Whether the argument is required
            
        Returns:
            DropdownItem for the suggestion
        """
        if is_required:
            # Required argument - format as arg_name=<required>
            suggestion_text = f"{arg_name}=<required>"
            if description:
                suggestion_text = f"{suggestion_text}  ({description})"
            return DropdownItem(
                main=suggestion_text,
                prefix="  [R]"
            )
        else:
            # Optional argument (with or without default)
            if default is not None and self.validate_default_value(default):
                # Auto-quote default values that contain spaces for better UX
                if ' ' in str(default):
                    suggestion_text = f'{arg_name}="{default}"'
                else:
                    suggestion_text = f"{arg_name}={default}"
            else:
                suggestion_text = f"{arg_name}=?"
            
            if description:
                suggestion_text = f"{suggestion_text}  ({description})"
            
            return DropdownItem(
                main=suggestion_text,
                prefix="  [O]"
            )
    
    def generate_from_dict_schema(
        self,
        schema: dict,
        provided_args: set[str]
    ) -> list[DropdownItem]:
        """
        Generate suggestions from a dict-based schema.
        
        Args:
            schema: Dict schema with 'properties' and 'required' keys
            provided_args: Set of argument names that have already been provided
            
        Returns:
            List of DropdownItem suggestions
        """
        suggestions = []
        properties = schema.get('properties', {})
        required_args = schema.get('required', [])
        
        for arg_name, arg_spec in properties.items():
            if arg_name in provided_args:
                continue
            
            default = None
            description = ""
            is_required = arg_name in required_args
            
            if isinstance(arg_spec, dict):
                default = arg_spec.get('default')
                description = arg_spec.get('description', '')
            
            # Validate and clean default value
            if default is not None and not self.validate_default_value(default):
                default = None
            
            suggestion = self.format_argument_suggestion(
                arg_name, default, description, is_required
            )
            suggestions.append(suggestion)
        
        return suggestions
    
    def generate_from_list_schema(
        self,
        schema: list,
        provided_args: set[str]
    ) -> list[DropdownItem]:
        """
        Generate suggestions from a list-based schema (list of PromptArgument objects).
        
        Args:
            schema: List of argument objects (dict or object with attributes)
            provided_args: Set of argument names that have already been provided
            
        Returns:
            List of DropdownItem suggestions
        """
        suggestions = []
        
        # First pass: collect required argument names
        required_set = set()
        for arg in schema:
            if isinstance(arg, dict):
                if arg.get('name') and arg.get('required', False):
                    required_set.add(arg['name'])
            elif hasattr(arg, 'name') and hasattr(arg, 'required') and arg.required:
                required_set.add(arg.name)
        
        # Second pass: generate suggestions
        for arg in schema:
            arg_name = None
            default = None
            description = ""
            
            if isinstance(arg, dict):
                arg_name = arg.get('name', '')
                default = arg.get('default')
                description = arg.get('description', '')
            elif hasattr(arg, 'name'):
                arg_name = arg.name
                description = getattr(arg, 'description', '') if hasattr(arg, 'description') else ''
                
                # Try to extract default from PromptArgument (Pydantic model)
                try:
                    if hasattr(arg, 'model_dump'):
                        arg_dict = arg.model_dump(exclude_unset=False, exclude_none=False)
                        default = arg_dict.get('default')
                    elif hasattr(arg, 'dict'):
                        arg_dict = arg.dict(exclude_unset=False, exclude_none=False)
                        default = arg_dict.get('default')
                    elif hasattr(arg, '__dict__'):
                        default = arg.__dict__.get('default')
                    else:
                        default = getattr(arg, 'default', None)
                except Exception:
                    default = None
            
            if arg_name and arg_name not in provided_args:
                is_required = arg_name in required_set
                
                # Validate and clean default value
                if default is not None and not self.validate_default_value(default):
                    default = None
                
                suggestion = self.format_argument_suggestion(
                    arg_name, default, description, is_required
                )
                suggestions.append(suggestion)
        
        return suggestions
    
    def generate_suggestions(
        self,
        command_name: str,
        current_text: str
    ) -> list[DropdownItem]:
        """
        Generate argument suggestions for a command.
        
        Args:
            command_name: Name of the command/prompt
            current_text: Current argument text being typed
            
        Returns:
            List of DropdownItem suggestions for remaining arguments
        """
        if command_name not in self.schema_cache:
            return []
        
        prompt, _ = self.schema_cache[command_name]
        if not hasattr(prompt, 'arguments') or not prompt.arguments:
            return []
        
        schema = prompt.arguments
        current_text = current_text.strip()
        
        # Extract already-provided arguments
        provided_args = self.extract_provided_args(current_text)
        
        # Generate suggestions based on schema type
        if isinstance(schema, dict):
            return self.generate_from_dict_schema(schema, provided_args)
        elif isinstance(schema, list):
            return self.generate_from_list_schema(schema, provided_args)
        else:
            return []

