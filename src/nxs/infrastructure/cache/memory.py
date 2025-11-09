"""In-memory cache implementation.

This module provides a simple in-memory cache that stores values in a dictionary.
It implements the Cache protocol and provides a has_changed method for change detection.
"""

from typing import TypeVar

from nxs.infrastructure.cache.base import Cache

K = TypeVar("K")
V = TypeVar("V")


class MemoryCache(Cache[K, V]):
    """Simple in-memory cache implementation.

    This cache stores values in a dictionary with no expiration. It provides
    basic get/set/clear operations and change detection.

    Example:
        >>> cache = MemoryCache[str, int]()
        >>> cache.set("key1", 42)
        >>> cache.get("key1")
        42
        >>> cache.has_changed("key1", 42)
        False
        >>> cache.has_changed("key1", 43)
        True
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory cache."""
        self._data: dict[K, V] = {}

    def get(self, key: K) -> V | None:
        """Get a value from the cache.

        Args:
            key: The cache key

        Returns:
            The cached value if found, None otherwise
        """
        return self._data.get(key)

    def set(self, key: K, value: V) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key
            value: The value to cache
        """
        self._data[key] = value

    def clear(self, key: K | None = None) -> None:
        """Clear cache entries.

        Args:
            key: If provided, clear only this key. If None, clear all entries.
        """
        if key is None:
            self._data.clear()
        else:
            self._data.pop(key, None)

    def has_changed(self, key: K, value: V) -> bool:
        """Check if a value has changed compared to what's cached.

        Args:
            key: The cache key
            value: The new value to compare

        Returns:
            True if the value has changed (or is not cached), False if unchanged
        """
        cached = self.get(key)
        return cached is None or cached != value

    def __len__(self) -> int:
        """Return the number of cached entries."""
        return len(self._data)

    def __contains__(self, key: K) -> bool:
        """Check if a key exists in the cache."""
        return key in self._data
