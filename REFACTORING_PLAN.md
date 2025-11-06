# Nexus Codebase Refactoring Plan

## Executive Summary

This document provides a comprehensive analysis of the Nexus codebase and outlines a detailed refactoring plan to improve code organization, decouple responsibilities, remove dead code, simplify implementations, and introduce maintainable abstractions. The refactoring will be done incrementally to avoid disrupting current functionality.

**Code Statistics:**
- **Largest files:** app.py (993 lines), autocomplete.py (905 lines), mcp_panel.py (866 lines), client.py (784 lines)
- **Total Python files:** ~30 files
- **Key concern:** Multiple god/blob classes with mixed responsibilities

---

## 1. Current Architecture Issues

### 1.1 God/Blob Classes

#### **NexusApp (`tui/app.py` - 993 lines)**

**Problems:**
- **Too many responsibilities** (violates Single Responsibility Principle):
  - UI lifecycle management (mounting, composing)
  - MCP connection initialization and management
  - Server status change callbacks
  - Artifact refresh orchestration with complex debouncing
  - Prompt caching and preloading
  - Autocomplete widget setup
  - Query processing coordination
  - Health check scheduling
  - Task management (refresh tasks tracking)

- **Complex state management:**
  ```python
  - self._mcp_initialized
  - self._refresh_tasks
  - self._refresh_lock
  - self._last_reconnect_progress_update
  - self._prompt_info_cache
  - self._prompt_schema_cache
  ```

- **Long methods:**
  - `_initialize_mcp_connections_async()` (90 lines)
  - `_refresh_mcp_panel_with_status()` (150+ lines)
  - `_periodic_artifact_refresh()` (100+ lines)
  - `_process_query()` (80+ lines)

**Impact:** Hard to test, maintain, and extend. Changes ripple across unrelated functionality.

---

#### **ArtifactManager (`core/artifact_manager.py` - 627 lines)**

**Problems:**
- **Mixed responsibilities:**
  - Configuration loading and validation
  - MCP client lifecycle management
  - Connection status tracking
  - Artifact fetching with retry logic
  - Caching layer implementation
  - Callback management and invocation
  - Change detection logic

- **Tight coupling:**
  - Directly manages MCPAuthClient instances
  - Knows about UI callbacks (status changes, reconnect progress)
  - Mixes business logic with infrastructure concerns

- **Complex methods:**
  - `initialize()` with nested callback factories (lines 60-128)
  - `get_server_artifacts()` with retry logic (lines 482-576)
  - `_fetch_with_retry()` generic retry mechanism (lines 433-480)

**Impact:** Difficult to unit test, hard to reuse components, tight coupling to UI layer.

---

#### **MCPAuthClient (`mcp_client/client.py` - 784 lines)**

**Problems:**
- **Multiple concerns in one class:**
  - Low-level connection management (streams, sessions)
  - Reconnection logic with exponential backoff
  - Health checking with periodic tasks
  - All MCP protocol operations (tools, prompts, resources)
  - Interactive CLI mode (not used in TUI)
  - OAuth flow handling

- **Complex connection lifecycle:**
  - Background connection task
  - Health check task
  - Stop/ready events coordination
  - Status transitions (5 states)

- **Duplicate code:**
  - `_run_session()` and `_setup_session()` are very similar
  - Reconnection logic duplicated in exception handler and normal path

**Impact:** Difficult to test individual concerns, hard to understand lifecycle, coupling of protocol operations with connection management.

---

#### **CommandControlAgent (`core/command_control.py` - 471 lines)**

**Problems:**
- **Complex parsing logic:**
  - `_parse_command_arguments()` (230 lines) - handles multiple formats, schema variations, defaults
  - `_parse_key_value_pairs()` (60 lines) - custom parser for arguments
  - Nested conditionals for different schema formats

- **Mixed responsibilities:**
  - Resource extraction
  - Command processing
  - Schema parsing and validation
  - Message conversion

- **Hard to extend:**
  - Adding new argument formats requires deep changes
  - Schema handling is brittle (many isinstance checks)

**Impact:** Hard to maintain, test individual parsing logic, extend with new formats.

---

### 1.2 Module Organization Issues

#### **Lack of Clear Boundaries**

