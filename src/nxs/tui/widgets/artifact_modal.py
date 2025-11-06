"""
ArtifactDescriptionModal - Modal dialog for displaying artifact descriptions.
"""

from textual.screen import ModalScreen
from textual.widgets import Button, Static, RichLog
from textual.containers import Container, Vertical, Horizontal
from textual.app import ComposeResult
from rich.text import Text
from rich.panel import Panel
from nxs.logger import get_logger

logger = get_logger("artifact_modal")


class ArtifactDescriptionModal(ModalScreen):
    """
    Modal dialog that displays artifact descriptions in a scrollable format.
    
    Features:
    - Scrollable content area for long descriptions
    - Shows artifact name and type in header
    - Close button and ESC key support
    - Proper formatting with Rich markup
    """

    def __init__(
        self,
        artifact_name: str,
        artifact_type: str,
        description: str | None,
        **kwargs
    ):
        """
        Initialize the modal dialog.

        Args:
            artifact_name: Name of the artifact
            artifact_type: Type of artifact ("T" for tool, "P" for prompt, "R" for resource)
            description: Description text (can be None)
        """
        super().__init__(**kwargs)
        self.artifact_name = artifact_name
        self.artifact_type = artifact_type
        self.description = description or "No description available."

    def compose(self) -> ComposeResult:
        """Compose the modal dialog layout."""
        # Determine artifact type label
        type_labels = {
            "T": "Tool",
            "P": "Prompt",
            "R": "Resource"
        }
        type_label = type_labels.get(self.artifact_type, "Artifact")
        
        # Create header with artifact name and type
        header_text = f"[bold cyan]{type_label}:[/] [bold]{self.artifact_name}[/]"
        
        with Container(id="artifact-modal-container"):
            # Header
            yield Static(header_text, id="artifact-modal-header")
            
            # Scrollable content area
            with Vertical(id="artifact-modal-content"):
                yield RichLog(
                    markup=True,
                    highlight=False,
                    auto_scroll=False,
                    wrap=True,
                    id="artifact-description-content"
                )
            
            # Footer with close button
            with Horizontal(id="artifact-modal-footer"):
                yield Button("Close", variant="primary", id="artifact-modal-close")

    def on_mount(self) -> None:
        """Called when the modal is mounted - populate the description."""
        description_widget = self.query_one("#artifact-description-content", RichLog)
        
        # Format description with Rich markup
        # Wrap long descriptions and handle None
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "artifact-modal-close":
            self.dismiss()

    def action_dismiss(self) -> None:
        """Dismiss the modal (ESC key support)."""
        self.dismiss()

