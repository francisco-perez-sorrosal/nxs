"""Schema adapter for normalizing different schema formats."""

from typing import Any
from nxs.logger import get_logger

logger = get_logger("parsers")


class SchemaInfo:
    """Normalized schema information."""
    
    def __init__(
        self,
        arg_names: list[str],
        required_args: list[str],
        schema_dict: dict[str, dict[str, Any]],
    ):
        self.arg_names = arg_names
        self.required_args = required_args
        self.schema_dict = schema_dict


class SchemaAdapter:
    """Adapter for normalizing different schema formats."""
    
    def normalize(self, schema: Any, command_name: str) -> SchemaInfo | None:
        """
        Normalize schema to a consistent format.
        
        Handles:
            - List of PromptArgument objects
            - Dict with 'properties' (JSON schema format)
            - Objects with 'properties' attribute
        
        Args:
            schema: The schema object (can be list, dict, or object)
            command_name: Command name for logging
            
        Returns:
            SchemaInfo with normalized schema data, or None if schema is invalid
        """
        if not schema:
            logger.debug(f"Prompt '{command_name}' has no arguments schema")
            return None
        
        arg_names: list[str] = []
        required_args: list[str] = []
        
        # Handle different schema formats
        if isinstance(schema, list):
            # List of PromptArgument objects
            for arg in schema:
                if hasattr(arg, 'name'):
                    arg_names.append(arg.name)
                    if hasattr(arg, 'required') and arg.required:
                        required_args.append(arg.name)
                elif isinstance(arg, dict):
                    arg_name = arg.get('name', '')
                    if arg_name:
                        arg_names.append(arg_name)
                        if arg.get('required', False):
                            required_args.append(arg_name)
        elif isinstance(schema, dict):
            # JSON schema format with 'properties'
            properties = schema.get('properties', {})
            arg_names = list(properties.keys())
            required_args = schema.get('required', [])
        else:
            # Try to get properties as an attribute
            if hasattr(schema, 'properties'):
                properties = getattr(schema, 'properties', {})
                if isinstance(properties, dict):
                    arg_names = list(properties.keys())
            if hasattr(schema, 'required'):
                required_args = getattr(schema, 'required', [])
        
        if not arg_names:
            logger.debug(f"Prompt '{command_name}' has no argument properties")
            return None
        
        # Build complete schema dictionary for validation and default extraction
        schema_dict = self._build_schema_dict(schema, command_name)
        
        return SchemaInfo(
            arg_names=arg_names,
            required_args=required_args,
            schema_dict=schema_dict,
        )
    
    def _build_schema_dict(self, schema: Any, command_name: str) -> dict[str, dict[str, Any]]:
        """
        Build a complete schema dictionary with defaults and metadata.
        
        Args:
            schema: The schema object
            command_name: Command name for logging
            
        Returns:
            Dictionary mapping argument names to their schema info
        """
        schema_dict: dict[str, dict[str, Any]] = {}
        
        if isinstance(schema, list):
            # Convert list of PromptArgument to schema dict format
            for arg in schema:
                if isinstance(arg, dict):
                    arg_name = arg.get('name', '')
                    if arg_name:
                        schema_dict[arg_name] = {
                            'required': arg.get('required', False),
                            'default': arg.get('default'),
                            'description': arg.get('description', ''),
                            'type': arg.get('type', 'string')
                        }
                elif hasattr(arg, 'name'):
                    arg_name = arg.name
                    default = self._extract_default(arg)
                    
                    schema_dict[arg_name] = {
                        'required': getattr(arg, 'required', False) if hasattr(arg, 'required') else False,
                        'default': default,
                        'description': getattr(arg, 'description', '') if hasattr(arg, 'description') else '',
                        'type': 'string'
                    }
        elif isinstance(schema, dict):
            # Already in dict format
            properties = schema.get('properties', {})
            if not isinstance(properties, dict):
                logger.warning(f"Prompt '{command_name}' has non-dict properties: {type(properties)}")
                properties = {}
            required_list = schema.get('required', [])
            required_set = set(required_list) if isinstance(required_list, list) else set()
            for arg_name, arg_spec in properties.items():
                if isinstance(arg_spec, dict):
                    schema_dict[arg_name] = {
                        'required': arg_name in required_set,
                        'default': arg_spec.get('default'),
                        'description': arg_spec.get('description', ''),
                        'type': arg_spec.get('type', 'string')
                    }
                else:
                    schema_dict[arg_name] = {
                        'required': arg_name in required_set,
                        'default': None,
                        'description': getattr(arg_spec, 'description', '') if hasattr(arg_spec, 'description') else '',
                        'type': 'string'
                    }
        
        return schema_dict
    
    def _extract_default(self, arg: Any) -> Any:
        """
        Extract default value from an argument object, handling Pydantic models.
        
        Args:
            arg: Argument object (may be Pydantic model)
            
        Returns:
            Default value or None
        """
        default = None
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
            pass
        
        # Filter out invalid defaults (PydanticUndefined, etc.)
        if default is not None:
            default_str = str(default)
            if 'Undefined' in default_str or 'PydanticUndefined' in default_str:
                default = None
            elif 'class' in default_str.lower() and '<' in default_str:
                default = None
        
        return default

