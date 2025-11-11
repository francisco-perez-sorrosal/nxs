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
    ):
        """Initialize a session.

        Args:
            metadata: Session metadata (ID, title, timestamps, etc.).
            conversation: Conversation instance with message history.
            agent_loop: Agent instance for query execution (AgentLoop or CommandControlAgent).
        """
        self.metadata = metadata
        self.conversation = conversation
        self.agent_loop = agent_loop

        logger.debug(
            f"Session initialized: {metadata.session_id}, "
            f"{conversation.get_message_count()} messages"
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
        self.metadata.last_active_at = datetime.now()
        logger.info(f"Session {self.metadata.session_id} history cleared")

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize session to dictionary for persistence.

        Returns:
            Dictionary containing:
            - metadata: Session metadata
            - conversation: Conversation state
            - Note: AgentLoop is NOT serialized (reconstructed on load)

        Example:
            >>> session_data = session.to_dict()
            >>> with open("session.json", "w") as f:
            ...     json.dump(session_data, f, indent=2)
        """
        return {
            "metadata": self.metadata.to_dict(),
            "conversation": self.conversation.to_dict(),
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

        # Update agent_loop's conversation to use restored one
        agent_loop.conversation = conversation

        session = cls(
            metadata=metadata,
            conversation=conversation,
            agent_loop=agent_loop,
        )

        logger.info(
            f"Session restored: {metadata.session_id}, "
            f"{conversation.get_message_count()} messages"
        )

        return session

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
