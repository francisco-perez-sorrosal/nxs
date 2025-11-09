"""Caching implementations for Nexus.

This package provides reusable caching abstractions that can be swapped
based on requirements. Currently supports in-memory caching.
"""

from nxs.infrastructure.cache.base import Cache
from nxs.infrastructure.cache.memory import MemoryCache

__all__ = [
    "Cache",
    "MemoryCache",
]
