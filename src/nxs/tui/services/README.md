# TUI Services Package

This package contains **Services** - classes that manage stateful operations and lifecycle management for the TUI layer.

## Services vs Handlers

The TUI layer uses two complementary patterns:

### Services (`tui/services/`)

Services manage **stateful operations** and **lifecycle management**:

- **Responsibilities:**
  - Maintain state and caches
  - Coordinate complex operations
  - Manage widget lifecycles
  - Provide data to widgets

- **Examples:**
  - `RefreshService` - Manages MCP panel refresh operations, task scheduling, debouncing
  - `PromptService` - Handles prompt caching, preloading, and schema management
  - `AutocompleteService` - Manages autocomplete widget lifecycle and cache synchronization
  - `MCPCoordinator` - Coordinates MCP initialization and setup

- **Characteristics:**
  - Hold internal state (caches, counters, flags)
  - May not subscribe to EventBus (operate via direct method calls)
  - Often injected into widgets or other services
  - Typically have `async` initialization methods

### Handlers (`tui/handlers/`)

Handlers process **events** from the EventBus:

- **Responsibilities:**
  - Subscribe to specific event types
  - Process events and coordinate responses
  - Update UI state based on events
  - Delegate work to services

- **Examples:**
  - `ConnectionHandler` - Handles `ConnectionStatusChanged` and `ReconnectProgress` events
  - `QueryHandler` - Handles query processing events
  - `RefreshHandler` - Handles `ArtifactsFetched` events

- **Characteristics:**
  - Subscribe to EventBus events
  - Stateless or minimal state (just references to services/widgets)
  - Handler methods named `handle_<event_type>`
  - Coordinate between events and services/widgets

## Pattern Guidelines

### When to create a Service:

```python
# ✅ Good - manages state and lifecycle
class CacheService:
    def __init__(self, cache: Cache):
        self._cache = cache

    async def preload_data(self):
        # Load and cache data
        pass

    def get_cached(self, key: str):
        return self._cache.get(key)
```

### When to create a Handler:

```python
# ✅ Good - processes events
class DataUpdatedHandler:
    def __init__(self, service: CacheService, widget_getter: Callable):
        self.service = service
        self.widget_getter = widget_getter

    def handle_data_updated(self, event: DataUpdated):
        # Update cache via service
        self.service.update(event.data)
        # Update widget
        widget = self.widget_getter()
        widget.refresh()
```

### Anti-patterns:

```python
# ❌ Bad - Handler managing state
class BadHandler:
    def __init__(self):
        self._cache = {}  # Should be in a Service!

    def handle_event(self, event):
        self._cache[event.key] = event.value

# ❌ Bad - Service subscribing to events
class BadService:
    def __init__(self, event_bus: EventBus):
        event_bus.subscribe(SomeEvent, self.on_event)  # Should be a Handler!
```

## Architecture Flow

```
EventBus (core/events/)
    ↓ publishes events
Handlers (tui/handlers/)
    ↓ delegate work
Services (tui/services/)
    ↓ update/query
Widgets (tui/widgets/)
```

## Current Services

| Service | Purpose | Key State |
|---------|---------|-----------|
| `RefreshService` | MCP panel refresh coordination | Task management, locks |
| `PromptService` | Prompt caching and preloading | Prompt info/schema caches |
| `AutocompleteService` | Autocomplete lifecycle | Mount status |
| `MCPCoordinator` | MCP initialization | Initialization state |

## Current Handlers

| Handler | Events | Delegates To |
|---------|--------|--------------|
| `ConnectionHandler` | `ConnectionStatusChanged`, `ReconnectProgress` | `RefreshService`, MCP panel |
| `QueryHandler` | Query processing | Agent, status queue |
| `RefreshHandler` | `ArtifactsFetched` | `RefreshService` |
