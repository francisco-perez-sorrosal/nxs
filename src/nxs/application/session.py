"""Session management for conversation persistence.

This module provides Session and SessionMetadata classes for managing
conversation sessions with persistence support.

A Session encapsulates:
- Conversation (message history + cache control)
- AgentLoop (orchestration)
- Metadata (title, tags, timestamps)

Sessions can be:
- Serialized to JSON for persistence
- Restored from JSON
- Executed via run_query()
- Identified by unique session_id
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from nxs.application.agentic_loop import AgentLoop
from nxs.application.conversation import Conversation
from nxs.application.cost_tracker import CostTracker
from nxs.application.progress_tracker import ResearchProgressTracker
from nxs.logger import get_logger

logger = get_logger(__name__)


@runtime_checkable
class AgentProtocol(Protocol):
    """Protocol for agent types that can execute queries.
    
    Supports both AgentLoop and CommandControlAgent (with composition).
    """
    
    async def run(
        self,
        query: str,
        use_streaming: bool = True,
        callbacks: Optional[dict[str, Callable]] = None,
    ) -> str:
        """Execute a query and return the response."""
        ...
    
    conversation: Conversation  # Agent must have access to conversation


@dataclass
class SessionMetadata:
    """Metadata for a conversation session.

    Contains session identification, timestamps, and user-defined attributes.
    """

    session_id: str
    title: str = "New Conversation"
    created_at: datetime = field(default_factory=datetime.now)
    last_active_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)
    model: str = "claude-sonnet-4.5"
    description: Optional[str] = None
    conversation_summary: Optional[str] = None
    summary_last_message_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize metadata to dictionary.

        Returns:
            Dictionary with all metadata fields.
        """
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat(),
            "tags": self.tags,
            "model": self.model,
            "description": self.description,
            "conversation_summary": self.conversation_summary,
            "summary_last_message_index": self.summary_last_message_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMetadata":
        """Deserialize metadata from dictionary.

        Args:
            data: Dictionary from to_dict().

        Returns:
            Restored SessionMetadata instance.
        """
        return cls(
            session_id=data["session_id"],
            title=data.get("title", "New Conversation"),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_active_at=datetime.fromisoformat(data["last_active_at"]),
            tags=data.get("tags", []),
            model=data.get("model", "claude-sonnet-4.5"),
            description=data.get("description"),
            conversation_summary=data.get("conversation_summary"),
            summary_last_message_index=data.get("summary_last_message_index", 0),
        )


