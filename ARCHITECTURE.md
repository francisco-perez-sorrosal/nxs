# NXS Architecture Overview

NXS is a full-screen TUI that orchestrates conversations between a user and Anthropic's Claude while brokering Model Context Protocol (MCP) resources, prompts, and tools. The codebase follows a layered architecture to keep user interface concerns, domain contracts, and infrastructure details separate and composable.

## Layered Design

```
┌───────────────┐
│ Presentation  │  Textual TUI, widgets, handlers, services
├───────────────┤
│ Application   │  Agent loop, artifact orchestration, connection lifecycle
├───────────────┤
│ Domain        │  Protocols, events, shared types
├───────────────┤
│ Infrastructure│  MCP client, caches, integrations
└───────────────┘
```

### Domain Layer — `src/nxs/domain`
- Defines the **protocols** (structural interfaces) used across the application, keeping higher-level code agnostic of concrete implementations.
- Hosts the **event system** (`events.bus`, `events.types`) used to bridge background services with the UI through a publish/subscribe model.
- Provides **typed enumerations and data classes** in `domain/types` for consistent status reporting (e.g., `ConnectionStatus`).
- Supplies exceptions and helper abstractions shared by multiple layers.

### Application Layer — `src/nxs/application`
- Coordinates the core runtime use cases without UI or infrastructure details.
- `AgentLoop` in `chat.py` runs the Claude conversation loop, handles tool-calling, and streams output via callbacks.
- `MCPConnectionManager` translates MCP server configuration into live `MCPClient` instances, tracks lifecycle across ALL servers, and emits connection events.
- `ArtifactManager` composes repository and cache to fetch MCP resources/prompts/tools and publishes `ArtifactsFetched` events.
- `command_control.py` wraps the agent loop with command parsing and context enrichment.
- Subpackages like `artifacts/`, `parsers/`, and `suggestions/` encapsulate reusable behaviours for formatting completions and validating user input.

### Infrastructure Layer — `src/nxs/infrastructure`
- Supplies concrete implementations for the domain protocols.
- `mcp/` wraps the `MCPAuthClient`, connection management, reconnection policy, storage, and CLI helpers.
- `cache/` includes baseline cache backends (in-memory, TTL) used by application services and the presentation layer.
- Acts as the integration point for remote MCP servers (currently remote HTTP endpoints via `ClientFactory` and `MCPAuthClient`).

### Presentation Layer — `src/nxs/presentation`

Implements the **Textual-based TUI** (`tui/nexus_app.py`) using two complementary patterns:

**Services** (`services/`) - Stateful operations and lifecycle management:
- Maintain state and caches
- Coordinate complex operations
- Manage widget lifecycles
- Provide data to widgets
- **Key services**:
  - `ServiceContainer` - Lazy initialization and lifecycle management
  - `PromptService` - Prompt caching, preloading, and schema management
  - `AutocompleteService` - Autocomplete widget lifecycle
  - `RefreshService` - MCP panel refresh coordination with debouncing
  - `StatusQueue` - FIFO queue for status panel updates
  - `AsyncQueueProcessor<T>` - Generic reusable pattern for background queue processing

**Handlers** (`handlers/`) - Event-driven coordination:
- Subscribe to EventBus events
- Process events and coordinate responses
- Delegate work to services
- Stateless or minimal state (just references)
- **Key handlers**:
  - `QueryHandler` - Processes queries through agent loop
  - Pattern: `handle_<event_type>` methods

**Queue-Based Components** (`tui/`):
- `QueryQueue` - FIFO queue for sequential query processing
- Both `StatusQueue` and `QueryQueue` use `AsyncQueueProcessor` to eliminate duplication

**Widgets** (`widgets/`):
- Render chat, MCP server status, autocomplete overlays, and status panels with Rich formatting

**Architecture Flow**:
```
EventBus → Handlers → Services → Widgets
```

The presentation layer consumes only application-layer facades and domain events, remaining free of networking or storage concerns.

## Supporting Modules
- `src/nxs/main.py` boots the application: loads environment variables, instantiates the agent loop, artifact manager, and TUI, and wires the shared `EventBus`.
- `src/nxs/config/` contains MCP server configuration (`nxs_mcp_config.json`) consumed by `ConnectionManager`.
- `src/nxs/prompts/` stores Claude prompt templates used by the agent.
- `src/nxs/logger.py` offers centralized Loguru configuration shared across modules.
- `src/nxs/utils.py` includes utility helpers (formatting, time utilities, etc.).

## Runtime Flow

### Startup
1. `python -m nxs` (Pixi task `start`) loads environment variables and configures logging.
2. `ArtifactManager` builds MCP clients via `ConnectionManager` and initiates asynchronous connections.
3. `NexusApp` mounts the TUI, the `ServiceContainer` starts background services (`QueryQueue`, `StatusQueue`) with lazy initialization, and schedules MCP initialization in the background.

