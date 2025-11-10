# Agentic Loop with Multi-Session Architecture - Comprehensive Plan

**Date**: 2025-11-09
**Status**: Architectural Design - Ready for Review

---

## Executive Summary

This document integrates the agentic loop improvements with multi-session support, creating a cohesive architecture that enables:
1. **Multiple concurrent conversation sessions** (like browser tabs)
2. **Session persistence and restoration** (save/load conversations)
3. **Real streaming with cache control** (90% cost reduction)
4. **Flexible tool management** (MCP + custom tools)
5. **Clean separation of concerns** (testable, maintainable)

**Key Innovation**: The `Conversation` class becomes the foundation for both improved agentic loops AND multi-session management.

---

## 1. Architectural Vision

### The Complete Picture

```
┌──────────────────────────────────────────────────────────────────┐
│                       SessionManager                              │
│  (Multi-Session Orchestration)                                   │
│                                                                   │
│  - create_session(id, metadata)                                  │
│  - switch_session(id)                                            │
│  - delete_session(id)                                            │
│  - list_sessions() → [{id, title, created, last_active}]        │
│  - save_all() / restore_all()                                    │
│                                                                   │
│  sessions: Dict[str, Session]                                    │
│  active_session_id: str                                          │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │ manages
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                          Session                                  │
│  (Single Conversation Session)                                   │
│                                                                   │
│  - session_id: str                                               │
│  - metadata: SessionMetadata (title, created, tags)              │
│  - conversation: Conversation                                    │
│  - agent_loop: AgentLoop                                         │
│  - is_active: bool                                               │
│                                                                   │
│  - run_query(text) → str                                         │
│  - get_history() → list[Message]                                 │
│  - clear_history()                                               │
│  - to_dict() / from_dict()                                       │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │ contains
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                       AgentLoop                                   │
│  (Agentic Execution Orchestrator)                                │
│                                                                   │
│  - Coordinates streaming                                         │
│  - Manages tool execution loop                                   │
│  - Handles callbacks for UI                                      │
│  - Error recovery                                                │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │ uses
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Conversation                                 │
│  (Message History & State Management)                            │
│                                                                   │
│  - messages: list[MessageParam]                                  │
│  - system_message: str | list[dict]                              │
│  - metadata: ConversationMetadata                                │
│                                                                   │
│  - add_user_message(text)                                        │
│  - add_assistant_message(message)                                │
│  - add_tool_results(results)                                     │
│  - get_messages_for_api() → with cache control                   │
│  - apply_history_strategy()                                      │
│  - to_dict() / from_dict()                                       │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │ uses
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                      ToolRegistry                                 │
│  (Uniform Tool Interface)                                        │
│                                                                   │
│  - providers: Dict[str, ToolProvider]                            │
│  - get_tool_definitions_for_api() → with cache control           │
│  - execute_tool(name, params) → result                           │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │ uses
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                         Claude                                    │
│  (Enhanced LLM Client)                                           │
│                                                                   │
│  - create_message() - sync                                       │
│  - stream_message() - async streaming                            │
│  - Full cache control support                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Abstractions

### 2.1. Session (New)

**Purpose**: Represents a single conversation session with its own state and metadata.

**Responsibilities**:
- Encapsulate a conversation instance
- Provide session-level metadata (title, created time, tags)
- Wrap AgentLoop for query execution
- Support serialization for persistence

**Implementation**:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class SessionMetadata:
    """Metadata for a conversation session."""
    session_id: str
    title: str = "New Conversation"
    created_at: datetime = field(default_factory=datetime.now)
    last_active_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)
    model: str = "claude-3-5-sonnet-20241022"
    system_message: Optional[str] = None

    def update_activity(self):
        """Update last active timestamp."""
        self.last_active_at = datetime.now()


class Session:
    """
    Represents a single conversation session.

    A session encapsulates:
    - Conversation state (message history)
    - AgentLoop for query processing
    - Metadata (title, timestamps, tags)
    - Persistence support
    """

    def __init__(
        self,
        session_id: str,
        conversation: Conversation,
        agent_loop: AgentLoop,
        metadata: Optional[SessionMetadata] = None,
    ):
        """
        Initialize a session.

        Args:
            session_id: Unique session identifier
            conversation: Conversation instance
            agent_loop: AgentLoop instance
            metadata: Optional session metadata
        """
        self.session_id = session_id
        self.conversation = conversation
        self.agent_loop = agent_loop
        self.metadata = metadata or SessionMetadata(session_id=session_id)
        self._is_active = False

    async def run_query(self, query: str, **kwargs) -> str:
        """
        Execute a query in this session.

        Args:
            query: User query
            **kwargs: Additional arguments for AgentLoop.run()

        Returns:
            Assistant response text
        """
        self.metadata.update_activity()
        return await self.agent_loop.run(query, **kwargs)

    def get_history(self) -> list[dict]:
        """Get conversation message history."""
        return self.conversation.messages.copy()

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation.clear_history()
        self.metadata.update_activity()

    def get_message_count(self) -> int:
        """Get total message count."""
        return len(self.conversation.messages)

    def get_token_estimate(self) -> int:
        """Estimate total tokens in conversation."""
        return self.conversation.get_token_estimate()

    @property
    def is_active(self) -> bool:
        """Check if this session is currently active."""
        return self._is_active

    def activate(self) -> None:
        """Mark session as active."""
        self._is_active = True
        self.metadata.update_activity()

    def deactivate(self) -> None:
        """Mark session as inactive."""
        self._is_active = False

    def to_dict(self) -> dict:
        """Serialize session to dictionary."""
        return {
            "session_id": self.session_id,
            "metadata": {
                "title": self.metadata.title,
                "created_at": self.metadata.created_at.isoformat(),
                "last_active_at": self.metadata.last_active_at.isoformat(),
                "tags": self.metadata.tags,
                "model": self.metadata.model,
                "system_message": self.metadata.system_message,
            },
            "conversation": self.conversation.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        llm: Claude,
        tool_registry: ToolRegistry,
        callbacks: Optional[dict] = None,
    ) -> "Session":
        """
        Restore session from dictionary.

        Args:
            data: Serialized session data
            llm: Claude instance
            tool_registry: ToolRegistry instance
            callbacks: Optional callbacks for AgentLoop

        Returns:
            Restored Session instance
        """
        session_id = data["session_id"]

        # Restore metadata
        metadata_dict = data["metadata"]
        metadata = SessionMetadata(
            session_id=session_id,
            title=metadata_dict["title"],
            created_at=datetime.fromisoformat(metadata_dict["created_at"]),
            last_active_at=datetime.fromisoformat(metadata_dict["last_active_at"]),
            tags=metadata_dict["tags"],
            model=metadata_dict["model"],
            system_message=metadata_dict.get("system_message"),
        )

        # Restore conversation
        conversation = Conversation.from_dict(data["conversation"])

        # Create agent loop
        agent_loop = AgentLoop(llm, conversation, tool_registry, callbacks)

        return cls(session_id, conversation, agent_loop, metadata)
```

