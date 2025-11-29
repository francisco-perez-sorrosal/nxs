"""Session Management Panel - UI for session switching and management.

This widget provides a beautiful, functional interface for managing multiple sessions:
- View all sessions with metadata (title, message count, last active)
- Create new sessions
- Switch between sessions
- Delete sessions
- Rename sessions
- Visual indication of active session

Design: Minimalist, keyboard-friendly, with clear visual hierarchy.
"""

from datetime import datetime
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Button, Input, Label
from textual.widget import Widget
from textual.message import Message
from textual.reactive import reactive
from rich.text import Text
from rich.table import Table
from rich.panel import Panel

from nxs.logger import get_logger

logger = get_logger("session_panel")


class SessionSelected(Message):
    """Message emitted when a session is selected."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id


class SessionDeleted(Message):
    """Message emitted when a session is deleted."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id


class SessionCreated(Message):
    """Message emitted when a new session is created."""

    def __init__(self, session_id: str, title: str) -> None:
        super().__init__()
        self.session_id = session_id
        self.title = title


class SessionItem(Static):
    """A single session item in the session list.

    Displays session title, metadata, and provides click interaction.
    Visual distinction for active session.
    """

    DEFAULT_CSS = """
    SessionItem {
        height: auto;
        padding: 0 1;
        margin: 0 1;
        border: none;
        background: $panel;
    }

    SessionItem:hover {
        background: $boost;
    }

    SessionItem.active {
        background: $accent;
        border: tall $accent;
    }

    SessionItem .session-title {
        text-style: bold;
    }

    SessionItem .session-meta {
        color: $text-muted;
    }
    """

    is_active = reactive(False)

    def __init__(
        self,
        session_id: str,
        title: str,
        message_count: int,
        last_active: datetime,
        is_active: bool = False,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.session_id = session_id
        self.title = title
        self.message_count = message_count
        self.last_active = last_active
        self.is_active = is_active

    def render(self) -> Text:
        """Render session item with title and metadata."""
        # Active indicator
        indicator = "▶ " if self.is_active else "  "

        # Title line
        title_text = Text()
        title_text.append(indicator, style="bold cyan" if self.is_active else "dim")
        title_text.append(self.title, style="bold white" if self.is_active else "white")

        # Metadata line
        time_ago = self._format_time_ago(self.last_active)
        meta_text = Text()
        meta_text.append(f"   {self.message_count} msgs · {time_ago}", style="dim")

        # Combine
        combined = Text()
        combined.append_text(title_text)
        combined.append("\n")
        combined.append_text(meta_text)

        return combined

    def _format_time_ago(self, dt: datetime) -> str:
        """Format datetime as human-readable 'time ago'."""
        now = datetime.now()
        diff = now - dt

        seconds = diff.total_seconds()

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            mins = int(seconds / 60)
            return f"{mins}m ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f"{days}d ago"
        else:
            return dt.strftime("%b %d")

    async def on_click(self) -> None:
        """Handle click - emit SessionSelected message."""
        if not self.is_active:
            self.post_message(SessionSelected(self.session_id))


class SessionPanel(Widget):
    """Session management panel with list of sessions and actions.

    Features:
    - Beautiful list of all sessions
    - Create new session button
    - Click to switch sessions
    - Delete session (with confirmation via popup)
    - Visual active session indicator
    - Auto-refresh when sessions change

    Essential UI for multi-session workflow.
    """

    DEFAULT_CSS = """
    SessionPanel {
        width: 100%;
        height: 100%;
        background: $panel;
        border: solid $primary;
    }

    SessionPanel > Container {
        width: 100%;
        height: 100%;
    }

    SessionPanel #session-header {
        height: 3;
        content-align: center middle;
        background: $primary;
        color: $text;
        text-style: bold;
    }

    SessionPanel #session-list {
        height: 1fr;
        overflow-y: auto;
        padding: 1 0;
    }

    SessionPanel #session-actions {
        height: auto;
        padding: 1;
        background: $panel-darken-1;
        align: center middle;
    }

    SessionPanel Button {
        width: 100%;
        margin: 0 1;
    }
    """

    active_session_id = reactive("")
    sessions = reactive([])

    def compose(self) -> ComposeResult:
        """Compose the session panel layout."""
        with Container():
            yield Static("📋 Sessions", id="session-header")

            with Vertical(id="session-list"):
                # Session items will be added dynamically
                yield Static("Loading sessions...", id="loading")

            with Horizontal(id="session-actions"):
                yield Button("➕ New Session", id="btn-new-session", variant="primary")

    def update_sessions(
        self,
        sessions: list[tuple[str, str, int, datetime]],
        active_session_id: str
    ) -> None:
        """Update the session list display.

        Args:
            sessions: List of (session_id, title, message_count, last_active)
            active_session_id: ID of the currently active session
        """
        self.active_session_id = active_session_id
        self.sessions = sessions

        # Clear current list
        session_list = self.query_one("#session-list", Vertical)
        session_list.remove_children()

        # Add session items
        if not sessions:
            session_list.mount(Static("No sessions yet.\nCreate one to get started!", id="empty-state"))
        else:
            for session_id, title, msg_count, last_active in sessions:
                item = SessionItem(
                    session_id=session_id,
                    title=title,
                    message_count=msg_count,
                    last_active=last_active,
                    is_active=(session_id == active_session_id),
                )
                session_list.mount(item)

        logger.debug(f"Updated session list: {len(sessions)} sessions")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "btn-new-session":
            # Emit message for parent to handle
            self.post_message(SessionCreated("new", "New Session"))

    async def on_session_selected(self, message: SessionSelected) -> None:
        """Bubble up session selection to parent."""
        # Message automatically bubbles up
        pass
