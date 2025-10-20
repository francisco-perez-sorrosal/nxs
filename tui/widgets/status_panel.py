"""
StatusPanel - A scrollable status display for tool calls and results.
"""

from textual.widgets import RichLog
from rich.panel import Panel
from rich.table import Table
from rich.json import JSON
import json


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
        # Create a panel for the tool call
        try:
            # Try to format params as JSON for better readability
            params_str = json.dumps(params, indent=2)
            params_display = JSON(params_str)
        except:
            # Fallback to string representation
            params_display = str(params)

        panel = Panel(
            params_display,
            title=f"[bold cyan]🔧 Tool Call: {name}[/]",
            border_style="cyan",
            expand=False
        )
        self.write(panel)
        self.write("\n")

    def add_tool_result(self, tool_name: str, result: str, success: bool = True):
        """
        Display a tool execution result.

        Args:
            tool_name: Name of the tool that was executed
            result: Result text or data
            success: Whether the tool executed successfully
        """
        status_icon = "✓" if success else "✗"
        status_color = "green" if success else "red"
        border_color = "green" if success else "red"

        panel = Panel(
            result,
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
