"""Base cache protocol and types.

This module re-exports the Cache protocol from protocols.py for convenience,
and provides type definitions for cache implementations.
"""

# Re-export Cache protocol from protocols to avoid duplication
from nxs.core.protocols import Cache

__all__ = ["Cache"]

