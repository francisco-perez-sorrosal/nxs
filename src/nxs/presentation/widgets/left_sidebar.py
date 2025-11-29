"""Left Sidebar - UI container for session management and state visualization.

Combines SessionPanel and StateViewerPanel in a beautiful, collapsible sidebar.
Provides unified navigation for multi-session workflow and session knowledge visibility.
"""

from typing import Optional, TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widget import Widget
from textual.reactive import reactive

from nxs.presentation.widgets.session_panel import SessionPanel, SessionSelected, SessionCreated
from nxs.presentation.widgets.state_viewer_panel import StateViewerPanel
from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.application.session_state import SessionState
    from datetime import datetime

logger = get_logger("left_sidebar")


class LeftSidebar(Widget):
    """Left sidebar combining session management and state visualization.

    Layout:
    ┌─────────────────────┐
    │  📋 Sessions        │
    │  ▶ Default          │
    │    10 msgs · 2h ago │
    │                     │
    │    Work Chat        │
    │    5 msgs · 3d ago  │
    │                     │
    │  ➕ New Session     │
    ├─────────────────────┤
    │  🧠 Knowledge       │
    │  👤 User Profile    │
    │    Name: Alice      │
    │    Role: Developer  │
    │                     │
    │  📚 Facts (5)       │
    │  ● API limit: 1000  │
    │  ● Port: 8080       │
    │  ...                │
    └─────────────────────┘

    Essential UI for multi-session + knowledge visualization.
    """

    DEFAULT_CSS = """
    LeftSidebar {
        width: 30;
        height: 100%;
        background: $panel;
        border-right: solid $primary;
    }

    LeftSidebar.hidden {
        display: none;
    }

    LeftSidebar > Vertical {
        width: 100%;
        height: 100%;
    }

    LeftSidebar #session-container {
        height: 55%;
        border-bottom: solid $primary;
    }

    LeftSidebar #state-container {
        height: 45%;
    }
    """

    is_visible = reactive(True)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._session_panel: Optional[SessionPanel] = None
        self._state_panel: Optional[StateViewerPanel] = None

    def compose(self) -> ComposeResult:
        """Compose the sidebar layout."""
        with Vertical():
            with Container(id="session-container"):
                self._session_panel = SessionPanel(id="session-panel")
                yield self._session_panel

            with Container(id="state-container"):
                self._state_panel = StateViewerPanel(id="state-viewer")
                yield self._state_panel

    def toggle_visibility(self) -> None:
        """Toggle sidebar visibility."""
        self.is_visible = not self.is_visible
        if self.is_visible:
            self.remove_class("hidden")
            logger.debug("Sidebar shown")
        else:
            self.add_class("hidden")
            logger.debug("Sidebar hidden")

    def update_sessions(
        self,
        sessions: list[tuple[str, str, int, "datetime"]],
        active_session_id: str
    ) -> None:
        """Update the session list.

        Args:
            sessions: List of (session_id, title, message_count, last_active)
            active_session_id: ID of the currently active session
        """
        if self._session_panel:
            self._session_panel.update_sessions(sessions, active_session_id)

    def update_state(self, session_state: Optional["SessionState"]) -> None:
        """Update the state visualization.

        Args:
            session_state: SessionState to display
        """
        if self._state_panel:
            self._state_panel.update_state(session_state)

    async def on_session_selected(self, message: SessionSelected) -> None:
        """Bubble up session selection."""
        # Message automatically bubbles to parent
        pass

    async def on_session_created(self, message: SessionCreated) -> None:
        """Bubble up session creation."""
        # Message automatically bubbles to parent
        pass