**Benefits**:
- ✅ Clear encapsulation of session state
- ✅ Session-level metadata for UI/organization
- ✅ Full persistence support
- ✅ Activity tracking built-in

---

### 2.2. SessionManager (Enhanced from Placeholder)

**Purpose**: Manage multiple conversation sessions with lifecycle and persistence.

**Responsibilities**:
- Create/delete sessions
- Switch active session
- Persist/restore all sessions
- Session discovery and listing
- Session metadata management

**Implementation**:

```python
from typing import Dict, Optional, Callable
from pathlib import Path
import json
import uuid

class SessionManager:
    """
    Manages multiple conversation sessions.

    Provides:
    - Session lifecycle (create, switch, delete)
    - Session persistence (save, load)
    - Active session tracking
    - Session listing and discovery
    """

    def __init__(
        self,
        llm: Claude,
        tool_registry: ToolRegistry,
        session_factory: Optional[Callable] = None,
        persistence_path: Optional[Path] = None,
    ):
        """
        Initialize session manager.

        Args:
            llm: Claude instance (shared across sessions)
            tool_registry: ToolRegistry instance (shared across sessions)
            session_factory: Optional custom session factory
            persistence_path: Optional path for session persistence
        """
        self.llm = llm
        self.tool_registry = tool_registry
        self.sessions: Dict[str, Session] = {}
        self.active_session_id: Optional[str] = None
        self._session_factory = session_factory or self._default_session_factory
        self._persistence_path = persistence_path or Path.home() / ".nxs" / "sessions"

        # Create persistence directory
        if self._persistence_path:
            self._persistence_path.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        session_id: Optional[str] = None,
        title: str = "New Conversation",
        system_message: Optional[str] = None,
        callbacks: Optional[dict] = None,
        **metadata_kwargs,
    ) -> Session:
        """
        Create a new conversation session.

        Args:
            session_id: Optional session ID (auto-generated if None)
            title: Session title
            system_message: Optional system message for this session
            callbacks: Optional callbacks for AgentLoop
            **metadata_kwargs: Additional metadata fields

        Returns:
            Created Session instance

        Raises:
            ValueError: If session_id already exists
        """
        # Generate ID if not provided
        if session_id is None:
            session_id = str(uuid.uuid4())

        # Check for duplicates
        if session_id in self.sessions:
            raise ValueError(f"Session '{session_id}' already exists")

        # Create session
        session = self._session_factory(
            session_id=session_id,
            title=title,
            system_message=system_message,
            callbacks=callbacks,
            **metadata_kwargs,
        )

        # Register session
        self.sessions[session_id] = session

        # Set as active if first session
        if self.active_session_id is None:
            self.active_session_id = session_id
            session.activate()

        logger.info(f"Created session: {session_id} ('{title}')")
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        return self.sessions.get(session_id)

    def get_active_session(self) -> Optional[Session]:
        """Get currently active session."""
        if self.active_session_id:
            return self.sessions.get(self.active_session_id)
        return None

    def switch_session(self, session_id: str) -> Session:
        """
        Switch to a different session.

        Args:
            session_id: ID of session to activate

        Returns:
            Activated Session instance

        Raises:
            ValueError: If session_id does not exist
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session '{session_id}' does not exist")

        # Deactivate current session
        if self.active_session_id and self.active_session_id in self.sessions:
            self.sessions[self.active_session_id].deactivate()

        # Activate new session
        self.active_session_id = session_id
        session = self.sessions[session_id]
        session.activate()

        logger.info(f"Switched to session: {session_id}")
        return session

    def delete_session(self, session_id: str) -> None:
        """
        Delete a session.

        Args:
            session_id: ID of session to delete
        """
        if session_id in self.sessions:
            # Delete from registry
            del self.sessions[session_id]

            # Delete persisted file
            if self._persistence_path:
                session_file = self._persistence_path / f"{session_id}.json"
                if session_file.exists():
                    session_file.unlink()

            # Clear active session if it was deleted
            if self.active_session_id == session_id:
                self.active_session_id = None

                # Auto-switch to another session if available
                if self.sessions:
                    next_session_id = next(iter(self.sessions.keys()))
                    self.switch_session(next_session_id)

            logger.info(f"Deleted session: {session_id}")

    def list_sessions(self) -> list[dict]:
        """
        List all sessions with metadata.

        Returns:
            List of session info dicts
        """
        return [
            {
                "session_id": sid,
                "title": session.metadata.title,
                "created_at": session.metadata.created_at.isoformat(),
                "last_active_at": session.metadata.last_active_at.isoformat(),
                "message_count": session.get_message_count(),
                "is_active": session.is_active,
                "tags": session.metadata.tags,
            }
            for sid, session in self.sessions.items()
        ]

    def rename_session(self, session_id: str, new_title: str) -> None:
        """Rename a session."""
        if session_id in self.sessions:
            self.sessions[session_id].metadata.title = new_title
            logger.info(f"Renamed session {session_id} to '{new_title}'")

    def tag_session(self, session_id: str, tags: list[str]) -> None:
        """Add tags to a session."""
        if session_id in self.sessions:
            self.sessions[session_id].metadata.tags = tags

    # === Persistence ===

    def save_session(self, session_id: str) -> None:
        """Save a single session to disk."""
        if session_id not in self.sessions:
            return

        if not self._persistence_path:
            logger.warning("Persistence path not configured")
            return

        session = self.sessions[session_id]
        session_file = self._persistence_path / f"{session_id}.json"

        with open(session_file, "w") as f:
            json.dump(session.to_dict(), f, indent=2)

        logger.debug(f"Saved session: {session_id}")

    def save_all_sessions(self) -> None:
        """Save all sessions to disk."""
        for session_id in self.sessions:
            self.save_session(session_id)
        logger.info(f"Saved {len(self.sessions)} sessions")

    def load_session(self, session_id: str, callbacks: Optional[dict] = None) -> Session:
        """
        Load a session from disk.

        Args:
            session_id: ID of session to load
            callbacks: Optional callbacks for AgentLoop

        Returns:
            Loaded Session instance
        """
        if not self._persistence_path:
            raise ValueError("Persistence path not configured")

        session_file = self._persistence_path / f"{session_id}.json"
        if not session_file.exists():
            raise FileNotFoundError(f"Session file not found: {session_file}")

        with open(session_file, "r") as f:
            data = json.load(f)

        session = Session.from_dict(
            data, self.llm, self.tool_registry, callbacks
        )

        self.sessions[session_id] = session
        logger.info(f"Loaded session: {session_id}")

        return session

    def restore_all_sessions(self, callbacks: Optional[dict] = None) -> int:
        """
        Restore all sessions from disk.

        Returns:
            Number of sessions restored
        """
        if not self._persistence_path or not self._persistence_path.exists():
            return 0

        count = 0
        for session_file in self._persistence_path.glob("*.json"):
            try:
                session_id = session_file.stem
                self.load_session(session_id, callbacks)
                count += 1
            except Exception as e:
                logger.error(f"Failed to load session {session_id}: {e}")

        logger.info(f"Restored {count} sessions")
        return count

    def _default_session_factory(
        self,
        session_id: str,
        title: str,
        system_message: Optional[str],
        callbacks: Optional[dict],
        **kwargs,
    ) -> Session:
        """Default factory for creating sessions."""
        # Create conversation
        conversation = Conversation(
            system_message=system_message,
            enable_caching=True,
        )

        # Create agent loop
        agent_loop = AgentLoop(
            llm=self.llm,
            conversation=conversation,
            tool_registry=self.tool_registry,
            callbacks=callbacks,
        )

        # Create metadata
        metadata = SessionMetadata(
            session_id=session_id,
            title=title,
            system_message=system_message,
            **kwargs,
        )

        # Create session
        return Session(session_id, conversation, agent_loop, metadata)
```

