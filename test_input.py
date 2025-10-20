#!/usr/bin/env python3
"""Minimal test to debug Input text visibility."""

from textual.app import App
from textual.widgets import Input, Header, Footer


class TestInputApp(App):
    """Test app to check Input text visibility."""

    CSS = """
    Input {
        border: solid green;
        height: 3;
        margin: 1;
    }
    """

    def compose(self):
        yield Header()
        yield Input(placeholder="Type here - can you see the text?", id="test-input")
        yield Footer()


if __name__ == "__main__":
    app = TestInputApp()
    app.run()