```
Current structure (issues highlighted):

src/nxs/
├── core/                          # Mix of domain logic and infrastructure
│   ├── artifact_manager.py       # Handles UI callbacks (boundary violation)
│   ├── command_control.py        # Complex parsing logic (should be extracted)
│   ├── chat.py                   # Minimal, good
│   ├── tools.py                  # Minimal, good
│   ├── mcp_config.py            # Config only, good
│   └── claude.py                 # Wrapper only, good
├── mcp_client/                   # Client concerns but also has CLI
│   ├── client.py                 # Too large, mixed concerns
│   ├── auth.py                   # Good
│   ├── storage.py               # Good
│   └── callback.py              # Good
├── mcp_client.py                # Legacy file (marked for backwards compatibility)
├── tui/                          # UI concerns but also has business logic
│   ├── app.py                    # God class with MCP management
│   ├── query_manager.py         # Good - single purpose
│   ├── status_queue.py          # Good - single purpose
│   └── widgets/
│       ├── autocomplete.py      # Very large (905 lines)
│       ├── mcp_panel.py         # Very large (866 lines)
│       └── ...
```

**Issues:**
1. **No clear domain layers** - UI, domain, and infrastructure are mixed
2. **Missing abstractions** - No interfaces/protocols for key contracts
3. **Circular dependencies potential** - Core knows about UI (callbacks)
4. **No separation of concerns** - Connection management, protocol operations, and business logic are intertwined

---

### 1.3 Dead Code

**Identified dead/unused code:**

1. **`MCPAuthClient._run_session()` (lines 464-490 in client.py)**
   - Similar to `_setup_session()` but never called
   - Contains interactive loop call which is CLI-specific
   - Should be removed or consolidated

2. **`MCPAuthClient.run_interactive()` and `interactive_loop()` (lines 604-658)**
   - CLI functionality not used in TUI context
   - Main entry point uses this but app doesn't
   - Could be extracted to a separate CLI client

3. **Legacy `mcp_client.py` (113 lines)**
   - Marked as "backwards compatibility"
   - Simple wrapper around ClientSession
   - Check if actually used anywhere, likely can be removed

4. **Unused imports across files:**
   - Many files have unused imports that were left from refactoring

5. **Command-line entry point in `client.py` (lines 738-785)**
   - Typer CLI app not used when client is imported as library
   - Should be extracted to `__main__.py` in mcp_client package

---

### 1.4 Code Simplification Opportunities

#### **Complex Command Parsing**

**Current state** (`command_control.py:115-330`):
```python
def _parse_command_arguments(self, query, command_name, prompt):
    """230 lines of nested conditionals"""
    - Handle list schema format
    - Handle dict schema format
    - Handle object attribute format
    - Parse positional args
    - Parse key=value args
    - Handle quoted strings
    - Extract defaults
    - Validate required args
```

**Issues:**
- Single method doing too much
- Multiple parsing strategies in one place
- Hard to test individual strategies
- Fragile error handling

---

#### **Refresh Orchestration**

**Current state** (`app.py:348-573`):
```python
def _schedule_refresh():
    """Cancel previous, create new task, track it"""

async def _refresh_mcp_panel_with_status():
    """150+ lines with complex locking, timeouts, caching logic"""
    - Acquire lock
    - Check server statuses
    - Fetch artifacts with timeout
    - Handle cache comparison
    - Update display
    - Schedule status clearing
```

**Issues:**
- Complex task cancellation and tracking
- Mixed concerns (locking, fetching, caching, UI updates)
- Hard to reason about state
- Difficult to test

---

#### **Nested Callback Factories**

**Current state** (`artifact_manager.py:83-102`):
```python
def make_status_callback(name: str):
    def status_callback(status: ConnectionStatus):
        self._server_statuses[name] = status
        if self.on_status_change:
            try:
                self.on_status_change(name, status)
            except Exception as e:
                logger.error(...)
    return status_callback
```

**Issues:**
- Factory pattern adds complexity
- Error handling duplicated
- Could use functools.partial instead

---

#### **Duplicate Status Formatting**

**Found in:**
- `mcp_panel.py:_format_server_display()` - standalone function
- `MCPPanel.update_servers()` - similar logic
- Status text generation duplicated

---

### 1.5 Misaligned Responsibilities

#### **UI Callbacks in Core Layer**

```python
# artifact_manager.py (CORE layer)
def __init__(self, ..., on_status_change: Callable, on_reconnect_progress: Callable):
    """Core component knows about UI callbacks"""
```

**Problem:** Core layer is aware of and coupled to UI layer. Violates dependency inversion.

**Should be:** Core publishes events/messages, UI subscribes.

---

#### **MCP Management in UI Layer**

```python
# app.py (UI layer)
async def _initialize_mcp_connections_async(self):
    """UI component managing MCP connections"""
    await self.artifact_manager.initialize()
    # ... complex initialization logic
```

**Problem:** UI layer orchestrating business/infrastructure concerns.

**Should be:** UI delegates to a coordinator/service in the core layer.

---

#### **Prompt Caching in UI**

