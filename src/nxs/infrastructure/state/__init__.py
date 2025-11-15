"""State persistence infrastructure.

This module provides concrete implementations of the StateProvider protocol
for different storage backends.
"""

from nxs.infrastructure.state.memory import InMemoryStateProvider
from nxs.infrastructure.state.file import FileStateProvider

__all__ = [
    "InMemoryStateProvider",
    "FileStateProvider",
]