**Benefits**:
- ✅ Full session lifecycle management
- ✅ Persistence to disk (JSON)
- ✅ Active session tracking
- ✅ Session discovery and listing
- ✅ Flexible session factory (customizable)
- ✅ Auto-save/restore support

---

### 2.3. Conversation (Enhanced)

**Already designed in previous analysis**, but now with additional considerations for sessions:

**Key Additions for Session Support**:

```python
class Conversation:
    """Enhanced with session-aware features."""

    def __init__(
        self,
        system_message: Optional[str | list[dict]] = None,
        max_history_messages: Optional[int] = None,
        enable_caching: bool = True,
        session_id: Optional[str] = None,  # NEW: Optional session association
    ):
        self._messages: list[MessageParam] = []
        self._system_message = system_message
        self._max_history_messages = max_history_messages
        self._enable_caching = enable_caching
        self._session_id = session_id  # NEW

    # ... (all previous methods)

    def to_dict(self) -> dict:
        """Serialize conversation with session ID."""
        return {
            "messages": self._messages,
            "system_message": self._system_message,
            "max_history_messages": self._max_history_messages,
            "enable_caching": self._enable_caching,
            "session_id": self._session_id,  # NEW
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        """Restore conversation from dict."""
        conv = cls(
            system_message=data.get("system_message"),
            max_history_messages=data.get("max_history_messages"),
            enable_caching=data.get("enable_caching", True),
            session_id=data.get("session_id"),  # NEW
        )
        conv._messages = data.get("messages", [])
        return conv
```