```python
# app.py (UI layer)
async def _preload_all_prompt_info(self):
    """UI component caching domain data"""
    self._prompt_info_cache = {}
    self._prompt_schema_cache = {}
```

**Problem:** UI responsible for data caching strategy.

**Should be:** Core/service layer handles caching, UI just consumes.

---

### 1.6 Missing Abstractions

#### **No Protocol/Interface for MCP Clients**

**Current:** Concrete `MCPAuthClient` used everywhere
```python
clients: dict[str, MCPAuthClient]
```

**Should have:**
```python
# Abstract protocol
class MCPClient(Protocol):
    async def list_tools(self) -> list[Tool]: ...
    async def call_tool(self, name: str, args: dict) -> CallToolResult: ...
    # ... other operations

clients: dict[str, MCPClient]
```

**Benefits:**
- Easy to mock for testing
- Can have multiple implementations
- Clear contract

---

#### **No Connection Manager Abstraction**

**Current:** `ArtifactManager` and `MCPAuthClient` both handle connections

**Should have:**
```python
class ConnectionManager:
    """Handles connection lifecycle, reconnection, health checks"""
    async def connect(server_config: ServerConfig) -> MCPClient
    async def disconnect(server_name: str)
    def get_status(server_name: str) -> ConnectionStatus
```

---

#### **No Parser Abstraction**

**Current:** Parsing logic embedded in `CommandControlAgent`

**Should have:**
```python
class ArgumentParser(Protocol):
    def parse(self, query: str, schema: Schema) -> dict[str, Any]

class PositionalArgumentParser(ArgumentParser): ...
class KeyValueArgumentParser(ArgumentParser): ...
class CompositeArgumentParser(ArgumentParser): ...
```

---

#### **No Caching Abstraction**

**Current:** Caching logic scattered across `ArtifactManager` and `NexusApp`

**Should have:**
```python
class Cache(Protocol[K, V]):
    def get(self, key: K) -> V | None
    def set(self, key: K, value: V)
    def clear(self, key: K | None = None)
    def has_changed(self, key: K, value: V) -> bool
```

---

#### **No Event/Message Bus**

**Current:** Direct callbacks from core to UI

**Should have:**
```python
class EventBus:
    def subscribe(self, event_type: Type[Event], handler: Callable)
    def publish(self, event: Event)

# Usage
bus.subscribe(ConnectionStatusChanged, self._on_connection_changed)
bus.publish(ConnectionStatusChanged(server_name="foo", status=CONNECTED))
```

---

## 2. Refactoring Plan

### Phase 1: Extract and Simplify (No Breaking Changes)

**Goal:** Extract reusable components and simplify complex methods without changing public APIs.

#### **Step 1.1: Extract Command Parsing** 🔴 **High Priority**

**Target:** `CommandControlAgent._parse_command_arguments()` and `_parse_key_value_pairs()`

**Actions:**
1. Create `core/parsers/` package:
   ```
   core/parsers/
   ├── __init__.py
   ├── base.py              # ArgumentParser protocol
   ├── positional.py        # PositionalArgumentParser
   ├── key_value.py         # KeyValueArgumentParser
   ├── schema_adapter.py    # Adapts various schema formats
   └── composite.py         # CompositeArgumentParser
   ```

2. Extract `_parse_key_value_pairs()` → `KeyValueArgumentParser.parse()`

3. Extract schema handling logic → `SchemaAdapter` class

4. Refactor `_parse_command_arguments()` to use new parsers

5. Add comprehensive unit tests for parsers

**Benefits:**
- Testable parsing logic
- Easier to add new formats
- Clearer separation of concerns
- Reusable across project

**Estimated effort:** 4-6 hours

---

#### **Step 1.2: Extract Connection Management** 🔴 **High Priority**

**Target:** `MCPAuthClient` connection lifecycle logic

**Actions:**
1. Create `mcp_client/connection/` package:
   ```
   mcp_client/connection/
   ├── __init__.py
   ├── manager.py           # ConnectionManager
   ├── health.py            # HealthChecker
   ├── reconnect.py         # ReconnectionStrategy
   └── lifecycle.py         # ConnectionLifecycle
   ```

2. Extract reconnection logic → `ExponentialBackoffStrategy`

3. Extract health checking → `HealthChecker` class

4. Extract connection lifecycle → `ConnectionLifecycle` class

5. Refactor `MCPAuthClient` to use these components

**Benefits:**
- Testable connection logic
- Reusable reconnection strategies
- Clearer separation of concerns
- Can swap strategies easily

**Estimated effort:** 6-8 hours

---

#### **Step 1.3: Extract Refresh Orchestration** 🟡 **Medium Priority**

