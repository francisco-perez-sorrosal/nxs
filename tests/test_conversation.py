"""Unit tests for Conversation class."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from anthropic.types import ContentBlock, Message, TextBlock, ToolUseBlock

from nxs.application.conversation import Conversation


class TestConversationBasics:
    """Test basic conversation operations."""

    def test_initialization(self):
        """Test conversation initialization with defaults."""
        conv = Conversation()
        assert conv.get_message_count() == 0
        assert conv.system_message is None
        assert conv.created_at is not None
        assert conv.last_modified_at is not None

    def test_initialization_with_system_message(self):
        """Test conversation initialization with system message."""
        system = "You are a helpful assistant."
        conv = Conversation(system_message=system)
        assert conv.system_message == system
        assert conv.get_message_count() == 0

    def test_initialization_with_config(self):
        """Test conversation initialization with full config."""
        conv = Conversation(
            system_message="Test system",
            max_history_messages=10,
            enable_caching=False,
        )
        assert conv.system_message == "Test system"
        assert conv._max_history_messages == 10
        assert conv._enable_caching is False


class TestMessageManagement:
    """Test message addition and management."""

    def test_add_user_message_string(self):
        """Test adding a simple string user message."""
        conv = Conversation(enable_caching=False)  # Disable caching for simpler assertion
        conv.add_user_message("Hello!")

        assert conv.get_message_count() == 1
        messages = conv.get_messages_for_api()
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello!"

    def test_add_user_message_rich_content(self):
        """Test adding a user message with rich content blocks."""
        conv = Conversation(enable_caching=False)  # Disable caching for simpler assertion
        content = [
            {"type": "text", "text": "Analyze this"},
            {"type": "image", "source": {"type": "base64", "data": "..."}}
        ]
        conv.add_user_message(content)

        assert conv.get_message_count() == 1
        messages = conv.get_messages_for_api()
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == content

    def test_add_assistant_message(self):
        """Test adding an assistant message from API response."""
        conv = Conversation()

        # Create a mock Message object
        mock_message = Mock(spec=Message)
        mock_message.content = [
            TextBlock(type="text", text="I can help with that!")
        ]

        conv.add_assistant_message(mock_message)

        assert conv.get_message_count() == 1
        messages = conv.get_messages_for_api()
        assert messages[0]["role"] == "assistant"
        assert len(messages[0]["content"]) == 1

    def test_add_tool_results(self):
        """Test adding tool execution results."""
        conv = Conversation()

        # Create mock tool use blocks
        tool_blocks = [
            ToolUseBlock(id="tool_1", type="tool_use", name="search", input={}),
            ToolUseBlock(id="tool_2", type="tool_use", name="calculate", input={}),
        ]
        results = ["Search result 1", "Calculation: 42"]

        conv.add_tool_results(tool_blocks, results)

        assert conv.get_message_count() == 1
        messages = conv.get_messages_for_api()
        assert messages[0]["role"] == "user"
        assert len(messages[0]["content"]) == 2
        assert messages[0]["content"][0]["type"] == "tool_result"
        assert messages[0]["content"][0]["tool_use_id"] == "tool_1"
        assert messages[0]["content"][0]["content"] == "Search result 1"

    def test_add_tool_results_mismatch_raises_error(self):
        """Test that mismatched tool blocks and results raises ValueError."""
        conv = Conversation()

        tool_blocks = [
            ToolUseBlock(id="tool_1", type="tool_use", name="search", input={})
        ]
        results = ["Result 1", "Result 2"]  # Mismatch!

        with pytest.raises(ValueError, match="Mismatch between tool_use_blocks"):
            conv.add_tool_results(tool_blocks, results)

    def test_conversation_flow(self):
        """Test a realistic conversation flow."""
        conv = Conversation(system_message="You are helpful.")

        # User asks a question
        conv.add_user_message("What is 2+2?")
        assert conv.get_message_count() == 1

        # Assistant responds
        mock_message = Mock(spec=Message)
        mock_message.content = [
            TextBlock(type="text", text="The answer is 4.")
        ]
        conv.add_assistant_message(mock_message)
        assert conv.get_message_count() == 2

        # User asks follow-up
        conv.add_user_message("And 4+4?")
        assert conv.get_message_count() == 3

        # Verify message order
        messages = conv.get_messages_for_api()
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"


class TestCacheControl:
    """Test prompt caching functionality."""

    def test_cache_control_disabled(self):
        """Test that cache control is not applied when disabled."""
        conv = Conversation(enable_caching=False)
        conv.add_user_message("Hello")

        messages = conv.get_messages_for_api()
        content = messages[0]["content"]

        # Content should remain as string, no cache_control
        assert isinstance(content, str)
        assert content == "Hello"

    def test_cache_control_on_last_user_message(self):
        """Test that cache control is applied to last user message."""
        conv = Conversation(enable_caching=True)
        conv.add_user_message("First message")
        conv.add_user_message("Second message")

        messages = conv.get_messages_for_api()

        # First message should not have cache control
        assert isinstance(messages[0]["content"], str)

        # Last user message should have cache control
        last_content = messages[1]["content"]
        assert isinstance(last_content, list)
        assert len(last_content) == 1
        assert last_content[0]["type"] == "text"
        assert last_content[0]["text"] == "Second message"
        assert last_content[0]["cache_control"] == {"type": "ephemeral"}

    def test_cache_control_with_rich_content(self):
        """Test cache control with rich content blocks."""
        conv = Conversation(enable_caching=True)
        content = [
            {"type": "text", "text": "First block"},
            {"type": "text", "text": "Second block"}
        ]
        conv.add_user_message(content)

        messages = conv.get_messages_for_api()
        result_content = messages[0]["content"]

        # Cache control should be on last block
        assert len(result_content) == 2
        assert "cache_control" not in result_content[0]
        assert result_content[1]["cache_control"] == {"type": "ephemeral"}

    def test_cache_control_does_not_mutate_internal_state(self):
        """Test that applying cache control doesn't mutate internal messages."""
        conv = Conversation(enable_caching=True)
        conv.add_user_message("Test")

        # Get messages with cache control
        messages1 = conv.get_messages_for_api()

        # Get messages again
        messages2 = conv.get_messages_for_api()

        # Both should have cache control
        assert isinstance(messages1[0]["content"], list)
        assert isinstance(messages2[0]["content"], list)

        # Internal state should still be string
        assert isinstance(conv._messages[0]["content"], str)

    def test_system_message_cache_control_enabled(self):
        """Test that system message gets cache control when enabled."""
        conv = Conversation(
            system_message="You are a helpful assistant.",
            enable_caching=True
        )

        system = conv.get_system_message_for_api()

        assert isinstance(system, list)
        assert len(system) == 1
        assert system[0]["type"] == "text"
        assert system[0]["text"] == "You are a helpful assistant."
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_system_message_cache_control_disabled(self):
        """Test that system message is plain string when caching disabled."""
        conv = Conversation(
            system_message="You are a helpful assistant.",
            enable_caching=False
        )

        system = conv.get_system_message_for_api()

        assert isinstance(system, str)
        assert system == "You are a helpful assistant."

    def test_system_message_none(self):
        """Test that None is returned when no system message is set."""
        conv = Conversation()
        assert conv.get_system_message_for_api() is None


