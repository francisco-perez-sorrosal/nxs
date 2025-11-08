"""
Widget representing an individual MCP artifact entry.
"""

from __future__ import annotations

from textual.widgets import Static
from textual.message import Message
from rich.text import Text


from .static_no_margin import StaticNoMargin


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
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.styles.height = "auto"
        self.artifact_name = artifact_name
        self.artifact_type = artifact_type
        self.description = description

        color = self._TYPE_COLORS.get(artifact_type, "white")
        display_text = f"  [{color}]({artifact_type})[/] {artifact_name}"
        self.update(Text.from_markup(display_text))

    def on_click(self) -> None:
        self.post_message(
            self.Clicked(self.artifact_name, self.artifact_type, self.description)
        )

