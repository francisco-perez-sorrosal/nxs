"""Session state management for semantic knowledge tracking.

This module provides the SessionState system that transforms sessions from
simple message containers into semantic knowledge bases. The system maintains
structured representations of conversations including user profiles, learned
facts, interaction context, and research history.

Key Components:
- SessionState: Top-level semantic state container
- UserProfile: Extracted information about the user
- KnowledgeBase: Facts and insights learned during the session
- InteractionContext: Current conversation flow and intent
- StateMetadata: Session statistics and usage tracking

Architecture:
    SessionState maintains rich semantic information beyond message history,
    enabling context-aware, personalized interactions through:
    - Automatic fact extraction
    - User preference tracking
    - Cross-query learning
    - Research continuity

Example:
    >>> state = SessionState(session_id="abc123")
    >>> state.user_profile.update_from_dict({"name": "Alice"})
    >>> state.knowledge_base.add_fact("API rate limit: 1000/hr", source="conversation")
    >>>
    >>> # Later query can reference this
    >>> context = state.get_context_for_prompt("Call the API")
    >>> # Context includes user name and API rate limit fact
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from nxs.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    "SessionState",
    "UserProfile",
    "Fact",
    "KnowledgeBase",
    "Intent",
    "InteractionContext",
    "StateMetadata",
]


# ============================================================================
# User Profile
# ============================================================================


@dataclass
class UserProfile:
    """Profile information about the user extracted from conversations.

    Captures WHO the user is, not WHAT they're asking about. This enables
    personalized, context-aware interactions by maintaining structured
    information about the user across the session.

    Attributes:
        name: User's name
        age: User's age
        location: User's location
        occupation: User's occupation
        expertise_level: Technical expertise ("beginner", "intermediate", "expert")
        programming_languages: Languages the user knows
        frameworks: Frameworks the user uses
        interests: User's interests and preferences
        communication_style: Preferred style ("concise", "detailed", "technical")
        current_project: Active project context
        project_tech_stack: Technologies in current project
        confidence_scores: Confidence levels for each extracted field
        last_updated: Timestamp of last update

    Example:
        >>> profile = UserProfile()
        >>> profile.update_from_dict({"name": "Alice", "expertise_level": "expert"})
        >>> print(profile.to_context_text())
        User's name: Alice
        Technical expertise: expert
    """

    # Identity
    name: Optional[str] = None
    age: Optional[int] = None
    location: Optional[str] = None
    occupation: Optional[str] = None

    # Technical context
    expertise_level: Optional[str] = None  # "beginner", "intermediate", "expert"
    programming_languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)

    # Preferences
    interests: list[str] = field(default_factory=list)
    communication_style: Optional[str] = None  # "concise", "detailed", "technical"

    # Project context
    current_project: Optional[str] = None
    project_tech_stack: list[str] = field(default_factory=list)

    # Meta
    confidence_scores: dict[str, float] = field(default_factory=dict)
    last_updated: Optional[datetime] = None

    def has_information(self) -> bool:
        """Check if profile has any meaningful information.

        Returns:
            True if any profile field is populated, False otherwise.

        Example:
            >>> profile = UserProfile()
            >>> profile.has_information()
            False
            >>> profile.name = "Alice"
            >>> profile.has_information()
            True
        """
        return any(
            [
                self.name,
                self.age,
                self.occupation,
                self.interests,
                self.programming_languages,
                self.current_project,
            ]
        )

    def update_from_dict(self, data: dict[str, Any]) -> None:
        """Update profile from extracted data.

        Merges new information with existing profile. For list fields,
        appends new items (deduplicates). For scalar fields, overwrites
        with new value.

        Args:
            data: Dictionary of profile fields to update

        Example:
            >>> profile = UserProfile()
            >>> profile.update_from_dict({"name": "Alice"})
            >>> profile.update_from_dict({"programming_languages": ["Python"]})
            >>> profile.name
            'Alice'
            >>> profile.programming_languages
            ['Python']
        """
        for key, value in data.items():
            if hasattr(self, key) and value:
                # Update field
                current = getattr(self, key)

                if isinstance(current, list):
                    # Append to list (deduplicate)
                    if isinstance(value, list):
                        for item in value:
                            if item not in current:
                                current.append(item)
                    elif value not in current:
                        current.append(value)
                else:
                    # Overwrite scalar
                    setattr(self, key, value)

                # Track confidence
                self.confidence_scores[key] = 0.8  # Default confidence

        self.last_updated = datetime.now()
        logger.debug(f"Updated user profile: {len(data)} fields")

    def to_context_text(self) -> str:
        """Convert profile to natural language context.

        Generates a human-readable summary of the user profile for
        injection into LLM prompts.

        Returns:
            Natural language description of user profile, or empty string
            if profile is empty.

        Example:
            >>> profile = UserProfile(name="Alice", expertise_level="expert")
            >>> profile.programming_languages = ["Python", "Rust"]
            >>> print(profile.to_context_text())
            User's name: Alice
            Technical expertise: expert
            Familiar with: Python, Rust
        """
        parts = []

        if self.name:
            parts.append(f"User's name: {self.name}")

        if self.occupation:
            parts.append(f"Occupation: {self.occupation}")

        if self.expertise_level:
            parts.append(f"Technical expertise: {self.expertise_level}")

        if self.programming_languages:
            parts.append(f"Familiar with: {', '.join(self.programming_languages)}")

        if self.interests:
            parts.append(f"Interests: {', '.join(self.interests)}")

        if self.current_project:
            parts.append(f"Current project: {self.current_project}")
            if self.project_tech_stack:
                parts.append(f"Project stack: {', '.join(self.project_tech_stack)}")

        if self.communication_style:
            parts.append(f"Prefers {self.communication_style} communication")

        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of profile for persistence.
        """
        return {
            "name": self.name,
            "age": self.age,
            "location": self.location,
            "occupation": self.occupation,
            "expertise_level": self.expertise_level,
            "programming_languages": self.programming_languages,
            "frameworks": self.frameworks,
            "interests": self.interests,
            "communication_style": self.communication_style,
            "current_project": self.current_project,
            "project_tech_stack": self.project_tech_stack,
            "confidence_scores": self.confidence_scores,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        """Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored UserProfile instance.
        """
        profile = cls(
            name=data.get("name"),
            age=data.get("age"),
            location=data.get("location"),
            occupation=data.get("occupation"),
            expertise_level=data.get("expertise_level"),
            programming_languages=data.get("programming_languages", []),
            frameworks=data.get("frameworks", []),
            interests=data.get("interests", []),
            communication_style=data.get("communication_style"),
            current_project=data.get("current_project"),
            project_tech_stack=data.get("project_tech_stack", []),
            confidence_scores=data.get("confidence_scores", {}),
        )

        if data.get("last_updated"):
            profile.last_updated = datetime.fromisoformat(data["last_updated"])

        return profile


# ============================================================================
# Knowledge Base
# ============================================================================


@dataclass
class Fact:
    """A single factual statement learned during the session.

    Facts are the atomic units of the knowledge base, representing discrete
    pieces of information extracted from conversations, research, or tool
    executions.

    Attributes:
        content: The factual statement text
        source: Source type ("conversation", "research", "tool", "file")
        confidence: Confidence level (0.0 to 1.0)
        timestamp: When the fact was recorded
        research_id: Optional link to research task
        message_index: Optional link to conversation message
        tags: Categorization tags
        references: Related file paths, URLs, etc.

    Example:
        >>> fact = Fact(
        ...     content="API rate limit is 1000 requests/hour",
        ...     source="conversation",
        ...     confidence=0.9,
        ...     timestamp=datetime.now()
        ... )
    """

    content: str
    source: str  # "conversation", "research", "tool", "file"
    confidence: float  # 0.0 to 1.0
    timestamp: datetime

    # Context
    research_id: Optional[str] = None
    message_index: Optional[int] = None

    # Metadata
    tags: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)  # File paths, URLs, etc.

    def __hash__(self) -> int:
        """Hash based on content for deduplication."""
        return hash(self.content)