---

## 3. Integration with Existing Architecture

### 3.1. NexusApp Integration

The TUI layer (`NexusApp`) will integrate with `SessionManager`:

```python
class NexusApp(App):
    """Enhanced with multi-session support."""

    def __init__(
        self,
        llm: Claude,
        tool_registry: ToolRegistry,
        artifact_manager: ArtifactManager,
        event_bus: EventBus,
    ):
        super().__init__()

        # Create session manager
        self.session_manager = SessionManager(
            llm=llm,
            tool_registry=tool_registry,
            persistence_path=Path.home() / ".nxs" / "sessions",
        )

        # Restore previous sessions
        self.session_manager.restore_all_sessions(callbacks=self._get_callbacks())

        # Create default session if none exist
        if not self.session_manager.sessions:
            self.session_manager.create_session(
                title="General Chat",
                callbacks=self._get_callbacks(),
            )

        # ... rest of initialization

    async def on_input_submitted(self, event) -> None:
        """Handle input with active session."""
        query = event.value.strip()
        if not query:
            return

        # Get active session
        session = self.session_manager.get_active_session()
        if not session:
            logger.error("No active session")
            return

        # Process query through session
        try:
            await session.run_query(query, stream=True)
        except Exception as e:
            logger.error(f"Error processing query: {e}")

    def _get_callbacks(self) -> dict:
        """Get callbacks for agent loop."""
        return {
            "on_start": self._on_query_start,
            "on_stream_chunk": self._on_stream_chunk,
            "on_stream_complete": self._on_stream_complete,
            "on_tool_call": self._on_tool_call,
            "on_tool_result": self._on_tool_result,
        }

    # === Session Management Actions ===

    async def action_new_session(self) -> None:
        """Create a new session (Ctrl+T)."""
        session = self.session_manager.create_session(
            title=f"Chat {len(self.session_manager.sessions) + 1}",
            callbacks=self._get_callbacks(),
        )
        self.session_manager.switch_session(session.session_id)
        # Update UI to show new session

    async def action_switch_session(self) -> None:
        """Show session switcher (Ctrl+Tab)."""
        # Display session picker overlay
        # User selects session
        # Call self.session_manager.switch_session(selected_id)

    async def action_close_session(self) -> None:
        """Close current session (Ctrl+W)."""
        active = self.session_manager.get_active_session()
        if active:
            # Confirm with user
            self.session_manager.delete_session(active.session_id)

    async def on_unmount(self) -> None:
        """Save sessions on exit."""
        self.session_manager.save_all_sessions()
```