class TestHistoryManagement:
    """Test history limits and truncation."""

    def test_history_limit_enforced(self):
        """Test that history limit truncates old messages."""
        conv = Conversation(max_history_messages=3, enable_caching=False)

        conv.add_user_message("Message 1")
        conv.add_user_message("Message 2")
        conv.add_user_message("Message 3")
        conv.add_user_message("Message 4")

        # Should only keep last 3 messages
        assert conv.get_message_count() == 3
        messages = conv.get_messages_for_api()
        assert messages[0]["content"] == "Message 2"
        assert messages[1]["content"] == "Message 3"
        assert messages[2]["content"] == "Message 4"

    def test_no_history_limit(self):
        """Test that no limit allows unlimited messages."""
        conv = Conversation(max_history_messages=None)

        for i in range(100):
            conv.add_user_message(f"Message {i}")

        assert conv.get_message_count() == 100

    def test_clear_history(self):
        """Test clearing conversation history."""
        conv = Conversation(system_message="Test")

        conv.add_user_message("Message 1")
        conv.add_user_message("Message 2")
        assert conv.get_message_count() == 2

        conv.clear_history()

        assert conv.get_message_count() == 0
        # System message should remain
        assert conv.system_message == "Test"


class TestTokenEstimation:
    """Test token counting estimation."""

    def test_token_estimate_empty(self):
        """Test token estimate for empty conversation."""
        conv = Conversation()
        assert conv.get_token_estimate() == 0

    def test_token_estimate_with_system(self):
        """Test token estimate includes system message."""
        # 28 chars = ~7 tokens (4 chars per token)
        conv = Conversation(system_message="You are a helpful assistant.")
        assert conv.get_token_estimate() >= 7

    def test_token_estimate_with_messages(self):
        """Test token estimate for conversation messages."""
        conv = Conversation()
        conv.add_user_message("Hello!")  # 6 chars = ~1 token
        conv.add_user_message("How are you?")  # 12 chars = ~3 tokens

        # Should be at least 4 tokens
        assert conv.get_token_estimate() >= 4

    def test_token_estimate_with_rich_content(self):
        """Test token estimate with rich content blocks."""
        conv = Conversation()
        content = [
            {"type": "text", "text": "Hello World"},  # 11 chars
            {"type": "image", "source": {}}  # Images not counted
        ]
        conv.add_user_message(content)

        # Only text content counted
        assert conv.get_token_estimate() >= 2


