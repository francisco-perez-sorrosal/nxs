"""Custom footer widget with reasoning checkbox."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Checkbox
from textual.reactive import reactive

from nxs.logger import get_logger

logger = get_logger("custom_footer")


class CustomFooter(Horizontal):
    """Custom footer with key bindings and reasoning checkbox.

    This footer combines the standard Textual footer (showing key bindings)
    with a checkbox for toggling reasoning mode on/off.
    """

    # Reactive property for reasoning enabled state
    reasoning_enabled = reactive(False)

    def compose(self) -> ComposeResult:
        """Compose the custom footer layout."""
        # Standard footer with key bindings (takes most of the space)
        yield Footer()

        # Reasoning checkbox on the right
        yield Checkbox(
            "[bold cyan]Reasoning[/]",
            value=False,
            id="reasoning-checkbox",
        )

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox state changes."""
        if event.checkbox.id == "reasoning-checkbox":
            self.reasoning_enabled = event.value
            logger.info(f"Reasoning mode {'enabled' if event.value else 'disabled'}")

    def get_reasoning_enabled(self) -> bool:
        """Get the current reasoning enabled state.

        Returns:
            True if reasoning checkbox is checked, False otherwise
        """
        try:
            checkbox = self.query_one("#reasoning-checkbox", Checkbox)
            return checkbox.value
        except Exception as e:
            logger.warning(f"Could not get reasoning checkbox state: {e}")
            return False

    def set_reasoning_enabled(self, enabled: bool) -> None:
        """Set the reasoning enabled state.

        Args:
            enabled: True to check the checkbox, False to uncheck it
        """
        try:
            checkbox = self.query_one("#reasoning-checkbox", Checkbox)
            checkbox.value = enabled
            self.reasoning_enabled = enabled
        except Exception as e:
            logger.warning(f"Could not set reasoning checkbox state: {e}")
