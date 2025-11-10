"""Unit tests for SessionManager class."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from nxs.application.claude import Claude
from nxs.application.session import Session
from nxs.application.session_manager_new import SessionManager
from nxs.application.tool_registry import ToolRegistry


class TestSessionManager:
    """Test SessionManager class."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock Claude instance."""
        llm = Mock(spec=Claude)
        llm.model = "claude-sonnet-4.5"
        return llm

    @pytest.fixture
    def mock_tool_registry(self):
        """Create a mock ToolRegistry."""
        registry = Mock(spec=ToolRegistry)
        registry.get_tool_count.return_value = 5
        return registry

    @pytest.fixture
    def temp_storage_dir(self, tmp_path):
        """Create a temporary storage directory."""
        storage = tmp_path / "sessions"
        storage.mkdir()
        return storage

    @pytest.fixture
    def session_manager(self, mock_llm, mock_tool_registry, temp_storage_dir):
        """Create a SessionManager instance."""
        return SessionManager(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            storage_dir=temp_storage_dir,
            system_message="You are helpful",
            enable_caching=True,
        )

    def test_initialization(self, session_manager, temp_storage_dir, mock_llm):
        """Test SessionManager initialization."""
        assert session_manager.llm == mock_llm
        assert session_manager.storage_dir == temp_storage_dir
        assert session_manager.system_message == "You are helpful"
        assert session_manager.enable_caching is True
        assert session_manager._active_session is None
        assert temp_storage_dir.exists()

    def test_initialization_creates_storage_dir(self, mock_llm, mock_tool_registry, tmp_path):
        """Test that initialization creates storage directory if it doesn't exist."""
        storage_dir = tmp_path / "new" / "nested" / "dir"
        assert not storage_dir.exists()

        manager = SessionManager(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            storage_dir=storage_dir,
        )

        assert storage_dir.exists()

    @pytest.mark.asyncio
    async def test_get_or_create_default_session_creates_new(self, session_manager):
        """Test creating a new default session when none exists."""
        session = await session_manager.get_or_create_default_session()

        assert session is not None
        assert session.session_id == SessionManager.DEFAULT_SESSION_ID
        assert session.title == "New Conversation"
        assert session_manager._active_session == session

    @pytest.mark.asyncio
    async def test_get_or_create_default_session_returns_cached(self, session_manager):
        """Test that subsequent calls return the same session."""
        session1 = await session_manager.get_or_create_default_session()
        session2 = await session_manager.get_or_create_default_session()

        assert session1 is session2

    @pytest.mark.asyncio
    async def test_get_or_create_default_session_restores_from_disk(
        self, session_manager, temp_storage_dir
    ):
        """Test restoring session from disk on startup."""
        # Create a saved session file
        session_data = {
            "metadata": {
                "session_id": "default",
                "title": "Saved Session",
                "created_at": "2025-01-01T12:00:00",
                "last_active_at": "2025-01-01T13:00:00",
                "tags": ["restored"],
                "model": "claude-sonnet-4.5",
                "description": "Test",
            },
            "conversation": {
                "messages": [{"role": "user", "content": "Hello"}],
                "system_message": "You are helpful",
                "enable_caching": True,
                "created_at": "2025-01-01T12:00:00",
                "last_modified_at": "2025-01-01T13:00:00",
            },
        }

        session_file = temp_storage_dir / SessionManager.SESSION_FILE_NAME
        with open(session_file, "w") as f:
            json.dump(session_data, f)

        # Get or create should restore from disk
        session = await session_manager.get_or_create_default_session()

        assert session.title == "Saved Session"
        assert session.metadata.tags == ["restored"]
        assert session.get_message_count() == 1

    @pytest.mark.asyncio
    async def test_get_or_create_default_session_handles_corrupt_file(
        self, session_manager, temp_storage_dir
    ):
        """Test that corrupt session file is handled gracefully."""
        # Create a corrupt session file
        session_file = temp_storage_dir / SessionManager.SESSION_FILE_NAME
        with open(session_file, "w") as f:
            f.write("{ corrupt json }")

        # Should create new session instead of crashing
        session = await session_manager.get_or_create_default_session()

        assert session.session_id == SessionManager.DEFAULT_SESSION_ID
        assert session.title == "New Conversation"

    def test_save_active_session(self, session_manager, temp_storage_dir):
        """Test saving active session to disk."""
        # Create a session with some state
        session = session_manager._create_new_session(
            SessionManager.DEFAULT_SESSION_ID, title="Test Session"
        )
        session_manager._active_session = session

        # Add a message to conversation
        session.conversation.add_user_message("Test message")

        # Save session
        session_manager.save_active_session()

        # Verify file was created
        session_file = temp_storage_dir / SessionManager.SESSION_FILE_NAME
        assert session_file.exists()

        # Verify contents
        with open(session_file, "r") as f:
            data = json.load(f)

        assert data["metadata"]["title"] == "Test Session"
        assert len(data["conversation"]["messages"]) == 1

    def test_save_active_session_no_session(self, session_manager):
        """Test saving when no active session exists."""
        # Should not crash
        session_manager.save_active_session()

    def test_get_active_session(self, session_manager):
        """Test getting the active session."""
        assert session_manager.get_active_session() is None

        session = session_manager._create_new_session("test")
        session_manager._active_session = session

        assert session_manager.get_active_session() == session

    def test_clear_active_session_history(self, session_manager):
        """Test clearing active session history."""
        session = session_manager._create_new_session("test")
        session.conversation.add_user_message("Test")
        session_manager._active_session = session

        assert session.get_message_count() == 1

        session_manager.clear_active_session_history()

        assert session.get_message_count() == 0

    def test_clear_active_session_history_no_session(self, session_manager):
        """Test clearing history when no active session."""
        # Should not crash
        session_manager.clear_active_session_history()

    def test_get_session_info(self, session_manager):
        """Test getting session information."""
        assert session_manager.get_session_info() is None

        session = session_manager._create_new_session("test", title="Test Chat")
        session.conversation.add_user_message("Message 1")
        session.conversation.add_user_message("Message 2")
        session_manager._active_session = session

        info = session_manager.get_session_info()

        assert info is not None
        assert info["session_id"] == "test"
        assert info["title"] == "Test Chat"
        assert info["message_count"] == "2"
        assert "created_at" in info
        assert "last_active_at" in info

    def test_create_new_session(self, session_manager):
        """Test creating a new session."""
        session = session_manager._create_new_session("test-1", title="My Chat")

        assert session.session_id == "test-1"
        assert session.title == "My Chat"
        assert session.conversation.system_message == "You are helpful"
        assert session.conversation._enable_caching is True
        assert session.metadata.model == "claude-sonnet-4.5"

    def test_create_new_session_default_title(self, session_manager):
        """Test creating session with default title."""
        session = session_manager._create_new_session("test-2")

        assert session.title == "New Conversation"

    @pytest.mark.asyncio
    async def test_round_trip_save_and_restore(self, session_manager, temp_storage_dir):
        """Test full round-trip of saving and restoring a session."""
        # Create and configure a session
        session1 = await session_manager.get_or_create_default_session()
        session1.title = "Test Round Trip"
        session1.conversation.add_user_message("User message")

        # Save session
        session_manager.save_active_session()

        # Clear active session to force restore
        session_manager._active_session = None

        # Restore session
        session2 = await session_manager.get_or_create_default_session()

        # Verify restored session matches original
        assert session2.title == "Test Round Trip"
        assert session2.get_message_count() == 1

    @pytest.mark.asyncio
    async def test_session_persistence_across_instances(
        self, mock_llm, mock_tool_registry, temp_storage_dir
    ):
        """Test that session persists across SessionManager instances."""
        # Create first manager and session
        manager1 = SessionManager(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            storage_dir=temp_storage_dir,
            system_message="Test",
        )

        session1 = await manager1.get_or_create_default_session()
        session1.title = "Persistent Session"
        session1.conversation.add_user_message("Message 1")
        manager1.save_active_session()

        # Create second manager (simulating app restart)
        manager2 = SessionManager(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            storage_dir=temp_storage_dir,
            system_message="Test",
        )

        session2 = await manager2.get_or_create_default_session()

        # Session should be restored
        assert session2.title == "Persistent Session"
        assert session2.get_message_count() == 1

    def test_storage_dir_expansion(self, mock_llm, mock_tool_registry):
        """Test that storage_dir handles tilde expansion."""
        manager = SessionManager(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            storage_dir=Path("~/.nxs/test"),
        )

        # Path should be expanded
        assert "~" not in str(manager.storage_dir)
        assert manager.storage_dir.is_absolute()

    def test_callbacks_passed_to_agent_loop(self, mock_llm, mock_tool_registry, temp_storage_dir):
        """Test that callbacks are passed to AgentLoop."""
        callbacks = {"on_stream_chunk": AsyncMock()}

        manager = SessionManager(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            storage_dir=temp_storage_dir,
            callbacks=callbacks,
        )

        session = manager._create_new_session("test")

        assert session.agent_loop.callbacks == callbacks