class KnowledgeBase:
    """Repository of facts and insights learned during the session.

    The knowledge base stores structured factual information extracted from
    conversations, research tasks, and tool executions. It enables efficient
    fact retrieval, semantic search, and deduplication.

    Features:
    - Fact deduplication based on content similarity
    - Confidence tracking and updating
    - Source-based querying
    - Recency-based retrieval
    - Relevance-based search

    Example:
        >>> kb = KnowledgeBase()
        >>> kb.add_fact("Python uses GIL", source="conversation", confidence=0.9)
        >>> kb.add_fact("API rate limit: 1000/hr", source="tool")
        >>>
        >>> # Search for relevant facts
        >>> facts = kb.get_relevant_facts("API limits", limit=5)
        >>> for fact in facts:
        ...     print(fact.content)
    """

    def __init__(self) -> None:
        """Initialize an empty knowledge base."""
        self.facts: list[Fact] = []
        self._fact_index: dict[int, Fact] = {}  # Hash → Fact

        logger.debug("KnowledgeBase initialized")

    def add_fact(
        self,
        content: str,
        source: str,
        confidence: float = 0.8,
        **kwargs: Any,
    ) -> None:
        """Add a new fact to the knowledge base.

        If a similar fact already exists, updates its confidence if the new
        confidence is higher.

        Args:
            content: The factual statement
            source: Source type ("conversation", "research", "tool", "file")
            confidence: Confidence level (0.0 to 1.0, default 0.8)
            **kwargs: Additional fact attributes (research_id, tags, etc.)

        Example:
            >>> kb = KnowledgeBase()
            >>> kb.add_fact(
            ...     "Server runs on port 8080",
            ...     source="tool",
            ...     confidence=0.95,
            ...     tags=["config"]
            ... )
        """
        fact = Fact(
            content=content,
            source=source,
            confidence=confidence,
            timestamp=datetime.now(),
            **kwargs,
        )

        # Deduplicate based on content similarity
        existing = self._find_similar_fact(content)
        if existing:
            # Update existing fact with higher confidence
            if confidence > existing.confidence:
                existing.confidence = confidence
                existing.timestamp = datetime.now()
                logger.debug(f"Updated existing fact with higher confidence: {content[:50]}...")
        else:
            # Add new fact
            self.facts.append(fact)
            self._fact_index[hash(content)] = fact
            logger.debug(f"Added new fact: {content[:50]}... (source={source}, confidence={confidence})")

    def _find_similar_fact(self, content: str) -> Optional[Fact]:
        """Find similar existing fact (simple string matching for now).

        Args:
            content: Fact content to search for

        Returns:
            Existing Fact if found, None otherwise

        Note:
            Currently uses exact case-insensitive matching. Future enhancement
            could use semantic similarity (embeddings).
        """
        content_lower = content.lower()
        for fact in self.facts:
            if fact.content.lower() == content_lower:
                return fact
        return None

    def get_relevant_facts(
        self,
        query: str,
        limit: int = 10,
        min_confidence: float = 0.5,
    ) -> list[Fact]:
        """Retrieve facts relevant to a query.

        Uses simple keyword matching for relevance scoring. Facts are ranked
        by the number of overlapping terms with the query.

        Args:
            query: Search query
            limit: Maximum number of facts to return
            min_confidence: Minimum confidence threshold

        Returns:
            List of relevant facts, sorted by relevance score

        Example:
            >>> kb = KnowledgeBase()
            >>> kb.add_fact("API rate limit: 1000/hr", "tool", 0.9)
            >>> kb.add_fact("Database timeout: 30s", "config", 0.8)
            >>> facts = kb.get_relevant_facts("API limits", limit=5)

        Note:
            Future enhancement: Use vector embeddings for semantic similarity.
        """
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        scored_facts: list[tuple[float, Fact]] = []
        for fact in self.facts:
            if fact.confidence < min_confidence:
                continue

            fact_terms = set(fact.content.lower().split())
            overlap = len(query_terms & fact_terms)

            if overlap > 0:
                score = overlap / len(query_terms)
                scored_facts.append((score, fact))

        # Sort by score descending
        scored_facts.sort(key=lambda x: x[0], reverse=True)

        return [fact for _, fact in scored_facts[:limit]]

    def search(self, query: str, limit: int = 5) -> list[Fact]:
        """Search facts (alias for get_relevant_facts).

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of relevant facts
        """
        return self.get_relevant_facts(query, limit=limit)

    def get_facts_by_source(self, source: str) -> list[Fact]:
        """Get all facts from a specific source.

        Args:
            source: Source type to filter by

        Returns:
            List of facts from the specified source

        Example:
            >>> kb = KnowledgeBase()
            >>> research_facts = kb.get_facts_by_source("research")
        """
        return [f for f in self.facts if f.source == source]

    def get_recent_facts(self, limit: int = 10) -> list[Fact]:
        """Get most recent facts.

        Args:
            limit: Maximum number of facts to return

        Returns:
            List of most recent facts, sorted by timestamp descending

        Example:
            >>> kb = KnowledgeBase()
            >>> recent = kb.get_recent_facts(limit=5)
        """
        sorted_facts = sorted(self.facts, key=lambda f: f.timestamp, reverse=True)
        return sorted_facts[:limit]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation for persistence.
        """
        return {
            "facts": [
                {
                    "content": f.content,
                    "source": f.source,
                    "confidence": f.confidence,
                    "timestamp": f.timestamp.isoformat(),
                    "research_id": f.research_id,
                    "message_index": f.message_index,
                    "tags": f.tags,
                    "references": f.references,
                }
                for f in self.facts
            ]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeBase":
        """Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored KnowledgeBase instance.
        """
        kb = cls()
        for fact_data in data.get("facts", []):
            fact = Fact(
                content=fact_data["content"],
                source=fact_data["source"],
                confidence=fact_data["confidence"],
                timestamp=datetime.fromisoformat(fact_data["timestamp"]),
                research_id=fact_data.get("research_id"),
                message_index=fact_data.get("message_index"),
                tags=fact_data.get("tags", []),
                references=fact_data.get("references", []),
            )
            kb.facts.append(fact)
            kb._fact_index[hash(fact.content)] = fact

        logger.debug(f"Restored KnowledgeBase: {len(kb.facts)} facts")
        return kb


# ============================================================================
# Interaction Context
# ============================================================================


@dataclass
class Intent:
    """User's intent in current interaction.

    Attributes:
        type: Intent type ("question", "command", "research", "chat", "clarification")
        confidence: Confidence level (0.0 to 1.0)
        details: Additional intent-specific details

    Example:
        >>> intent = Intent(type="question", confidence=0.9, details={"topic": "API"})
    """

    type: str  # "question", "command", "research", "chat", "clarification"
    confidence: float
    details: dict[str, Any] = field(default_factory=dict)


class InteractionContext:
    """Current context and flow of the interaction.

    Tracks the immediate conversational context including recent exchanges,
    current topic/intent, and conversation flow patterns. Maintains a sliding
    window of recent interactions for context-aware responses.

    Attributes:
        recent_exchanges: Last N exchanges (sliding window)
        current_topic: Current conversation topic
        current_intent: Current user intent
        question_count: Number of questions asked
        command_count: Number of commands executed
        research_count: Number of research tasks performed
        max_exchanges: Maximum exchanges to keep in window

    Example:
        >>> ctx = InteractionContext()
        >>> ctx.add_exchange("What is Python?", "Python is a programming language...")
        >>> ctx.update_intent(Intent(type="question", confidence=0.9))
        >>> print(ctx.get_summary())
    """

    def __init__(self) -> None:
        """Initialize interaction context with empty state."""
        self.recent_exchanges: list[dict[str, str]] = []
        self.current_topic: Optional[str] = None
        self.current_intent: Optional[Intent] = None

        # Flow tracking
        self.question_count: int = 0
        self.command_count: int = 0
        self.research_count: int = 0

        # Context window
        self.max_exchanges: int = 5  # Keep last 5 exchanges

        logger.debug("InteractionContext initialized")

    def add_exchange(self, user_msg: str, assistant_msg: str) -> None:
        """Add an exchange to recent history.

        Maintains a sliding window of recent exchanges, automatically removing
        oldest exchanges when the window is full.

        Args:
            user_msg: User's message
            assistant_msg: Assistant's response

        Example:
            >>> ctx = InteractionContext()
            >>> ctx.add_exchange("Hello", "Hi there!")
            >>> len(ctx.recent_exchanges)
            1
        """
        exchange = {
            "user": user_msg,
            "assistant": assistant_msg,
            "timestamp": datetime.now().isoformat(),
        }

        self.recent_exchanges.append(exchange)

        # Keep only last N exchanges
        if len(self.recent_exchanges) > self.max_exchanges:
            self.recent_exchanges.pop(0)

        logger.debug(f"Added exchange to context (window size: {len(self.recent_exchanges)})")

    def update_intent(self, intent: Intent) -> None:
        """Update current intent.

        Args:
            intent: New intent to set

        Example:
            >>> ctx = InteractionContext()
            >>> ctx.update_intent(Intent(type="question", confidence=0.9))
            >>> ctx.question_count
            1
        """
        self.current_intent = intent

        # Update counts
        if intent.type == "question":
            self.question_count += 1
        elif intent.type == "command":
            self.command_count += 1
        elif intent.type == "research":
            self.research_count += 1

        logger.debug(f"Updated intent: {intent.type} (confidence={intent.confidence})")

    def get_summary(self) -> str:
        """Get context summary.

        Returns:
            Natural language summary of current context.

        Example:
            >>> ctx = InteractionContext()
            >>> ctx.current_topic = "Python programming"
            >>> ctx.update_intent(Intent(type="question", confidence=0.9))
            >>> print(ctx.get_summary())
            Current topic: Python programming
            User intent: question
            Recent exchanges: 0
        """
        parts = []

        if self.current_topic:
            parts.append(f"Current topic: {self.current_topic}")

        if self.current_intent:
            parts.append(f"User intent: {self.current_intent.type}")

        if self.recent_exchanges:
            parts.append(f"Recent exchanges: {len(self.recent_exchanges)}")

        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation for persistence.
        """
        return {
            "recent_exchanges": self.recent_exchanges,
            "current_topic": self.current_topic,
            "current_intent": {
                "type": self.current_intent.type,
                "confidence": self.current_intent.confidence,
                "details": self.current_intent.details,
            }
            if self.current_intent
            else None,
            "question_count": self.question_count,
            "command_count": self.command_count,
            "research_count": self.research_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InteractionContext":
        """Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored InteractionContext instance.
        """
        ctx = cls()
        ctx.recent_exchanges = data.get("recent_exchanges", [])
        ctx.current_topic = data.get("current_topic")

        if data.get("current_intent"):
            intent_data = data["current_intent"]
            ctx.current_intent = Intent(
                type=intent_data["type"],
                confidence=intent_data["confidence"],
                details=intent_data.get("details", {}),
            )

        ctx.question_count = data.get("question_count", 0)
        ctx.command_count = data.get("command_count", 0)
        ctx.research_count = data.get("research_count", 0)

        logger.debug(
            f"Restored InteractionContext: {len(ctx.recent_exchanges)} exchanges, "
            f"{ctx.question_count} questions"
        )
        return ctx


# ============================================================================
# State Metadata (Statistics)
# ============================================================================


class StateMetadata:
    """Session statistics and usage tracking.

    Tracks performance metrics, costs, and usage patterns for the session.
    Provides detailed statistics beyond basic cost tracking.

    Note:
        This complements the existing CostTracker system by providing
        additional metadata and statistics.

    Attributes:
        message_count: Total messages in session
        tool_call_count: Total tool executions
        research_task_count: Total research tasks
        total_input_tokens: Total input tokens used
        total_output_tokens: Total output tokens used
        total_cache_creation_tokens: Cache creation tokens
        total_cache_read_tokens: Cache read tokens
        total_cost: Total cost in USD
        cost_breakdown: Detailed cost breakdown
        tool_usage: Tool usage counts
        tool_success_rate: Tool success rates
        session_duration: Session duration in seconds
        average_response_time: Average response time in seconds

    Example:
        >>> metadata = StateMetadata()
        >>> metadata.record_interaction({"usage": {"input_tokens": 100}})
        >>> metadata.total_input_tokens
        100
    """

    def __init__(self) -> None:
        """Initialize state metadata with zero values."""
        # Interaction counts
        self.message_count: int = 0
        self.tool_call_count: int = 0
        self.research_task_count: int = 0

        # Token usage
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cache_creation_tokens: int = 0
        self.total_cache_read_tokens: int = 0

        # Costs (USD)
        self.total_cost: float = 0.0
        self.cost_breakdown: dict[str, float] = {
            "input": 0.0,
            "output": 0.0,
            "cache_creation": 0.0,
            "cache_read": 0.0,
        }

        # Tool usage
        self.tool_usage: dict[str, int] = {}  # tool_name → count
        self.tool_success_rate: dict[str, float] = {}  # tool_name → success rate

        # Timing
        self.session_duration: float = 0.0  # seconds
        self.average_response_time: float = 0.0  # seconds
        self._response_times: list[float] = []

        logger.debug("StateMetadata initialized")

    def record_interaction(self, metadata: dict[str, Any]) -> None:
        """Record metadata from an interaction.

        Args:
            metadata: Dictionary with usage and cost information

        Example:
            >>> meta = StateMetadata()
            >>> meta.record_interaction({
            ...     "usage": {"input_tokens": 100, "output_tokens": 50},
            ...     "cost": 0.001
            ... })
        """
        self.message_count += 1

        # Token usage
        if "usage" in metadata:
            usage = metadata["usage"]
            self.total_input_tokens += usage.get("input_tokens", 0)
            self.total_output_tokens += usage.get("output_tokens", 0)
            self.total_cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
            self.total_cache_read_tokens += usage.get("cache_read_input_tokens", 0)

        # Cost
        if "cost" in metadata:
            self.total_cost += metadata["cost"]
            if "cost_breakdown" in metadata:
                for key, value in metadata["cost_breakdown"].items():
                    self.cost_breakdown[key] = self.cost_breakdown.get(key, 0.0) + value

        # Response time
        if "response_time" in metadata:
            self._response_times.append(metadata["response_time"])
            self.average_response_time = sum(self._response_times) / len(self._response_times)

        logger.debug(f"Recorded interaction metadata (message #{self.message_count})")

    def record_tool_call(self, tool_name: str, success: bool, execution_time: float = 0) -> None:
        """Record a tool call.

        Args:
            tool_name: Name of the tool executed
            success: Whether execution succeeded
            execution_time: Execution time in seconds

        Example:
            >>> meta = StateMetadata()
            >>> meta.record_tool_call("search", success=True, execution_time=0.5)
            >>> meta.tool_usage["search"]
            1
        """
        self.tool_call_count += 1
        self.tool_usage[tool_name] = self.tool_usage.get(tool_name, 0) + 1

        # Update success rate
        if tool_name not in self.tool_success_rate:
            self.tool_success_rate[tool_name] = 1.0 if success else 0.0
        else:
            # Running average
            count = self.tool_usage[tool_name]
            current_rate = self.tool_success_rate[tool_name]
            new_rate = (current_rate * (count - 1) + (1.0 if success else 0.0)) / count
            self.tool_success_rate[tool_name] = new_rate

        logger.debug(f"Recorded tool call: {tool_name} (success={success})")

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics.

        Returns:
            Dictionary with key statistics.

        Example:
            >>> meta = StateMetadata()
            >>> summary = meta.get_summary()
            >>> summary["message_count"]
            0
        """
        return {
            "message_count": self.message_count,
            "tool_calls": self.tool_call_count,
            "research_tasks": self.research_task_count,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost_usd": round(self.total_cost, 4),
            "avg_response_time_sec": round(self.average_response_time, 2),
            "cache_efficiency": self._calculate_cache_efficiency(),
        }

    def _calculate_cache_efficiency(self) -> float:
        """Calculate cache hit rate.

        Returns:
            Cache efficiency ratio (0.0 to 1.0).
        """
        total_input = self.total_input_tokens + self.total_cache_read_tokens
        if total_input == 0:
            return 0.0
        return self.total_cache_read_tokens / total_input

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation for persistence.
        """
        return {
            "message_count": self.message_count,
            "tool_call_count": self.tool_call_count,
            "research_task_count": self.research_task_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_creation_tokens": self.total_cache_creation_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cost": self.total_cost,
            "cost_breakdown": self.cost_breakdown,
            "tool_usage": self.tool_usage,
            "tool_success_rate": self.tool_success_rate,
            "session_duration": self.session_duration,
            "average_response_time": self.average_response_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateMetadata":
        """Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored StateMetadata instance.
        """
        metadata = cls()
        for key, value in data.items():
            if hasattr(metadata, key) and key != "_response_times":
                setattr(metadata, key, value)

        logger.debug(f"Restored StateMetadata: {metadata.message_count} messages")
        return metadata


# ============================================================================
# Session State (Top Level)
# ============================================================================


class SessionState:
    """Top-level semantic state container for an agent session.

    SessionState maintains a rich, structured representation of the conversation
    that goes beyond message history. It extracts and stores semantic information,
    enabling context-aware, personalized interactions.

    This is the core of the semantic knowledge system, transforming sessions from
    simple message containers into queryable knowledge bases.

    Components:
    - UserProfile: Information about the user
    - KnowledgeBase: Facts learned during session
    - InteractionContext: Current conversation flow
    - StateMetadata: Session statistics
    - ResearchProgressTracker integration: Active research + history

    Lifecycle:
    1. Created at session start
    2. Updated incrementally after each interaction
    3. Persisted periodically and at session end
    4. Can be loaded to resume previous sessions

    Example:
        >>> state = SessionState(session_id="abc123")
        >>>
        >>> # Add user information
        >>> state.user_profile.update_from_dict({"name": "Alice"})
        >>>
        >>> # Add learned fact
        >>> state.knowledge_base.add_fact("API limit: 1000/hr", source="tool")
        >>>
        >>> # Get context for prompt
        >>> context = state.get_context_for_prompt("Call the API")
        >>> # Context includes user name and API rate limit
    """

    def __init__(self, session_id: str) -> None:
        """Initialize session state.

        Args:
            session_id: Unique session identifier

        Example:
            >>> state = SessionState(session_id="session-123")
        """
        # Identity
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_updated = datetime.now()

        # Core components
        self.user_profile = UserProfile()
        self.knowledge_base = KnowledgeBase()
        self.interaction_context = InteractionContext()
        self.state_metadata = StateMetadata()

        logger.info(f"SessionState initialized: {session_id}")

    def mark_updated(self) -> None:
        """Mark state as updated.

        Updates the last_updated timestamp.
        """
        self.last_updated = datetime.now()

    def get_context_for_prompt(
        self,
        query: str,
        mode: str = "auto",
    ) -> str:
        """Extract relevant context from state for LLM prompt.

        This is the key method that transforms SessionState into natural language
        context that gets injected into LLM prompts.

        Args:
            query: The current user query
            mode: Context verbosity ("minimal", "standard", "comprehensive")

        Returns:
            Natural language context string for prompt injection

        Example:
            >>> state = SessionState("session-1")
            >>> state.user_profile.name = "Alice"
            >>> state.knowledge_base.add_fact("API limit: 1000/hr", "tool")
            >>> context = state.get_context_for_prompt("Call the API")
            >>> print(context)
            # User Profile
            User's name: Alice
            <BLANKLINE>
            # Relevant Facts from Session
            - API limit: 1000/hr
        """
        sections = []

        # 1. User Profile Context (if relevant)
        if self.user_profile.has_information():
            profile_text = self.user_profile.to_context_text()
            if profile_text:
                sections.append(f"# User Profile\n{profile_text}\n")

        # 2. Relevant Facts from Knowledge Base
        relevant_facts = self.knowledge_base.get_relevant_facts(query, limit=10)
        if relevant_facts:
            sections.append("# Relevant Facts from Session\n")
            for fact in relevant_facts:
                sections.append(f"- {fact.content}")
            sections.append("")

        # 3. Interaction Context
        context_summary = self.interaction_context.get_summary()
        if context_summary:
            sections.append(f"# Current Context\n{context_summary}\n")

        return "\n".join(sections)

    def get_compact_context(self) -> str:
        """Get minimal context summary (for token efficiency).

        Returns:
            Compact one-line summary of session state.

        Example:
            >>> state = SessionState("session-1")
            >>> state.user_profile.name = "Alice"
            >>> state.knowledge_base.add_fact("Test fact", "test")
            >>> state.get_compact_context()
            'User: Alice | 1 facts learned'
        """
        parts = []

        if self.user_profile.name:
            parts.append(f"User: {self.user_profile.name}")

        fact_count = len(self.knowledge_base.facts)
        if fact_count > 0:
            parts.append(f"{fact_count} facts learned")

        return " | ".join(parts) if parts else "New session"

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary for persistence.

        Returns:
            Dictionary containing all state components.

        Example:
            >>> state = SessionState("session-1")
            >>> data = state.to_dict()
            >>> "session_id" in data
            True
        """
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "user_profile": self.user_profile.to_dict(),
            "knowledge_base": self.knowledge_base.to_dict(),
            "interaction_context": self.interaction_context.to_dict(),
            "state_metadata": self.state_metadata.to_dict(),
            # Phase 2: Add research tracking
            # "active_research": self.active_research.to_dict() if self.active_research else None,
            # "research_history": [r.to_dict() for r in self.research_history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        """Deserialize state from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored SessionState instance.

        Example:
            >>> data = {"session_id": "session-1", ...}
            >>> state = SessionState.from_dict(data)
            >>> state.session_id
            'session-1'
        """
        state = cls(session_id=data["session_id"])
        state.created_at = datetime.fromisoformat(data["created_at"])
        state.last_updated = datetime.fromisoformat(data["last_updated"])

        state.user_profile = UserProfile.from_dict(data.get("user_profile", {}))
        state.knowledge_base = KnowledgeBase.from_dict(data.get("knowledge_base", {}))
        state.interaction_context = InteractionContext.from_dict(
            data.get("interaction_context", {})
        )
        state.state_metadata = StateMetadata.from_dict(data.get("state_metadata", {}))

        logger.info(
            f"SessionState restored: {state.session_id}, "
            f"{len(state.knowledge_base.facts)} facts, "
            f"{state.interaction_context.question_count} questions"
        )

        return state
