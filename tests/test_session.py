"""Unit tests for Session and SessionMetadata classes."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from nxs.application.chat import AgentLoop
from nxs.application.conversation import Conversation
from nxs.application.session import Session, SessionMetadata


class TestSessionMetadata:
    """Test SessionMetadata class."""

    def test_initialization_defaults(self):
        """Test SessionMetadata initialization with defaults."""
        metadata = SessionMetadata(session_id="test-1")

        assert metadata.session_id == "test-1"
        assert metadata.title == "New Conversation"
        assert isinstance(metadata.created_at, datetime)
        assert isinstance(metadata.last_active_at, datetime)
        assert metadata.tags == []
        assert metadata.model == "claude-sonnet-4.5"
        assert metadata.description is None

    def test_initialization_with_values(self):
        """Test SessionMetadata initialization with custom values."""
        created = datetime(2025, 1, 1, 12, 0, 0)
        metadata = SessionMetadata(
            session_id="test-2",
            title="My Chat",
            created_at=created,
            tags=["work", "important"],
            model="claude-opus-4",
            description="Test session",
        )

        assert metadata.session_id == "test-2"
        assert metadata.title == "My Chat"
        assert metadata.created_at == created
        assert metadata.tags == ["work", "important"]
        assert metadata.model == "claude-opus-4"
        assert metadata.description == "Test session"

    def test_to_dict(self):
        """Test metadata serialization to dictionary."""
        created = datetime(2025, 1, 1, 12, 0, 0)
        metadata = SessionMetadata(
            session_id="test-3",
            title="Test",
            created_at=created,
            last_active_at=created,
            tags=["tag1"],
            model="test-model",
            description="Description",
        )

        data = metadata.to_dict()

        assert data["session_id"] == "test-3"
        assert data["title"] == "Test"
        assert data["created_at"] == created.isoformat()
        assert data["last_active_at"] == created.isoformat()
        assert data["tags"] == ["tag1"]
        assert data["model"] == "test-model"
        assert data["description"] == "Description"

    def test_from_dict(self):
        """Test metadata deserialization from dictionary."""
        created = datetime(2025, 1, 1, 12, 0, 0)
        data = {
            "session_id": "test-4",
            "title": "Restored",
            "created_at": created.isoformat(),
            "last_active_at": created.isoformat(),
            "tags": ["tag1", "tag2"],
            "model": "claude-sonnet-4.5",
            "description": "Test",
        }

        metadata = SessionMetadata.from_dict(data)

        assert metadata.session_id == "test-4"
        assert metadata.title == "Restored"
        assert metadata.created_at == created
        assert metadata.last_active_at == created
        assert metadata.tags == ["tag1", "tag2"]
        assert metadata.model == "claude-sonnet-4.5"
        assert metadata.description == "Test"

    def test_from_dict_with_defaults(self):
        """Test metadata deserialization with missing optional fields."""
        created = datetime(2025, 1, 1, 12, 0, 0)
        data = {
            "session_id": "test-5",
            "created_at": created.isoformat(),
            "last_active_at": created.isoformat(),
        }

        metadata = SessionMetadata.from_dict(data)

        assert metadata.session_id == "test-5"
        assert metadata.title == "New Conversation"  # Default
        assert metadata.tags == []  # Default
        assert metadata.model == "claude-sonnet-4.5"  # Default
        assert metadata.description is None  # Default

    def test_round_trip_serialization(self):
        """Test full round-trip serialization."""
        original = SessionMetadata(
            session_id="test-6",
            title="Round Trip",
            tags=["test"],
            model="test-model",
            description="Testing",
        )

        data = original.to_dict()
        restored = SessionMetadata.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.title == original.title
        assert restored.tags == original.tags
        assert restored.model == original.model
        assert restored.description == original.description


class TestSession:
    """Test Session class."""

    @pytest.fixture
    def mock_conversation(self):
        """Create a mock Conversation."""
        conversation = Mock(spec=Conversation)
        conversation.get_message_count.return_value = 5
        conversation.get_token_estimate.return_value = 100
        conversation.to_dict.return_value = {
            "messages": [],
            "system_message": "Test",
            "enable_caching": True,
        }
        return conversation

    @pytest.fixture
    def mock_agent_loop(self):
        """Create a mock AgentLoop."""
        agent_loop = Mock(spec=AgentLoop)
        agent_loop.run = AsyncMock(return_value="Test response")
        return agent_loop

    @pytest.fixture
    def session_metadata(self):
        """Create test SessionMetadata."""
        return SessionMetadata(session_id="test-session", title="Test Chat")

    @pytest.fixture
    def session(self, session_metadata, mock_conversation, mock_agent_loop):
        """Create a test Session."""
        return Session(
            metadata=session_metadata,
            conversation=mock_conversation,
            agent_loop=mock_agent_loop,
        )

    def test_initialization(self, session, session_metadata, mock_conversation):
        """Test Session initialization."""
        assert session.metadata == session_metadata
        assert session.conversation == mock_conversation
        assert session.session_id == "test-session"
        assert session.title == "Test Chat"

    @pytest.mark.asyncio
    async def test_run_query(self, session, mock_agent_loop):
        """Test running a query through the session."""
        result = await session.run_query("What is 2+2?")

        assert result == "Test response"
        mock_agent_loop.run.assert_called_once_with(
            query="What is 2+2?", callbacks=None, use_streaming=True
        )

    @pytest.mark.asyncio
    async def test_run_query_with_callbacks(self, session, mock_agent_loop):
        """Test running a query with custom callbacks."""
        callbacks = {"on_stream_chunk": AsyncMock()}

        result = await session.run_query(
            "Hello", callbacks=callbacks, use_streaming=False
        )

        assert result == "Test response"
        mock_agent_loop.run.assert_called_once_with(
            query="Hello", callbacks=callbacks, use_streaming=False
        )

    @pytest.mark.asyncio
    async def test_run_query_updates_last_active(self, session):
        """Test that run_query updates last_active_at timestamp."""
        original_time = session.metadata.last_active_at

        # Small delay to ensure timestamp difference
        import asyncio
        await asyncio.sleep(0.01)

        await session.run_query("Test")

        assert session.metadata.last_active_at > original_time

    def test_clear_history(self, session, mock_conversation):
        """Test clearing conversation history."""
        original_time = session.metadata.last_active_at

        import time
        time.sleep(0.01)

        session.clear_history()

        mock_conversation.clear_history.assert_called_once()
        assert session.metadata.last_active_at > original_time

    def test_get_message_count(self, session, mock_conversation):
        """Test getting message count."""
        # Reset call count from initialization
        mock_conversation.get_message_count.reset_mock()

        count = session.get_message_count()

        assert count == 5
        mock_conversation.get_message_count.assert_called_once()

    def test_get_token_estimate(self, session, mock_conversation):
        """Test getting token estimate."""
        tokens = session.get_token_estimate()

        assert tokens == 100
        mock_conversation.get_token_estimate.assert_called_once()

    def test_to_dict(self, session, session_metadata, mock_conversation):
        """Test session serialization."""
        data = session.to_dict()

        assert "metadata" in data
        assert "conversation" in data
        assert data["metadata"]["session_id"] == "test-session"
        mock_conversation.to_dict.assert_called_once()

    def test_from_dict(self, mock_agent_loop, mock_conversation):
        """Test session deserialization."""
        created = datetime(2025, 1, 1, 12, 0, 0)
        data = {
            "metadata": {
                "session_id": "restored-session",
                "title": "Restored Chat",
                "created_at": created.isoformat(),
                "last_active_at": created.isoformat(),
                "tags": [],
                "model": "claude-sonnet-4.5",
                "description": None,
            },
            "conversation": {
                "messages": [],
                "system_message": "Test",
                "enable_caching": True,
            },
        }

        session = Session.from_dict(data, mock_agent_loop)

        assert session.session_id == "restored-session"
        assert session.title == "Restored Chat"
        assert session.metadata.created_at == created

    def test_title_property_setter(self, session):
        """Test setting title via property."""
        original_time = session.metadata.last_active_at

        import time
        time.sleep(0.01)

        session.title = "New Title"

        assert session.title == "New Title"
        assert session.metadata.title == "New Title"
        assert session.metadata.last_active_at > original_time

    def test_session_properties(self, session, session_metadata):
        """Test session property accessors."""
        assert session.session_id == session_metadata.session_id
        assert session.title == session_metadata.title
        assert session.created_at == session_metadata.created_at
        assert session.last_active_at == session_metadata.last_active_at

    def test_round_trip_serialization(self, session, mock_agent_loop):
        """Test full round-trip serialization."""
        # Serialize
        data = session.to_dict()

        # Deserialize
        restored = Session.from_dict(data, mock_agent_loop)

        # Verify metadata preserved
        assert restored.session_id == session.session_id
        assert restored.title == session.title

        # Verify agent loop was updated with restored conversation
        assert mock_agent_loop.conversation is not None
