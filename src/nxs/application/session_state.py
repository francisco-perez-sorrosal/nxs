"""Session state management - comprehensive state container for sessions.

This module provides SessionState and its component classes for managing
rich, structured session information beyond just conversation messages.

Components:
- UserProfile: Extracted user information (name, preferences, context)
- KnowledgeBase: Facts and insights learned during the session
- InteractionContext: Current conversation context and intent
- SessionStateMetadata: Session-level statistics and metadata

SessionState transforms a session from a flat message sequence into a
semantic, queryable knowledge structure.
"""

from datetime import datetime
from typing import Any, Optional

from nxs.application.conversation import Conversation
from nxs.domain.protocols import StateProvider
from nxs.logger import get_logger

logger = get_logger(__name__)


class UserProfile:
    """Stores extracted information about the user.

    This component maintains a structured representation of user information
    extracted from conversation (via LLM in Phase 3). It enables personalized
    responses and context-aware interactions.

    Attributes:
        name: User's name (if mentioned)
        preferences: User preferences and settings
        context: Additional contextual information about the user
        facts: Key facts about the user extracted from conversation
    """

    def __init__(
        self,
        name: Optional[str] = None,
        preferences: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
        facts: Optional[list[str]] = None,
    ):
        """Initialize user profile.

        Args:
            name: User's name (if known)
            preferences: User preferences dict
            context: Additional user context dict
            facts: List of extracted facts about the user
        """
        self.name = name
        self.preferences = preferences or {}
        self.context = context or {}
        self.facts = facts or []
        self._last_updated = datetime.now()

    def update_name(self, name: str) -> None:
        """Update user's name."""
        self.name = name
        self._last_updated = datetime.now()
        logger.debug(f"Updated user name: {name}")

    def add_preference(self, key: str, value: Any) -> None:
        """Add or update a user preference.

        Args:
            key: Preference key
            value: Preference value
        """
        self.preferences[key] = value
        self._last_updated = datetime.now()
        logger.debug(f"Updated user preference: {key}={value}")

    def add_fact(self, fact: str) -> None:
        """Add a fact about the user.

        Args:
            fact: Fact to add (deduplicated)
        """
        if fact not in self.facts:
            self.facts.append(fact)
            self._last_updated = datetime.now()
            logger.debug(f"Added user fact: {fact}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of user profile
        """
        return {
            "name": self.name,
            "preferences": self.preferences,
            "context": self.context,
            "facts": self.facts,
            "last_updated": self._last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        """Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored UserProfile instance
        """
        profile = cls(
            name=data.get("name"),
            preferences=data.get("preferences", {}),
            context=data.get("context", {}),
            facts=data.get("facts", []),
        )
        if "last_updated" in data:
            profile._last_updated = datetime.fromisoformat(data["last_updated"])
        return profile

    @property
    def last_updated(self) -> datetime:
        """Get last update timestamp."""
        return self._last_updated


class KnowledgeBase:
    """Stores facts and insights learned during the session.

    The knowledge base maintains a structured collection of facts extracted
    from conversation, tool results, and reasoning processes. Facts can be
    tagged, sourced, and timestamped for tracking.

    Attributes:
        facts: List of fact dictionaries with metadata
    """

    def __init__(self, facts: Optional[list[dict[str, Any]]] = None):
        """Initialize knowledge base.

        Args:
            facts: Initial facts list
        """
        self.facts = facts or []
        self._last_updated = datetime.now()

    def add_fact(
        self,
        content: str,
        source: str = "conversation",
        tags: Optional[list[str]] = None,
        confidence: float = 1.0,
    ) -> None:
        """Add a fact to the knowledge base.

        Args:
            content: The fact content
            source: Source of the fact (conversation, tool, research, etc.)
            tags: Optional tags for categorization
            confidence: Confidence score (0.0-1.0)
        """
        fact = {
            "content": content,
            "source": source,
            "tags": tags or [],
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
        }

        # Deduplicate by content
        if not any(f["content"] == content for f in self.facts):
            self.facts.append(fact)
            self._last_updated = datetime.now()
            logger.debug(f"Added fact: {content} (source={source})")

    def get_facts_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """Get all facts with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of matching facts
        """
        return [f for f in self.facts if tag in f.get("tags", [])]

    def get_facts_by_source(self, source: str) -> list[dict[str, Any]]:
        """Get all facts from a specific source.

        Args:
            source: Source to filter by

        Returns:
            List of matching facts
        """
        return [f for f in self.facts if f.get("source") == source]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of knowledge base
        """
        return {
            "facts": self.facts,
            "last_updated": self._last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeBase":
        """Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored KnowledgeBase instance
        """
        kb = cls(facts=data.get("facts", []))
        if "last_updated" in data:
            kb._last_updated = datetime.fromisoformat(data["last_updated"])
        return kb

    @property
    def last_updated(self) -> datetime:
        """Get last update timestamp."""
        return self._last_updated

    def __len__(self) -> int:
        """Return number of facts."""
        return len(self.facts)


class InteractionContext:
    """Manages current conversation context and intent.

    Tracks the current state of the conversation, including the last few
    exchanges, current topic, and user intent. This enables context-aware
    responses.

    Attributes:
        current_topic: Current conversation topic (if identifiable)
        last_user_intent: Last detected user intent
        recent_exchanges: Recent conversation exchanges for context
    """

    def __init__(
        self,
        current_topic: Optional[str] = None,
        last_user_intent: Optional[str] = None,
        recent_exchanges: Optional[list[dict[str, str]]] = None,
    ):
        """Initialize interaction context.

        Args:
            current_topic: Current topic of conversation
            last_user_intent: Last detected user intent
            recent_exchanges: Recent conversation exchanges
        """
        self.current_topic = current_topic
        self.last_user_intent = last_user_intent
        self.recent_exchanges = recent_exchanges or []
        self._last_updated = datetime.now()

    def add_exchange(self, user_message: str, assistant_response: str) -> None:
        """Add a conversation exchange to recent context.

        Keeps a sliding window of recent exchanges (e.g., last 5).

        Args:
            user_message: User's message
            assistant_response: Assistant's response
        """
        exchange = {
            "user": user_message,
            "assistant": assistant_response,
            "timestamp": datetime.now().isoformat(),
        }
        self.recent_exchanges.append(exchange)

        # Keep only last 5 exchanges
        if len(self.recent_exchanges) > 5:
            self.recent_exchanges = self.recent_exchanges[-5:]

        self._last_updated = datetime.now()

    def update_topic(self, topic: str) -> None:
        """Update current conversation topic.

        Args:
            topic: New topic
        """
        self.current_topic = topic
        self._last_updated = datetime.now()
        logger.debug(f"Updated conversation topic: {topic}")

    def update_intent(self, intent: str) -> None:
        """Update last user intent.

        Args:
            intent: Detected user intent
        """
        self.last_user_intent = intent
        self._last_updated = datetime.now()
        logger.debug(f"Updated user intent: {intent}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of interaction context
        """
        return {
            "current_topic": self.current_topic,
            "last_user_intent": self.last_user_intent,
            "recent_exchanges": self.recent_exchanges,
            "last_updated": self._last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InteractionContext":
        """Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored InteractionContext instance
        """
        context = cls(
            current_topic=data.get("current_topic"),
            last_user_intent=data.get("last_user_intent"),
            recent_exchanges=data.get("recent_exchanges", []),
        )
        if "last_updated" in data:
            context._last_updated = datetime.fromisoformat(data["last_updated"])
        return context

    @property
    def last_updated(self) -> datetime:
        """Get last update timestamp."""
        return self._last_updated


class SessionStateMetadata:
    """Session-level statistics and metadata.

    Tracks session performance metrics, costs, and other statistics.
    Separate from Session.metadata which is more focused on session identity.

    Attributes:
        total_tokens_used: Total tokens used in session
        total_cost: Total cost in USD
        tool_call_count: Number of tool calls made
        reasoning_task_count: Number of reasoning tasks completed
    """

    def __init__(
        self,
        total_tokens_used: int = 0,
        total_cost: float = 0.0,
        tool_call_count: int = 0,
        reasoning_task_count: int = 0,
        custom_metrics: Optional[dict[str, Any]] = None,
    ):
        """Initialize session state metadata.

        Args:
            total_tokens_used: Total tokens used
            total_cost: Total cost in USD
            tool_call_count: Number of tool calls
            reasoning_task_count: Number of reasoning tasks
            custom_metrics: Additional custom metrics
        """
        self.total_tokens_used = total_tokens_used
        self.total_cost = total_cost
        self.tool_call_count = tool_call_count
        self.reasoning_task_count = reasoning_task_count
        self.custom_metrics = custom_metrics or {}
        self._created_at = datetime.now()
        self._last_updated = datetime.now()

    def record_tool_call(self, tokens: int = 0, cost: float = 0.0) -> None:
        """Record a tool call.

        Args:
            tokens: Tokens used by this tool call
            cost: Cost of this tool call
        """
        self.tool_call_count += 1
        self.total_tokens_used += tokens
        self.total_cost += cost
        self._last_updated = datetime.now()

    def record_reasoning_task(self, tokens: int = 0, cost: float = 0.0) -> None:
        """Record a reasoning task completion.

        Args:
            tokens: Tokens used by this reasoning task
            cost: Cost of this reasoning task
        """
        self.reasoning_task_count += 1
        self.total_tokens_used += tokens
        self.total_cost += cost
        self._last_updated = datetime.now()

    def add_custom_metric(self, key: str, value: Any) -> None:
        """Add or update a custom metric.

        Args:
            key: Metric key
            value: Metric value
        """
        self.custom_metrics[key] = value
        self._last_updated = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of metadata
        """
        return {
            "total_tokens_used": self.total_tokens_used,
            "total_cost": self.total_cost,
            "tool_call_count": self.tool_call_count,
            "reasoning_task_count": self.reasoning_task_count,
            "custom_metrics": self.custom_metrics,
            "created_at": self._created_at.isoformat(),
            "last_updated": self._last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionStateMetadata":
        """Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored SessionStateMetadata instance
        """
        metadata = cls(
            total_tokens_used=data.get("total_tokens_used", 0),
            total_cost=data.get("total_cost", 0.0),
            tool_call_count=data.get("tool_call_count", 0),
            reasoning_task_count=data.get("reasoning_task_count", 0),
            custom_metrics=data.get("custom_metrics", {}),
        )
        if "created_at" in data:
            metadata._created_at = datetime.fromisoformat(data["created_at"])
        if "last_updated" in data:
            metadata._last_updated = datetime.fromisoformat(data["last_updated"])
        return metadata

    @property
    def created_at(self) -> datetime:
        """Get creation timestamp."""
        return self._created_at

    @property
    def last_updated(self) -> datetime:
        """Get last update timestamp."""
        return self._last_updated


class SessionState:
    """Top-level session state container.

    SessionState is the comprehensive state management layer that transforms
    a session from a flat message sequence into a semantic, queryable
    knowledge structure.

    Components:
    - conversation: Message history (reuses existing Conversation class)
    - user_profile: Extracted user information
    - knowledge_base: Facts learned during session
    - interaction_context: Current conversation context
    - metadata: Session statistics and metrics

    Future components (later phases):
    - research_history: Completed reasoning tasks (ResearchProgressTracker)

    This class follows the same serialization pattern as Conversation for
    consistency and compatibility with StateProvider.
    """

    def __init__(
        self,
        session_id: str,
        conversation: Conversation,
        user_profile: Optional[UserProfile] = None,
        knowledge_base: Optional[KnowledgeBase] = None,
        interaction_context: Optional[InteractionContext] = None,
        metadata: Optional[SessionStateMetadata] = None,
        state_provider: Optional[StateProvider] = None,
    ):
        """Initialize session state.

        Args:
            session_id: Unique session identifier
            conversation: Conversation instance (manages messages)
            user_profile: User profile (created if None)
            knowledge_base: Knowledge base (created if None)
            interaction_context: Interaction context (created if None)
            metadata: Session state metadata (created if None)
            state_provider: Optional StateProvider for persistence
        """
        self.session_id = session_id
        self.conversation = conversation
        self.user_profile = user_profile or UserProfile()
        self.knowledge_base = knowledge_base or KnowledgeBase()
        self.interaction_context = interaction_context or InteractionContext()
        self.metadata = metadata or SessionStateMetadata()
        self.state_provider = state_provider

        self._created_at = datetime.now()
        self._last_modified_at = datetime.now()

        logger.debug(f"SessionState initialized: session_id={session_id}")

    async def save(self) -> None:
        """Save session state to storage using StateProvider.

        Persists all components to the configured StateProvider.
        No-op if no StateProvider is configured.
        """
        if self.state_provider is None:
            logger.debug(f"No StateProvider configured for session {self.session_id}")
            return

        state_key = f"session_state:{self.session_id}"
        try:
            data = self.to_dict()
            await self.state_provider.save(state_key, data)
            logger.info(f"SessionState saved: {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to save SessionState {self.session_id}: {e}", exc_info=True)

    def get_context_for_prompt(
        self,
        include_user_profile: bool = True,
        include_knowledge: bool = True,
        include_interaction: bool = True,
        max_exchanges: int = 5,
        max_facts: int = 10,
    ) -> str:
        """Generate context summary for prompt injection.

        Phase 4: Basic context generation
        Phase 5+: Relevance filtering and token optimization

        Args:
            include_user_profile: Include user profile information
            include_knowledge: Include knowledge base facts
            include_interaction: Include interaction context
            max_exchanges: Maximum number of recent exchanges to include
            max_facts: Maximum number of facts to include

        Returns:
            Formatted context string ready for prompt injection
        """
        sections = []

        # User Profile Section
        if include_user_profile and (
            self.user_profile.name
            or self.user_profile.preferences
            or self.user_profile.facts
        ):
            profile_parts = []

            if self.user_profile.name:
                profile_parts.append(f"Name: {self.user_profile.name}")

            if self.user_profile.preferences:
                prefs = ", ".join(
                    f"{k}: {v}" for k, v in self.user_profile.preferences.items()
                )
                profile_parts.append(f"Preferences: {prefs}")

            if self.user_profile.facts:
                facts_str = "; ".join(self.user_profile.facts[:5])  # Limit to 5 facts
                profile_parts.append(f"About user: {facts_str}")

            if profile_parts:
                sections.append(
                    "## User Profile\n" + "\n".join(profile_parts)
                )

        # Knowledge Base Section
        if include_knowledge and self.knowledge_base.facts:
            # Get recent facts (limited by max_facts)
            recent_facts = self.knowledge_base.facts[-max_facts:]
            if recent_facts:
                facts_list = []
                for fact in recent_facts:
                    source = fact.get("source", "unknown")
                    content = fact.get("content", "")
                    confidence = fact.get("confidence", 1.0)
                    facts_list.append(
                        f"- {content} (source: {source}, confidence: {confidence:.2f})"
                    )

                sections.append(
                    "## Known Facts\n" + "\n".join(facts_list)
                )

        # Interaction Context Section
        if include_interaction:
            context_parts = []

            if self.interaction_context.current_topic:
                context_parts.append(f"Current topic: {self.interaction_context.current_topic}")

            if self.interaction_context.current_intent:
                context_parts.append(f"User intent: {self.interaction_context.current_intent}")

            # Include recent exchanges summary
            if self.interaction_context.exchanges:
                recent_exchanges = self.interaction_context.exchanges[-max_exchanges:]
                if recent_exchanges:
                    exchanges_summary = []
                    for i, exchange in enumerate(recent_exchanges, 1):
                        user_preview = exchange["user_message"][:100]
                        if len(exchange["user_message"]) > 100:
                            user_preview += "..."
                        exchanges_summary.append(
                            f"{i}. User asked about: {user_preview}"
                        )

                    context_parts.append(
                        f"Recent conversation ({len(recent_exchanges)} exchanges):\n"
                        + "\n".join(exchanges_summary)
                    )

            if context_parts:
                sections.append(
                    "## Conversation Context\n" + "\n".join(context_parts)
                )

        # Combine all sections
        if sections:
            return "\n\n".join(sections)
        else:
            return ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize session state to dictionary.

        Returns:
            Dictionary containing all session state:
            - session_id: Session identifier
            - conversation: Conversation state (from Conversation.to_dict())
            - user_profile: User profile state
            - knowledge_base: Knowledge base state
            - interaction_context: Interaction context state
            - metadata: Session state metadata
            - created_at: Creation timestamp (ISO format)
            - last_modified_at: Last modification timestamp (ISO format)
        """
        self._last_modified_at = datetime.now()

        return {
            "session_id": self.session_id,
            "conversation": self.conversation.to_dict(),
            "user_profile": self.user_profile.to_dict(),
            "knowledge_base": self.knowledge_base.to_dict(),
            "interaction_context": self.interaction_context.to_dict(),
            "metadata": self.metadata.to_dict(),
            "created_at": self._created_at.isoformat(),
            "last_modified_at": self._last_modified_at.isoformat(),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        state_provider: Optional[StateProvider] = None,
    ) -> "SessionState":
        """Deserialize session state from dictionary.

        Args:
            data: Dictionary from to_dict()
            state_provider: Optional StateProvider for persistence

        Returns:
            Restored SessionState instance with all components
        """
        # Restore conversation
        conversation = Conversation.from_dict(data["conversation"])

        # Restore components
        user_profile = UserProfile.from_dict(data.get("user_profile", {}))
        knowledge_base = KnowledgeBase.from_dict(data.get("knowledge_base", {}))
        interaction_context = InteractionContext.from_dict(
            data.get("interaction_context", {})
        )
        metadata = SessionStateMetadata.from_dict(data.get("metadata", {}))

        # Create SessionState
        session_state = cls(
            session_id=data["session_id"],
            conversation=conversation,
            user_profile=user_profile,
            knowledge_base=knowledge_base,
            interaction_context=interaction_context,
            metadata=metadata,
            state_provider=state_provider,
        )

        # Restore timestamps
        if "created_at" in data:
            session_state._created_at = datetime.fromisoformat(data["created_at"])
        if "last_modified_at" in data:
            session_state._last_modified_at = datetime.fromisoformat(
                data["last_modified_at"]
            )

        logger.info(
            f"SessionState restored: {session_state.session_id}, "
            f"{len(session_state.knowledge_base)} facts, "
            f"{session_state.conversation.get_message_count()} messages"
        )

        return session_state

    @property
    def created_at(self) -> datetime:
        """Get session state creation timestamp."""
        return self._created_at

    @property
    def last_modified_at(self) -> datetime:
        """Get last modification timestamp."""
        return self._last_modified_at

    def get_context_summary(self) -> str:
        """Get a summary of current session context.

        Returns a formatted string summarizing the session state for
        potential injection into prompts (Phase 4).

        Returns:
            Context summary string
        """
        parts = []

        # User profile
        if self.user_profile.name:
            parts.append(f"User: {self.user_profile.name}")
        if self.user_profile.facts:
            parts.append(f"User facts: {', '.join(self.user_profile.facts[:3])}")

        # Knowledge base
        if len(self.knowledge_base) > 0:
            parts.append(f"Known facts: {len(self.knowledge_base)}")

        # Interaction context
        if self.interaction_context.current_topic:
            parts.append(f"Topic: {self.interaction_context.current_topic}")

        # Metadata
        parts.append(
            f"Session: {self.metadata.tool_call_count} tool calls, "
            f"{self.metadata.reasoning_task_count} reasoning tasks"
        )

        return " | ".join(parts) if parts else "New session"