### Query Processing
1. The user submits text through `NexusInput`; the `QueryQueue` ensures sequential FIFO processing.
2. `QueryHandler` processes the query through `AgentLoop`.
3. `AgentLoop` appends the message history, calls Claude with available tools (fetched through `ToolManager`/`ArtifactManager`), and streams output via callbacks consumed by TUI services.
4. If Claude requests tool execution, `ToolManager` marshals tool calls back to the appropriate `MCPClient` and injects the results before continuing the conversation loop.
5. Final responses are streamed back to the chat panel; status updates appear in the status panel via `StatusQueue` which ensures FIFO ordering.

### Artifact & Connection Updates
- `ConnectionManager` publishes `ConnectionStatusChanged` and `ReconnectProgress` events as MCP clients connect or retry.
- `ArtifactManager` fetches resources/prompts/tools and publishes `ArtifactsFetched` when caches change.
- Presentation handlers update the MCP panel, autocomplete lists, and status messages in response to these events.

## Event-Driven Coordination
- The **EventBus** (`domain/events/bus.py`) decouples background services from UI widgets using a synchronous fire-and-forget pattern.
- Event handlers are synchronous but schedule async work via `asyncio.create_task()`, allowing non-blocking event propagation.
- Handlers in `presentation/handlers/` subscribe to events and delegate work to services in `presentation/services/` to update widgets.
- This keeps event handling declarative and makes it easy to plug in new listeners or services without touching the data producers.

## Extensibility Points
- **MCP integrations**: Add or modify server entries in `src/nxs/config/nxs_mcp_config.json`. New server types can be supported by extending `ClientFactory`.
- **Artifacts & prompts**: Extend repository logic inside `application/artifacts/` or add prompt templates in `src/nxs/prompts/`.
- **TUI behaviour**: Create new widgets under `presentation/widgets/`, register handlers/services, and subscribe to events.
- **Caching strategies**: Provide alternate cache implementations by fulfilling the `Cache` protocol (`domain/protocols/cache.py`).
- **Testing**: Use the `tests/` suite as examples for mocking protocols and verifying handlers/services in isolation.

## Interaction with External Services
- Claude communication is abstracted behind `application/claude.py`, simplifying credential loading and message formatting.
- MCP clients rely on `nxs.infrastructure.mcp.client.MCPAuthClient` for authenticated HTTP transport, automatic reconnects, and tool execution.
- Logging is centralized via `nxs.logger.get_logger`, ensuring consistent, colorized output across layers and simplifying traceability during debugging.

This architecture enables the TUI to stay responsive while background tasks connect to remote services, fetch artifacts, and execute tools, all without hard-coupling UI components to networking or storage concerns. Developers can extend or replace each layer independently by targeting the domain protocols and event contracts described above.

## Naming Conventions

To maintain consistency and clarity across the codebase, the following naming conventions are established:

### Class Suffixes and Their Meanings

**Manager**
- **Purpose**: Owns lifecycle and state of specific resources
- **Scope**: Resource creation, destruction, tracking, and state queries
- **Examples**:
  - `MCPConnectionManager`: Manages ALL MCP server connections (aggregate)
  - `ToolManager`: Manages tool discovery and execution
- **When to use**: When a class is responsible for the full lifecycle of a set of resources

**Service**
- **Purpose**: Long-lived background operations and stateful processes
- **Scope**: Runs continuously, maintains internal state, provides async operations
- **Responsibilities**:
  - Maintain state and caches
  - Coordinate complex operations
  - Manage widget lifecycles
  - Provide data to widgets
- **Characteristics**:
  - Hold internal state (caches, counters, flags)
  - May not subscribe to EventBus (operate via direct method calls)
  - Often injected into widgets or other services
  - Typically have `async` initialization methods
- **Examples**:
  - `PromptService`: Prompt caching, preloading, and schema management
  - `AutocompleteService`: Manages autocomplete widget lifecycle and state
  - `RefreshService`: Coordinates MCP panel refresh operations with debouncing
- **When to use**: When a class provides ongoing background functionality or maintains significant state
- **Anti-pattern**: Services should NOT subscribe to EventBus (use Handlers instead)

**Queue**
- **Purpose**: FIFO queue processing with background worker
- **Scope**: Sequential item processing, ensures ordering guarantees
- **Examples**:
  - `StatusQueue`: Async queue for status panel updates
  - `QueryQueue`: Async queue for sequential query processing
- **When to use**: When you need FIFO processing with a background worker (typically wraps `AsyncQueueProcessor`)

**Processor**
- **Purpose**: Generic/reusable processing patterns
- **Scope**: Framework-level abstractions, often generic/templated
- **Examples**:
  - `AsyncQueueProcessor<T>`: Generic async FIFO queue processor