**Key Bindings for Multi-Session**:
- `Ctrl+T` - New session
- `Ctrl+Tab` - Switch session (show picker)
- `Ctrl+W` - Close session
- `Ctrl+1` through `Ctrl+9` - Quick switch to session 1-9
- `Ctrl+Shift+S` - Save all sessions

---

### 3.2. UI Components for Sessions

**Session Tabs Widget** (New):

```python
class SessionTabs(Widget):
    """
    Display session tabs (like browser tabs).

    Shows:
    - Session title
    - Active indicator
    - Message count
    - Close button
    """

    def compose(self) -> ComposeResult:
        """Render session tabs."""
        sessions = self.app.session_manager.list_sessions()

        for session in sessions:
            yield SessionTab(
                session_id=session["session_id"],
                title=session["title"],
                is_active=session["is_active"],
                message_count=session["message_count"],
            )

    def on_session_tab_clicked(self, event: SessionTabClicked) -> None:
        """Handle session tab click."""
        self.app.session_manager.switch_session(event.session_id)
        self.refresh()
```

**Session Picker Overlay** (New):

```python
class SessionPicker(ModalScreen):
    """
    Session picker overlay (like Ctrl+Tab in VS Code).

    Shows list of sessions with:
    - Title
    - Last active time
    - Message count
    - Preview of last message
    """

    def compose(self) -> ComposeResult:
        sessions = self.app.session_manager.list_sessions()

        # Sort by last active
        sessions.sort(key=lambda s: s["last_active_at"], reverse=True)

        yield Container(
            Static("Switch Session", classes="header"),
            *[
                SessionListItem(s) for s in sessions
            ],
            classes="session-picker",
        )

    def on_list_item_selected(self, event) -> None:
        """Switch to selected session."""
        self.app.session_manager.switch_session(event.session_id)
        self.dismiss()
```

