"""Cache protocol."""

from typing import Protocol, TypeVar

__all__ = ["Cache", "K", "V"]

# Type variables for generic Cache protocol
# Note: Invariant (default) is correct for Cache since we both read and write
K = TypeVar("K", contravariant=False)
V = TypeVar("V", contravariant=False)


class Cache(Protocol[K, V]):
    """Protocol for caching implementations.

    This protocol defines a simple caching interface that can be implemented
    by various caching strategies (in-memory, TTL-based, LRU, etc.).

    Type Parameters:
        K: The key type
        V: The value type
    """

    def get(self, key: K) -> V | None:
        """Get a value from the cache.

        Args:
            key: The cache key

        Returns:
            The cached value if found, None otherwise
        """
        ...

    def set(self, key: K, value: V) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key
            value: The value to cache
        """
        ...

    def clear(self, key: K | None = None) -> None:
        """Clear cache entries.

        Args:
            key: If provided, clear only this key. If None, clear all entries.
        """
        ...

    def has_changed(self, key: K, value: V) -> bool:
        """Check if a value has changed compared to what's cached.

        Args:
            key: The cache key
            value: The new value to compare

        Returns:
            True if the value has changed (or is not cached), False if unchanged
        """
        ...
