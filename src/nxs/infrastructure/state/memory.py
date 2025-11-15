"""In-memory state provider implementation.

This module provides a simple in-memory state storage for testing and
development. State is stored in a dictionary and is lost when the
application exits.
"""

import copy
from typing import Any

from nxs.logger import get_logger

logger = get_logger(__name__)


class InMemoryStateProvider:
    """In-memory state provider for testing and development.

    Stores state in a dictionary. All state is lost when the application exits.
    Useful for unit tests and development where persistence is not needed.

    Thread-safe for asyncio (single-threaded event loop).

    Example:
        >>> provider = InMemoryStateProvider()
        >>> await provider.save("session:123", {"data": "value"})
        >>> data = await provider.load("session:123")
        >>> print(data)
        {'data': 'value'}
        >>> await provider.delete("session:123")
        >>> assert await provider.load("session:123") is None
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory state store."""
        self._data: dict[str, dict[str, Any]] = {}
        logger.debug("InMemoryStateProvider initialized (state will not persist)")

    async def save(self, key: str, data: dict[str, Any]) -> None:
        """Save state data under a key.

        Args:
            key: Unique key for the state (e.g., "session:abc123")
            data: State data as a dictionary

        Note:
            Creates a deep copy of the data to prevent mutations
        """
        # Deep copy to prevent external mutations
        self._data[key] = copy.deepcopy(data)
        logger.debug(f"Saved state: key='{key}', size={len(data)} fields")

    async def load(self, key: str) -> dict[str, Any] | None:
        """Load state data by key.

        Args:
            key: The state key to load

        Returns:
            State data dictionary if found, None if key doesn't exist

        Note:
            Returns a deep copy to prevent external mutations
        """
        if key not in self._data:
            logger.debug(f"State not found: key='{key}'")
            return None

        # Deep copy to prevent external mutations
        data = copy.deepcopy(self._data[key])
        logger.debug(f"Loaded state: key='{key}', size={len(data)} fields")
        return data

    async def exists(self, key: str) -> bool:
        """Check if state exists for a key.

        Args:
            key: The state key to check

        Returns:
            True if key exists, False otherwise
        """
        exists = key in self._data
        logger.debug(f"State exists check: key='{key}', exists={exists}")
        return exists

    async def delete(self, key: str) -> None:
        """Delete state by key.

        Args:
            key: The state key to delete

        Note:
            Silently succeeds if key doesn't exist (idempotent)
        """
        if key in self._data:
            del self._data[key]
            logger.debug(f"Deleted state: key='{key}'")
        else:
            logger.debug(f"Delete called on non-existent key: '{key}' (no-op)")

    async def list_keys(self, prefix: str | None = None) -> list[str]:
        """List all available state keys.

        Args:
            prefix: Optional prefix filter (e.g., "session:")

        Returns:
            List of keys, optionally filtered by prefix
        """
        if prefix is None:
            keys = list(self._data.keys())
        else:
            keys = [k for k in self._data.keys() if k.startswith(prefix)]

        logger.debug(f"Listed keys: prefix='{prefix}', count={len(keys)}")
        return keys

    def clear_all(self) -> None:
        """Clear all stored state.

        Utility method for testing cleanup.
        """
        count = len(self._data)
        self._data.clear()
        logger.debug(f"Cleared all state: {count} keys removed")

    def __len__(self) -> int:
        """Return the number of stored keys."""
        return len(self._data)

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in the store."""
        return key in self._data