class Session:
    """Conversation session with persistence support.

    A Session combines:
    - Conversation: Message history and state
    - AgentLoop: Query execution and orchestration
    - SessionMetadata: Identification and attributes

    Sessions are the unit of persistence - they can be saved to JSON
    and restored later, allowing users to continue conversations across
    application restarts.

    Example:
        >>> metadata = SessionMetadata(session_id="session-1", title="My Chat")
        >>> conversation = Conversation(system_message="You are helpful")
        >>> agent_loop = AgentLoop(llm, conversation, tool_registry)
        >>>
        >>> session = Session(
        ...     metadata=metadata,
        ...     conversation=conversation,
        ...     agent_loop=agent_loop
        ... )
        >>>
        >>> # Run a query
        >>> result = await session.run_query("Hello!")
        >>>
        >>> # Persist session
        >>> session_data = session.to_dict()
        >>> json.dump(session_data, file)
    """

    def __init__(
        self,
        metadata: SessionMetadata,
        conversation: Conversation,
        agent_loop: AgentProtocol,
        conversation_cost_tracker: Optional[CostTracker] = None,
        reasoning_cost_tracker: Optional[CostTracker] = None,
        summarization_cost_tracker: Optional[CostTracker] = None,
        # Legacy support: if cost_tracker is provided, use it for conversation
        cost_tracker: Optional[CostTracker] = None,
        # Phase 6: Tracker persistence
        trackers: Optional[dict[str, ResearchProgressTracker]] = None,
    ):
        """Initialize a session.

        Args:
            metadata: Session metadata (ID, title, timestamps, etc.).
            conversation: Conversation instance with message history.
            agent_loop: Agent instance for query execution (AgentLoop or CommandControlAgent).
            conversation_cost_tracker: Optional cost tracker for conversation costs (created if None).
            reasoning_cost_tracker: Optional cost tracker for reasoning costs (created if None).
            summarization_cost_tracker: Optional cost tracker for summarization costs (created if None).
            cost_tracker: Legacy parameter - if provided, used for conversation_cost_tracker.
            trackers: Phase 6: Optional dict of query_id -> ResearchProgressTracker for persistence.
        """
        self.metadata = metadata
        self.conversation = conversation
        self.agent_loop = agent_loop
        
        # Support legacy cost_tracker parameter for backward compatibility
        if cost_tracker is not None:
            self.conversation_cost_tracker = cost_tracker
        else:
            self.conversation_cost_tracker = conversation_cost_tracker or CostTracker()
        
        self.reasoning_cost_tracker = reasoning_cost_tracker or CostTracker()
        self.summarization_cost_tracker = summarization_cost_tracker or CostTracker()

        # Phase 6: Tracker persistence - store trackers by query ID
        self.trackers: dict[str, ResearchProgressTracker] = trackers or {}

        logger.debug(
            f"Session initialized: {metadata.session_id}, "
            f"{conversation.get_message_count()} messages, "
            f"{len(self.trackers)} tracker(s)"
        )

    async def run_query(
        self,
        query: str,
        callbacks: Optional[dict[str, Callable]] = None,
        use_streaming: bool = True,
    ) -> str:
        """Execute a query through the agent loop.

        Convenience method that delegates to agent_loop.run() and
        updates last_active_at timestamp.

        Args:
            query: User's query/message.
            callbacks: Optional callbacks for streaming, tool calls, etc.
            use_streaming: Whether to use real streaming (default True).

        Returns:
            Final text response from Claude.

        Example:
            >>> result = await session.run_query("What is 2+2?")
            >>> print(result)  # "4"
        """
        # Update last active timestamp
        self.metadata.last_active_at = datetime.now()

        # Delegate to agent loop
        result = await self.agent_loop.run(
            query=query, callbacks=callbacks, use_streaming=use_streaming
        )

        logger.debug(
            f"Session {self.metadata.session_id} query completed: "
            f"{len(result)} chars returned"
        )

        return result

    def clear_history(self) -> None:
        """Clear conversation history while preserving session metadata.

        Useful for starting a fresh conversation within the same session.

        Example:
            >>> session.clear_history()
            >>> assert session.get_message_count() == 0
        """
        self.conversation.clear_history()
        self.conversation_cost_tracker.reset()
        self.reasoning_cost_tracker.reset()
        self.summarization_cost_tracker.reset()
        self.metadata.last_active_at = datetime.now()
        logger.info(f"Session {self.metadata.session_id} history cleared")

    def update_conversation_summary(self, summary: str, last_message_index: int) -> None:
        """Update stored conversation summary metadata.

        Args:
            summary: Summary text describing the conversation.
            last_message_index: Index of the last message included in the summary.
        """
        self.metadata.conversation_summary = summary
        self.metadata.summary_last_message_index = last_message_index
        self.metadata.last_active_at = datetime.now()
        logger.debug(
            "Updated session summary: session_id=%s messages=%s",
            self.metadata.session_id,
            last_message_index,
        )

    def get_message_count(self) -> int:
        """Get conversation message count.

        Returns:
            Number of messages in the conversation.
        """
        return self.conversation.get_message_count()

    def get_token_estimate(self) -> int:
        """Estimate token count for the conversation.

        Returns:
            Estimated token count.
        """
        return self.conversation.get_token_estimate()

    def get_cost_summary(self) -> dict[str, Any]:
        """Get formatted cost summary for the session (total of all cost types).

        Returns:
            Dictionary with total cost summary (conversation + reasoning + summarization):
            - total_input_tokens: Total input tokens used
            - total_output_tokens: Total output tokens used
            - total_cost: Total cost in USD
            - round_count: Total conversation rounds
        """
        conv_summary = self.conversation_cost_tracker.get_total()
        reason_summary = self.reasoning_cost_tracker.get_total()
        summ_summary = self.summarization_cost_tracker.get_total()
        
        return {
            "total_input_tokens": conv_summary.total_input_tokens + reason_summary.total_input_tokens + summ_summary.total_input_tokens,
            "total_output_tokens": conv_summary.total_output_tokens + reason_summary.total_output_tokens + summ_summary.total_output_tokens,
            "total_cost": conv_summary.total_cost + reason_summary.total_cost + summ_summary.total_cost,
            "round_count": conv_summary.round_count,
        }
    
    def get_conversation_cost_summary(self) -> dict[str, Any]:
        """Get conversation cost summary (excludes reasoning and summarization).

        Returns:
            Dictionary with conversation cost summary
        """
        summary = self.conversation_cost_tracker.get_total()
        return {
            "total_input_tokens": summary.total_input_tokens,
            "total_output_tokens": summary.total_output_tokens,
            "total_cost": summary.total_cost,
            "round_count": summary.round_count,
        }
    
    def get_reasoning_cost_summary(self) -> dict[str, Any]:
        """Get reasoning cost summary (excludes conversation and summarization).

        Returns:
            Dictionary with reasoning cost summary
        """
        summary = self.reasoning_cost_tracker.get_total()
        return {
            "total_input_tokens": summary.total_input_tokens,
            "total_output_tokens": summary.total_output_tokens,
            "total_cost": summary.total_cost,
            "round_count": summary.round_count,
        }
    
    def get_summarization_cost_summary(self) -> dict[str, Any]:
        """Get summarization cost summary (excludes conversation and reasoning).

        Returns:
            Dictionary with summarization cost summary
        """
        summary = self.summarization_cost_tracker.get_total()
        return {
            "total_input_tokens": summary.total_input_tokens,
            "total_output_tokens": summary.total_output_tokens,
            "total_cost": summary.total_cost,
            "round_count": summary.round_count,
        }

    def reset_costs(self) -> None:
        """Reset all cost tracking for the session."""
        self.conversation_cost_tracker.reset()
        self.reasoning_cost_tracker.reset()
        self.summarization_cost_tracker.reset()
        logger.info(f"Session {self.metadata.session_id} costs reset")

    def to_dict(self) -> dict[str, Any]:
        """Serialize session to dictionary for persistence.

        Phase 6: Now includes tracker persistence.

        Returns:
            Dictionary containing:
            - metadata: Session metadata
            - conversation: Conversation state
            - conversation_cost_tracker: Conversation cost tracking data
            - reasoning_cost_tracker: Reasoning cost tracking data
            - summarization_cost_tracker: Summarization cost tracking data
            - cost_tracker: Legacy field (conversation costs) for backward compatibility
            - trackers: Phase 6: Dict of query_id -> tracker state
            - Note: AgentLoop is NOT serialized (reconstructed on load)

        Example:
            >>> session_data = session.to_dict()
            >>> with open("session.json", "w") as f:
            ...     json.dump(session_data, f, indent=2)
        """
        # Phase 6: Serialize trackers
        trackers_dict = {
            query_id: tracker.to_dict() for query_id, tracker in self.trackers.items()
        }

        return {
            "metadata": self.metadata.to_dict(),
            "conversation": self.conversation.to_dict(),
            "conversation_cost_tracker": self.conversation_cost_tracker.to_dict(),
            "reasoning_cost_tracker": self.reasoning_cost_tracker.to_dict(),
            "summarization_cost_tracker": self.summarization_cost_tracker.to_dict(),
            # Legacy support: include cost_tracker for backward compatibility
            "cost_tracker": self.conversation_cost_tracker.to_dict(),
            # Phase 6: Include trackers
            "trackers": trackers_dict,
            # Note: AgentLoop is not serialized - it's reconstructed on load
            # with fresh LLM and tool registry instances
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], agent_loop: AgentProtocol
    ) -> "Session":
        """Deserialize session from dictionary.

        Args:
            data: Dictionary from to_dict().
            agent_loop: Agent instance to use (not persisted, can be AgentLoop or CommandControlAgent).

        Returns:
            Restored Session instance.

        Example:
            >>> with open("session.json") as f:
            ...     session_data = json.load(f)
            >>>
            >>> # Create fresh agent loop with current dependencies
            >>> agent_loop = AgentLoop(llm, conversation, tool_registry)
            >>>
            >>> # Restore session
            >>> session = Session.from_dict(session_data, agent_loop)
        """
        metadata = SessionMetadata.from_dict(data["metadata"])
        conversation = Conversation.from_dict(data["conversation"])
        
        # Clean up corrupted summaries (duplicate concatenations) on load
        # This ensures summaries are always clean when loaded from disk
        if metadata.conversation_summary:
            # Import here to avoid circular dependency
            from nxs.application.summarization.service import SummarizationService
            
            if SummarizationService._detect_duplicate_summary(metadata.conversation_summary):
                logger.warning(
                    f"Detected duplicate concatenated summary for session {metadata.session_id} "
                    f"during load. Cleaning up corrupted summary."
                )
                cleaned_summary = SummarizationService._clean_duplicate_summary(metadata.conversation_summary)
                if cleaned_summary != metadata.conversation_summary:
                    metadata.conversation_summary = cleaned_summary
                    logger.info(
                        f"Cleaned summary for session {metadata.session_id} on load: "
                        f"reduced from {len(data['metadata'].get('conversation_summary', ''))} "
                        f"to {len(cleaned_summary)} chars"
                    )

        # Restore cost trackers (support both new format and legacy)
        conversation_cost_tracker = None
        reasoning_cost_tracker = None
        summarization_cost_tracker = None
        
        if "conversation_cost_tracker" in data:
            conversation_cost_tracker = CostTracker.from_dict(data["conversation_cost_tracker"])
        elif "cost_tracker" in data:
            # Legacy support: use cost_tracker as conversation_cost_tracker
            conversation_cost_tracker = CostTracker.from_dict(data["cost_tracker"])
        
        if "reasoning_cost_tracker" in data:
            reasoning_cost_tracker = CostTracker.from_dict(data["reasoning_cost_tracker"])
        
        if "summarization_cost_tracker" in data:
            summarization_cost_tracker = CostTracker.from_dict(data["summarization_cost_tracker"])

        # Phase 6: Restore trackers
        trackers: dict[str, ResearchProgressTracker] = {}
        if "trackers" in data:
            for query_id, tracker_data in data["trackers"].items():
                try:
                    tracker = ResearchProgressTracker.from_dict(tracker_data)
                    trackers[query_id] = tracker
                    logger.debug(f"Restored tracker for query: {query_id}")
                except Exception as e:
                    logger.warning(
                        f"Failed to restore tracker for query {query_id}: {e}",
                        exc_info=True,
                    )

        # Update agent_loop's conversation to use restored one
        agent_loop.conversation = conversation

        session = cls(
            metadata=metadata,
            conversation=conversation,
            agent_loop=agent_loop,
            conversation_cost_tracker=conversation_cost_tracker,
            reasoning_cost_tracker=reasoning_cost_tracker,
            summarization_cost_tracker=summarization_cost_tracker,
            trackers=trackers,
        )

        total_cost = session.get_cost_summary()["total_cost"]
        logger.info(
            f"Session restored: {metadata.session_id}, "
            f"{conversation.get_message_count()} messages, "
            f"{len(trackers)} tracker(s), "
            f"${total_cost:.6f} total cost"
        )

        return session

    # Phase 6: Tracker management methods

    def save_tracker(self, query_id: str, tracker: ResearchProgressTracker) -> None:
        """Save a tracker for a query.

        Args:
            query_id: Unique identifier for the query (typically hash or UUID)
            tracker: ResearchProgressTracker instance to save
        """
        self.trackers[query_id] = tracker
        self.metadata.last_active_at = datetime.now()
        logger.debug(f"Saved tracker for query: {query_id}")

    def get_tracker(self, query_id: str) -> Optional[ResearchProgressTracker]:
        """Get a tracker for a query.

        Args:
            query_id: Unique identifier for the query

        Returns:
            ResearchProgressTracker if found, None otherwise
        """
        return self.trackers.get(query_id)

    def list_trackers(self) -> list[tuple[str, ResearchProgressTracker]]:
        """List all trackers in this session.

        Returns:
            List of (query_id, tracker) tuples
        """
        return list(self.trackers.items())

    def delete_tracker(self, query_id: str) -> bool:
        """Delete a tracker for a query.

        Args:
            query_id: Unique identifier for the query

        Returns:
            True if tracker was deleted, False if not found
        """
        if query_id in self.trackers:
            del self.trackers[query_id]
            logger.debug(f"Deleted tracker for query: {query_id}")
            return True
        return False

    def cleanup_old_trackers(self, max_age_days: int = 30) -> int:
        """Phase 6: Cleanup old trackers based on age.

        Args:
            max_age_days: Maximum age in days (default: 30)

        Returns:
            Number of trackers deleted
        """
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        deleted_count = 0

        query_ids_to_delete = []
        for query_id, tracker in self.trackers.items():
            if tracker.created_at < cutoff_date:
                query_ids_to_delete.append(query_id)

        for query_id in query_ids_to_delete:
            del self.trackers[query_id]
            deleted_count += 1

        if deleted_count > 0:
            logger.info(
                f"Cleaned up {deleted_count} old tracker(s) older than {max_age_days} days"
            )

        return deleted_count

    @property
    def session_id(self) -> str:
        """Get session ID."""
        return self.metadata.session_id

    @property
    def title(self) -> str:
        """Get session title."""
        return self.metadata.title

    @title.setter
    def title(self, value: str) -> None:
        """Set session title and update last_active_at."""
        self.metadata.title = value
        self.metadata.last_active_at = datetime.now()

    @property
    def created_at(self) -> datetime:
        """Get session creation timestamp."""
        return self.metadata.created_at

    @property
    def last_active_at(self) -> datetime:
        """Get last active timestamp."""
        return self.metadata.last_active_at
