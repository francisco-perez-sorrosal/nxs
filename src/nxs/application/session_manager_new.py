"""Session manager for conversation persistence and lifecycle.

This module provides SessionManager for managing conversation sessions.

Phase 1 Implementation (Current):
- Single session only
- Session persistence to JSON
- Auto-save and auto-restore
- Battle-test architecture

Future Enhancement (Phase 2):
- Multiple concurrent sessions (like browser tabs)
- Session switching
- Session creation/deletion
- TUI integration with session tabs
"""

import json
from pathlib import Path
from typing import Callable, Optional

from nxs.application.chat import AgentLoop
from nxs.application.claude import Claude
from nxs.application.conversation import Conversation
from nxs.application.session import Session, SessionMetadata
from nxs.application.tool_registry import ToolRegistry
from nxs.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Manages conversation sessions with persistence.

    Current Implementation (Single Session):
    - Manages one active session
    - Auto-saves session on updates
    - Auto-restores session on startup
    - Provides session lifecycle methods

    Future Enhancement (Multi-Session):
    - Multiple sessions: Dict[session_id, Session]
    - Active session switching
    - Session creation/deletion
    - TUI integration

    Example (Current - Single Session):
        >>> manager = SessionManager(
        ...     llm=claude,
        ...     tool_registry=tool_registry,
        ...     storage_dir=Path("~/.nxs/sessions")
        ... )
        >>>
        >>> # Get or create default session
        >>> session = await manager.get_or_create_default_session()
        >>>
        >>> # Run query
        >>> result = await session.run_query("Hello!")
        >>>
        >>> # Auto-save on exit
        >>> manager.save_active_session()
    """

    DEFAULT_SESSION_ID = "default"
    SESSION_FILE_NAME = "session.json"

    def __init__(
        self,
        llm: Claude,
        tool_registry: ToolRegistry,
        storage_dir: Path,
        system_message: Optional[str] = None,
        enable_caching: bool = True,
        callbacks: Optional[dict[str, Callable]] = None,
    ):
        """Initialize session manager.

        Args:
            llm: Claude API wrapper.
            tool_registry: ToolRegistry for tools.
            storage_dir: Directory for session persistence.
            system_message: Default system message for new conversations.
            enable_caching: Enable prompt caching (default True).
            callbacks: Default callbacks for agent loop.
        """
        self.llm = llm
        self.tool_registry = tool_registry
        self.storage_dir = Path(storage_dir).expanduser()
        self.system_message = system_message
        self.enable_caching = enable_caching
        self.callbacks = callbacks or {}

        # Current implementation: Single active session
        self._active_session: Optional[Session] = None

        # Future: Multiple sessions
        # self._sessions: Dict[str, Session] = {}
        # self._active_session_id: Optional[str] = None

        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"SessionManager initialized: storage_dir={self.storage_dir}")

    async def get_or_create_default_session(self) -> Session:
        """Get or create the default session.

        Attempts to restore from disk. If not found, creates new session.

        Returns:
            The default Session instance.

        Example:
            >>> session = await manager.get_or_create_default_session()
            >>> print(session.session_id)  # "default"
        """
        if self._active_session is not None:
            return self._active_session

        # Try to restore from disk
        session_path = self.storage_dir / self.SESSION_FILE_NAME

        if session_path.exists():
            logger.info(f"Restoring session from {session_path}")
            try:
                self._active_session = await self._load_session_from_file(
                    session_path
                )
                logger.info(
                    f"Session restored: {self._active_session.session_id}, "
                    f"{self._active_session.get_message_count()} messages"
                )
                return self._active_session
            except Exception as e:
                logger.error(f"Failed to restore session: {e}", exc_info=True)
                logger.warning("Creating new session instead")

        # Create new session
        self._active_session = self._create_new_session(self.DEFAULT_SESSION_ID)
        logger.info(f"Created new session: {self.DEFAULT_SESSION_ID}")

        return self._active_session

    def _create_new_session(
        self, session_id: str, title: Optional[str] = None
    ) -> Session:
        """Create a new session.

        Args:
            session_id: Unique identifier for the session.
            title: Optional session title (defaults to "New Conversation").

        Returns:
            New Session instance.
        """
        # Create metadata
        metadata = SessionMetadata(
            session_id=session_id,
            title=title or "New Conversation",
            model=self.llm.model,
        )

        # Create conversation
        conversation = Conversation(
            system_message=self.system_message,
            enable_caching=self.enable_caching,
        )

        # Create agent loop
        agent_loop = AgentLoop(
            llm=self.llm,
            conversation=conversation,
            tool_registry=self.tool_registry,
            callbacks=self.callbacks,
        )

        # Create session
        session = Session(
            metadata=metadata,
            conversation=conversation,
            agent_loop=agent_loop,
        )

        logger.debug(f"Created session: {session_id}")

        return session

    async def _load_session_from_file(self, path: Path) -> Session:
        """Load session from JSON file.

        Args:
            path: Path to session JSON file.

        Returns:
            Restored Session instance.

        Raises:
            Exception: If loading fails.
        """
        with open(path, "r") as f:
            data = json.load(f)

        # Restore conversation from saved data
        conversation = Conversation.from_dict(data["conversation"])

        # Create fresh agent loop with restored conversation
        agent_loop = AgentLoop(
            llm=self.llm,
            conversation=conversation,
            tool_registry=self.tool_registry,
            callbacks=self.callbacks,
        )

        # Restore session
        session = Session.from_dict(data, agent_loop)

        return session

    def save_active_session(self) -> None:
        """Save the active session to disk.

        Persists session state to JSON file in storage directory.

        Example:
            >>> manager.save_active_session()
        """
        if self._active_session is None:
            logger.debug("No active session to save")
            return

        session_path = self.storage_dir / self.SESSION_FILE_NAME

        try:
            data = self._active_session.to_dict()

            with open(session_path, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(
                f"Session saved: {self._active_session.session_id} -> {session_path}"
            )

        except Exception as e:
            logger.error(f"Failed to save session: {e}", exc_info=True)

    def get_active_session(self) -> Optional[Session]:
        """Get the currently active session.

        Returns:
            Active Session or None if no session exists.

        Example:
            >>> session = manager.get_active_session()
            >>> if session:
            ...     print(f"Active: {session.session_id}")
        """
        return self._active_session

    def clear_active_session_history(self) -> None:
        """Clear the active session's conversation history.

        Preserves session metadata and structure.

        Example:
            >>> manager.clear_active_session_history()
        """
        if self._active_session is not None:
            self._active_session.clear_history()
            logger.info(
                f"Cleared history for session: {self._active_session.session_id}"
            )

    def get_session_info(self) -> Optional[dict[str, str]]:
        """Get information about the active session.

        Returns:
            Dictionary with session info, or None if no active session.

        Example:
            >>> info = manager.get_session_info()
            >>> if info:
            ...     print(f"Session: {info['title']}")
        """
        if self._active_session is None:
            return None

        return {
            "session_id": self._active_session.session_id,
            "title": self._active_session.title,
            "message_count": str(self._active_session.get_message_count()),
            "created_at": self._active_session.created_at.isoformat(),
            "last_active_at": self._active_session.last_active_at.isoformat(),
        }

    # Future methods for multi-session support:
    #
    # def create_session(self, session_id: str, title: str = "New") -> Session:
    #     """Create a new session and add to sessions dict."""
    #     ...
    #
    # def switch_session(self, session_id: str) -> Session:
    #     """Switch active session."""
    #     ...
    #
    # def delete_session(self, session_id: str) -> None:
    #     """Delete a session."""
    #     ...
    #
    # def list_sessions(self) -> list[SessionMetadata]:
    #     """List all sessions."""
    #     ...
    #
    # def save_all_sessions(self) -> None:
    #     """Save all sessions to disk."""
    #     ...