**Target:** `NexusApp._schedule_refresh()` and `_refresh_mcp_panel_with_status()`

**Actions:**
1. Create `tui/services/` package:
   ```
   tui/services/
   ├── __init__.py
   ├── refresh_coordinator.py   # RefreshCoordinator
   └── artifact_fetcher.py      # ArtifactFetcher
   ```

2. Extract task management → `RefreshCoordinator`:
   ```python
   class RefreshCoordinator:
       def schedule_refresh(self, server_name: str | None, delay: float = 0.0)
       def cancel_pending_refreshes(self)
       async def refresh(self, server_name: str | None)
   ```

3. Extract fetching logic → `ArtifactFetcher`:
   ```python
   class ArtifactFetcher:
       async def fetch_with_timeout(self, server_name: str) -> Artifacts
       async def fetch_all(self) -> dict[str, Artifacts]
   ```

4. Refactor `NexusApp` to delegate to these services

**Benefits:**
- Testable refresh logic
- Clearer responsibilities
- Reduced complexity in NexusApp
- Reusable components

**Estimated effort:** 5-7 hours

---

#### **Step 1.4: Extract and Simplify Callback Management** 🟡 **Medium Priority**

**Target:** Callback factories in `ArtifactManager`

**Actions:**
1. Replace factory functions with `functools.partial`:
   ```python
   # Before
   def make_status_callback(name: str):
       def status_callback(status: ConnectionStatus):
           # ...
       return status_callback

   # After
   from functools import partial
   callback = partial(self._handle_status_change, server_name=name)
   ```

2. Create dedicated callback handler methods:
   ```python
   def _handle_status_change(self, status: ConnectionStatus, server_name: str):
       """Single method handling status changes"""

   def _handle_reconnect_progress(self, attempts: int, max_attempts: int,
                                   next_retry_delay: float, server_name: str):
       """Single method handling reconnect progress"""
   ```

3. Centralize error handling in callback methods

**Benefits:**
- Simpler code
- Less nesting
- Consistent error handling
- Easier to test

**Estimated effort:** 2-3 hours

---

### Phase 2: Introduce Abstractions and Protocols

**Goal:** Add interfaces/protocols for key components to enable better testing and extensibility.

#### **Step 2.1: Define Core Protocols** 🔴 **High Priority**

**Actions:**
1. Create `core/protocols.py`:
   ```python
   from typing import Protocol

   class MCPClient(Protocol):
       """Protocol for MCP client operations"""
       async def list_tools(self) -> list[Tool]: ...
       async def call_tool(self, name: str, args: dict) -> CallToolResult: ...
       async def list_prompts(self) -> list[Prompt]: ...
       async def get_prompt(self, name: str, args: dict) -> list[PromptMessage]: ...
       async def list_resources(self) -> list[Resource]: ...
       async def read_resource(self, uri: str) -> Any: ...
       @property
       def is_connected(self) -> bool: ...

   class ArgumentParser(Protocol):
       """Protocol for argument parsing"""
       def parse(self, query: str, schema: Any) -> dict[str, Any]: ...

   class Cache(Protocol[K, V]):
       """Protocol for caching"""
       def get(self, key: K) -> V | None: ...
       def set(self, key: K, value: V) -> None: ...
       def clear(self, key: K | None = None) -> None: ...
   ```

2. Update type hints across codebase to use protocols:
   ```python
   # Before
   clients: dict[str, MCPAuthClient]

   # After
   clients: dict[str, MCPClient]
   ```

**Benefits:**
- Clear contracts
- Easy mocking for tests
- Type safety
- Documentation via types

**Estimated effort:** 3-4 hours

---

#### **Step 2.2: Implement Event Bus** 🟡 **Medium Priority**

**Target:** Replace direct callbacks with event-based communication

**Actions:**
1. Create `core/events/` package:
   ```python
   core/events/
   ├── __init__.py
   ├── bus.py                 # EventBus implementation
   ├── types.py               # Event types
   └── handlers.py            # Handler registry
   ```

2. Define event types:
   ```python
   @dataclass
   class Event:
       timestamp: float = field(default_factory=time.time)

   @dataclass
   class ConnectionStatusChanged(Event):
       server_name: str
       status: ConnectionStatus

   @dataclass
   class ReconnectProgress(Event):
       server_name: str
       attempts: int
       max_attempts: int
       next_retry_delay: float

   @dataclass
   class ArtifactsFetched(Event):
       server_name: str
       artifacts: dict[str, list]
   ```

