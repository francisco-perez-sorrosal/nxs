"""State provider protocol for persistent storage of session state.

This protocol defines the interface for state persistence backends
(in-memory, file system, database, etc.) used by SessionState and SessionManager.
"""

from typing import Any, Protocol

__all__ = ["StateProvider"]


class StateProvider(Protocol):
    """Protocol for state persistence providers.

    State providers abstract different storage backends (in-memory, file system,
    database, cloud storage, etc.) behind a uniform interface for session state
    persistence.

    This enables:
    - Multiple storage backends with the same interface
    - Easy testing with mock providers
    - Runtime switching between storage strategies
    - Backward compatibility when adding new backends

    Example implementations:
    - InMemoryStateProvider: Dict-based storage for testing
    - FileStateProvider: JSON file storage for local persistence
    - DatabaseStateProvider: SQL/NoSQL database storage (future)
    - CloudStateProvider: S3/cloud storage (future)

    Example:
        >>> provider = FileStateProvider(sessions_dir="~/.nexus/sessions")
        >>> await provider.save("session:123", {"conversation": {...}})
        >>> data = await provider.load("session:123")
        >>> if data:
        ...     print(f"Loaded session: {data['session_id']}")
    """

    async def save(self, key: str, data: dict[str, Any]) -> None:
        """Save state data under a key.

        Args:
            key: Unique key for the state (e.g., "session:abc123")
            data: State data as a JSON-serializable dictionary

        Raises:
            IOError: If storage operation fails (disk full, permissions, etc.)
            ValueError: If data is not JSON-serializable

        Example:
            >>> await provider.save("session:123", {
            ...     "session_id": "123",
            ...     "conversation": {"messages": [...]},
            ...     "created_at": "2024-01-01T00:00:00"
            ... })
        """
        ...

    async def load(self, key: str) -> dict[str, Any] | None:
        """Load state data by key.

        Args:
            key: The state key to load

        Returns:
            State data dictionary if found, None if key doesn't exist

        Raises:
            IOError: If storage read operation fails
            ValueError: If stored data is corrupted or not valid JSON

        Example:
            >>> data = await provider.load("session:123")
            >>> if data is None:
            ...     print("Session not found")
            >>> else:
            ...     print(f"Loaded {len(data)} fields")
        """
        ...

    async def exists(self, key: str) -> bool:
        """Check if state exists for a key.

        Args:
            key: The state key to check

        Returns:
            True if key exists, False otherwise

        Example:
            >>> if await provider.exists("session:123"):
            ...     print("Session found")
        """
        ...

    async def delete(self, key: str) -> None:
        """Delete state by key.

        Args:
            key: The state key to delete

        Note:
            Silently succeeds if key doesn't exist (idempotent)

        Example:
            >>> await provider.delete("session:123")
        """
        ...

    async def list_keys(self, prefix: str | None = None) -> list[str]:
        """List all available state keys.

        Args:
            prefix: Optional prefix filter (e.g., "session:" to list only sessions)

        Returns:
            List of keys, optionally filtered by prefix

        Example:
            >>> # List all sessions
            >>> sessions = await provider.list_keys(prefix="session:")
            >>> print(f"Found {len(sessions)} sessions")
            >>>
            >>> # List all keys
            >>> all_keys = await provider.list_keys()
        """
        ...
