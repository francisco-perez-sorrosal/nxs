"""
ChatPanel - A scrollable chat display using RichLog with Rich markup support.
Clean, simple version that works WITH Rich, not against it.
"""

from textual.widgets import RichLog
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.panel import Panel
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
        Create a renderable with left-aligned headers and syntax-highlighted code blocks.

        This method:
        1. Extracts code blocks (triple backticks) and renders them with Syntax highlighting
        2. Processes headers separately to ensure left alignment
        3. Renders remaining markdown normally
        4. Combines everything in a Group renderable

        Args:
            markdown_text: The markdown text to render

        Returns:
            A Group containing left-aligned headers, markdown content, and syntax-highlighted code blocks
        """
        # BUGFIX: Ensure markdown headers start on new lines
        # Sometimes Claude streams text like "...text:# Header" without line breaks
        # This regex adds a newline before any # that follows non-whitespace
        markdown_text = re.sub(r'(\S)(#+\s+)', r'\1\n\n\2', markdown_text)

        # Extract code blocks with their positions and language
        # Pattern matches: ```language\ncode\n``` or ```\ncode\n```
        # Handles cases with/without language specifier and optional whitespace
        code_block_pattern = r'```(\w+)?\s*\n(.*?)```'
        code_blocks = []
        for match in re.finditer(code_block_pattern, markdown_text, re.DOTALL):
            language = match.group(1) or "python"  # Default to python if no language specified
            code = match.group(2)
            # Remove leading/trailing newlines from code content
            code = code.strip('\n')
            start_pos = match.start()
            end_pos = match.end()
            code_blocks.append((start_pos, end_pos, code, language))

        # Sort code blocks by position
        code_blocks.sort(key=lambda x: x[0])

        # Split markdown text at code block boundaries
        renderables = []
        last_pos = 0

        for start_pos, end_pos, code, language in code_blocks:
            # Process markdown before this code block
            if start_pos > last_pos:
                markdown_section = markdown_text[last_pos:start_pos]
                if markdown_section.strip():
                    renderables.extend(self._process_markdown_section(markdown_section))

            # Render code block with Syntax highlighting
            # Note: Padding is applied at the Group level in finish_assistant_message()
            syntax = Syntax(code, language, theme="monokai", line_numbers=True)
            renderables.append(syntax)
            renderables.append(Text())  # Add spacing after code block

            last_pos = end_pos

        # Process remaining markdown after last code block
        if last_pos < len(markdown_text):
            markdown_section = markdown_text[last_pos:]
            if markdown_section.strip():
                renderables.extend(self._process_markdown_section(markdown_section))

        # If no code blocks were found, process entire text normally
        if not code_blocks:
            renderables = self._process_markdown_section(markdown_text)

        # If we only have one renderable and it's Markdown, just return it
        if len(renderables) == 1 and isinstance(renderables[0], Markdown):
            return renderables[0]

        # Otherwise, return a Group of all renderables
        return Group(*renderables) if renderables else Markdown(markdown_text, justify="left")

    def _process_markdown_section(self, markdown_text: str):
        """
        Process a markdown section, handling headers with left alignment.

        Args:
            markdown_text: The markdown text to process

        Returns:
            List of renderables (Text headers, Markdown content, etc.)
        """
        renderables = []
        lines = markdown_text.split('\n')
        current_chunk = []

        for line in lines:
            # Check if line is a markdown header
            if re.match(r'^#+\s+', line):
                # First, flush any accumulated non-header lines as markdown
                if current_chunk:
                    chunk_text = '\n'.join(current_chunk)
                    if chunk_text.strip():
                        md = Markdown(chunk_text, justify="left")
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
            chunk_text = '\n'.join(current_chunk)
            if chunk_text.strip():
                md = Markdown(chunk_text, justify="left")
                renderables.append(md)

        return renderables if renderables else [Markdown(markdown_text, justify="left")]
