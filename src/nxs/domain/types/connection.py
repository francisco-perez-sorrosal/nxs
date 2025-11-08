"""Connection-related domain types."""

from enum import Enum

__all__ = ["ConnectionStatus"]


class ConnectionStatus(Enum):
    """Status of an MCP client connection.

    This enum represents the various states a connection can be in throughout
    its lifecycle.
    """

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