---

## 4. Complete Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                         NexusApp (TUI)                              │
│  - session_manager: SessionManager                                 │
│  - Keyboard shortcuts for session management                       │
│  - SessionTabs widget (shows all sessions)                         │
│  - SessionPicker overlay (Ctrl+Tab)                                │
└────────────────┬───────────────────────────────────────────────────┘
                 │
                 │ uses
                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                      SessionManager                                 │
│  sessions: Dict[str, Session]                                      │
│  active_session_id: str                                            │
│                                                                     │
│  - create_session(id, title, system_msg)                           │
│  - switch_session(id)                                              │
│  - delete_session(id)                                              │
│  - save_all_sessions() / restore_all_sessions()                    │
└────────────────┬───────────────────────────────────────────────────┘
                 │
                 │ manages
                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                           Session                                   │
│  session_id: str                                                   │
│  metadata: SessionMetadata                                         │
│  conversation: Conversation                                        │
│  agent_loop: AgentLoop                                             │
│                                                                     │
│  - run_query(text) → str                                           │
│  - get_history() → messages                                        │
│  - to_dict() / from_dict()                                         │
└────────────────┬───────────────────────────────────────────────────┘
                 │
                 │ contains
                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                         AgentLoop                                   │
│  conversation: Conversation                                        │
│  tool_registry: ToolRegistry                                       │
│  llm: Claude                                                       │
│  callbacks: dict                                                   │
│                                                                     │
│  - run(query, stream=True) → str                                   │
│  - _stream_response() → Message                                    │
│  - _execute_tools() → results                                      │
└────────────────┬───────────────────────────────────────────────────┘
                 │
                 │ delegates to
                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                      Conversation                                   │
│  messages: list[MessageParam]                                      │
│  system_message: str | list[dict]                                  │
│  session_id: Optional[str]                                         │
│                                                                     │
│  - add_user_message(text)                                          │
│  - add_assistant_message(message)                                  │
│  - add_tool_results(results)                                       │
│  - get_messages_for_api() → with cache control                     │
│  - to_dict() / from_dict()                                         │
└────────────────┬───────────────────────────────────────────────────┘
                 │
                 │ uses (shared across sessions)
                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                      ToolRegistry                                   │
│  providers: Dict[str, ToolProvider]                                │
│  - MCP Provider                                                    │
│  - Text Editor Provider                                            │
│  - Web Search Provider                                             │
│  - Custom Tool Provider                                            │
│                                                                     │
│  - get_tool_definitions_for_api() → with cache control             │
│  - execute_tool(name, params) → result                             │
└────────────────┬───────────────────────────────────────────────────┘
                 │
                 │ uses (shared across sessions)
                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                          Claude                                     │