3. Implement event bus:
   ```python
   class EventBus:
       def __init__(self):
           self._handlers: dict[Type[Event], list[Callable]] = {}

       def subscribe(self, event_type: Type[Event], handler: Callable[[Event], None]):
           if event_type not in self._handlers:
               self._handlers[event_type] = []
           self._handlers[event_type].append(handler)

       def publish(self, event: Event):
           event_type = type(event)
           for handler in self._handlers.get(event_type, []):
               try:
                   handler(event)
               except Exception as e:
                   logger.error(f"Error in event handler: {e}")
   ```

4. Refactor to use events:
   ```python
   # Core layer publishes
   event_bus.publish(ConnectionStatusChanged(
       server_name="foo",
       status=ConnectionStatus.CONNECTED
   ))

   # UI layer subscribes
   event_bus.subscribe(ConnectionStatusChanged, self._on_connection_changed)
   ```

**Benefits:**
- Decouples core from UI
- Easy to add new handlers
- Testable event flow
- Clear event history for debugging

**Estimated effort:** 6-8 hours

---

#### **Step 2.3: Implement Caching Abstraction** 🟢 **Low Priority**

**Actions:**
1. Create `core/cache/` package:
   ```python
   core/cache/
   ├── __init__.py
   ├── base.py                # Cache protocol
   ├── memory.py              # In-memory cache
   └── ttl.py                 # TTL-based cache
   ```

2. Implement cache:
   ```python
   class MemoryCache(Cache[K, V]):
       def __init__(self):
           self._data: dict[K, V] = {}

       def get(self, key: K) -> V | None:
           return self._data.get(key)

       def set(self, key: K, value: V) -> None:
           self._data[key] = value

       def clear(self, key: K | None = None) -> None:
           if key is None:
               self._data.clear()
           else:
               self._data.pop(key, None)

       def has_changed(self, key: K, value: V) -> bool:
           cached = self.get(key)
           return cached is None or cached != value
   ```

3. Replace caching logic in `ArtifactManager` and `NexusApp` with cache instances

**Benefits:**
- Reusable caching
- Easy to swap implementations
- Testable caching logic
- Can add features (TTL, LRU, etc.)

**Estimated effort:** 4-5 hours

---

### Phase 3: Decompose God Classes

**Goal:** Break down large classes into focused, single-responsibility components.

#### **Step 3.1: Decompose NexusApp** 🔴 **High Priority**

**Current responsibilities:**
1. UI lifecycle (mounting, composing)
2. MCP connection orchestration
3. Status change handling
4. Refresh coordination
5. Prompt caching
6. Autocomplete setup
7. Query processing
8. Periodic tasks

**Proposed structure:**
```
tui/
├── app.py                        # Slim orchestrator (200-300 lines)
├── services/
│   ├── mcp_coordinator.py        # MCP initialization & coordination
│   ├── refresh_coordinator.py    # Artifact refresh logic
│   ├── prompt_service.py         # Prompt caching & preloading
│   └── autocomplete_service.py   # Autocomplete setup & management
└── handlers/
    ├── connection_handler.py     # Handle connection events
    ├── query_handler.py          # Handle query processing
    └── refresh_handler.py        # Handle refresh events
```

**Refactored NexusApp:**
```python
class NexusApp(App):
    """Slim TUI application orchestrator"""

    def __init__(self, agent_loop, artifact_manager):
        super().__init__()
        self.agent_loop = agent_loop
        self.artifact_manager = artifact_manager

        # Inject services
        self.mcp_coordinator = MCPCoordinator(artifact_manager)
        self.refresh_coordinator = RefreshCoordinator(artifact_manager)
        self.prompt_service = PromptService(artifact_manager)
        self.query_manager = QueryManager(processor=self._process_query)
        self.status_queue = StatusQueue(status_panel_getter=self._get_status_panel)

    def compose(self) -> ComposeResult:
        """Just UI composition"""
        ...

    async def on_mount(self) -> None:
        """Delegate to coordinators"""
        await self.query_manager.start()
        await self.status_queue.start()
        await self.mcp_coordinator.initialize()
        ...
```

**Services:**
```python
class MCPCoordinator:
    """Handles MCP initialization and lifecycle"""

    async def initialize(self):
        """Initialize all MCP connections"""
        await self.artifact_manager.initialize()
        await self._load_resources_and_commands()
        await self.prompt_service.preload_all()

class RefreshCoordinator:
    """Handles artifact refresh scheduling"""

    def schedule_refresh(self, server_name: str | None, delay: float = 0.0):
        ...

class PromptService:
    """Handles prompt caching and preloading"""

    async def preload_all(self):
        ...

    def get_cached_info(self, command: str) -> str | None:
        ...
```

**Benefits:**
- NexusApp focused on UI orchestration only
- Services are testable in isolation
- Clear separation of concerns
- Easy to modify/extend individual services
- Reduced file size (993 → ~300 lines for app.py)

