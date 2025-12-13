"""
StatusPanel - A scrollable status display for tool calls and results.
"""

import json
from typing import Any, Iterable, Tuple

from rich.console import Group
from rich.json import JSON
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual.widgets import RichLog


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
        super().__init__(markup=True, highlight=True, auto_scroll=True, wrap=True, **kwargs)
        self.border_title = self.BORDER_TITLE
        self.border_style = "yellow"
        self.show_border = True
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
        params_display = self._build_display_with_code(formatted_params)

        panel = Panel(params_display, title=f"[bold cyan]🔧 Tool Call: {name}[/]", border_style="cyan", expand=False)
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
                if key in {"content", "code", "stdout", "stderr"} and isinstance(value, str):
                    normalized_value = self._normalize_multiline_text(value)
                    if key == "code" or self._looks_like_python(normalized_value):
                        new_obj[key] = normalized_value
                    elif len(value) > 200:
                        new_obj[key] = value[:200] + "... (truncated)"
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
            normalized = self._normalize_structure(data)
            return self._truncate_content_fields(normalized)
        elif isinstance(data, str):
            # Try to parse as JSON first
            try:
                parsed_data = json.loads(data)
                normalized = self._normalize_structure(parsed_data)
                return self._truncate_content_fields(normalized)
            except json.JSONDecodeError:
                # Not JSON, try to parse as Python repr (e.g., "[{...}, {...}]")
                try:
                    import ast

                    parsed_data = ast.literal_eval(data)
                    normalized = self._normalize_structure(parsed_data)
                    return self._truncate_content_fields(normalized)
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
        if isinstance(formatted_data, dict):
            json_str = json.dumps(formatted_data, indent=2, ensure_ascii=False)
            return JSON(json_str)
        if isinstance(formatted_data, list):
            renderable = self._format_json_array(formatted_data)
            if renderable is not None:
                return renderable
            json_str = json.dumps(formatted_data, indent=2, ensure_ascii=False)
            return JSON(json_str)
        else:
            # It's a string, display as rich text
            return Text(str(formatted_data))

    def _format_json_array(self, data: list) -> Any | None:
        """Format a list of dicts as a table when feasible."""
        if not data:
            return JSON("[]")

        normalized_items: list[Any] = [self._normalize_structure(item) for item in data]

        if all(isinstance(item, dict) for item in normalized_items):
            first = normalized_items[0]
            keys = list(first.keys())
            if keys and all(set(item.keys()) == set(keys) for item in normalized_items):
                table = Table(show_header=True, header_style="bold cyan", expand=True)
                for key in keys:
                    table.add_column(str(key), overflow="fold")

                for item in normalized_items:
                    row: list[str] = []
                    for key in keys:
                        value = item.get(key)
                        if isinstance(value, (dict, list)):
                            row.append(json.dumps(value, ensure_ascii=False))
                        else:
                            row.append(str(value))
                    table.add_row(*row)

                return table

        # Fallback to JSON display
        json_str = json.dumps(normalized_items, indent=2, ensure_ascii=False)
        return JSON(json_str)

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
        result_display = self._build_display_with_code(formatted_result)

        panel = Panel(
            result_display,
            title=f"[{status_color}]{status_icon} Result: {tool_name}[/]",
            border_style=border_color,
            expand=False,
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

    # Phase 6: Tracker progress display methods

    def add_progress_summary(self, tracker_data: dict):
        """
        Phase 6: Display research progress summary.

        Args:
            tracker_data: Dictionary with tracker information:
                - attempts: List of attempt summaries
                - plan_progress: Dict with completed/total steps
                - tool_summary: Dict with successful/total tools
                - knowledge_gaps: List of identified gaps
        """
        # Build summary text
        summary_parts = []

        # Attempts summary
        if "attempts" in tracker_data:
            attempts = tracker_data["attempts"]
            summary_parts.append(f"[bold]Attempts:[/] {len(attempts)}")
            for attempt in attempts:
                strategy = attempt.get("strategy", "unknown")
                quality = attempt.get("quality_score", "N/A")
                summary_parts.append(f"  - {strategy}: Quality {quality}")

        # Plan progress
        if "plan_progress" in tracker_data:
            progress = tracker_data["plan_progress"]
            completed = progress.get("completed", 0)
            total = progress.get("total", 0)
            summary_parts.append(f"\n[bold]Plan Progress:[/] {completed}/{total} steps completed")

        # Tool summary
        if "tool_summary" in tracker_data:
            tool_sum = tracker_data["tool_summary"]
            successful = tool_sum.get("successful", 0)
            total_tools = tool_sum.get("total", 0)
            summary_parts.append(f"[bold]Tools:[/] {successful}/{total_tools} successful")

        # Knowledge gaps
        if "knowledge_gaps" in tracker_data:
            gaps = tracker_data["knowledge_gaps"]
            if gaps:
                gaps_text = ", ".join(gaps[:3])
                summary_parts.append(f"[bold]Knowledge Gaps:[/] {gaps_text}")

        # Display summary
        if summary_parts:
            summary_text = "\n".join(summary_parts)
            panel = Panel(
                summary_text,
                title="[bold cyan]📊 Research Progress[/]",
                border_style="cyan",
                expand=False,
            )
            self.write(panel)
            self.write("\n")

    def add_plan_progress(self, completed_steps: list, pending_steps: list):
        """
        Phase 6: Display plan progress with completed and pending steps.

        Args:
            completed_steps: List of completed step descriptions
            pending_steps: List of pending step descriptions
        """
        table = Table(title="Plan Progress", show_header=True, header_style="bold cyan")
        table.add_column("Status", style="white")
        table.add_column("Step", style="cyan")

        # Add completed steps
        for step in completed_steps[:10]:  # Limit to 10 for display
            table.add_row("[green]✓[/]", step)

        # Add pending steps
        for step in pending_steps[:10]:  # Limit to 10 for display
            table.add_row("[yellow]○[/]", step)

        if len(completed_steps) + len(pending_steps) > 20:
            table.add_row(
                "[dim]...[/]",
                f"[dim]{len(completed_steps) + len(pending_steps) - 20} more steps[/]",
            )

        self.write(table)
        self.write("\n")

    def add_tool_execution_log(self, tool_executions: list):
        """
        Phase 6: Display tool execution log.

        Args:
            tool_executions: List of tool execution dictionaries with:
                - tool_name: Name of the tool
                - success: Whether execution succeeded
                - execution_time_ms: Execution time in milliseconds
                - result: Tool result (truncated)
        """
        table = Table(
            title="Tool Execution Log", show_header=True, header_style="bold cyan"
        )
        table.add_column("Tool", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("Time", style="dim")
        table.add_column("Result", style="white", overflow="fold")

        # Display recent executions (last 10)
        for exec_data in tool_executions[-10:]:
            tool_name = exec_data.get("tool_name", "unknown")
            success = exec_data.get("success", False)
            time_ms = exec_data.get("execution_time_ms", 0)
            result = exec_data.get("result", "")

            status_icon = "[green]✓[/]" if success else "[red]✗[/]"
            time_str = f"{time_ms:.0f}ms" if time_ms > 0 else "N/A"
            result_preview = result[:50] + "..." if len(result) > 50 else result

            table.add_row(tool_name, status_icon, time_str, result_preview)

        if len(tool_executions) > 10:
            table.add_row(
                "[dim]...[/]",
                "",
                "",
                f"[dim]{len(tool_executions) - 10} more executions[/]",
            )

        self.write(table)
        self.write("\n")

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _build_display_with_code(self, formatted_data: Any) -> Any:
        """Combine structured data display with highlighted code snippets."""
        if isinstance(formatted_data, str) and self._looks_like_python(formatted_data):
            return self._render_code_snippet(formatted_data)

        snippets = list(self._extract_code_snippets(formatted_data))
        base_display = self._create_json_display(formatted_data)

        if not snippets:
            return base_display

        renderables: list[Any] = []

        if base_display and not (
            isinstance(formatted_data, str)
            and len(snippets) == 1
            and snippets[0][1].strip() == str(formatted_data).strip()
        ):
            renderables.append(base_display)
            renderables.append(Text())

        for path, code in snippets:
            label = Text(path or "Code", style="bold magenta")
            renderables.append(label)
            renderables.append(self._render_code_snippet(code))
            renderables.append(Text())

        if renderables and isinstance(renderables[-1], Text) and not renderables[-1].plain:
            renderables.pop()

        return Group(*renderables) if len(renderables) > 1 else renderables[0]

    def _render_code_snippet(self, code: str) -> Syntax:
        normalized = self._normalize_multiline_text(code).strip("\n")
        return Syntax(normalized, "python", theme="monokai", line_numbers=True)

    def _extract_code_snippets(self, data: Any, path: str = "") -> Iterable[Tuple[str, str]]:
        """Yield probable Python code snippets found within data structures."""
        if isinstance(data, dict):
            for key, value in data.items():
                next_path = f"{path}.{key}" if path else key
                yield from self._extract_code_snippets(value, next_path)
        elif isinstance(data, list):
            for index, item in enumerate(data):
                next_path = f"{path}[{index}]" if path else f"[{index}]"
                yield from self._extract_code_snippets(item, next_path)
        elif isinstance(data, str):
            normalized = self._normalize_multiline_text(data)

            if self._looks_like_python(normalized):
                yield path, normalized

    def _maybe_parse_structure(self, text: str) -> Any | None:
        stripped = text.strip()
        if not stripped:
            return None

        if (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        ):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                import ast

                try:
                    return ast.literal_eval(stripped)
                except (ValueError, SyntaxError):
                    return None
        return None

    def _normalize_structure(self, data: Any) -> Any:
        """Recursively parse strings that contain structured data."""
        if isinstance(data, dict):
            return {key: self._normalize_structure(value) for key, value in data.items()}
        if isinstance(data, list):
            return [self._normalize_structure(item) for item in data]
        if isinstance(data, str):
            parsed = self._maybe_parse_structure(data)
            if parsed is not None:
                return self._normalize_structure(parsed)
            return data
        return data

    def _normalize_multiline_text(self, text: str) -> str:
        """Convert escaped newline/tab sequences into real whitespace."""
        return (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
        )

    def _looks_like_python(self, text: str) -> bool:
        stripped = self._normalize_multiline_text(text).strip()
        if stripped.count("\n") < 1:
            return False
        python_indicators = (
            "def ",
            "class ",
            "import ",
            "from ",
            "for ",
            "while ",
            " if ",
            "elif ",
            "try:",
            "except ",
            "with ",
            "return ",
            "print(",
            "lambda ",
            "async def ",
            "await ",
        )
        return any(indicator in stripped for indicator in python_indicators)
