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

    def __init__(self, artifact_name: str, artifact_type: str, description: str | None, **kwargs):
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
        self._mouse_over = False  # Track if mouse is hovering over overlay

    def compose(self) -> ComposeResult:
        """Compose the overlay layout."""
        # Determine artifact type label
        type_labels = {"T": "Tool", "P": "Prompt", "R": "Resource"}
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
                    markup=True, highlight=False, auto_scroll=False, wrap=True, id="artifact-description-content"
                )

            # Footer with dismiss hint
            yield Static("[dim]Press ESC or click outside to close[/]", id="artifact-overlay-footer")

    def on_mount(self) -> None:
        """Called when the overlay is mounted - populate the description."""
        # Make overlay focusable so it can receive keyboard events
        self.can_focus = True

        # Populate initial content
        self._populate_content()

    def _populate_content(self) -> None:
        """Populate the overlay with current artifact description."""
        description_widget = self.query_one("#artifact-description-content", RichLog)

        # Clear existing content
        description_widget.clear()

        # Format description with Rich markup - no panel wrapper, just direct text
        if self.description:
            description_widget.write(self.description)
        else:
            description_widget.write("[dim]No description available.[/]")

    def update_content(self, artifact_name: str, artifact_type: str, description: str | None) -> None:
        """
        Update the overlay with new artifact information.

        Args:
            artifact_name: Name of the artifact
            artifact_type: Type of artifact ("T", "P", "R")
            description: Description text
        """
        self.artifact_name = artifact_name
        self.artifact_type = artifact_type
        self.description = description or "No description available."

        # Update title
        type_labels = {"T": "Tool", "P": "Prompt", "R": "Resource"}
        type_label = type_labels.get(artifact_type, "Artifact")
        title_widget = self.query_one("#artifact-overlay-title", Static)
        title_widget.update(f"[bold cyan]{type_label}:[/] [bold]{artifact_name}[/]")

        # Update content
        self._populate_content()

    def show_and_start_timer(self) -> None:
        """Show the overlay and start auto-dismiss timer."""
        # Cancel any existing timer
        self._cancel_timer()

        # Reset mouse hover state (fresh start for new overlay)
        self._mouse_over = False

        # Show the overlay
        self.display = True
        self.focus()

        # Start new auto-dismiss timer
        self._dismiss_timer = asyncio.create_task(self._auto_dismiss())

    async def _auto_dismiss(self) -> None:
        """Auto-dismiss the overlay after 5 seconds, unless mouse is hovering."""
        try:
            await asyncio.sleep(5.0)
            # Don't dismiss if mouse is still hovering
            if self._mouse_over:
                logger.debug(f"Auto-dismiss delayed for {self.artifact_name} - mouse still hovering")
                # Wait until mouse leaves, checking every 0.5 seconds
                while self._mouse_over and self.is_attached:
                    await asyncio.sleep(0.5)

            # Now dismiss if still attached
            if self.is_attached:
                self.display = False  # Hide instead of remove
        except asyncio.CancelledError:
            # Timer was cancelled, which is expected behavior
            logger.debug(f"Auto-dismiss timer cancelled for {self.artifact_name}")
        except Exception as e:
            logger.error(f"Error in auto-dismiss: {e}")

    def _cancel_timer(self) -> None:
        """Cancel the auto-dismiss timer if it's running."""
        if self._dismiss_timer and not self._dismiss_timer.done():
            self._dismiss_timer.cancel()

    def on_unmount(self) -> None:
        """Clean up when overlay is removed."""
        self._cancel_timer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "artifact-overlay-close":
            self._cancel_timer()
            self.display = False  # Hide instead of remove

    def action_dismiss(self) -> None:
        """Dismiss the overlay (ESC key support via binding)."""
        self._cancel_timer()
        self.display = False  # Hide instead of remove

    def on_key(self, event) -> None:
        """Handle key events - dismiss on ESC key."""
        if event.key == "escape":
            self._cancel_timer()
            self.display = False  # Hide instead of remove
            event.stop()
        else:
            # Allow other keys to propagate
            event.allow_default_behavior()

    def on_click(self, event) -> None:
        """Handle clicks - dismiss if clicking outside content."""
        # In Textual, the clicked widget is accessible via event.control
        # Only dismiss if clicking directly on the overlay container itself
        # (not on children like the content area, header, or buttons)
        clicked_widget = getattr(event, "control", None)

        # Check if the click is on the overlay container itself
        if clicked_widget is not None:
            if clicked_widget == self or (
                hasattr(clicked_widget, "id") and clicked_widget.id == "artifact-description-overlay"
            ):
                # Don't dismiss if clicking on interactive elements (header, close button, content)
                # Only dismiss if clicking on the container background
                if clicked_widget == self:
                    self._cancel_timer()
                    self.display = False  # Hide instead of remove

    def on_enter(self, event) -> None:
        """Handle mouse entering the overlay."""
        self._mouse_over = True
        logger.debug(f"Mouse entered overlay for {self.artifact_name}")

    def on_leave(self, event) -> None:
        """Handle mouse leaving the overlay."""
        self._mouse_over = False
        logger.debug(f"Mouse left overlay for {self.artifact_name}")