**Estimated effort:** 10-12 hours

---

#### **Step 3.2: Decompose ArtifactManager** 🔴 **High Priority**

**Current responsibilities:**
1. Config loading
2. Connection management
3. Artifact fetching
4. Caching
5. Status tracking
6. Callback invocation
7. Change detection

**Proposed structure:**
```
core/
├── artifact_manager.py           # Slim facade (200-300 lines)
├── artifacts/
│   ├── repository.py             # Artifact fetching & aggregation
│   ├── cache.py                  # Artifact caching logic
│   └── change_detector.py        # Detect artifact changes
└── connection/
    ├── manager.py                # Connection lifecycle
    └── registry.py               # Client registry
```

**Refactored ArtifactManager:**
```python
class ArtifactManager:
    """Facade for artifact operations"""

    def __init__(self, config: Optional[MCPServersConfig] = None):
        self.config = config or load_mcp_config()
        self.connection_manager = ConnectionManager(self.config)
        self.artifact_repository = ArtifactRepository(self.connection_manager)
        self.artifact_cache = ArtifactCache()

    async def initialize(self, use_auth: bool = False):
        await self.connection_manager.connect_all(use_auth)

    async def get_tools(self) -> list[Tool]:
        return await self.artifact_repository.get_all_tools()

    async def get_prompts(self) -> list[Prompt]:
        return await self.artifact_repository.get_all_prompts()

    # ... delegate to services
```

**Services:**
```python
class ConnectionManager:
    """Manages MCP client connections"""

    async def connect(self, server_name: str, config: ServerConfig, use_auth: bool):
        ...

    async def disconnect(self, server_name: str):
        ...

    def get_status(self, server_name: str) -> ConnectionStatus:
        ...

class ArtifactRepository:
    """Fetches and aggregates artifacts"""

    async def get_all_tools(self) -> list[Tool]:
        ...

    async def get_server_artifacts(self, server_name: str) -> dict:
        ...

class ArtifactCache:
    """Caches artifacts with change detection"""

    def get_cached(self, server_name: str) -> dict | None:
        ...

    def has_changed(self, server_name: str, artifacts: dict) -> bool:
        ...
```

**Benefits:**
- Clear separation of concerns
- Testable components
- Reusable services
- Event bus integration point
- Reduced file size (627 → ~200 lines for manager)

**Estimated effort:** 8-10 hours

---

#### **Step 3.3: Decompose MCPAuthClient** 🟡 **Medium Priority**

**Current responsibilities:**
1. Low-level connection (streams, transports)
2. Session management
3. Reconnection with backoff
4. Health checking
5. All MCP operations (tools, prompts, resources)
6. Interactive CLI mode

**Proposed structure:**
```
mcp_client/
├── client.py                     # Slim protocol client (200-300 lines)
├── connection/
│   ├── manager.py                # Connection lifecycle
│   ├── health.py                 # Health checker
│   └── reconnect.py              # Reconnection strategy
├── operations/
│   ├── tools.py                  # Tool operations
│   ├── prompts.py                # Prompt operations
│   └── resources.py              # Resource operations
└── cli/
    └── interactive.py            # CLI interactive mode
```

**Refactored MCPAuthClient:**
```python
class MCPAuthClient:
    """MCP protocol client (slim wrapper)"""

    def __init__(self, server_url: str, transport_type: str = "streamable_http"):
        self.server_url = server_url
        self.transport_type = transport_type
        self.session: ClientSession | None = None

        # Delegate to components
        self.connection_manager = ConnectionLifecycleManager(server_url, transport_type)
        self.tools_operations = ToolsOperations(lambda: self.session)
        self.prompts_operations = PromptsOperations(lambda: self.session)
        self.resources_operations = ResourcesOperations(lambda: self.session)

    async def connect(self, use_auth: bool = False):
        self.session = await self.connection_manager.connect(use_auth)

    async def disconnect(self):
        await self.connection_manager.disconnect()

    # Delegate operations
    async def list_tools(self) -> list[Tool]:
        return await self.tools_operations.list_tools()

    async def call_tool(self, name: str, args: dict) -> CallToolResult:
        return await self.tools_operations.call_tool(name, args)
```

**Benefits:**
- Clear separation of protocol operations
- Testable components independently
- Can mock individual operations
- CLI extracted to separate module
- Reduced file size (784 → ~250 lines for client)

**Estimated effort:** 8-10 hours

---

### Phase 4: Remove Dead Code

**Goal:** Clean up unused code to reduce maintenance burden.

#### **Step 4.1: Remove Dead Code in MCPAuthClient** 🟢 **Low Priority**