│  model: str                                                        │
│  client: Anthropic                                                 │
│                                                                     │
│  - create_message(...) → Message                                   │
│  - stream_message(...) → AsyncIterator[Message]                    │
└────────────────────────────────────────────────────────────────────┘
```

**Key Insights**:
1. **SessionManager** is the entry point for all session operations
2. **Session** encapsulates a single conversation (1:1 with Conversation)
3. **AgentLoop** and **Conversation** are decoupled from sessions (can work standalone)
4. **ToolRegistry** and **Claude** are shared across all sessions (singleton-like)
5. **NexusApp** integrates SessionManager and provides UI for session management

---

## 5. Implementation Plan

### Phase 1: Foundation (2-3 days)

**Goal**: Create core abstractions without sessions

**Tasks**:
1. ✅ Create `Conversation` class
   - Message management
   - Cache control
   - Serialization
2. ✅ Create `ToolRegistry` + `ToolProvider` protocol
   - MCP provider
   - Tool routing
3. ✅ Enhance `Claude` wrapper
   - Streaming support
   - Cache control
4. ✅ Add unit tests

**Deliverables**:
- `application/conversation.py`
- `application/tool_registry.py`
- Enhanced `application/claude.py`
- Tests

### Phase 2: AgentLoop Refactor (2-3 days)

**Goal**: Refactor AgentLoop to use new abstractions

**Tasks**:
1. ✅ Update `AgentLoop` to accept `Conversation` and `ToolRegistry`
2. ✅ Implement real streaming
3. ✅ Remove fake streaming logic
4. ✅ Maintain backward compatibility
5. ✅ Update tests

**Deliverables**:
- Refactored `application/agentic_loop.py`
- Updated tests
- Deprecation warnings

### Phase 3: Session Management (3-4 days)

**Goal**: Add multi-session support

**Tasks**:
1. ✅ Create `Session` class
   - Session metadata
   - Conversation encapsulation
   - Serialization
2. ✅ Create `SessionManager` class
   - Session lifecycle
   - Persistence
   - Active session tracking
3. ✅ Add session persistence
   - Save to JSON
   - Restore from JSON
4. ✅ Add unit tests

**Deliverables**:
- `application/session.py`
- `application/session_manager.py`
- Session persistence logic
- Tests

### Phase 4: TUI Integration (3-4 days)

**Goal**: Integrate sessions into NexusApp

**Tasks**:
1. ✅ Update `NexusApp` to use `SessionManager`
2. ✅ Create `SessionTabs` widget
3. ✅ Create `SessionPicker` overlay
4. ✅ Add keyboard shortcuts
5. ✅ Update input handling to use active session
6. ✅ Add session persistence hooks (on exit, periodically)
7. ✅ Update styles and layout

**Deliverables**:
- Updated `tui/nexus_app.py`
- New `tui/widgets/session_tabs.py`
- New `tui/widgets/session_picker.py`
- Updated `tui/styles.tcss`
- Integration tests

### Phase 5: Polish & Documentation (1-2 days)

**Goal**: Finalize and document

**Tasks**:
1. ✅ Remove deprecated code
2. ✅ Update all documentation
3. ✅ Add migration guide
4. ✅ Create user guide for sessions
5. ✅ Add performance benchmarks

**Deliverables**:
- Updated `ARCHITECTURE.md`
- Session user guide
- Migration guide
- Benchmarks

**Total Time**: 11-16 days

---

## 6. Key Design Decisions

### 6.1. Shared vs Per-Session Resources

**Decision**: `Claude` and `ToolRegistry` are **shared** across sessions

**Rationale**:
- ✅ **Efficiency**: Single LLM client, single tool registry
- ✅ **Cache sharing**: Prompt cache shared across sessions
- ✅ **Resource management**: Easier to manage connection pools
- ✅ **Simplicity**: No need to manage per-session resources

**Trade-off**: Cannot have different models per session (can be added later if needed)

### 6.2. Session Persistence Format

**Decision**: JSON files in `~/.nxs/sessions/`

**Rationale**:
- ✅ **Human-readable**: Easy to inspect and debug
- ✅ **Simple**: No database required
- ✅ **Portable**: Easy to backup/restore
- ✅ **Git-friendly**: Can version control sessions

**Trade-off**: Not as performant as binary formats (acceptable for typical usage)

### 6.3. Active Session Tracking

**Decision**: `SessionManager` tracks single active session

**Rationale**:
- ✅ **Simplicity**: Clear which session receives input
- ✅ **UI clarity**: Only one active tab
- ✅ **Matches browser behavior**: Familiar UX

**Alternative considered**: Multiple active sessions (rejected - too complex)

### 6.4. Session Metadata

**Decision**: Rich metadata (title, timestamps, tags)

**Rationale**:
- ✅ **Organization**: Users can organize sessions
- ✅ **Discovery**: Easy to find sessions
- ✅ **UI/UX**: Better session picker experience

**Trade-off**: Slightly more complex persistence (acceptable)

### 6.5. Backward Compatibility

**Decision**: Maintain full backward compatibility in Phase 1-2

**Rationale**:
- ✅ **Low risk**: Existing code continues working
- ✅ **Gradual migration**: Can migrate incrementally
- ✅ **Testing**: Can test new code alongside old

**Approach**: Deprecation warnings, dual API support

---

## 7. Benefits Summary

### For Users

- ✅ **Multiple conversations** - Like browser tabs
- ✅ **Session persistence** - Never lose conversations
- ✅ **Better organization** - Name, tag, search sessions
- ✅ **Faster responses** - Real streaming + caching
- ✅ **Lower costs** - 90% reduction on cached tokens

### For Developers

- ✅ **Clean architecture** - Clear separation of concerns
- ✅ **Testability** - Each component independently testable
- ✅ **Extensibility** - Easy to add features
- ✅ **Maintainability** - Well-organized, documented code

### For the Project

- ✅ **Modern best practices** - 2025 Anthropic recommendations
- ✅ **Future-proof** - Ready for new features
- ✅ **Well-architected** - Solid foundation

---

## 8. Migration Strategy

### Backward Compatibility Approach

```python
# Old API (still works with deprecation warning)
agent_loop = AgentLoop(llm, clients, callbacks)
await agent_loop.run(query)

