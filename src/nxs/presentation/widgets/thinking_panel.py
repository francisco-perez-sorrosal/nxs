"""
ThinkingPanel - Unified display for reasoning traces and tool execution.

Combines the previous StatusPanel and ReasoningTracePanel into a single,
chronological view of the agent's thinking process.
"""

from textual.widgets import RichLog
from rich.panel import Panel
from rich.table import Table
from rich.json import JSON
from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text
import json
from typing import Any, Iterable, Tuple, Optional

from nxs.application.reasoning.types import ComplexityAnalysis, ExecutionStrategy, EvaluationResult


class ThinkingPanel(RichLog):
    """
    Unified thinking process panel showing reasoning and tool execution.

    Displays events chronologically as they occur:
    - 🧠 Reasoning events (complexity, strategy, planning, quality)
    - 🔧 Tool calls and results
    - ⚡ Auto-escalation alerts

    Features:
    - Chronological event ordering
    - Beautiful Rich formatting with panels, tables, syntax highlighting
    - Color-coded by event type and status
    - Auto-scrolling
    - Collapsible via keyboard shortcut
    """

    BORDER_TITLE = "Thinking Process"

    # Color schemes for different event types
    STRATEGY_COLORS = {
        "DIRECT": "green",
        "LIGHT_PLANNING": "yellow",
        "DEEP_REASONING": "red",
    }

    COMPLEXITY_COLORS = {
        "SIMPLE": "green",
        "MEDIUM": "yellow",
        "COMPLEX": "red",
    }

    def __init__(self, **kwargs):
        """Initialize the thinking panel with Rich markup enabled."""
        super().__init__(markup=True, highlight=True, auto_scroll=True, wrap=True, **kwargs)
        self.border_title = self.BORDER_TITLE
        self.border_style = "cyan"
        self.show_border = True
        self.write("[bold cyan]🧠 Adaptive Reasoning & Tool Execution[/]\n")
        self.add_divider()

    # ====================================================================
    # 🧠 REASONING EVENTS
    # ====================================================================

    def on_analysis_start(self):
        """Display complexity analysis start message."""
        self.write("[dim]🔍 Analyzing query complexity...[/]\n")

    def on_analysis_complete(self, complexity: ComplexityAnalysis):
        """
        Display complexity analysis result.

        Args:
            complexity: ComplexityAnalysis with level, strategy, reasoning
        """
        table = Table(
            title="Complexity Analysis",
            show_header=False,
            border_style="blue",
            expand=False,
        )
        table.add_column("Field", style="cyan bold", width=18)
        table.add_column("Value", style="white")

        # Color-code complexity level
        level_color = self.COMPLEXITY_COLORS.get(complexity.complexity_level.value, "white")
        table.add_row("Complexity", f"[{level_color} bold]{complexity.complexity_level.value}[/]")

        # Color-code strategy
        strategy_color = self.STRATEGY_COLORS.get(complexity.recommended_strategy.value, "white")
        table.add_row("Strategy", f"[{strategy_color} bold]{complexity.recommended_strategy.value}[/]")

        table.add_row("Iterations", str(complexity.estimated_iterations))

        # Truncate long rationale
        rationale = complexity.rationale
        if len(rationale) > 120:
            rationale = rationale[:120] + "..."
        table.add_row("Reasoning", rationale)

        panel = Panel(table, border_style="blue", expand=False)
        self.write(panel)
        self.write("\n")

    def on_strategy_selected(self, strategy: ExecutionStrategy, reason: str):
        """
        Display strategy selection.

        Args:
            strategy: Selected execution strategy
            reason: Reason for selection
        """
        color = self.STRATEGY_COLORS.get(strategy.value, "white")
        self.write(f"[{color} bold]▶ Executing with {strategy.value} strategy[/]\n")
        if reason:
            self.write(f"[dim]  {reason}[/]\n")
        self.write("\n")

    def on_planning_start(self):
        """Display planning start message."""
        self.write("[dim]📋 Generating execution plan...[/]\n")

    def on_planning_complete(self, plan, mode: str):
        """
        Display planning completion with plan steps.

        Args:
            plan: ResearchPlan object with subtasks
            mode: Planning mode (light or deep)
        """
        mode_color = "yellow" if mode == "light" else "red"
        subtask_count = len(plan.subtasks) if plan and plan.subtasks else 0

        self.write(f"[{mode_color} bold]✓ Plan ready ({mode} mode): {subtask_count} step(s)[/]\n")

        # Show plan steps in a table
        if plan and plan.subtasks:
            plan_table = Table(
                show_header=True,
                border_style=mode_color,
                expand=False,
                title="Execution Plan",
            )
            plan_table.add_column("#", style="dim", width=3, justify="right")
            plan_table.add_column("Step", style="white", overflow="fold")

            for i, subtask in enumerate(plan.subtasks, 1):
                plan_table.add_row(str(i), subtask.query)

            panel = Panel(plan_table, border_style=mode_color, expand=False)
            self.write(panel)
        self.write("\n")

    def on_response_for_judgment(self, response: str, strategy: str):
        """
        Display the response being evaluated.

        Args:
            response: Assistant's response to judge
            strategy: Strategy used to generate response
        """
        # Show the full response being judged (no truncation)
        text = Text()
        text.append("Response for Evaluation:\n", style="cyan bold")
        text.append(response, style="white")

        panel = Panel(
            text,
            title=f"[yellow]Judging {strategy} Response[/]",
            border_style="yellow",
            expand=False,
        )
        self.write(panel)
        self.write("\n")

    def on_quality_check_start(self):
        """Display quality evaluation start message."""
        self.write("[dim]🔎 Evaluating response quality...[/]\n")

    def on_quality_check_complete(self, evaluation: EvaluationResult):
        """
        Display quality evaluation result.

        Args:
            evaluation: EvaluationResult with quality assessment
        """
        status = "SUFFICIENT" if evaluation.is_complete else "INSUFFICIENT"
        status_color = "green" if evaluation.is_complete else "red"
        status_icon = "✓" if evaluation.is_complete else "✗"

        # Summary table
        table = Table(
            title="Quality Evaluation",
            show_header=False,
            border_style=status_color,
            expand=False,
        )
        table.add_column("Field", style="cyan bold", width=18)
        table.add_column("Value", style="white")

        table.add_row("Status", f"[{status_color} bold]{status_icon} {status}[/]")
        table.add_row("Confidence", f"{evaluation.confidence:.2f}")

        panel = Panel(table, border_style=status_color, expand=False)
        self.write(panel)
        self.write("\n")

        # Show judge's reasoning in detail
        if evaluation.reasoning:
            reasoning_panel = Panel(
                evaluation.reasoning,
                title="[yellow]Judge's Assessment[/]",
                border_style="yellow",
                expand=False,
            )
            self.write(reasoning_panel)
            self.write("\n")

    def on_auto_escalation(
        self,
        from_strategy: ExecutionStrategy,
        to_strategy: ExecutionStrategy,
        reason: str,
        confidence: float,
    ):
        """
        Display auto-escalation alert.

        Args:
            from_strategy: Strategy being escalated from
            to_strategy: Strategy being escalated to
            reason: Reason for escalation
            confidence: Quality score that triggered escalation
        """
        text = Text()
        text.append("⚡ AUTO-ESCALATION ", style="bold red blink")
        text.append(f"{from_strategy.value}", style="yellow bold")
        text.append(" → ", style="white")
        text.append(f"{to_strategy.value}\n", style="red bold")
        text.append(f"\nQuality: {confidence:.2f}\n", style="dim")
        text.append(reason, style="white")  # Show full reason, no truncation

        panel = Panel(
            text,
            border_style="red",
            expand=False,
        )
        self.write(panel)
        self.write("\n")

    def on_final_response(
        self,
        strategy_used: ExecutionStrategy,
        attempts: int,
        final_quality: float,
        escalated: bool,
    ):
        """
        Display final response summary.

        Args:
            strategy_used: Final strategy that produced response
            attempts: Number of execution attempts
            final_quality: Final quality score
            escalated: Whether strategy was escalated
        """
        table = Table(
            title="✅ Response Complete",
            show_header=False,
            border_style="green",
            expand=False,
        )
        table.add_column("Field", style="cyan bold", width=18)
        table.add_column("Value", style="white")

        strategy_color = self.STRATEGY_COLORS.get(strategy_used.value, "green")
        table.add_row("Final Strategy", f"[{strategy_color} bold]{strategy_used.value}[/]")
        table.add_row("Attempts", str(attempts))
        table.add_row("Quality Score", f"{final_quality:.2f}")
        table.add_row("Escalated", "[yellow bold]Yes[/]" if escalated else "[green]No[/]")

        panel = Panel(table, border_style="green", expand=False)
        self.write(panel)
        self.write("\n")
        self.add_divider()

    # ====================================================================
    # 🔧 TOOL EXECUTION EVENTS
    # ====================================================================

    def add_tool_call(self, name: str, params: dict):
        """
        Display a tool call with parameters.

        Args:
            name: Tool name
            params: Tool parameters as dictionary
        """
        # Format params with truncation
        formatted_params = self._format_json_data(params)
        params_display = self._build_display_with_code(formatted_params)

        panel = Panel(
            params_display,
            title=f"[bold cyan]🔧 Tool Call: {name}[/]",
            border_style="cyan",
            expand=False,
        )
        self.write(panel)
        self.write("\n")

    def add_tool_result(self, tool_name: str, result: str | list | dict, success: bool = True):
        """
        Display tool execution result.

        Args:
            tool_name: Name of executed tool
            result: Result data (JSON string, dict, list, or text)
            success: Whether execution succeeded
        """
        status_icon = "✓" if success else "✗"
        status_color = "green" if success else "red"

        # Format result with syntax highlighting
        formatted_result = self._format_json_data(result)
        result_display = self._build_display_with_code(formatted_result)

        panel = Panel(
            result_display,
            title=f"[{status_color} bold]{status_icon} Result: {tool_name}[/]",
            border_style=status_color,
            expand=False,
        )
        self.write(panel)
        self.write("\n")

    # ====================================================================
    # INFO & STATUS MESSAGES
    # ====================================================================

    def add_info_message(self, message: str):
        """Add informational message."""
        self.write(f"[dim]ℹ {message}[/]\n")

    def add_error_message(self, message: str):
        """Add error message."""
        self.write(f"[bold red]✗ Error:[/] {message}\n")

    def add_success_message(self, message: str):
        """Add success message."""
        self.write(f"[bold green]✓ {message}[/]\n")

    # ====================================================================
    # UTILITY METHODS
    # ====================================================================

    def add_divider(self):
        """Add visual divider between thinking sessions."""
        self.write("[dim]" + "═" * 70 + "[/]\n")

    def clear_panel(self):
        """Clear all content."""
        self.clear()
        self.write("[bold cyan]🧠 Adaptive Reasoning & Tool Execution[/]\n")
        self.add_divider()

    # ====================================================================
    # DATA FORMATTING (from StatusPanel)
    # ====================================================================

    def _truncate_content_fields(self, obj: Any) -> Any:
        """Recursively truncate content fields to prevent overwhelming display."""
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
                    new_obj[key] = self._truncate_content_fields(value)
            return new_obj
        elif isinstance(obj, list):
            return [self._truncate_content_fields(item) for item in obj]
        else:
            return obj

    def _format_json_data(self, data: str | list | dict) -> Any:
        """Format JSON data with parsing and truncation."""
        if isinstance(data, (dict, list)):
            normalized = self._normalize_structure(data)
            return self._truncate_content_fields(normalized)
        elif isinstance(data, str):
            try:
                parsed_data = json.loads(data)
                normalized = self._normalize_structure(parsed_data)
                return self._truncate_content_fields(normalized)
            except json.JSONDecodeError:
                try:
                    import ast
                    parsed_data = ast.literal_eval(data)
                    normalized = self._normalize_structure(parsed_data)
                    return self._truncate_content_fields(normalized)
                except (ValueError, SyntaxError):
                    return data
        else:
            return data

    def _create_json_display(self, formatted_data: Any) -> Any:
        """Create Rich JSON display from formatted data."""
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
            return Text(str(formatted_data))

    def _format_json_array(self, data: list) -> Any | None:
        """Format list of dicts as table when feasible."""
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

        json_str = json.dumps(normalized_items, indent=2, ensure_ascii=False)
        return JSON(json_str)

    def _build_display_with_code(self, formatted_data: Any) -> Any:
        """Combine structured data with syntax-highlighted code snippets."""
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
        """Render code with syntax highlighting."""
        normalized = self._normalize_multiline_text(code).strip("\n")
        return Syntax(normalized, "python", theme="monokai", line_numbers=True)

    def _extract_code_snippets(self, data: Any, path: str = "") -> Iterable[Tuple[str, str]]:
        """Extract Python code snippets from data structures."""
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

    def _normalize_structure(self, data: Any) -> Any:
        """Recursively parse strings containing structured data."""
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

    def _maybe_parse_structure(self, text: str) -> Any | None:
        """Try to parse string as JSON or Python literal."""
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

    def _normalize_multiline_text(self, text: str) -> str:
        """Convert escaped newlines/tabs to real whitespace."""
        return (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
        )

    def _looks_like_python(self, text: str) -> bool:
        """Heuristic to detect Python code."""
        stripped = self._normalize_multiline_text(text).strip()
        if stripped.count("\n") < 1:
            return False
        python_indicators = (
            "def ", "class ", "import ", "from ", "for ", "while ",
            " if ", "elif ", "try:", "except ", "with ", "return ",
            "print(", "lambda ", "async def ", "await ",
        )
        return any(indicator in stripped for indicator in python_indicators)
