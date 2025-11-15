"""Unit tests for SessionState and its component classes."""

import asyncio

import pytest

from nxs.application.conversation import Conversation
from nxs.application.session_state import (
    UserProfile,
    KnowledgeBase,
    InteractionContext,
    SessionStateMetadata,
    SessionState,
)
from nxs.infrastructure.state import InMemoryStateProvider


class TestUserProfile:
    """Test UserProfile component."""

    def test_initialization(self):
        """Test profile initialization with defaults."""
        profile = UserProfile()
        assert profile.name is None
        assert profile.preferences == {}
        assert profile.context == {}
        assert profile.facts == []
        assert profile.last_updated is not None

    def test_initialization_with_data(self):
        """Test profile initialization with data."""
        profile = UserProfile(
            name="Alice",
            preferences={"theme": "dark"},
            context={"location": "SF"},
            facts=["likes Python", "works in tech"],
        )
        assert profile.name == "Alice"
        assert profile.preferences == {"theme": "dark"}
        assert profile.context == {"location": "SF"}
        assert len(profile.facts) == 2

    def test_update_name(self):
        """Test updating user name."""
        profile = UserProfile()
        profile.update_name("Bob")
        assert profile.name == "Bob"

    def test_add_preference(self):
        """Test adding preferences."""
        profile = UserProfile()
        profile.add_preference("language", "Python")
        assert profile.preferences["language"] == "Python"

    def test_add_fact(self):
        """Test adding facts with deduplication."""
        profile = UserProfile()
        profile.add_fact("likes coffee")
        profile.add_fact("likes coffee")  # Duplicate
        assert len(profile.facts) == 1
        assert "likes coffee" in profile.facts

    def test_serialization(self):
        """Test to_dict and from_dict."""
        profile = UserProfile(
            name="Charlie",
            preferences={"mode": "pro"},
            facts=["expert coder"],
        )

        # Serialize
        data = profile.to_dict()
        assert data["name"] == "Charlie"
        assert "last_updated" in data

        # Deserialize
        restored = UserProfile.from_dict(data)
        assert restored.name == "Charlie"
        assert restored.preferences == {"mode": "pro"}
        assert restored.facts == ["expert coder"]


class TestKnowledgeBase:
    """Test KnowledgeBase component."""

    def test_initialization(self):
        """Test knowledge base initialization."""
        kb = KnowledgeBase()
        assert len(kb) == 0
        assert kb.facts == []

    def test_add_fact(self):
        """Test adding facts."""
        kb = KnowledgeBase()
        kb.add_fact("Python is a programming language", source="conversation")
        assert len(kb) == 1
        assert kb.facts[0]["content"] == "Python is a programming language"
        assert kb.facts[0]["source"] == "conversation"

    def test_add_fact_with_metadata(self):
        """Test adding facts with full metadata."""
        kb = KnowledgeBase()
        kb.add_fact(
            "API key is required",
            source="tool",
            tags=["api", "security"],
            confidence=0.9,
        )

        fact = kb.facts[0]
        assert fact["content"] == "API key is required"
        assert fact["source"] == "tool"
        assert "api" in fact["tags"]
        assert fact["confidence"] == 0.9
        assert "timestamp" in fact

    def test_deduplicate_facts(self):
        """Test that duplicate facts are not added."""
        kb = KnowledgeBase()
        kb.add_fact("Same fact", source="a")
        kb.add_fact("Same fact", source="b")  # Duplicate content
        assert len(kb) == 1

    def test_get_facts_by_tag(self):
        """Test filtering facts by tag."""
        kb = KnowledgeBase()
        kb.add_fact("Fact 1", tags=["python"])
        kb.add_fact("Fact 2", tags=["python", "web"])
        kb.add_fact("Fact 3", tags=["rust"])

        python_facts = kb.get_facts_by_tag("python")
        assert len(python_facts) == 2

    def test_get_facts_by_source(self):
        """Test filtering facts by source."""
        kb = KnowledgeBase()
        kb.add_fact("Fact 1", source="conversation")
        kb.add_fact("Fact 2", source="tool")
        kb.add_fact("Fact 3", source="conversation")

        conv_facts = kb.get_facts_by_source("conversation")
        assert len(conv_facts) == 2

    def test_serialization(self):
        """Test to_dict and from_dict."""
        kb = KnowledgeBase()
        kb.add_fact("Test fact", source="test", tags=["test"])

        # Serialize
        data = kb.to_dict()
        assert len(data["facts"]) == 1

        # Deserialize
        restored = KnowledgeBase.from_dict(data)
        assert len(restored) == 1
        assert restored.facts[0]["content"] == "Test fact"