class TestPersistence:
    """Test conversation serialization and deserialization."""

    def test_to_dict_basic(self):
        """Test basic conversation serialization."""
        conv = Conversation(system_message="Test")
        conv.add_user_message("Hello")

        data = conv.to_dict()

        assert data["system_message"] == "Test"
        assert len(data["messages"]) == 1
        assert data["enable_caching"] is True
        assert "created_at" in data
        assert "last_modified_at" in data

    def test_from_dict_restoration(self):
        """Test conversation deserialization."""
        original = Conversation(
            system_message="Test system",
            max_history_messages=10,
            enable_caching=False
        )
        original.add_user_message("Message 1")
        original.add_user_message("Message 2")

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = Conversation.from_dict(data)

        assert restored.system_message == "Test system"
        assert restored._max_history_messages == 10
        assert restored._enable_caching is False
        assert restored.get_message_count() == 2

        messages = restored.get_messages_for_api()
        assert messages[0]["content"] == "Message 1"
        assert messages[1]["content"] == "Message 2"

    def test_from_dict_preserves_timestamps(self):
        """Test that timestamps are preserved during serialization."""
        original = Conversation()
        original.add_user_message("Test")

        data = original.to_dict()
        restored = Conversation.from_dict(data)

        assert restored.created_at == original.created_at
        assert restored.last_modified_at == original.last_modified_at

    def test_round_trip_serialization(self):
        """Test full round-trip serialization preserves all state."""
        conv1 = Conversation(system_message="System")
        conv1.add_user_message("User 1")

        mock_message = Mock(spec=Message)
        mock_message.content = [TextBlock(type="text", text="Assistant 1")]
        conv1.add_assistant_message(mock_message)

        conv1.add_user_message("User 2")

        # Round trip
        data = conv1.to_dict()
        conv2 = Conversation.from_dict(data)

        # Verify everything matches
        assert conv2.system_message == conv1.system_message
        assert conv2.get_message_count() == conv1.get_message_count()
        assert conv2.created_at == conv1.created_at


class TestSystemMessageProperty:
    """Test system message property setter."""

    def test_system_message_setter(self):
        """Test setting system message via property."""
        conv = Conversation()
        assert conv.system_message is None

        conv.system_message = "New system message"

        assert conv.system_message == "New system message"

    def test_system_message_setter_updates_timestamp(self):
        """Test that setting system message updates last_modified_at."""
        conv = Conversation()
        original_time = conv.last_modified_at

        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.01)

        conv.system_message = "Updated"

        assert conv.last_modified_at > original_time
