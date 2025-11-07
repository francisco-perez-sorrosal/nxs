"""Event types for the event bus system.

This module defines all event types used throughout the application
to decouple components and enable event-driven communication.
"""

import time
from dataclasses import dataclass, field

from nxs.mcp_client.connection.lifecycle import ConnectionStatus


@dataclass
class Event:
    """Base class for all events.

    All events in the system should inherit from this base class.
    The timestamp field is automatically set when the event is created.
    """

    timestamp: float = field(default_factory=time.time, init=False)
    """Timestamp when the event was created (Unix timestamp)."""


@dataclass
class ConnectionStatusChanged(Event):
    """Event published when an MCP server connection status changes.

    This event is published by the core layer (ArtifactManager) whenever
    a server's connection status changes (e.g., DISCONNECTED -> CONNECTED).

    Attributes:
        server_name: Name of the server whose status changed
        status: New connection status
        previous_status: Previous connection status (if available)
    """

    server_name: str
    """Name of the MCP server."""
    status: ConnectionStatus
    """New connection status."""
    previous_status: ConnectionStatus | None = None
    """Previous connection status (if available)."""


@dataclass
class ReconnectProgress(Event):
    """Event published during MCP server reconnection attempts.

    This event is published periodically during reconnection attempts
    to provide progress information to subscribers (e.g., UI layer).

    Attributes:
        server_name: Name of the server being reconnected
        attempts: Current reconnection attempt number (1-based)
        max_attempts: Maximum number of reconnection attempts
        next_retry_delay: Seconds until the next retry attempt
    """

    server_name: str
    """Name of the MCP server."""
    attempts: int
    """Current reconnection attempt number (1-based)."""
    max_attempts: int
    """Maximum number of reconnection attempts."""
    next_retry_delay: float
    """Seconds until the next retry attempt."""


@dataclass
class ArtifactsFetched(Event):
    """Event published when artifacts are fetched for an MCP server.

    This event is published by ArtifactManager after successfully fetching
    artifacts (tools, prompts, resources) for a server. This allows the UI
    layer to refresh displays when artifacts change.

    Attributes:
        server_name: Name of the server
        artifacts: Dictionary containing fetched artifacts with keys:
                   "tools", "prompts", "resources"
                   Each value is a list of dicts with "name" and "description" keys
        changed: Whether the artifacts changed compared to cache
    """

    server_name: str
    """Name of the MCP server."""
    artifacts: dict[str, list[dict[str, str | None]]]
    """Fetched artifacts dictionary with keys: tools, prompts, resources."""
    changed: bool = False
    """Whether the artifacts changed compared to the cached version."""

