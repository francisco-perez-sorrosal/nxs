"""
ReasoningTracePanel - A collapsible trace display for adaptive reasoning events.
"""

from textual.widgets import RichLog
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nxs.application.reasoning.types import ComplexityAnalysis, ExecutionStrategy, EvaluationResult


class ReasoningTracePanel(RichLog):
    """
    A reasoning trace panel that displays adaptive reasoning events.

    Features:
    - Shows complexity analysis results
    - Displays strategy selection and changes
    - Shows planning steps
    - Displays quality evaluation
    - Highlights auto-escalation events
    - Collapsible via keyboard shortcut
    - Rich formatting for structured data
    - Auto-scrolling

    Events:
    - on_analysis_start: Analysis phase begins
    - on_analysis_complete: Complexity analysis result
    - on_strategy_selected: Strategy selected for execution
    - on_planning_start: Planning phase begins
    - on_planning_complete: Planning result
    - on_quality_check_start: Quality evaluation begins
    - on_quality_check_complete: Quality evaluation result
    - on_auto_escalation: Strategy escalated due to insufficient quality
    - on_final_response: Final response delivered
    """

    BORDER_TITLE = "Reasoning Trace"
    
    # Color mapping for strategies and complexity levels
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
        """Initialize the reasoning trace panel with Rich markup enabled."""
        super().__init__(markup=True, highlight=True, auto_scroll=True, wrap=True, **kwargs)
        self.write("[bold magenta]Adaptive Reasoning Trace[/]\n")
        self.add_divider()

    # ====================================================================
    # Complexity Analysis Events
    # ====================================================================

    def on_analysis_start(self):
        """Display analysis start message."""
        self.write("[dim]🔍 Starting complexity analysis...[/]\n")

    def on_analysis_complete(self, complexity: ComplexityAnalysis):
        """
        Display complexity analysis result.

        Args:
            complexity: ComplexityAnalysis result with level, strategy, and reasoning
        """
        # Create a table for the analysis
        table = Table(
            title="Complexity Analysis",
            show_header=False,
            border_style="blue",
            expand=False,
        )
        table.add_column("Field", style="cyan", width=20)
        table.add_column("Value", style="white")

        # Color-code complexity level
        level_color = self.COMPLEXITY_COLORS.get(complexity.complexity_level.value, "white")
        table.add_row("Complexity", f"[{level_color}]{complexity.complexity_level.value}[/]")

        # Color-code strategy
        strategy_color = self.STRATEGY_COLORS.get(complexity.recommended_strategy.value, "white")
        table.add_row("Strategy", f"[{strategy_color}]{complexity.recommended_strategy.value}[/]")

        table.add_row("Iterations", str(complexity.estimated_iterations))
        table.add_row("Reasoning", complexity.rationale[:100] + "..." if len(complexity.rationale) > 100 else complexity.rationale)

        panel = Panel(table, border_style="blue", expand=False)
        self.write(panel)
        self.write("\n")

    # ====================================================================
    # Strategy Selection Events
    # ====================================================================

    def on_strategy_selected(self, strategy: ExecutionStrategy, reason: str):
        """
        Display strategy selection.

        Args:
            strategy: Selected execution strategy
            reason: Reason for selection
        """
        color = self.STRATEGY_COLORS.get(strategy.value, "white")
        self.write(f"[{color}]▶ Executing with {strategy.value} strategy[/]\n")
        if reason:
            self.write(f"[dim]  Reason: {reason}[/]\n")
        self.write("\n")

    # ====================================================================
    # Planning Events
    # ====================================================================

    def on_planning_start(self):
        """Display planning start message."""
        self.write("[dim]📋 Starting task planning...[/]\n")

    def on_planning_complete(self, subtask_count: int, mode: str):
        """
        Display planning completion.

        Args:
            subtask_count: Number of subtasks generated
            mode: Planning mode (light or deep)
        """
        mode_color = "yellow" if mode == "light" else "red"
        self.write(f"[{mode_color}]✓ Planning complete ({mode} mode): {subtask_count} subtasks[/]\n\n")

    # ====================================================================
    # Quality Evaluation Events
    # ====================================================================

    def on_response_for_judgment(self, response: str, strategy: str):
        """Display the assistant response that will be evaluated.
        
        Args:
            response: The assistant's response to be judged
            strategy: The strategy used to generate this response
        """
        # Truncate very long responses but show substantial content
        max_preview_length = 500
        response_preview = response[:max_preview_length]
        if len(response) > max_preview_length:
            response_preview += f"\n[dim]... ({len(response) - max_preview_length} more characters)[/]"
        
        table = Table(
            title=f"Response to Judge ({strategy} strategy)",
            show_header=False,
            border_style="yellow",
            expand=False,
        )
        table.add_column("Content", style="white", overflow="fold")
        table.add_row(response_preview)
        
        panel = Panel(table, border_style="yellow", expand=False)
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
        confidence = evaluation.confidence

        # Create summary table with key metrics
        summary_table = Table(
            title="Quality Evaluation Summary",
            show_header=False,
            border_style=status_color,
            expand=False,
        )
        summary_table.add_column("Field", style="cyan", width=20)
        summary_table.add_column("Value", style="white")

        summary_table.add_row("Status", f"[{status_color}]{status}[/]")
        summary_table.add_row("Confidence", f"{confidence:.2f}")

        panel = Panel(summary_table, border_style=status_color, expand=False)
        self.write(panel)
        self.write("\n")

        # Show full reasoning text in a separate panel
        if evaluation.reasoning:
            reasoning_panel = Panel(
                evaluation.reasoning,
                title="Judge's Reasoning (Full Text)",
                border_style="yellow",
                expand=False,
            )
            self.write(reasoning_panel)
            self.write("\n")

    # ====================================================================
    # Auto-Escalation Events
    # ====================================================================

    def on_auto_escalation(
        self,
        from_strategy: ExecutionStrategy,
        to_strategy: ExecutionStrategy,
        reason: str,
        confidence: float,
    ):
        """
        Display auto-escalation event (CRITICAL).

        Args:
            from_strategy: Strategy being escalated from
            to_strategy: Strategy being escalated to
            reason: Reason for escalation
            confidence: Quality confidence score that triggered escalation
        """
        text = Text()
        text.append("⚡ AUTO-ESCALATION ", style="bold red blink")
        text.append(f"{from_strategy.value}", style="yellow")
        text.append(" → ", style="white")
        text.append(f"{to_strategy.value}\n", style="red")

        panel = Panel(
            text,
            subtitle=f"Quality: {confidence:.2f} | {reason[:80]}",
            border_style="red",
            expand=False,
        )
        self.write(panel)
        self.write("\n")

    # ====================================================================
    # Final Response Events
    # ====================================================================

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
            strategy_used: Final strategy that produced the response
            attempts: Number of execution attempts
            final_quality: Final quality score
            escalated: Whether strategy was escalated
        """
        table = Table(
            title="✅ Final Response",
            show_header=False,
            border_style="green",
            expand=False,
        )
        table.add_column("Field", style="cyan", width=20)
        table.add_column("Value", style="white")

        table.add_row("Strategy Used", f"[green]{strategy_used.value}[/]")
        table.add_row("Attempts", str(attempts))
        table.add_row("Final Quality", f"{final_quality:.2f}")
        table.add_row("Escalated", "[yellow]Yes[/]" if escalated else "[green]No[/]")

        panel = Panel(table, border_style="green", expand=False)
        self.write(panel)
        self.write("\n")
        self.add_divider()

    # ====================================================================
    # Utility Methods
    # ====================================================================

    def add_divider(self):
        """Add a visual divider between reasoning sessions."""
        self.write("[dim]" + "═" * 60 + "[/]\n")

    def clear_trace(self):
        """Clear all trace messages."""
        self.clear()
        self.write("[bold magenta]Adaptive Reasoning Trace[/]\n")
        self.add_divider()

    def add_info_message(self, message: str):
        """
        Add an informational message to the trace panel.

        Args:
            message: Info message text
        """
        self.write(f"[dim]ℹ {message}[/]\n")

    def add_error_message(self, message: str):
        """
        Add an error message to the trace panel.

        Args:
            message: Error message text
        """
        self.write(f"[bold red]✗ Reasoning Error:[/] {message}\n")

