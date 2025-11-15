"""Domain protocols - interfaces for all implementations.

This module defines protocols (structural types) that describe the contracts
that various components in the system must satisfy. Using protocols allows for
better type safety, easier testing with mocks, and clearer documentation of
expected interfaces.
"""

from nxs.domain.protocols.mcp_client import MCPClient
from nxs.domain.protocols.cache import Cache, K, V
from nxs.domain.protocols.parser import ArgumentParser
from nxs.domain.protocols.factory import ClientProvider
from nxs.domain.protocols.state import StateProvider

__all__ = [
    "MCPClient",
    "Cache",
    "K",
    "V",
    "ArgumentParser",
    "ClientProvider",
    "StateProvider",
]