class TestInteractionContext:
    """Test InteractionContext component."""

    def test_initialization(self):
        """Test context initialization."""
        context = InteractionContext()
        assert context.current_topic is None
        assert context.last_user_intent is None
        assert context.recent_exchanges == []

    def test_add_exchange(self):
        """Test adding conversation exchanges."""
        context = InteractionContext()
        context.add_exchange("Hello", "Hi there!")
        assert len(context.recent_exchanges) == 1
        assert context.recent_exchanges[0]["user"] == "Hello"
        assert context.recent_exchanges[0]["assistant"] == "Hi there!"

    def test_sliding_window(self):
        """Test that only last 5 exchanges are kept."""
        context = InteractionContext()
        for i in range(10):
            context.add_exchange(f"User {i}", f"Assistant {i}")

        assert len(context.recent_exchanges) == 5
        # Should have exchanges 5-9
        assert context.recent_exchanges[0]["user"] == "User 5"
        assert context.recent_exchanges[-1]["user"] == "User 9"

    def test_update_topic(self):
        """Test updating current topic."""
        context = InteractionContext()
        context.update_topic("Python programming")
        assert context.current_topic == "Python programming"

    def test_update_intent(self):
        """Test updating user intent."""
        context = InteractionContext()
        context.update_intent("asking_question")
        assert context.last_user_intent == "asking_question"

    def test_serialization(self):
        """Test to_dict and from_dict."""
        context = InteractionContext(
            current_topic="Testing",
            last_user_intent="learning",
        )
        context.add_exchange("Test?", "Answer")

        # Serialize
        data = context.to_dict()
        assert data["current_topic"] == "Testing"
        assert len(data["recent_exchanges"]) == 1

        # Deserialize
        restored = InteractionContext.from_dict(data)
        assert restored.current_topic == "Testing"
        assert restored.last_user_intent == "learning"
        assert len(restored.recent_exchanges) == 1


class TestSessionStateMetadata:
    """Test SessionStateMetadata component."""

    def test_initialization(self):
        """Test metadata initialization."""
        metadata = SessionStateMetadata()
        assert metadata.total_tokens_used == 0
        assert metadata.total_cost == 0.0
        assert metadata.tool_call_count == 0
        assert metadata.reasoning_task_count == 0
        assert metadata.custom_metrics == {}

    def test_record_tool_call(self):
        """Test recording tool calls."""
        metadata = SessionStateMetadata()
        metadata.record_tool_call(tokens=100, cost=0.01)
        assert metadata.tool_call_count == 1
        assert metadata.total_tokens_used == 100
        assert metadata.total_cost == 0.01

    def test_record_reasoning_task(self):
        """Test recording reasoning tasks."""
        metadata = SessionStateMetadata()
        metadata.record_reasoning_task(tokens=500, cost=0.05)
        assert metadata.reasoning_task_count == 1
        assert metadata.total_tokens_used == 500
        assert metadata.total_cost == 0.05

    def test_accumulation(self):
        """Test that metrics accumulate correctly."""
        metadata = SessionStateMetadata()
        metadata.record_tool_call(tokens=100, cost=0.01)
        metadata.record_tool_call(tokens=200, cost=0.02)
        metadata.record_reasoning_task(tokens=300, cost=0.03)

        assert metadata.tool_call_count == 2
        assert metadata.reasoning_task_count == 1
        assert metadata.total_tokens_used == 600
        assert metadata.total_cost == 0.06

    def test_custom_metrics(self):
        """Test adding custom metrics."""
        metadata = SessionStateMetadata()
        metadata.add_custom_metric("custom_counter", 42)
        assert metadata.custom_metrics["custom_counter"] == 42

    def test_serialization(self):
        """Test to_dict and from_dict."""
        metadata = SessionStateMetadata(
            total_tokens_used=1000,
            total_cost=0.10,
            tool_call_count=5,
        )
        metadata.add_custom_metric("test", "value")

        # Serialize
        data = metadata.to_dict()
        assert data["total_tokens_used"] == 1000
        assert "created_at" in data

        # Deserialize
        restored = SessionStateMetadata.from_dict(data)
        assert restored.total_tokens_used == 1000
        assert restored.total_cost == 0.10
        assert restored.tool_call_count == 5
        assert restored.custom_metrics["test"] == "value"


