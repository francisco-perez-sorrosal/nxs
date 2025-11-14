"""
Widget representing an individual artifact entry (MCP or local).
"""

from __future__ import annotations

from textual.message import Message
from rich.text import Text

from nxs.logger import get_logger
from .static_no_margin import StaticNoMargin

logger = get_logger("artifact_item")


class ArtifactItem(StaticNoMargin):
    """Clickable artifact item widget."""

    class Clicked(Message):
        """Message emitted when an artifact entry is activated."""

        def __init__(
            self,
            artifact_name: str,
            artifact_type: str,
            description: str | None,
        ) -> None:
            super().__init__()
            self.artifact_name = artifact_name
            self.artifact_type = artifact_type
            self.description = description

    _TYPE_COLORS: dict[str, str] = {"T": "cyan", "P": "green", "R": "magenta"}

    def __init__(
        self,
        artifact_name: str,
        artifact_type: str,
        description: str | None,
        enabled: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.styles.height = "auto"
        self.artifact_name = artifact_name
        self.artifact_type = artifact_type
        self.description = description
        self._enabled = enabled

        # Render content directly in __init__ (same structure as before refactoring)
        color = self._TYPE_COLORS.get(artifact_type, "white")
        display_text = f"  [{color}]({artifact_type})[/] {artifact_name}"
        
        logger.debug(
            f"Initializing artifact: name={artifact_name!r}, type={artifact_type}, "
            f"display_text={display_text!r}"
        )
        
        self.update(Text.from_markup(display_text))

    def set_enabled(self, enabled: bool) -> None:
        """Update the enabled state and re-render.

        Args:
            enabled: New enabled state
        """
        if self._enabled != enabled:
            self._enabled = enabled
            # Re-render when enabled state changes
            color = self._TYPE_COLORS.get(self.artifact_type, "white")
            display_text = f"  [{color}]({self.artifact_type})[/] {self.artifact_name}"
            self.update(Text.from_markup(display_text))

    @property
    def enabled(self) -> bool:
        """Get the current enabled state."""
        return self._enabled

    def on_click(self) -> None:
        """Handle click events - show details for all artifacts."""
        # Always show details on click (removed toggle functionality for simplicity)
        self.post_message(self.Clicked(self.artifact_name, self.artifact_type, self.description))
