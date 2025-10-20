#!/usr/bin/env python3
"""Debug script to check Input widget styles in our app."""

from textual.app import App
from textual.widgets import Input
from tui.widgets.input_field import NexusInput


class DebugApp(App):
    """Minimal app to debug NexusInput styles."""

    # Use the actual project CSS
    CSS_PATH = "tui/styles.tcss"

    def compose(self):
        yield NexusInput(id="input")

    def on_mount(self) -> None:
        """Check styles after mounting."""
        input_widget = self.query_one("#input", NexusInput)

        # Write to file instead of stdout
        with open("input_styles_debug.txt", "w") as f:
            f.write("=" * 80 + "\n")
            f.write("NexusInput styles:\n")
            f.write(f"  color: {input_widget.styles.color}\n")
            f.write(f"  background: {input_widget.styles.background}\n")
            f.write(f"  border: {input_widget.styles.border}\n")
            f.write(f"  height: {input_widget.styles.height}\n")
            f.write("=" * 80 + "\n")

            # Also check computed styles
            f.write("Computed styles:\n")
            f.write(f"  display: {input_widget.styles.display}\n")
            f.write(f"  opacity: {input_widget.styles.opacity}\n")
            f.write(f"  visibility: {input_widget.styles.visibility}\n")
            f.write(f"  text_opacity: {input_widget.styles.text_opacity}\n")
            f.write("=" * 80 + "\n")

        self.exit()


if __name__ == "__main__":
    app = DebugApp()
    app.run()