class TestSessionState:
    """Test SessionState top-level container."""

    def test_initialization(self):
        """Test session state initialization."""
        conversation = Conversation()
        state = SessionState(
            session_id="test-123",
            conversation=conversation,
        )

        assert state.session_id == "test-123"
        assert state.conversation is conversation
        assert state.user_profile is not None
        assert state.knowledge_base is not None
        assert state.interaction_context is not None
        assert state.metadata is not None

    def test_initialization_with_components(self):
        """Test initialization with custom components."""
        conversation = Conversation()
        profile = UserProfile(name="Alice")
        kb = KnowledgeBase()
        kb.add_fact("Test fact")

        state = SessionState(
            session_id="test-456",
            conversation=conversation,
            user_profile=profile,
            knowledge_base=kb,
        )

        assert state.user_profile.name == "Alice"
        assert len(state.knowledge_base) == 1

    @pytest.mark.asyncio
    async def test_save_without_provider(self):
        """Test save without state provider (should be no-op)."""
        conversation = Conversation()
        state = SessionState(
            session_id="test-789",
            conversation=conversation,
        )

        # Should not raise error
        await state.save()

    @pytest.mark.asyncio
    async def test_save_with_provider(self):
        """Test save with state provider."""
        provider = InMemoryStateProvider()
        conversation = Conversation()
        state = SessionState(
            session_id="test-save",
            conversation=conversation,
            state_provider=provider,
        )

        # Save state
        await state.save()

        # Verify saved
        assert await provider.exists("session_state:test-save")

        # Load and verify
        saved_data = await provider.load("session_state:test-save")
        assert saved_data is not None
        assert saved_data["session_id"] == "test-save"

    def test_serialization(self):
        """Test to_dict and from_dict."""
        conversation = Conversation()
        conversation.add_user_message("Hello")

        state = SessionState(
            session_id="test-serial",
            conversation=conversation,
        )
        state.user_profile.update_name("Bob")
        state.knowledge_base.add_fact("Important fact")
        state.interaction_context.update_topic("Testing")
        state.metadata.record_tool_call(tokens=100, cost=0.01)

        # Serialize
        data = state.to_dict()
        assert data["session_id"] == "test-serial"
        assert "conversation" in data
        assert "user_profile" in data
        assert "knowledge_base" in data
        assert "interaction_context" in data
        assert "metadata" in data
        assert "created_at" in data

        # Deserialize
        restored = SessionState.from_dict(data)
        assert restored.session_id == "test-serial"
        assert restored.user_profile.name == "Bob"
        assert len(restored.knowledge_base) == 1
        assert restored.interaction_context.current_topic == "Testing"
        assert restored.metadata.tool_call_count == 1
        assert restored.conversation.get_message_count() == 1

    def test_get_context_summary(self):
        """Test context summary generation."""
        conversation = Conversation()
        state = SessionState(
            session_id="test-summary",
            conversation=conversation,
        )

        # Initially empty
        summary = state.get_context_summary()
        assert "New session" in summary or "Session:" in summary

        # Add some context
        state.user_profile.update_name("Alice")
        state.user_profile.add_fact("Likes Python")
        state.knowledge_base.add_fact("Python is great")
        state.interaction_context.update_topic("Programming")
        state.metadata.record_tool_call()

        # Should include various components
        summary = state.get_context_summary()
        assert "Alice" in summary
        assert "Programming" in summary or "topic" in summary.lower()


class TestSessionStateIntegration:
    """Integration tests for SessionState with other components."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_provider(self):
        """Test complete save/load lifecycle."""
        provider = InMemoryStateProvider()
        conversation = Conversation(system_message="You are helpful")
        conversation.add_user_message("What is Python?")

        # Create state
        state = SessionState(
            session_id="lifecycle-test",
            conversation=conversation,
            state_provider=provider,
        )
        state.user_profile.update_name("TestUser")
        state.knowledge_base.add_fact("Python is a language", source="conversation")
        state.interaction_context.update_topic("Python basics")
        state.metadata.record_tool_call(tokens=150, cost=0.015)

        # Save
        await state.save()

        # Load from provider
        saved_data = await provider.load("session_state:lifecycle-test")
        assert saved_data is not None

        # Restore
        restored = SessionState.from_dict(saved_data, state_provider=provider)

        # Verify all components
        assert restored.session_id == "lifecycle-test"
        assert restored.user_profile.name == "TestUser"
        assert len(restored.knowledge_base) == 1
        assert restored.interaction_context.current_topic == "Python basics"
        assert restored.metadata.total_tokens_used == 150
        assert restored.metadata.total_cost == 0.015
        assert restored.conversation.system_message == "You are helpful"
        assert restored.conversation.get_message_count() == 1
