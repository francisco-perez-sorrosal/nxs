"""TTL (Time-To-Live) cache implementation.

This module provides a cache implementation that automatically expires entries
after a specified time-to-live period.
"""

import time
from typing import TypeVar

from nxs.core.cache.base import Cache

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Cache[K, V]):
    """TTL-based cache implementation.
    
    This cache stores values with an expiration time. Entries are automatically
    considered expired after the TTL period. The cache is checked for expired
    entries on get operations.
    
    Example:
        >>> cache = TTLCache[str, int](ttl=60.0)  # 60 seconds TTL
        >>> cache.set("key1", 42)
        >>> cache.get("key1")
        42
        >>> # Wait 61 seconds...
        >>> cache.get("key1")  # Returns None (expired)
        None
    """
    
    def __init__(self, ttl: float = 300.0) -> None:
        """Initialize a TTL cache.
        
        Args:
            ttl: Time-to-live in seconds. Default is 300 seconds (5 minutes).
        """
        self._data: dict[K, tuple[V, float]] = {}  # (value, expiration_time)
        self.ttl = ttl
    
    def _is_expired(self, expiration_time: float) -> bool:
        """Check if an entry has expired.
        
        Args:
            expiration_time: The expiration timestamp
            
        Returns:
            True if expired, False otherwise
        """
        return time.time() > expiration_time
    
    def _cleanup_expired(self) -> None:
        """Remove expired entries from the cache."""
        current_time = time.time()
        expired_keys = [
            key for key, (_, exp_time) in self._data.items()
            if current_time > exp_time
        ]
        for key in expired_keys:
            del self._data[key]
    
    def get(self, key: K) -> V | None:
        """Get a value from the cache.
        
        Automatically removes expired entries before checking.
        
        Args:
            key: The cache key
            
        Returns:
            The cached value if found and not expired, None otherwise
        """
        self._cleanup_expired()
        
        entry = self._data.get(key)
        if entry is None:
            return None
        
        value, expiration_time = entry
        if self._is_expired(expiration_time):
            del self._data[key]
            return None
        
        return value
    
    def set(self, key: K, value: V) -> None:
        """Set a value in the cache with TTL.
        
        Args:
            key: The cache key
            value: The value to cache
        """
        expiration_time = time.time() + self.ttl
        self._data[key] = (value, expiration_time)
    
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
        
        Expired entries are considered as changed (not cached).
        
        Args:
            key: The cache key
            value: The new value to compare
            
        Returns:
            True if the value has changed (or is not cached/expired), False if unchanged
        """
        cached = self.get(key)  # This automatically handles expiration
        return cached is None or cached != value
    
    def __len__(self) -> int:
        """Return the number of cached entries (excluding expired ones)."""
        self._cleanup_expired()
        return len(self._data)
    
    def __contains__(self, key: K) -> bool:
        """Check if a key exists in the cache (and is not expired)."""
        return self.get(key) is not None

