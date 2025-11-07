"""Positional argument parser for space-separated arguments."""

from typing import Any
from nxs.core.parsers.base import ArgumentParser
from nxs.logger import get_logger

logger = get_logger("parsers")


class PositionalArgumentParser:
    """Parser for positional (space-separated) arguments."""
    
    def parse(
        self,
        query_remaining: str,
        arg_names: list[str],
        schema_dict: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        """
        Parse positional arguments from query string.
        
        Examples:
            'value1 value2' -> {'arg1': 'value1', 'arg2': 'value2'}
            '@resource_id' -> {'arg1': 'resource_id'} (when single arg)
            '@mcp://server/resource' -> {'arg1': 'resource'}
        
        Args:
            query_remaining: The query string with space-separated values
            arg_names: List of valid argument names from the schema
            schema_dict: Complete schema dictionary (not used in parsing, but required by protocol)
            
        Returns:
            Dictionary of parsed arguments
        """
        args: dict[str, str] = {}
        
        # Special case: single argument with @ resource reference
        if len(arg_names) == 1 and query_remaining.startswith('@'):
            arg_name = arg_names[0]
            resource_ref = query_remaining[1:].strip()
            resource_id = self._extract_resource_id(resource_ref)
            args[arg_name] = resource_id
            logger.debug(f"Parsed single argument '{arg_name}' = '{resource_id}' from resource reference")
            return args
        
        # Parse as positional arguments
        values = query_remaining.split()
        for i, arg_name in enumerate(arg_names):
            if i < len(values):
                value = values[i].strip().strip('"').strip("'")
                # Remove @ prefix if present
                if value.startswith('@'):
                    value = value[1:]
                    value = self._extract_resource_id(value)
                args[arg_name] = value
                logger.debug(f"Parsed positional argument '{arg_name}' = '{value}'")
        
        return args
    
    def _extract_resource_id(self, resource_ref: str) -> str:
        """
        Extract resource ID from various formats.
        
        Handles:
            - 'mcp://server/resource_id' -> 'resource_id'
            - 'server:resource_id' -> 'resource_id'
            - 'resource_id' -> 'resource_id'
        
        Args:
            resource_ref: Resource reference string
            
        Returns:
            Extracted resource ID
        """
        # If it contains a colon, it might be "mcp_name:resource_id"
        if ':' in resource_ref and not resource_ref.startswith('mcp://'):
            parts = resource_ref.split(':', 1)
            resource_ref = parts[1] if len(parts) > 1 else resource_ref
        
        # Extract just the resource identifier (remove mcp:// prefix if present)
        if resource_ref.startswith('mcp://'):
            # Extract resource ID from URI like "mcp://server/resource_id"
            resource_id = resource_ref.split('/', 3)[-1] if '/' in resource_ref[6:] else resource_ref
        else:
            resource_id = resource_ref
        
        return resource_id

