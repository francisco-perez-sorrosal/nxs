"""Event bus implementation for decoupled event-driven communication.

The EventBus allows components to publish and subscribe to events without
direct coupling. This enables clean separation between layers (e.g., core
layer publishing events, UI layer subscribing to them).

Event Handler Contract:
    Event handlers MUST be synchronous (non-async) functions. This is enforced
    at subscription time. Handlers should be fast coordinators that schedule
    async work rather than executing it directly.

    Good: handler schedules async work via asyncio.create_task()
    Bad:  handler is async and tries to await operations
"""

import asyncio
from typing import Callable, Type, TypeVar

from nxs.logger import get_logger

from .types import Event

logger = get_logger("events.bus")

T = TypeVar("T", bound=Event)

# Type alias for event handlers - must be synchronous
EventHandler = Callable[[Event], None]


class EventBus:
    """Event bus for publishing and subscribing to events.

    The EventBus provides a simple publish-subscribe mechanism where:
    - Publishers create event instances and call `publish(event)`
    - Subscribers register handlers for specific event types using `subscribe()`

    Example:
        ```python
        # In core layer (publisher)
        event_bus = EventBus()
        event_bus.publish(ConnectionStatusChanged(
            server_name="my_server",
            status=ConnectionStatus.CONNECTED
        ))

        # In UI layer (subscriber)
        def handle_status_change(event: ConnectionStatusChanged):
            print(f"Server {event.server_name} is now {event.status.value}")

        event_bus.subscribe(ConnectionStatusChanged, handle_status_change)
        ```

    Thread safety:
        This implementation is NOT thread-safe. It assumes all operations
        happen within the same async event loop. For thread-safe operations,
        external synchronization is required.
    """

    def __init__(self):
        """Initialize the event bus."""
        self._handlers: dict[Type[Event], list[Callable[[Event], None]]] = {}
        """Registry of event handlers by event type."""

    def subscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        """
        Subscribe to events of a specific type.

        Args:
            event_type: The type of event to subscribe to (e.g., ConnectionStatusChanged)
            handler: Callback function that will be called when events of this type are published.
                    The handler receives the event instance as its argument.
                    MUST be synchronous (non-async). Async handlers will raise TypeError.

        Raises:
            TypeError: If handler is an async function (coroutine function)

        Example:
            ```python
            def handle_status(event: ConnectionStatusChanged):
                print(f"Status changed: {event.server_name} -> {event.status.value}")

            event_bus.subscribe(ConnectionStatusChanged, handle_status)
            ```

        Note:
            Event handlers must be synchronous. If you need to perform async operations,
            schedule them using asyncio.create_task() rather than making the handler async.

            Good pattern:
                def handler(event):
                    asyncio.create_task(async_operation())

            Bad pattern:
                async def handler(event):  # ← Will raise TypeError
                    await async_operation()
        """
        # Validate handler is synchronous
        if asyncio.iscoroutinefunction(handler):
            raise TypeError(
                f"Event handlers must be synchronous functions. "
                f"Handler {handler.__name__} is an async function (coroutine function). "
                f"To perform async work, schedule it using asyncio.create_task() instead."
            )

        if event_type not in self._handlers:
            self._handlers[event_type] = []

        # Avoid duplicate subscriptions of the same handler
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug(f"Subscribed handler for {event_type.__name__}")
        else:
            logger.debug(f"Handler already subscribed for {event_type.__name__}, skipping")

    def unsubscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        """
        Unsubscribe a handler from events of a specific type.

        Args:
            event_type: The type of event to unsubscribe from
            handler: The handler callback to remove

        Note:
            If the handler was not subscribed, this is a no-op.
        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                logger.debug(f"Unsubscribed handler for {event_type.__name__}")
            except ValueError:
                logger.debug(f"Handler not found in subscriptions for {event_type.__name__}")

    def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribed handlers.

        Args:
            event: The event instance to publish

        Execution Model:
            Handlers are called synchronously in the order they were subscribed.
            This method blocks until all handlers have completed. Handlers must
            be synchronous (non-async) - this is enforced at subscription time.

            If handlers need to perform async work, they should schedule it using
            asyncio.create_task() rather than awaiting it directly.

        Error Handling:
            If a handler raises an exception, it is logged and does not prevent
            other handlers from being called.

        Example:
            ```python
            event_bus.publish(ConnectionStatusChanged(
                server_name="my_server",
                status=ConnectionStatus.CONNECTED
            ))
            ```
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            logger.debug(f"No handlers subscribed for {event_type.__name__}")
            return

        logger.debug(f"Publishing {event_type.__name__} to {len(handlers)} handler(s)")

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"Error in event handler for {event_type.__name__}: {e}",
                    exc_info=True,
                )

    def clear(self) -> None:
        """
        Clear all event subscriptions.

        This is useful for cleanup or testing scenarios.
        """
        self._handlers.clear()
        logger.debug("Event bus cleared")

    def has_subscribers(self, event_type: Type[Event]) -> bool:
        """
        Check if there are any subscribers for a specific event type.

        Args:
            event_type: The event type to check

        Returns:
            True if there are any subscribers, False otherwise
        """
        return event_type in self._handlers and len(self._handlers[event_type]) > 0
