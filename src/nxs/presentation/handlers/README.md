# TUI Handlers Package

This package contains **Handlers** - classes that process events from the EventBus.

## Pattern Overview

Handlers are the bridge between the event-driven core layer and the TUI layer. They:

1. Subscribe to specific event types from `EventBus`
2. Process events and extract relevant data
3. Coordinate updates to widgets and services
4. Maintain minimal state (just references)

## Design Principles

### Single Responsibility
Each handler focuses on one category of events:
- `ConnectionHandler` - Connection lifecycle events
- `RefreshHandler` - Artifact refresh events
- `QueryHandler` - Query processing

### Event-Driven
Handlers react to events, they don't poll or maintain timers. All proactive behavior should be in Services.

### Stateless Coordination
Handlers don't maintain business state. They coordinate between:
- EventBus (source of events)
- Services (stateful operations)
- Widgets (UI updates)

## Handler Template

```python
from typing import TYPE_CHECKING, Callable
from nxs.domain.events import SomeEvent
from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.presentation.services.some_service import SomeService
    from nxs.presentation.widgets.some_widget import SomeWidget

logger = get_logger("some_handler")


class SomeHandler:
    """
    Handles SomeEvent events.

    This handler processes SomeEvent events and coordinates
    updates to the SomeWidget via SomeService.
    """

    def __init__(
        self,
        service: "SomeService",
        widget_getter: Callable[[], "SomeWidget"],
    ):
        """
        Initialize the handler.

        Args:
            service: Service to delegate operations to
            widget_getter: Function to get the widget
        """
        self.service = service
        self.widget_getter = widget_getter

    def handle_some_event(self, event: SomeEvent) -> None:
        """
        Handle SomeEvent.

        Args:
            event: The event to process
        """
        logger.debug(f"Processing event: {event}")

        # Extract event data
        data = event.data

        # Delegate to service
        self.service.process(data)

        # Update widget
        try:
            widget = self.widget_getter()
            widget.update(data)
        except Exception as e:
            logger.error(f"Error updating widget: {e}")
```

## Current Handlers

### ConnectionHandler

**Events:** `ConnectionStatusChanged`, `ReconnectProgress`

**Responsibilities:**
- Updates MCP panel with connection status
- Caches reconnection info from events
- Schedules refreshes via RefreshService
- Implements debouncing for reconnection progress

**Key Pattern:** Event-sourced caching - caches data from events instead of querying implementation details.

### RefreshHandler

**Events:** `ArtifactsFetched`

**Responsibilities:**
- Schedules MCP panel refreshes when artifacts change
- Delegates to RefreshService for actual refresh coordination

**Key Pattern:** Simple event-to-service delegation.

### QueryHandler

**Events:** Query processing (not from EventBus)

**Responsibilities:**
- Processes user queries through agent
- Updates status panel
- Manages query lifecycle

**Note:** This handler predates the EventBus pattern and may be refactored in the future.

## Testing Handlers

Handlers are easy to test because they're stateless coordinators:

```python
def test_handler():
    # Mock dependencies
    service = Mock()
    widget = Mock()
    handler = SomeHandler(service, lambda: widget)

    # Create event
    event = SomeEvent(data="test")

    # Process event
    handler.handle_some_event(event)

    # Assert coordination happened
    service.process.assert_called_once_with("test")
    widget.update.assert_called_once_with("test")
```

## See Also

- [Services README](../services/README.md) - Stateful operations and lifecycle management
- [Domain Events](../../domain/events/) - Event definitions and EventBus
