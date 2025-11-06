"""
ArtifactDescriptionOverlay - Non-disruptive overlay for displaying artifact descriptions.
"""

import asyncio
from textual.widgets import Static, RichLog, Button
from textual.containers import Container, Vertical, Horizontal
from textual.app import ComposeResult
from textual.binding import Binding
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
        
        # Format description with Rich markup - no panel wrapper, just direct text
        if self.description:
            description_widget.write(self.description)
        else:
            description_widget.write("[dim]No description available.[/]")
        
        # Make overlay focusable so it can receive keyboard events
        self.can_focus = True
        self.focus()
        
        # Auto-dismiss after 10 seconds if user doesn't interact
        self._dismiss_timer = asyncio.create_task(self._auto_dismiss())

    async def _auto_dismiss(self) -> None:
        """Auto-dismiss the overlay after 10 seconds."""
        await asyncio.sleep(5.0)
        if self.is_attached:
            self.remove()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "artifact-overlay-close":
            if self._dismiss_timer:
                self._dismiss_timer.cancel()
            self.remove()

    def action_dismiss(self) -> None:
        """Dismiss the overlay (ESC key support via binding)."""
        if self._dismiss_timer:
            self._dismiss_timer.cancel()
        self.remove()
    
    def on_key(self, event) -> None:
        """Handle key events - dismiss on ESC key."""
        if event.key == "escape":
            if self._dismiss_timer:
                self._dismiss_timer.cancel()
            self.remove()
            event.stop()
        else:
            # Allow other keys to propagate
            event.allow_default_behavior()

    def on_click(self, event) -> None:
        """Handle clicks - dismiss if clicking outside content."""
        # In Textual, the clicked widget is accessible via event.control
        # Only dismiss if clicking directly on the overlay container itself
        # (not on children like the content area, header, or buttons)
        clicked_widget = getattr(event, 'control', None)
        
        # Check if the click is on the overlay container itself
        if clicked_widget is not None:
            if clicked_widget == self or (hasattr(clicked_widget, 'id') and clicked_widget.id == "artifact-description-overlay"):
                # Don't dismiss if clicking on interactive elements (header, close button, content)
                # Only dismiss if clicking on the container background
                if clicked_widget == self:
                    if self._dismiss_timer:
                        self._dismiss_timer.cancel()
                    self.remove()

