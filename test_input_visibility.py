#!/usr/bin/env python3
"""Test if Input text is actually visible when typing."""

from textual.app import App
from textual.widgets import Header, Footer
from tui.widgets.input_field import NexusInput


class TestVisibility(App):
    """Test app to verify input text visibility."""

    CSS_PATH = "tui/styles.tcss"

    TITLE = "Input Visibility Test"

    def compose(self):
        yield Header()
        yield NexusInput(id="input", resources=[], commands=[])
        yield Footer()

    def on_mount(self):
        """Focus input and log info."""
        input_widget = self.query_one("#input", NexusInput)
        input_widget.focus()

        with open("visibility_test.log", "w") as f:
            f.write("Input Widget Styles:\n")
            f.write(f"color: {input_widget.styles.color}\n")
            f.write(f"background: {input_widget.styles.background}\n")
            f.write("\nType in the input field and see if text is visible!\n")
            f.write("Press Ctrl+C to exit\n")


if __name__ == "__main__":
    app = TestVisibility()
    app.run()