**Actions:**
1. Remove `_run_session()` method (never called)
2. Move CLI code (`interactive_loop`, `run_interactive`, typer app) to `mcp_client/cli/interactive.py`
3. Create separate CLI entry point if needed

**Estimated effort:** 2-3 hours

---

#### **Step 4.2: Evaluate and Remove Legacy Code** 🟢 **Low Priority**

**Actions:**
1. Check if `mcp_client.py` is actually used:
   ```bash
   grep -r "from nxs.mcp_client import" src/
   grep -r "import nxs.mcp_client" src/
   ```

2. If not used, remove the file

3. Update documentation accordingly

**Estimated effort:** 1-2 hours

---

#### **Step 4.3: Clean Up Unused Imports** 🟢 **Low Priority**

**Actions:**
1. Use `autoflake` to detect unused imports:
   ```bash
   autoflake --remove-all-unused-imports --recursive src/
   ```

2. Review and apply changes

**Estimated effort:** 1 hour

---

### Phase 5: Improve Module Organization

**Goal:** Reorganize code into clear domain boundaries.

#### **Step 5.1: Establish Clear Layers** 🟡 **Medium Priority**

**Proposed structure:**
```
src/nxs/
├── domain/                       # Pure business logic (no dependencies on infra/ui)
│   ├── models/                   # Domain models
│   ├── services/                 # Domain services
│   └── events/                   # Domain events
├── infrastructure/               # External concerns (MCP, network, storage)
│   ├── mcp/                      # MCP client & operations
│   │   ├── client.py
│   │   ├── operations/
│   │   └── connection/
│   └── cache/                    # Caching implementations
├── application/                  # Use cases & application services
│   ├── services/                 # Application services
│   │   ├── artifact_service.py
│   │   ├── prompt_service.py
│   │   └── query_service.py
│   └── handlers/                 # Event handlers
└── presentation/                 # UI layer (Textual TUI)
    ├── app.py
    ├── widgets/
    ├── services/                 # UI-specific services
    └── handlers/                 # UI event handlers
```

**Migration plan:**
1. Create new structure alongside existing
2. Move files incrementally
3. Update imports
4. Remove old structure when done

**Benefits:**
- Clear dependencies (domain ← application ← infrastructure/presentation)
- Easier to understand architecture
- Testable without dependencies
- Can swap TUI for web UI easily

**Estimated effort:** 12-15 hours

---

## 3. Testing Strategy

### 3.1 Current Testing Gaps

**Issues:**
- Only one test file: `tests/test_main.py`
- No unit tests for individual components
- No integration tests for MCP operations
- No tests for TUI widgets
- Hard to test due to tight coupling

### 3.2 Testing Plan

#### **Phase 1: Add Unit Tests for Extracted Components**

**Priority order:**
1. Parsers (Step 1.1) - **High priority**
   - Test each parser independently
   - Test composite parser
   - Test schema adapters

2. Connection logic (Step 1.2) - **High priority**
   - Test reconnection strategies
   - Test health checker
   - Mock network operations

3. Services (Steps 3.1-3.3) - **Medium priority**
   - Test each service in isolation
   - Mock dependencies
   - Test error scenarios

#### **Phase 2: Add Integration Tests**

