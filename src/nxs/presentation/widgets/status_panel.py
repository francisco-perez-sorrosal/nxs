"""
StatusPanel - A scrollable status display for tool calls and results.
"""

from textual.widgets import RichLog
from rich.panel import Panel
from rich.table import Table
from rich.json import JSON
import json
from typing import Any


class StatusPanel(RichLog):
    """
    A status panel that displays tool execution information.

    Features:
    - Displays tool calls with parameters
    - Shows tool results with success/failure indicators
    - Rich formatting for structured data
    - Auto-scrolling
    """

    BORDER_TITLE = "Status"

    def __init__(self, **kwargs):
        """Initialize the status panel with Rich markup enabled."""
        super().__init__(
            markup=True,
            highlight=True,
            auto_scroll=True,
            wrap=True,
            **kwargs
        )
        self.write("[bold yellow]Tool Execution Status[/]\n")
        self.add_divider()

    def add_tool_call(self, name: str, params: dict):
        """
        Display a tool call with its parameters.

        Args:
            name: Tool name
            params: Tool parameters as a dictionary
        """
        # Format params with content truncation (same pipeline as tool results)
        formatted_params = self._format_json_data(params)
        params_display = self._create_json_display(formatted_params)

        panel = Panel(
            params_display,
            title=f"[bold cyan]🔧 Tool Call: {name}[/]",
            border_style="cyan",
            expand=False
        )
        self.write(panel)
        self.write("\n")

    def _truncate_content_fields(self, obj: Any) -> Any:
        """
        Recursively truncate 'content' fields in JSON objects/arrays to 100 characters.
        
        Args:
            obj: Data structure (dict, list, or primitive)
            
        Returns:
            Data structure with truncated content fields
        """
        if isinstance(obj, dict):
            new_obj = {}
            for key, value in obj.items():
                if key == "content" and isinstance(value, str):
                    # Truncate content to 100 chars
                    if len(value) > 100:
                        new_obj[key] = value[:100] + "... (truncated)"
                    else:
                        new_obj[key] = value
                else:
                    # Recursively process nested structures
                    new_obj[key] = self._truncate_content_fields(value)
            return new_obj
        elif isinstance(obj, list):
            # Process each element in the array
            return [self._truncate_content_fields(item) for item in obj]
        else:
            # Return primitive values as-is
            return obj
    
    def _format_json_data(self, data: str | list | dict) -> Any:
        """
        Format JSON data with parsing and content truncation.
        
        Handles different input types (JSON strings, Python repr strings, dicts, lists),
        parses them, and truncates content fields for display.
        
        Args:
            data: Data that may be a string (JSON or Python repr), list, or dict
            
        Returns:
            Formatted data structure (dict/list) with truncated content fields, or original string if not parseable
        """
        # Handle different input types
        if isinstance(data, (dict, list)):
            # Already a data structure, truncate and return
            return self._truncate_content_fields(data)
        elif isinstance(data, str):
            # Try to parse as JSON first
            try:
                parsed_data = json.loads(data)
                return self._truncate_content_fields(parsed_data)
            except json.JSONDecodeError:
                # Not JSON, try to parse as Python repr (e.g., "[{...}, {...}]")
                try:
                    import ast
                    parsed_data = ast.literal_eval(data)
                    return self._truncate_content_fields(parsed_data)
                except (ValueError, SyntaxError):
                    # Not parseable, return as-is
                    return data
        else:
            # Unknown type, return as-is
            return data
    
    def _create_json_display(self, formatted_data: Any) -> Any:
        """
        Create Rich JSON display object from formatted data.
        
        Args:
            formatted_data: Formatted data structure (dict/list) or string
            
        Returns:
            Rich JSON object for display, or plain string if not a data structure
        """
        if isinstance(formatted_data, (dict, list)):
            # It's a data structure, use Rich JSON for pretty formatting
            json_str = json.dumps(formatted_data, indent=2, ensure_ascii=False)
            return JSON(json_str)
        else:
            # It's a string, display as plain text
            return formatted_data

    def add_tool_result(self, tool_name: str, result: str | list | dict, success: bool = True):
        """
        Display a tool execution result.

        Args:
            tool_name: Name of the tool that was executed
            result: Result text or data (may be JSON string, Python repr string, or data structure)
            success: Whether the tool executed successfully
        """
        status_icon = "✓" if success else "✗"
        status_color = "green" if success else "red"
        border_color = "green" if success else "red"

        # Format the result with pretty JSON and truncated content (same pipeline as tool calls)
        formatted_result = self._format_json_data(result)
        result_display = self._create_json_display(formatted_result)

        panel = Panel(
            result_display,
            title=f"[{status_color}]{status_icon} Result: {tool_name}[/]",
            border_style=border_color,
            expand=False
        )
        self.write(panel)
        self.write("\n")

    def add_info_message(self, message: str):
        """
        Add an informational message to the status panel.

        Args:
            message: Info message text
        """
        self.write(f"[dim]ℹ {message}[/]\n")

    def add_error_message(self, message: str):
        """
        Add an error message to the status panel.

        Args:
            message: Error message text
        """
        self.write(f"[bold red]✗ Error:[/] {message}\n")

    def add_success_message(self, message: str):
        """
        Add a success message to the status panel.

        Args:
            message: Success message text
        """
        self.write(f"[bold green]✓ {message}[/]\n")

    def add_table(self, title: str, data: dict):
        """
        Add a table display for structured data.

        Args:
            title: Table title
            data: Dictionary to display as key-value pairs
        """
        table = Table(title=title, show_header=True, header_style="bold cyan")
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="white")

        for key, value in data.items():
            table.add_row(str(key), str(value))

        self.write(table)
        self.write("\n")

    def add_divider(self):
        """Add a visual divider between sections."""
        self.write("[dim]" + "─" * 60 + "[/]\n")

    def clear_status(self):
        """Clear all status messages."""
        self.clear()
        self.write("[bold yellow]Tool Execution Status[/]\n")
        self.add_divider()
