"""Key-value argument parser for key=value format."""

from typing import Any
from nxs.logger import get_logger

logger = get_logger("parsers")


class KeyValueArgumentParser:
    """Parser for key=value format arguments."""
    
    def parse(
        self,
        query_remaining: str,
        arg_names: list[str],
        schema_dict: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        """
        Parse key=value pairs from query string.
        
        Examples:
            'style="very format"' -> {'style': 'very format'}
            'style=very key2="value with spaces"' -> {'style': 'very', 'key2': 'value with spaces'}
            "style='single quotes'" -> {'style': 'single quotes'}
        
        Args:
            query_remaining: The query string with key=value pairs
            arg_names: List of valid argument names from the schema
            schema_dict: Complete schema dictionary (not used in parsing, but required by protocol)
            
        Returns:
            Dictionary of parsed arguments
        """
        args: dict[str, str] = {}
        
        if '=' not in query_remaining:
            return args
        
        pairs = self._parse_key_value_pairs(query_remaining)
        for key, value in pairs:
            if key in arg_names:
                args[key] = value
                logger.debug(f"Parsed argument '{key}' = '{value}' from key=value format")
        
        return args
    
    def _parse_key_value_pairs(self, text: str) -> list[tuple[str, str]]:
        """
        Parse key=value pairs from text, handling quoted strings correctly.
        
        Examples:
            'style="very format"' -> [('style', 'very format')]
            'style=very key2="value with spaces"' -> [('style', 'very'), ('key2', 'value with spaces')]
            "style='single quotes'" -> [('style', 'single quotes')]
        
        Args:
            text: String containing key=value pairs
            
        Returns:
            List of (key, value) tuples
        """
        pairs = []
        i = 0
        while i < len(text):
            # Skip whitespace
            while i < len(text) and text[i].isspace():
                i += 1
            if i >= len(text):
                break
            
            # Find the key (everything up to =)
            key_start = i
            while i < len(text) and text[i] != '=' and not text[i].isspace():
                i += 1
            
            if i >= len(text) or text[i] != '=':
                # No = found, skip this token
                while i < len(text) and not text[i].isspace():
                    i += 1
                continue
            
            key = text[key_start:i].strip()
            i += 1  # Skip the =
            
            # Skip whitespace after =
            while i < len(text) and text[i].isspace():
                i += 1
            
            if i >= len(text):
                # No value after =
                pairs.append((key, ''))
                break
            
            # Parse the value (handling quoted strings)
            value_start = i
            if text[i] in ['"', "'"]:
                # Quoted string
                quote_char = text[i]
                i += 1  # Skip opening quote
                value_start = i
                # Find closing quote
                while i < len(text) and text[i] != quote_char:
                    # Handle escaped quotes
                    if text[i] == '\\' and i + 1 < len(text) and text[i + 1] == quote_char:
                        i += 2
                    else:
                        i += 1
                value = text[value_start:i]
                i += 1  # Skip closing quote
            else:
                # Unquoted value - take until next space or end
                while i < len(text) and not text[i].isspace():
                    i += 1
                value = text[value_start:i].strip()
            
            pairs.append((key, value))
        
        return pairs

