"""
ChatPanel - A scrollable chat display using RichLog with Rich markup support.
Clean, simple version that works WITH Rich, not against it.
"""

from textual.widgets import RichLog
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.panel import Panel
from rich.align import Align
from rich.padding import Padding
from rich.text import Text
from rich.console import Group
import re


class ChatPanel(RichLog):
    """
    A chat panel that displays conversation history with Rich formatting.

    Features:
    - Auto-scrolling to bottom on new messages
    - Rich markup for colored/styled text
    - Proper markdown rendering for assistant messages
    - Right-aligned assistant label with indented content
    """

    BORDER_TITLE = "Chat"

    def __init__(self, **kwargs):
        """Initialize the chat panel with Rich markup enabled."""
        super().__init__(
            markup=True,        # Enable Rich console markup ([bold], [cyan], etc.)
            highlight=True,     # Auto syntax highlighting for code-like text
            auto_scroll=True,   # Automatically scroll to bottom on new content
            wrap=True,          # Let Rich handle wrapping naturally
            **kwargs
        )
        # State for assistant message streaming
        self._assistant_buffer = ""
        self._assistant_active = False

    def add_user_message(self, text: str):
        """
        Add a user message to the chat.

        Args:
            text: The user's message text
        """
        self.write(f"[bold cyan]User:[/] {text}\n\n")

    def add_assistant_message_start(self):
        """
        Mark the start of an assistant message.

        Displays "Assistant:" right-aligned and prepares for response.
        """
        # BUGFIX: Right-align the "Assistant:" label using Text with justify
        # This is more reliable than Align in RichLog context
        label = Text("Assistant:", style="bold green", justify="right")
        self.write(label)
        self.write("\n\n")

        # Reset buffer for new message
        self._assistant_buffer = ""
        self._assistant_active = True

    def add_assistant_chunk(self, chunk: str):
        """
        Accumulate assistant response chunks.

        Args:
            chunk: A piece of the assistant's response
        """
        if self._assistant_active:
            self._assistant_buffer += chunk

    def finish_assistant_message(self):
        """
        Render the complete assistant message as formatted markdown.

        The message is displayed with left padding to create the indented layout.
        """
        if self._assistant_active and self._assistant_buffer:
            # BUGFIX: Render markdown with custom header handling to prevent centering
            md = self._create_left_aligned_markdown(self._assistant_buffer)

            # Add left padding to create the indented right-side layout
            # Using 40 chars for the left margin
            padded_md = Padding(md, (0, 0, 0, 40))

            # Write the formatted markdown
            self.write(padded_md)
            self.write("\n\n")

            # Reset state
            self._assistant_buffer = ""
            self._assistant_active = False

    def add_assistant_message(self, text: str):
        """
        Add a complete assistant message (non-streaming).

        Args:
            text: The assistant's complete message text
        """
        # Right-align the label using Text with justify
        label = Text("Assistant:", style="bold green", justify="right")
        self.write(label)
        self.write("\n\n")

        # Render as markdown with custom header handling to prevent centering
        md = self._create_left_aligned_markdown(text)
        padded_md = Padding(md, (0, 0, 0, 40))
        self.write(padded_md)
        self.write("\n\n")

    def add_code_block(self, code: str, language: str = "python", theme: str = "monokai"):
        """
        Add a syntax-highlighted code block.

        Args:
            code: The code to display
            language: Programming language for syntax highlighting
            theme: Color theme for syntax highlighting
        """
        syntax = Syntax(code, language, theme=theme, line_numbers=True)
        padded_syntax = Padding(syntax, (0, 0, 0, 40))
        self.write(padded_syntax)
        self.write("\n")

    def add_markdown(self, markdown_text: str):
        """
        Render markdown content with padding.

        Args:
            markdown_text: Markdown-formatted text
        """
        md = Markdown(markdown_text, justify="left")
        padded_md = Padding(md, (0, 0, 0, 40))
        self.write(padded_md)
        self.write("\n")

    def add_panel(self, content: str, title: str = "", style: str = "cyan"):
        """
        Add a styled panel (useful for system messages, notifications).

        Args:
            content: Panel content
            title: Optional panel title
            style: Border style/color
        """
        panel = Panel(content, title=title, border_style=style)
        self.write(panel)
        self.write("\n")

    def add_divider(self):
        """Add a visual divider between sections."""
        self.write("[dim]" + "─" * 80 + "[/]\n")

    def clear_chat(self):
        """Clear all chat history."""
        self.clear()

    def _create_left_aligned_markdown(self, markdown_text: str):
        """
        Create a renderable with left-aligned headers.

        This is a workaround for Rich's Markdown class which hardcodes
        center-alignment for headers (h1, h2, etc.) in the source.

        We parse the markdown and render headers as styled Text objects
        with left alignment, while still using Markdown for the rest.

        Args:
            markdown_text: The markdown text to render

        Returns:
            A Group containing left-aligned headers and markdown content
        """
        # BUGFIX: Ensure markdown headers start on new lines
        # Sometimes Claude streams text like "...text:# Header" without line breaks
        # This regex adds a newline before any # that follows non-whitespace
        markdown_text = re.sub(r'(\S)(#+\s+)', r'\1\n\n\2', markdown_text)

        # Split the markdown into lines and process headers separately
        lines = markdown_text.split('\n')
        renderables = []
        current_chunk = []

        for line in lines:
            # Check if line is a markdown header
            if re.match(r'^#+\s+', line):
                # First, flush any accumulated non-header lines as markdown
                if current_chunk:
                    md = Markdown('\n'.join(current_chunk), justify="left")
                    renderables.append(md)
                    current_chunk = []

                # Render header as styled Text with left alignment
                # Remove the # symbols and style appropriately
                level = len(line) - len(line.lstrip('#'))
                header_text = line.lstrip('#').strip()

                if level == 1:
                    styled_header = Text(header_text, style="bold magenta", justify="left")
                elif level == 2:
                    styled_header = Text(header_text, style="bold cyan", justify="left")
                else:
                    styled_header = Text(header_text, style="bold", justify="left")

                renderables.append(Text())  # Add spacing before header
                renderables.append(styled_header)
                renderables.append(Text())  # Add spacing after header
            else:
                # Accumulate non-header lines
                current_chunk.append(line)

        # Flush any remaining non-header content
        if current_chunk:
            md = Markdown('\n'.join(current_chunk), justify="left")
            renderables.append(md)

        # If we only have one renderable and it's Markdown, just return it
        if len(renderables) == 1 and isinstance(renderables[0], Markdown):
            return renderables[0]

        # Otherwise, return a Group of all renderables
        return Group(*renderables) if renderables else Markdown(markdown_text, justify="left")
