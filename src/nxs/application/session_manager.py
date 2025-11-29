"""Session manager for conversation persistence and lifecycle.

This module provides SessionManager for managing conversation sessions.

Multi-Session Support:
- Multiple concurrent sessions (like browser tabs)
- Session creation, switching, and deletion
- Session persistence via StateProvider (pluggable backends)
- Auto-save and auto-restore
- Active session management

TUI Integration (Future):
- Session tabs widget
- Keyboard shortcuts for switching
- Session creation/deletion UI
"""

import asyncio
import json
from pathlib import Path
from typing import Callable, Optional, Dict, cast, Any, TYPE_CHECKING

from nxs.application.agentic_loop import AgentLoop
from nxs.application.claude import Claude
from nxs.application.conversation import Conversation
from nxs.application.session import Session, SessionMetadata, AgentProtocol
from nxs.application.tool_registry import ToolRegistry
from nxs.application.summarization import SummarizationService, SummaryResult
from nxs.domain.protocols import StateProvider
from nxs.domain.events import EventBus
from nxs.logger import get_logger

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

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
        >>> from nxs.application.summarization import SummarizationService
        >>> summarizer = SummarizationService(llm=claude)
        >>> manager = SessionManager(
        ...     llm=claude,
        ...     tool_registry=tool_registry,
        ...     storage_dir=Path("~/.nxs/sessions"),
        ...     summarizer=summarizer,
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
        >>> summarizer = SummarizationService(llm=claude)
        >>> manager = SessionManager(llm=claude, tool_registry=registry, summarizer=summarizer)
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
        summarizer: SummarizationService,
        tool_registry: Optional[ToolRegistry] = None,
        storage_dir: Optional[Path] = None,
        system_message: Optional[str] = None,
        enable_caching: bool = True,
        callbacks: Optional[dict[str, Callable]] = None,
        agent_factory: Optional[Callable[[Conversation], AgentProtocol]] = None,
        state_provider: Optional[StateProvider] = None,
        event_bus: Optional[EventBus] = None,
        anthropic_client: Optional["AsyncAnthropic"] = None,
    ):
        """Initialize session manager.

        Args:
            llm: Claude API wrapper.
            summarizer: Shared summarization service instance used to summarize sessions.
            tool_registry: ToolRegistry for tools (optional if using agent_factory).
            storage_dir: Directory for session persistence (defaults to ~/.nxs/sessions).
                        Ignored if state_provider is provided.
            system_message: Default system message for new conversations.
            enable_caching: Enable prompt caching (default True).
            callbacks: Default callbacks for agent loop.
            agent_factory: Optional factory function to create custom agent loops.
                          Signature: (conversation: Conversation) -> AgentLoop
                          If provided, tool_registry is optional.
            state_provider: Optional StateProvider for pluggable persistence backends.
                           If None, creates FileStateProvider with storage_dir.
            event_bus: Optional EventBus for state change notifications (Phase 2).
            anthropic_client: Optional AsyncAnthropic client for StateExtractor (Phase 3).

        Example (with custom agent factory):
            >>> def create_command_agent(conversation):
            ...     # Create CommandControlAgent instead of plain AgentLoop
            ...     return CommandControlAgent(...)
            >>>
            >>> manager = SessionManager(
            ...     llm=claude,
            ...     agent_factory=create_command_agent
            ... )

        Example (with custom state provider):
            >>> from nxs.infrastructure.state import InMemoryStateProvider
            >>> provider = InMemoryStateProvider()
            >>> manager = SessionManager(
            ...     llm=claude,
            ...     tool_registry=registry,
            ...     state_provider=provider
            ... )
        """
        self.llm = llm
        self.tool_registry = tool_registry
        self.system_message = system_message
        self.enable_caching = enable_caching
        self.callbacks = callbacks or {}
        self._agent_factory = agent_factory
        self._summarizer = summarizer
        self._summary_locks: Dict[str, asyncio.Lock] = {}
        self.event_bus = event_bus
        self.anthropic_client = anthropic_client  # Phase 3

        # Validate: need either tool_registry or agent_factory
        if tool_registry is None and agent_factory is None:
            raise ValueError(
                "SessionManager requires either tool_registry or agent_factory"
            )

        # StateProvider integration
        # If no state provider given, create FileStateProvider for backward compatibility
        if state_provider is None:
            from nxs.infrastructure.state import FileStateProvider

            self.storage_dir = Path(storage_dir or Path.home() / ".nxs" / "sessions").expanduser()
            self.state_provider = FileStateProvider(base_dir=self.storage_dir)
            logger.debug(f"Created FileStateProvider: base_dir={self.storage_dir}")
        else:
            self.state_provider = state_provider
            # For backward compatibility, set storage_dir if provider is FileStateProvider
            if hasattr(state_provider, 'base_dir'):
                self.storage_dir = Path(state_provider.base_dir)
            else:
                # Use default path for non-file providers
                self.storage_dir = Path(storage_dir or Path.home() / ".nxs" / "sessions").expanduser()
            logger.debug(f"Using provided StateProvider: {type(state_provider).__name__}")

        # Multi-session support
        self._sessions: Dict[str, Session] = {}
        self._active_session_id: Optional[str] = None

        # Migrate old session.json to new default.json format if needed
        # Only needed for FileStateProvider
        if isinstance(self.state_provider, type) and hasattr(self.state_provider, 'base_dir'):
            self._migrate_legacy_session_file()

        logger.info(
            f"SessionManager initialized: provider={type(self.state_provider).__name__}"
        )

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

        Attempts to restore from storage. If not found, creates new session.
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

        # Try to restore from storage using StateProvider
        session_key = f"session:{self.DEFAULT_SESSION_ID}"

        if await self.state_provider.exists(session_key):
            logger.info(f"Restoring session from storage: key={session_key}")
            try:
                session = await self._load_session(session_key)
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

        # Create session (Phase 3: pass anthropic_client for StateExtractor)
        session = Session(
            metadata=metadata,
            conversation=conversation,
            agent_loop=cast(AgentProtocol, agent_loop),
            event_bus=self.event_bus,
            state_provider=self.state_provider,
            anthropic_client=self.anthropic_client,  # Phase 3
        )

        return session

    async def _load_session(self, session_key: str) -> Session:
        """Load session from storage using StateProvider.

        Args:
            session_key: State key for the session (e.g., "session:default").

        Returns:
            Restored Session instance.

        Raises:
            Exception: If loading fails.
        """
        # Load data from StateProvider
        data = await self.state_provider.load(session_key)
        if data is None:
            raise ValueError(f"Session not found: {session_key}")

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

        # Restore session with state management dependencies
        session = Session.from_dict(
            data,
            cast(AgentProtocol, agent_loop),
            event_bus=self.event_bus,
            state_provider=self.state_provider,
            anthropic_client=self.anthropic_client,
        )

        return session

    async def _save_session_async(self, session: Session) -> None:
        """Save a specific session using StateProvider (async).

        Args:
            session: The Session instance to save.

        Internal async helper for saving individual sessions.
        """
        session_key = f"session:{session.session_id}"

        try:
            data = session.to_dict()
            await self.state_provider.save(session_key, data)

            logger.info(f"Session saved: {session.session_id} (key={session_key})")
        except Exception as e:
            logger.error(
                f"Failed to save session {session.session_id}: {e}", exc_info=True
            )

    def _save_session(self, session: Session) -> None:
        """Save a specific session (synchronous wrapper).

        Args:
            session: The Session instance to save.

        Internal helper for saving individual sessions.
        Fire-and-forget async save for backward compatibility.
        """
        # Fire-and-forget async save
        asyncio.create_task(self._save_session_async(session))

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

    @property
    def summarizer(self) -> SummarizationService:
        """Return the shared summarization service instance."""
        return self._summarizer

    async def update_session_summary(
        self,
        session: Session,
        *,
        force: bool = False,
    ) -> SummaryResult | None:
        """Generate and persist an updated summary for the given session."""
        lock = self._summary_locks.setdefault(session.session_id, asyncio.Lock())

        async with lock:
            messages = session.conversation.get_messages()
            total_messages = len(messages)

            if total_messages == 0:
                return SummaryResult(
                    summary="",
                    total_messages=0,
                    messages_summarized=0,
                    skipped=True,
                )

            metadata = session.metadata
            start_index = 0 if force else max(metadata.summary_last_message_index or 0, 0)
            existing_summary = metadata.conversation_summary or ""
            
            # Clean up corrupted summaries (duplicate concatenations) on load
            if existing_summary and self._summarizer._detect_duplicate_summary(existing_summary):
                logger.warning(
                    f"Detected duplicate concatenated summary for session {session.session_id}. "
                    f"Cleaning up corrupted summary."
                )
                cleaned_summary = self._summarizer._clean_duplicate_summary(existing_summary)
                if cleaned_summary != existing_summary:
                    session.update_conversation_summary(cleaned_summary, metadata.summary_last_message_index)
                    existing_summary = cleaned_summary
                    logger.info(
                        f"Cleaned summary for session {session.session_id}: "
                        f"reduced from {len(metadata.conversation_summary)} to {len(cleaned_summary)} chars"
                    )

            result = await self._summarizer.summarize(
                messages,
                existing_summary=existing_summary,
                start_index=start_index,
                force=force,
            )

            # Only update summary if:
            # 1. We have a new summary AND it's different from the existing one, OR
            # 2. We've processed more messages than before
            if result.summary and not result.skipped:
                # Normalize both summaries for comparison (strip whitespace)
                normalized_existing = existing_summary.strip()
                normalized_new = result.summary.strip()
                
                # Only update if the summary actually changed or we processed new messages
                if (
                    normalized_new != normalized_existing
                    or result.messages_summarized > metadata.summary_last_message_index
                ):
                    # Additional safeguard: check if the new summary is a duplicate concatenation
                    # This can happen if the LLM returns a summary that includes the existing summary
                    if normalized_existing and normalized_new.startswith(normalized_existing):
                        # The new summary starts with the existing one - likely a concatenation issue
                        # Extract only the new part (everything after the existing summary)
                        # But be careful: the LLM might have reformatted, so we need to be smarter
                        # For now, if the new summary is significantly longer and starts with existing,
                        # it's likely a concatenation - reject it and log a warning
                        if len(normalized_new) > len(normalized_existing) * 1.5:
                            logger.warning(
                                f"Detected potential summary concatenation for session {session.session_id}. "
                                f"Existing length: {len(normalized_existing)}, New length: {len(normalized_new)}. "
                                f"Skipping update to prevent duplication."
                            )
                            # Don't update - keep existing summary
                            return result
                    
                    session.update_conversation_summary(result.summary, result.messages_summarized)
                    logger.debug(
                        f"Updated summary for session {session.session_id}: "
                        f"messages_summarized={result.messages_summarized}, "
                        f"summary_length={len(result.summary)}"
                    )
                else:
                    logger.debug(
                        f"Skipped summary update for session {session.session_id}: "
                        f"no new content (messages_summarized={result.messages_summarized}, "
                        f"last_index={metadata.summary_last_message_index})"
                    )
            elif (
                result.messages_summarized > metadata.summary_last_message_index
            ):
                metadata.summary_last_message_index = result.messages_summarized

            if result.error:
                logger.warning(
                    "Summary generation reported an issue (session=%s): %s",
                    session.session_id,
                    result.error,
                )

            return result

    async def update_active_session_summary(self, force: bool = False) -> SummaryResult | None:
        """Update summary for the currently active session."""
        session = self.get_active_session()
        if session is None:
            return None
        return await self.update_session_summary(session, force=force)

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

    def get_all_sessions_info(self) -> list[dict[str, Any]]:
        """Get information about all sessions.

        Returns:
            List of dictionaries with session info, sorted by last_active descending.

        Example:
            >>> sessions = manager.get_all_sessions_info()
            >>> for session in sessions:
            ...     print(f"{session['title']}: {session['message_count']} messages")
        """
        from datetime import datetime

        sessions_info = []
        for session_id, session in self._sessions.items():
            sessions_info.append({
                "session_id": session.session_id,
                "title": session.title,
                "message_count": session.get_message_count(),
                "created_at": session.created_at,
                "last_active": session.last_active_at,
            })

        # Sort by last_active descending (most recent first)
        sessions_info.sort(key=lambda x: x["last_active"], reverse=True)

        return sessions_info

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

    async def delete_session_async(self, session_id: str) -> None:
        """Delete a session (async).

        Removes session from memory and deletes from storage.
        If the deleted session was active, automatically switches to
        another session if available.

        Args:
            session_id: ID of the session to delete.

        Raises:
            ValueError: If session_id does not exist.

        Example:
            >>> await manager.delete_session_async("work")
        """
        if session_id not in self._sessions:
            raise ValueError(f"Session '{session_id}' does not exist")

        # Delete session from storage using StateProvider
        session_key = f"session:{session_id}"
        try:
            await self.state_provider.delete(session_key)
            logger.debug(f"Deleted session from storage: {session_key}")
        except Exception as e:
            logger.error(f"Failed to delete session from storage {session_key}: {e}")

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

    def delete_session(self, session_id: str) -> None:
        """Delete a session (synchronous wrapper).

        Removes session from memory and deletes from storage.
        Fire-and-forget for backward compatibility.

        Args:
            session_id: ID of the session to delete.

        Raises:
            ValueError: If session_id does not exist.

        Example:
            >>> manager.delete_session("work")
        """
        # Fire-and-forget async delete
        asyncio.create_task(self.delete_session_async(session_id))

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

        Phase 6: Also cleans up old trackers before saving.

        Example:
            >>> manager.save_all_sessions()
        """
        # Phase 6: Cleanup old trackers in all sessions before saving
        for session in self._sessions.values():
            if hasattr(session, "cleanup_old_trackers"):
                deleted_count = session.cleanup_old_trackers(max_age_days=30)
                if deleted_count > 0:
                    logger.info(
                        f"Cleaned up {deleted_count} old tracker(s) in session {session.session_id}"
                    )

        for session in self._sessions.values():
            self._save_session(session)

        logger.info(f"Saved {len(self._sessions)} session(s)")

    async def restore_all_sessions(self) -> None:
        """Restore all sessions from storage.

        Loads all session keys found via StateProvider.
        Sets default session as active if it exists, otherwise
        sets the first session found as active.

        Example:
            >>> await manager.restore_all_sessions()
        """
        try:
            # List all session keys using StateProvider
            session_keys = await self.state_provider.list_keys(prefix="session:")

            if not session_keys:
                logger.debug("No sessions found in storage")
                return

            # Load each session
            for session_key in session_keys:
                try:
                    session = await self._load_session(session_key)
                    self._sessions[session.session_id] = session
                    logger.info(f"Restored session: {session.session_id}")
                except Exception as e:
                    logger.error(
                        f"Failed to restore {session_key}: {e}", exc_info=True
                    )

            # Set default as active if it exists
            if self.DEFAULT_SESSION_ID in self._sessions:
                self._active_session_id = self.DEFAULT_SESSION_ID
                logger.debug(f"Set default session as active")
            elif self._sessions:
                self._active_session_id = next(iter(self._sessions.keys()))
                logger.debug(f"Set first session as active: {self._active_session_id}")

        except Exception as e:
            logger.error(f"Error during session restoration: {e}", exc_info=True)
