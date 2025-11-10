"""Session manager for conversation persistence and lifecycle.

This module provides SessionManager for managing conversation sessions.

Multi-Session Support:
- Multiple concurrent sessions (like browser tabs)
- Session creation, switching, and deletion
- Session persistence to JSON (one file per session)
- Auto-save and auto-restore
- Active session management

TUI Integration (Future):
- Session tabs widget
- Keyboard shortcuts for switching
- Session creation/deletion UI
"""

import json
from pathlib import Path
from typing import Callable, Optional, Dict

from nxs.application.chat import AgentLoop
from nxs.application.claude import Claude
from nxs.application.conversation import Conversation
from nxs.application.session import Session, SessionMetadata
from nxs.application.tool_registry import ToolRegistry
from nxs.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Manages conversation sessions with persistence.

    Multi-Session Implementation:
    - Manages multiple concurrent sessions: Dict[session_id, Session]
    - Active session tracking and switching
    - Session creation and deletion
    - Auto-save and auto-restore for all sessions
    - Per-session JSON files: {session_id}.json

    Example (Single Session - Default Usage):
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

    Example (Multi-Session Usage):
        >>> manager = SessionManager(llm=claude, tool_registry=registry)
        >>>
        >>> # Create multiple sessions
        >>> session1 = manager.create_session("work", "Work Chat")
        >>> session2 = manager.create_session("personal", "Personal Chat")
        >>>
        >>> # Switch between sessions
        >>> manager.switch_session("work")
        >>> active = manager.get_active_session()
        >>>
        >>> # List all sessions
        >>> sessions = manager.list_sessions()
        >>>
        >>> # Delete a session
        >>> manager.delete_session("personal")
        >>>
        >>> # Save all sessions
        >>> manager.save_all_sessions()
    """

    DEFAULT_SESSION_ID = "default"

    def __init__(
        self,
        llm: Claude,
        tool_registry: Optional[ToolRegistry] = None,
        storage_dir: Optional[Path] = None,
        system_message: Optional[str] = None,
        enable_caching: bool = True,
        callbacks: Optional[dict[str, Callable]] = None,
        agent_factory: Optional[Callable[[Conversation], AgentLoop]] = None,
    ):
        """Initialize session manager.

        Args:
            llm: Claude API wrapper.
            tool_registry: ToolRegistry for tools (optional if using agent_factory).
            storage_dir: Directory for session persistence (defaults to ~/.nxs/sessions).
            system_message: Default system message for new conversations.
            enable_caching: Enable prompt caching (default True).
            callbacks: Default callbacks for agent loop.
            agent_factory: Optional factory function to create custom agent loops.
                          Signature: (conversation: Conversation) -> AgentLoop
                          If provided, tool_registry is optional.

        Example (with custom agent factory):
            >>> def create_command_agent(conversation):
            ...     # Create CommandControlAgent instead of plain AgentLoop
            ...     return CommandControlAgent(...)
            >>>
            >>> manager = SessionManager(
            ...     llm=claude,
            ...     agent_factory=create_command_agent
            ... )
        """
        self.llm = llm
        self.tool_registry = tool_registry
        self.storage_dir = Path(storage_dir or Path.home() / ".nxs" / "sessions").expanduser()
        self.system_message = system_message
        self.enable_caching = enable_caching
        self.callbacks = callbacks or {}
        self._agent_factory = agent_factory

        # Validate: need either tool_registry or agent_factory
        if tool_registry is None and agent_factory is None:
            raise ValueError(
                "SessionManager requires either tool_registry or agent_factory"
            )

        # Multi-session support
        self._sessions: Dict[str, Session] = {}
        self._active_session_id: Optional[str] = None

        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Migrate old session.json to new default.json format if needed
        self._migrate_legacy_session_file()

        logger.info(f"SessionManager initialized: storage_dir={self.storage_dir}")

    def _migrate_legacy_session_file(self) -> None:
        """Migrate legacy session.json to new default.json format.

        For backward compatibility with single-session implementation.
        """
        old_session_file = self.storage_dir / "session.json"
        new_session_file = self.storage_dir / f"{self.DEFAULT_SESSION_ID}.json"

        # Only migrate if old file exists and new file doesn't
        if old_session_file.exists() and not new_session_file.exists():
            try:
                # Read old file
                with open(old_session_file, "r") as f:
                    data = json.load(f)

                # Update session_id in metadata if present
                if "metadata" in data and "session_id" in data["metadata"]:
                    data["metadata"]["session_id"] = self.DEFAULT_SESSION_ID

                # Write to new location
                with open(new_session_file, "w") as f:
                    json.dump(data, f, indent=2)

                logger.info(
                    f"Migrated legacy session file: {old_session_file} -> {new_session_file}"
                )

                # Delete old file
                old_session_file.unlink()
                logger.debug(f"Deleted legacy session file: {old_session_file}")

            except Exception as e:
                logger.error(
                    f"Failed to migrate legacy session file: {e}", exc_info=True
                )

    async def get_or_create_default_session(self) -> Session:
        """Get or create the default session.

        Attempts to restore from disk. If not found, creates new session.
        Backward compatible with single-session usage.

        Returns:
            The default Session instance.

        Example:
            >>> session = await manager.get_or_create_default_session()
            >>> print(session.session_id)  # "default"
        """
        # Check if default session already exists in memory
        if self.DEFAULT_SESSION_ID in self._sessions:
            # Make it active if not already
            if self._active_session_id != self.DEFAULT_SESSION_ID:
                self._active_session_id = self.DEFAULT_SESSION_ID
            return self._sessions[self.DEFAULT_SESSION_ID]

        # Try to restore from disk
        session_path = self.storage_dir / f"{self.DEFAULT_SESSION_ID}.json"

        if session_path.exists():
            logger.info(f"Restoring session from {session_path}")
            try:
                session = await self._load_session_from_file(session_path)
                self._sessions[self.DEFAULT_SESSION_ID] = session
                self._active_session_id = self.DEFAULT_SESSION_ID
                logger.info(
                    f"Session restored: {session.session_id}, "
                    f"{session.get_message_count()} messages"
                )
                return session
            except Exception as e:
                logger.error(f"Failed to restore session: {e}", exc_info=True)
                logger.warning("Creating new session instead")

        # Create new session
        session = self.create_session(self.DEFAULT_SESSION_ID, "Default Session")
        logger.info(f"Created new session: {self.DEFAULT_SESSION_ID}")

        return session

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

        # Create agent loop (use factory if provided, otherwise default)
        if self._agent_factory:
            agent_loop = self._agent_factory(conversation)
            logger.debug(f"Created session with custom agent factory: {session_id}")
        else:
            agent_loop = AgentLoop(
                llm=self.llm,
                conversation=conversation,
                tool_registry=self.tool_registry,
                callbacks=self.callbacks,
            )
            logger.debug(f"Created session with default AgentLoop: {session_id}")

        # Create session
        session = Session(
            metadata=metadata,
            conversation=conversation,
            agent_loop=agent_loop,
        )

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

        # Create fresh agent loop with restored conversation (use factory if provided)
        if self._agent_factory:
            agent_loop = self._agent_factory(conversation)
            logger.debug("Restored session with custom agent factory")
        else:
            agent_loop = AgentLoop(
                llm=self.llm,
                conversation=conversation,
                tool_registry=self.tool_registry,
                callbacks=self.callbacks,
            )
            logger.debug("Restored session with default AgentLoop")

        # Restore session
        session = Session.from_dict(data, agent_loop)

        return session

    def _save_session(self, session: Session) -> None:
        """Save a specific session to disk.

        Args:
            session: The Session instance to save.

        Internal helper for saving individual sessions.
        """
        session_file = self.storage_dir / f"{session.session_id}.json"

        try:
            data = session.to_dict()
            with open(session_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Session saved: {session.session_id} -> {session_file}")
        except Exception as e:
            logger.error(
                f"Failed to save session {session.session_id}: {e}", exc_info=True
            )

    def save_active_session(self) -> None:
        """Save the active session to disk.

        Persists session state to JSON file in storage directory.

        Example:
            >>> manager.save_active_session()
        """
        session = self.get_active_session()
        if session is None:
            logger.debug("No active session to save")
            return

        self._save_session(session)

    def get_active_session(self) -> Optional[Session]:
        """Get the currently active session.

        Returns:
            Active Session or None if no session exists.

        Example:
            >>> session = manager.get_active_session()
            >>> if session:
            ...     print(f"Active: {session.session_id}")
        """
        if self._active_session_id is None:
            return None
        return self._sessions.get(self._active_session_id)

    def clear_active_session_history(self) -> None:
        """Clear the active session's conversation history.

        Preserves session metadata and structure.

        Example:
            >>> manager.clear_active_session_history()
        """
        session = self.get_active_session()
        if session is not None:
            session.clear_history()
            logger.info(f"Cleared history for session: {session.session_id}")

    def get_session_info(self) -> Optional[dict[str, str]]:
        """Get information about the active session.

        Returns:
            Dictionary with session info, or None if no active session.

        Example:
            >>> info = manager.get_session_info()
            >>> if info:
            ...     print(f"Session: {info['title']}")
        """
        session = self.get_active_session()
        if session is None:
            return None

        return {
            "session_id": session.session_id,
            "title": session.title,
            "message_count": str(session.get_message_count()),
            "created_at": session.created_at.isoformat(),
            "last_active_at": session.last_active_at.isoformat(),
        }

    def create_session(self, session_id: str, title: str = "New Conversation") -> Session:
        """Create a new session and add to sessions dict.

        Args:
            session_id: Unique identifier for the session.
            title: Session title (default: "New Conversation").

        Returns:
            The newly created Session instance.

        Raises:
            ValueError: If session_id already exists.

        Example:
            >>> session = manager.create_session("work", "Work Chat")
            >>> print(session.session_id)  # "work"
        """
        if session_id in self._sessions:
            raise ValueError(f"Session '{session_id}' already exists")

        session = self._create_new_session(session_id, title)
        self._sessions[session_id] = session

        # Auto-set as active if first session
        if self._active_session_id is None:
            self._active_session_id = session_id

        logger.info(f"Created session: {session_id}")
        return session

    def switch_session(self, session_id: str) -> Session:
        """Switch active session.

        Auto-saves the currently active session before switching to preserve
        any unsaved changes.

        Args:
            session_id: ID of the session to switch to.

        Returns:
            The newly active Session instance.

        Raises:
            ValueError: If session_id does not exist.

        Example:
            >>> session = manager.switch_session("work")
            >>> print(session.session_id)  # "work"
        """
        if session_id not in self._sessions:
            raise ValueError(f"Session '{session_id}' does not exist")

        # Auto-save current active session before switching
        if self._active_session_id is not None:
            current_session = self.get_active_session()
            if current_session:
                self._save_session(current_session)
                logger.debug(
                    f"Auto-saved session before switch: {self._active_session_id}"
                )

        self._active_session_id = session_id
        logger.info(f"Switched to session: {session_id}")
        return self._sessions[session_id]

    def delete_session(self, session_id: str) -> None:
        """Delete a session.

        Removes session from memory and deletes its file from disk.
        If the deleted session was active, automatically switches to
        another session if available.

        Args:
            session_id: ID of the session to delete.

        Raises:
            ValueError: If session_id does not exist.

        Example:
            >>> manager.delete_session("work")
        """
        if session_id not in self._sessions:
            raise ValueError(f"Session '{session_id}' does not exist")

        # Delete session file if exists
        session_file = self.storage_dir / f"{session_id}.json"
        if session_file.exists():
            try:
                session_file.unlink()
                logger.debug(f"Deleted session file: {session_file}")
            except Exception as e:
                logger.error(f"Failed to delete session file {session_file}: {e}")

        # Remove from memory
        del self._sessions[session_id]

        # Clear active session if deleted
        if self._active_session_id == session_id:
            self._active_session_id = None
            # Auto-switch to another session if available
            if self._sessions:
                self._active_session_id = next(iter(self._sessions.keys()))
                logger.info(f"Auto-switched to session: {self._active_session_id}")

        logger.info(f"Deleted session: {session_id}")

    def list_sessions(self) -> list[SessionMetadata]:
        """List all sessions.

        Returns:
            List of SessionMetadata for all sessions.

        Example:
            >>> sessions = manager.list_sessions()
            >>> for session_meta in sessions:
            ...     print(f"{session_meta.session_id}: {session_meta.title}")
        """
        return [session.metadata for session in self._sessions.values()]

    def save_all_sessions(self) -> None:
        """Save all sessions to disk.

        Persists all session states to their respective JSON files.

        Example:
            >>> manager.save_all_sessions()
        """
        for session in self._sessions.values():
            self._save_session(session)

        logger.info(f"Saved {len(self._sessions)} session(s)")

    async def restore_all_sessions(self) -> None:
        """Restore all sessions from storage directory.

        Loads all session JSON files found in storage directory.
        Sets default session as active if it exists, otherwise
        sets the first session found as active.

        Example:
            >>> await manager.restore_all_sessions()
        """
        if not self.storage_dir.exists():
            logger.debug("Storage directory does not exist, no sessions to restore")
            return

        for session_file in self.storage_dir.glob("*.json"):
            try:
                session = await self._load_session_from_file(session_file)
                self._sessions[session.session_id] = session
                logger.info(f"Restored session: {session.session_id}")
            except Exception as e:
                logger.error(
                    f"Failed to restore {session_file}: {e}", exc_info=True
                )

        # Set default as active if it exists
        if self.DEFAULT_SESSION_ID in self._sessions:
            self._active_session_id = self.DEFAULT_SESSION_ID
            logger.debug(f"Set default session as active")
        elif self._sessions:
            self._active_session_id = next(iter(self._sessions.keys()))
            logger.debug(f"Set first session as active: {self._active_session_id}")