# New API (recommended)
conversation = Conversation(system_message="...")
tool_registry = ToolRegistry()
tool_registry.register_provider(MCPToolProvider(clients))
agent_loop = AgentLoop(llm, conversation, tool_registry, callbacks)
await agent_loop.run(query)

# Session API (full featured)
session_manager = SessionManager(llm, tool_registry)
session = session_manager.create_session(title="My Chat")
await session.run_query(query)
```

### Migration Steps for Existing Code

1. **Phase 1-2**: No changes required, warnings appear
2. **Phase 3**: Optional migration to new API
3. **Phase 4**: TUI automatically uses sessions
4. **Phase 5**: Deprecated API removed

---

## 9. Questions for Review

Before proceeding, please confirm:

1. **Architecture**: Does the Session/SessionManager design align with your vision?

2. **Persistence**: Is JSON file persistence acceptable, or prefer SQLite/other?

3. **Shared Resources**: Agree with sharing Claude/ToolRegistry across sessions?

4. **UI Components**: Approve session tabs + picker design?

5. **Priorities**: Which phase should I implement first?
   - [ ] Phase 1-2 (Foundation + AgentLoop)
   - [ ] Phase 3 (Session Management)
   - [ ] Phase 4 (TUI Integration)
   - [ ] All phases sequentially

6. **Timeline**: Is 11-16 days acceptable?

---

## Conclusion

This plan integrates:
- ✅ **Agentic loop improvements** (streaming, caching, tools)
- ✅ **Multi-session support** (like browser tabs)
- ✅ **Clean architecture** (separation of concerns)
- ✅ **Persistence** (save/restore conversations)
- ✅ **Backward compatibility** (gradual migration)

**Ready to proceed with implementation?**
