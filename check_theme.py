#!/usr/bin/env python3
"""Check what the theme colors actually are."""

from textual.app import App


class ThemeCheck(App):
    def on_mount(self) -> None:
        """Print theme variables."""
        with open("theme_colors.txt", "w") as f:
            f.write("Theme CSS Variables:\n")
            f.write("=" * 80 + "\n")
            for key, value in sorted(self.get_css_variables().items()):
                f.write(f"{key}: {value}\n")
        self.exit()


if __name__ == "__main__":
    app = ThemeCheck()
    app.run()
