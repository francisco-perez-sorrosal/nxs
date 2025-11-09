"""Event system for decoupled component communication.

This package provides an event bus system that allows components to communicate
without direct coupling. The core layer publishes events, and the UI layer
subscribes to them.

Example:
    ```python
    from nxs.domain.events import EventBus, ConnectionStatusChanged
    from nxs.domain.types import ConnectionStatus

    # Create event bus
    event_bus = EventBus()

    # Subscribe to events
    def handle_status(event: ConnectionStatusChanged):
        print(f"Server {event.server_name} is {event.status.value}")

    event_bus.subscribe(ConnectionStatusChanged, handle_status)

    # Publish events
    event_bus.publish(ConnectionStatusChanged(
        server_name="my_server",
        status=ConnectionStatus.CONNECTED
    ))
    ```
"""

from .bus import EventBus
from .types import (
    ArtifactsFetched,
    ConnectionStatusChanged,
    Event,
    ReconnectProgress,
)

__all__ = [
    "EventBus",
    "Event",
    "ConnectionStatusChanged",
    "ReconnectProgress",
    "ArtifactsFetched",
]
