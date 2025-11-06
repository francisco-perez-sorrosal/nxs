"""
ArtifactDescriptionOverlay - Non-disruptive overlay for displaying artifact descriptions.
"""

import asyncio
from textual.widgets import Static, RichLog, Button
from textual.containers import Container, Vertical, Horizontal
from textual.app import ComposeResult
from textual.binding import Binding
from rich.text import Text
from rich.panel import Panel
from nxs.logger import get_logger

logger = get_logger("artifact_overlay")


class ArtifactDescriptionOverlay(Container):
    """
    Non-disruptive overlay widget that displays artifact descriptions.
    
    Features:
    - Positions near the artifact that was clicked
    - Scrollable content for long descriptions
    - Dismissible by clicking outside, ESC key, or close button
    - Doesn't block the entire screen
    """
    
    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
    ]

    def __init__(
        self,
        artifact_name: str,
        artifact_type: str,
        description: str | None,
        **kwargs
    ):
        """
        Initialize the overlay.

        Args:
            artifact_name: Name of the artifact
            artifact_type: Type of artifact ("T" for tool, "P" for prompt, "R" for resource)
            description: Description text (can be None)
        """
        super().__init__(**kwargs)
        self.artifact_name = artifact_name
        self.artifact_type = artifact_type
        self.description = description or "No description available."
        self._dismiss_timer: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        """Compose the overlay layout."""
        # Determine artifact type label
        type_labels = {
            "T": "Tool",
            "P": "Prompt",
            "R": "Resource"
        }
        type_label = type_labels.get(self.artifact_type, "Artifact")
        
        with Container(id="artifact-overlay-container"):
            # Header with artifact name and type
            with Horizontal(id="artifact-overlay-header"):
                header_text = f"[bold cyan]{type_label}:[/] [bold]{self.artifact_name}[/]"
                yield Static(header_text, id="artifact-overlay-title")
                yield Button("×", variant="default", id="artifact-overlay-close")
            
            # Scrollable content area
            with Vertical(id="artifact-overlay-content"):
                yield RichLog(
                    markup=True,
                    highlight=False,
                    auto_scroll=False,
                    wrap=True,
                    id="artifact-description-content"
                )
            
            # Footer with dismiss hint
            yield Static("[dim]Press ESC or click outside to close[/]", id="artifact-overlay-footer")

    def on_mount(self) -> None:
        """Called when the overlay is mounted - populate the description."""
        description_widget = self.query_one("#artifact-description-content", RichLog)
        
        # Format description with Rich markup
        if self.description:
            # Create a panel for the description
            description_panel = Panel(
                self.description,
                border_style="dim",
                padding=(1, 2),
                expand=False
            )
            description_widget.write(description_panel)
        else:
            description_widget.write("[dim]No description available.[/]")
        
        # Auto-dismiss after 10 seconds if user doesn't interact
        self._dismiss_timer = asyncio.create_task(self._auto_dismiss())

    async def _auto_dismiss(self) -> None:
        """Auto-dismiss the overlay after 10 seconds."""
        await asyncio.sleep(10.0)
        if self.is_attached:
            self.remove()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "artifact-overlay-close":
            if self._dismiss_timer:
                self._dismiss_timer.cancel()
            self.remove()

    def action_dismiss(self) -> None:
        """Dismiss the overlay (ESC key support)."""
        if self._dismiss_timer:
            self._dismiss_timer.cancel()
        self.remove()

    def on_click(self, event) -> None:
        """Handle clicks - dismiss if clicking outside content."""
        # Check if click is on the container itself (not children)
        if event.target == self or (hasattr(event.target, 'id') and event.target.id == "artifact-overlay-container"):
            if self._dismiss_timer:
                self._dismiss_timer.cancel()
            self.remove()