- **When to use**: When creating reusable patterns that eliminate code duplication across similar components

**Handler**
- **Purpose**: Event subscribers that react to domain events
- **Scope**: Subscribe to EventBus, delegate to services, typically stateless
- **Responsibilities**:
  - Subscribe to specific event types
  - Process events and coordinate responses
  - Update UI state based on events
  - Delegate work to services
- **Characteristics**:
  - Stateless or minimal state (just references to services/widgets)
  - Handler methods named `handle_<event_type>`
  - Coordinate between events and services/widgets
- **Examples**:
  - `QueryHandler`: Processes queries through agent loop
  - `ConnectionHandler`: Handles `ConnectionStatusChanged` and `ReconnectProgress` events
  - `RefreshHandler`: Handles `ArtifactsFetched` events
- **When to use**: When a class primarily responds to events from the EventBus
- **Anti-pattern**: Handlers should NOT maintain business state (use Services instead)

**Coordinator**
- **Purpose**: Multi-service orchestration and wiring
- **Scope**: Initializes multiple services, coordinates cross-cutting concerns
- **Examples**:
  - `MCPCoordinator`: Initializes MCP connections and coordinates related services
- **When to use**: When a class's main job is to wire together and orchestrate multiple services

**Orchestrator**
- **Purpose**: Strategy/algorithm selection (behavioral pattern)
- **Scope**: Chooses appropriate strategy based on context, delegates execution
- **Examples**:
  - `CompletionOrchestrator`: Selects completion strategy based on input type
- **When to use**: When implementing the Strategy pattern for runtime algorithm selection

### Connection Management Naming

The codebase uses two distinct connection managers with clear scopes:

- **`MCPConnectionManager`** (application layer): Manages ALL MCP server connections (aggregate/global scope)
- **`SingleConnectionManager`** (infrastructure layer): Manages a SINGLE connection's lifecycle (per-client scope)

This naming makes the scope distinction immediately clear without reading implementation details.

### Cache Abstractions

- **`Cache`** (protocol): Generic caching protocol for dependency injection
- **`MemoryCache`**: Simple in-memory dictionary-based implementation
- Direct usage preferred over wrapper classes for simplicity

### Services vs Handlers Pattern Guidelines

The presentation layer uses complementary Services and Handlers patterns:

**When to create a Service:**
```python
# ✅ Good - manages state and lifecycle
class CacheService:
    def __init__(self, cache: Cache):
        self._cache = cache  # Internal state

    async def preload_data(self):
        # Load and cache data
        pass

    def get_cached(self, key: str):
        return self._cache.get(key)
```

**When to create a Handler:**
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

**Anti-patterns:**
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

## Recent Architectural Improvements

### Service Consolidation (2025-11-09)

**Problem**: `StatusQueue` and `QueryQueue` (formerly `QueryManager`) were nearly identical implementations of the same async queue pattern, resulting in ~200 lines of code duplication.

**Solution**: Created `AsyncQueueProcessor<T>` - a generic, reusable async FIFO queue processor that both services now wrap.

**Benefits**:
- ✅ **Eliminated ~200 lines of duplication** between StatusQueue and QueryQueue
- ✅ **Established reusable pattern** for future queue-based services (e.g., artifact processing queues)
- ✅ **Zero breaking changes** - all public APIs preserved
- ✅ **Type-safe and well-documented** - comprehensive error handling and examples
- ✅ **Supports both sync and async processors** - auto-detects via `asyncio.iscoroutinefunction()`

**Pattern**:
```python
# Generic queue processor
processor = AsyncQueueProcessor[T](
    processor=process_item,  # sync or async function
    name="QueueName"
)

await processor.start()
await processor.enqueue(item)
await processor.stop()
```

### Lazy Service Initialization

**Pattern**: `ServiceContainer` uses lazy initialization via `@property` decorators for all services except MCP initialization (which must be eager for autocomplete).

**Benefits**:
- ✅ **No multi-step initialization ceremony** - services created on first access
- ✅ **Clear dependency order** - enforced by property access patterns
- ✅ **Reduced startup time** - only create services when actually used
- ✅ **Simpler testing** - can mock individual services without creating entire graph

### Event Bus Pattern

**Design Decision**: EventBus uses **synchronous fire-and-forget** pattern, not async.

**Rationale**:
- Events are notifications, not RPC calls
- Handlers schedule async work via `asyncio.create_task()` for non-blocking execution
- Making EventBus async would require all publishers to be async, adding complexity without benefit
- Current pattern correctly separates event propagation from async work execution

**Pattern**:
```python
# Event handler (synchronous)
def handle_event(self, event: SomeEvent):
    # Schedule async work without blocking
    asyncio.create_task(self._do_async_work(event))
```