**Tests:**
- MCP client connection flow
- Artifact fetching and caching
- Query processing end-to-end
- UI interaction flows (using Textual's testing utilities)

#### **Phase 3: Add Property-Based Tests**

**Use Hypothesis for:**
- Command parsing with various inputs
- Argument combinations
- Schema variations

---

## 4. Implementation Timeline

### Week 1-2: Foundation
- [ ] Step 1.1: Extract command parsing (4-6h)
- [ ] Step 1.2: Extract connection management (6-8h)
- [ ] Step 2.1: Define core protocols (3-4h)
- [ ] Add unit tests for parsers and connection logic
- **Deliverable:** Reusable parsers, connection components with tests

### Week 3-4: Services & Abstractions
- [ ] Step 1.3: Extract refresh orchestration (5-7h)
- [ ] Step 1.4: Simplify callback management (2-3h)
- [ ] Step 2.2: Implement event bus (6-8h)
- [ ] Add unit tests for services
- **Deliverable:** Event-driven architecture, testable services

### Week 5-6: Decomposition
- [ ] Step 3.1: Decompose NexusApp (10-12h)
- [ ] Step 3.2: Decompose ArtifactManager (8-10h)
- [ ] Add integration tests
- **Deliverable:** Focused, single-responsibility classes

### Week 7-8: Polish & Cleanup
- [ ] Step 3.3: Decompose MCPAuthClient (8-10h)
- [ ] Step 4.1-4.3: Remove dead code (4-6h)
- [ ] Step 2.3: Implement caching abstraction (4-5h)
- [ ] Add comprehensive tests
- **Deliverable:** Clean, well-tested codebase

### Week 9-10: Reorganization (Optional)
- [ ] Step 5.1: Reorganize into layers (12-15h)
- [ ] Update documentation
- [ ] Final testing and validation
- **Deliverable:** Clear architectural boundaries

**Total estimated effort:** 80-100 hours (2-2.5 months part-time)

---

## 5. Risk Mitigation

### Risks & Mitigation Strategies

1. **Breaking existing functionality**
   - **Mitigation:** Incremental refactoring, comprehensive tests before changes
   - **Detection:** CI/CD with automated testing

2. **Performance regression**
   - **Mitigation:** Profile before and after changes
   - **Detection:** Performance benchmarks

3. **Introducing new bugs**
   - **Mitigation:** Code review, pair programming on critical sections
   - **Detection:** Increased test coverage

4. **Scope creep**
   - **Mitigation:** Stick to plan, defer new features
   - **Detection:** Regular progress reviews

---

## 6. Success Criteria

### Quantitative Metrics

- [ ] **Reduce largest file sizes by 60%+**
  - NexusApp: 993 → ~300 lines
  - ArtifactManager: 627 → ~200 lines
  - MCPAuthClient: 784 → ~250 lines
  - AutoComplete: 905 → ~400 lines (extract generators)
  - MCPPanel: 866 → ~400 lines (extract formatters)

- [ ] **Increase test coverage to 70%+**
  - Current: ~5% (only test_main.py)
  - Target: 70% line coverage, 60% branch coverage

- [ ] **Reduce cyclomatic complexity**
  - Methods with complexity > 15: 0
  - Average method complexity: < 5

- [ ] **Eliminate circular dependencies**
  - Core ← Application ← Infrastructure/Presentation
  - Zero circular imports

### Qualitative Metrics

- [ ] **Single Responsibility Principle**
  - Each class has one clear purpose
  - Easy to explain what a class does in one sentence

- [ ] **Dependency Inversion**
  - Core depends on abstractions, not concretions
  - UI depends on application services, not infrastructure

- [ ] **Open/Closed Principle**
  - Easy to add new parsers without modifying existing code
  - Easy to add new MCP operations without modifying client
  - Easy to add new UI components without modifying core

- [ ] **Testability**
  - Components can be tested in isolation
  - Dependencies can be easily mocked
  - Tests run fast (< 1 second for unit tests)

- [ ] **Maintainability**
  - New developers can understand architecture in < 1 day
  - Changes can be made confidently without breaking unrelated functionality
  - Clear boundaries between layers

---

## 7. Additional Recommendations

### 7.1 Documentation Improvements

1. **Add Architecture Decision Records (ADRs)**
   - Document why certain patterns were chosen
   - Useful for future maintainers

2. **Create API documentation**
   - Use Sphinx with autodoc
   - Document protocols/interfaces clearly

3. **Add sequence diagrams**
   - Query processing flow
   - MCP connection lifecycle
   - Artifact refresh flow

### 7.2 Code Quality Tools

1. **Setup pre-commit hooks**
   - Black for formatting
   - Ruff for linting
   - MyPy for type checking
   - Run tests before commit

2. **Add CI/CD pipeline**
   - Run tests on every PR
   - Check coverage thresholds
   - Lint and type check
   - Build documentation

3. **Use code complexity metrics**
   - Radon for cyclomatic complexity
   - Fail build if complexity > threshold

### 7.3 Performance Considerations

1. **Profile the application**
   - Identify bottlenecks before refactoring
   - Ensure refactoring doesn't degrade performance

2. **Consider async optimizations**
   - Use `asyncio.gather()` for parallel operations
   - Implement connection pooling if needed

3. **Optimize caching strategy**
   - Add TTL to cache entries
   - Implement cache invalidation strategies

---

## 8. Conclusion

This refactoring plan addresses all identified issues:

✅ **Better module organization** - Clear layers with domain, application, infrastructure, and presentation

✅ **Decoupled responsibilities** - God classes broken down into focused services

✅ **Dead code removal** - CLI code extracted, unused methods removed

✅ **Simplified code** - Complex methods extracted into dedicated components

✅ **Aligned responsibilities** - Core doesn't know about UI, clear event flow

✅ **Abstractions for maintainability** - Protocols, event bus, caching abstraction

The plan is **incremental**, **testable**, and **low-risk**. Each phase delivers value independently and can be paused/resumed without leaving the codebase in a broken state.

**Next step:** Review with team, prioritize phases, and begin implementation!
