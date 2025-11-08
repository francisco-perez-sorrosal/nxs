# Nexus Phase 3 Refinement Plan - Architectural Consolidation

## Executive Summary

After completing Phases 1-2 of the Nexus refactoring, the codebase has achieved significant improvements in decomposition, separation of concerns, and pattern consistency. However, a comprehensive architectural analysis has revealed **35+ distinct issues** across 5 major categories that must be addressed to achieve true architectural excellence.

**Phase 3 Goals:**
1. **Fix Critical Layer Violations** - Eliminate core-to-infrastructure dependencies
2. **Consolidate Dual Responsibilities** - Separate connection management from artifact management
3. **Reduce God Objects** - Decompose NexusApp and simplify service coordination
4. **Establish Clean Boundaries** - Enforce proper layering and dependency direction
5. **Remove Technical Debt** - Eliminate debugging code, print statements, and redundancies

**Timeline:** 5-6 weeks, 30-35 hours total effort
**Risk Level:** Medium (requires careful refactoring of core components)

---

## Phase 1-3 Achievements & Remaining Issues

### ✅ What Was Accomplished

**Phase 1-2 Successes:**
- Protocol abstractions (MCPClient, Cache, ArgumentParser)
- Event-driven architecture (EventBus with 3 event types)
- Parser extraction (composite, positional, key-value strategies)
- Connection management decomposition (ConnectionManager, HealthChecker, ReconnectionStrategy)
- Widget decomposition (AutoComplete 905→120 lines, MCPPanel 838→~300 lines)
- Service/Handler pattern established
- Completion strategy pattern implemented

### ❌ Critical Issues Remaining

**Architecture Analysis Summary:**
- **6 Critical Layer Violations** - Core depends on infrastructure
- **8 Package Structure Issues** - Poor cohesion, over-engineering
- **7 Redundancies** - Duplicate code, state, caching
- **9 Abstraction Problems** - Mutable state, dual responsibilities
- **5 Inconsistent Patterns** - Mixed logging, debugging code, callbacks

**Severity Breakdown:**
- **MUST FIX (Critical):** 6 issues affecting architecture fundamentals
- **SHOULD FIX (High):** 11 issues impacting maintainability
- **COULD FIX (Medium/Low):** 18 issues for polish and optimization

---

## Critical Findings (MUST FIX)

### 1. Core Layer Depends on MCP Infrastructure
**Severity: CRITICAL**
**Files:** `core/artifact_manager.py:28`, `core/events/types.py`

**Problem:**
```python
from nxs.mcp_client.client import ConnectionStatus  # VIOLATION
from nxs.mcp_client.factory import ClientFactory      # VIOLATION
```

The domain layer (core) directly imports from infrastructure layer (mcp_client), violating clean architecture. ConnectionStatus is imported from TWO different locations.

**Impact:**
- Cannot test core without MCP infrastructure
- Impossible to swap MCP implementations
- Dependency Inversion Principle violated
- Core layer is not independently usable

---

### 2. ArtifactManager Has Dual Responsibilities
**Severity: CRITICAL**
**File:** `core/artifact_manager.py` (314 lines)

**Problem:**
ArtifactManager does TWO distinct things:
1. **Artifact Access** - Getting resources, prompts, tools (lines 142-237)
2. **Connection Management** - Client lifecycle, initialization, status tracking (lines 69-107)

Also manages:
- Client factory (lines 73-79)
- Artifact cache service (lines 58-62)
- Change detector (lines 61-62)
- Previous status tracking (line 64)
- Status change callbacks (lines 264-288)
- Reconnection progress (lines 290-313)

**Impact:**
- Too many reasons to change
- Violates Single Responsibility Principle
- Hard to test concerns independently
- Mixed infrastructure and domain logic

---

### 3. NexusApp God Object
**Severity: CRITICAL**
**File:** `tui/app.py` (524 lines, 18+ methods, 22+ attributes)

**Problem:**
NexusApp manages everything:
- UI layout composition
- 8+ service lifecycle (StatusQueue, RefreshService, PromptService, AutocompleteService, MCPCoordinator, ConnectionHandler, QueryHandler, RefreshHandler)
- Event subscription (5+ event types)
- Widget getters (5+ getter methods)
- MCP initialization orchestration
- Resource/command state tracking

**Impact:**
- Extremely difficult to test
- Changes ripple across entire file
- High cognitive load
- No clear boundaries
- Violates SRP

---

### 4. AgentLoop Message State Leaks
**Severity: CRITICAL**
**File:** `core/chat.py:15`

**Problem:**
```python
self.messages: list[MessageParam] = []  # Shared mutable state
```

This list is:
- Mutable and shared across multiple `run()` calls
- Not cleared between sessions
- Modified by subclasses (CommandControlAgent appends directly)
- Causes state leaks between invocations

**Impact:**
- Messages accumulate from previous conversations
- Concurrent calls would share state
- Testing is difficult
- Violates stateless design

---

### 5. TUI Services Orchestrate Core Layer
**Severity: HIGH**
**Files:** `tui/services/mcp_coordinator.py`, `tui/services/prompt_service.py`

**Problem:**
```python
# MCPCoordinator
await self.artifact_manager.initialize(use_auth=use_auth)
resources = await self.artifact_manager.get_resource_list()

# PromptService
prompt_info = await self.artifact_manager.find_prompt(command)
```

TUI services are calling core layer implementation details and orchestrating initialization.

**Impact:**
- Tight coupling between layers
- TUI has too much knowledge of core
- Cannot test core independently
- Violates layering principle

---

### 6. ToolManager Error Handling Bug
**Severity: HIGH**
**File:** `core/tools.py:80-87`

**Problem:**
```python
try:
    tool_output: CallToolResult | None = await client.call_tool(...)
    # ...
except Exception as e:
    # BUG: tool_output might not exist if exception thrown before assignment
    tool_result_part = cls._build_tool_result_part(
        tool_use_id,
        json.dumps({"error": error_message}),
        "error" if tool_output and tool_output.isError else "success",  # NameError risk
    )
```

**Impact:**
- Potential NameError at runtime
- Error path references variable that may not exist
- Critical bug in error handling

---

## Architectural Violations

### AV1: Layer Dependency Direction

**Current (WRONG):**
```
Core Layer → Infrastructure Layer (mcp_client)
  ↓
Presentation Layer (tui) → Infrastructure Layer
```

**Should Be:**
```
Infrastructure Layer (mcp_client) → Core Protocols
     ↑
Core Layer → Core Protocols
     ↑
Presentation Layer (tui)
```

**Violations:**
1. `core/artifact_manager.py` imports `ConnectionStatus` from `mcp_client.client`
2. `core/artifact_manager.py` imports `ClientFactory` from `mcp_client.factory`
3. `core/events/types.py` imports from `mcp_client.connection.lifecycle`
4. `tui/app.py` imports `ConnectionStatus` from `mcp_client.client`

---

### AV2: Mixed Concerns Within Components

**CommandControlAgent** (`core/command_control.py`):
- Resource extraction (lines 27-42)
- Command parsing (lines 45-100)
- Prompt execution (lines 102-148)
- Message conversion (lines 208-242)
- Debugging code (lines 159-160, 165-166)

**ArtifactManager** (`core/artifact_manager.py`):
- Client lifecycle management
- Artifact repository access
- Cache management
- Change detection
- Status tracking
- Event publishing

---

### AV3: Inappropriate Service Coupling

**Pattern Found:**
```
TUI Service → Core Manager → Core Repository → Infrastructure Client
```

**Issue:**
TUI services (MCPCoordinator, PromptService) know too much about core implementation:
- Call `artifact_manager.initialize()`
- Access `artifact_manager.get_resource_list()`
- Orchestrate core layer operations

**Should Be:**
```
TUI Service → Core Facade (high-level interface)
```

---

## Package Structure Issues

### Issue 1: Artifacts Package Lacks Coherence

**Location:** `core/artifacts/`

**Contents:**
- `repository.py` - DATA ACCESS (fetches from clients)
- `cache.py` - DATA STORAGE (caches collections)
- `change_detector.py` - DATA COMPARISON (detects changes)

**Problem:**
These are three different concerns grouped together. Repository doesn't belong with cache/change_detector.

**Recommendation:**
- Keep repository in `core/artifacts/`
- Move cache to `core/cache/` (already has cache implementations)
- Move change_detector to separate `core/sync/` or keep in artifacts with clear rationale

---

### Issue 2: Completion Package Over-Engineered

**Location:** `tui/completion/` (843 lines total)

**Files:**
- `applier.py` (275 lines) - 10+ methods, many could be utilities
- `prompt_utils.py` (177 lines) - Utilities
- `schema_cache.py` (56 lines) - Potentially redundant with PromptService
- `command_completion.py` (84 lines)
- `argument_completion.py` (89 lines)
- `resource_completion.py` (49 lines)
- `orchestrator.py` + `strategy.py`

**Problem:**
- Too many layers of abstraction for autocomplete
- CompletionApplier is doing too much
- Utilities scattered across multiple files
- Schema caching might be duplicate

**Impact:**
- Difficult to understand completion flow
- High maintenance burden
- Excessive class creation

---

### Issue 3: Parser Package Structure

**Location:** `core/parsers/`

**Problem:**
- `base.py` Protocol is re-exported from `core/protocols.py` (confusion)
- Mix of implementations and utilities in same package
- Schema handling split between `schema_adapter.py` and `utils.py`

**Recommendation:**
- Keep protocol in `core/protocols.py` only
- Clearly separate strategies from utilities

---

### Issue 4: TUI Services Unclear Boundaries

**Location:** `tui/services/`

**Services:**
- `MCPCoordinator` - Orchestrates MCP initialization (should be in core?)
- `PromptService` - Manages prompt caching (business logic in TUI?)
- `AutocompleteService` - Manages autocomplete lifecycle
- `RefreshService` - Refreshes MCP panel

**Problem:**
These services are UI services but deeply coupled to core layer. They should be adapters/facades, not orchestrators.

---

### Issue 5: Handlers Package Under-Utilized

**Location:** `tui/handlers/`

**Classes:**
- `ConnectionHandler` - Thin wrapper for connection events
- `QueryHandler` - Thin wrapper for query processing
- `RefreshHandler` - Thin wrapper for refresh

**Problem:**
Handlers are minimal wrappers that add indirection without clear benefit. Logic is already in services.

**Recommendation:**
- Consolidate handlers into services if they don't add value
- Or give handlers clear responsibility (event→UI translation)

---

## Redundancies and Duplication

### R1: ConnectionStatus Defined in Two Places

**Locations:**
- `mcp_client/connection/lifecycle.py:12-19` (definition)
- `mcp_client/client.py` (imports from lifecycle)

**But imported from TWO paths:**
```python
# artifact_manager.py
from nxs.mcp_client.client import ConnectionStatus

# events/types.py
from nxs.mcp_client.connection.lifecycle import ConnectionStatus
```

**Solution:**
Move to `core/types.py` or `core/protocols.py` as canonical location.

---

### R2: Message Conversion Functions

**Location:** `core/command_control.py:208-242`

**Problem:**
Conversion functions are:
- Only used in one place (line 148)
- Not tested independently
- Mixed with debugging code (traceback imports)
- Should be in shared utility module

---

### R3: Repository Fetch Logic Duplication

**Location:** `core/artifacts/repository.py`

**Methods with similar patterns:**
- `get_resources()` (lines 41-54)
- `get_prompts()` (lines 56-67)
- `get_tools()` (lines 69-88)
- `get_server_artifacts()` (lines 119-218)

Each iterates through clients with try/except. Pattern repeats.

Also: Retry logic in `_fetch_with_retry()` is only used by `get_server_artifacts()`, not other methods.

---

### R4: Prompt Schema Cache Duplication

**Locations:**
- `tui/services/prompt_service.py` - Caches as tuples
- `tui/completion/schema_cache.py` - Another cache?

**Problem:**
Unclear which cache should be used where. Potential for cache invalidation issues.

---

### R5: Resource/Command Lists Duplicated

**Location:** `tui/app.py:103-104, 248-249, 273-274`

**Problem:**
```python
self.resources: list[str] = []  # Line 103
self.commands: list[str] = []   # Line 104

# Later:
self.resources = resources      # Line 248
self.commands = commands        # Line 249

# And again:
self.resources = await self.artifact_manager.get_resource_list()  # Line 273
```

Lists passed to widgets and synced in multiple places.

---

### R6: Callback Dictionaries with String Keys

**Location:** `core/chat.py:16, 26-27, 29-30, 47-52, 62-66, 72-79, 86-87`

**Problem:**
```python
self.callbacks = callbacks or {}

if 'on_start' in callbacks:
    await callbacks['on_start']()
```

Pattern repeats 5+ times with magic strings. No type safety.

**Recommendation:**
Create callback protocol or dataclass with typed methods.

---

### R7: Widget Getter Methods

**Location:** `tui/app.py`

**Methods:**
- `_get_status_panel()`
- `_get_mcp_panel()`
- `_get_input()`
- `_get_autocomplete()`
- `_get_chat_panel()`

**Problem:**
Pattern repeated for widget discovery. Services take getters as dependencies.

**Recommendation:**
Either pass widgets directly or create WidgetRegistry.

---

## Technical Debt

### TD1: Debugging Code in Production

**Locations:**
- `core/command_control.py:159-160, 165-166`
- `tui/services/prompt_service.py:88-89`
- `mcp_client/storage.py`

**Code:**
```python
import traceback
logger.error(traceback.format_exc())
```

**Should Use:**
```python
logger.exception("Error message")  # Automatically includes traceback
```

---

### TD2: Print Statements

**Locations:**
- `core/tools.py:82` - `print(error_message)`
- `mcp_client/callback.py` - `print(f"🖥️  Started callback...")`
- `mcp_client/auth.py` - Multiple print statements

**Should Use:**
```python
logger.info("Message")  # or logger.error()
```

---

### TD3: Inconsistent Error Handling

**Across Completion Strategies:**
- Different strategies have different error approaches
- Errors may be silently swallowed
- Orchestrator catches all exceptions and logs, returns empty list

---

### TD4: Missing Type Safety

**Callback Pattern:**
- String-keyed dictionaries for callbacks
- No IDE support
- Easy to typo names
- No compile-time checking

**Protocol Implementations:**
- No explicit protocol marking
- No runtime_checkable decorators
- Duck typing without contracts

---

## Phase 3 Refactoring Strategy

### Design Principles

**Principle 1: Respect Layer Boundaries**
- Core depends ONLY on protocols/abstractions
- Infrastructure implements protocols
- Presentation depends on core, never infrastructure
- No circular dependencies

**Principle 2: Single Responsibility**
- Each class has ONE reason to change
- Separate concerns even if related
- Extract mixed responsibilities

**Principle 3: Dependency Inversion**
- High-level modules don't depend on low-level
- Both depend on abstractions
- Protocols define contracts

**Principle 4: Remove Redundancy**
- Single Source of Truth for each concept
- DRY principle strictly enforced
- No duplicate caching, state, or logic

**Principle 5: Clean Up Technical Debt**
- Remove debugging code
- Standardize on logger
- Fix type safety issues
- Complete error handling

---

## Phase 3 Implementation Plan

### Phase 3.1: Fix Critical Layer Violations (Week 1, 8-10 hours)

**Goal:** Eliminate all core-to-infrastructure dependencies

#### Step 3.1.1: Move ConnectionStatus to Core Types (2-3 hours)

**Actions:**
1. Create `core/types.py` with ConnectionStatus enum
2. Update all imports to use `core.types.ConnectionStatus`
3. Remove from `mcp_client/connection/lifecycle.py` or mark as re-export
4. Update `core/artifact_manager.py`, `core/events/types.py`, `tui/app.py`
5. Run type checker and tests

**Files Modified:**
- Create: `core/types.py`
- Update: `core/artifact_manager.py`, `core/events/types.py`, `tui/app.py`
- Update: `mcp_client/client.py`, `mcp_client/connection/lifecycle.py`

**Expected Result:**
Core layer has no imports from mcp_client.

---

#### Step 3.1.2: Extract ClientFactory from ArtifactManager Dependencies (2-3 hours)

**Problem:**
```python
from nxs.mcp_client.factory import ClientFactory  # In core/artifact_manager.py
```

**Solution:**
Create protocol for client creation:

```python
# core/protocols.py
class ClientProvider(Protocol):
    """Protocol for creating MCP clients."""

    def create_clients(
        self,
        servers_config: dict,
        status_callback: Callable,
        progress_callback: Callable,
    ) -> dict[str, MCPClient]:
        """Create clients for configured servers."""
        ...
```

Then inject via constructor:
```python
# core/artifact_manager.py
def __init__(
    self,
    config: Optional[MCPServersConfig] = None,
    event_bus: Optional[EventBus] = None,
    client_provider: Optional[ClientProvider] = None,  # Protocol, not concrete
    ...
):
```

**Files Modified:**
- Update: `core/protocols.py` (add ClientProvider)
- Update: `core/artifact_manager.py` (use protocol)
- Update: `mcp_client/factory.py` (implement protocol)
- Update: `main.py`, `tui/app.py` (inject factory)

---

#### Step 3.1.3: Fix TUI Layer Imports (1 hour)

**Problem:**
```python
from nxs.mcp_client.client import ConnectionStatus  # In tui/app.py
```

**Solution:**
```python
from nxs.core.types import ConnectionStatus
```

**Files Modified:**
- Update: `tui/app.py`
- Update any other TUI files importing from mcp_client

---

#### Step 3.1.4: Verify Layer Boundaries (1 hour)

**Actions:**
1. Run dependency analysis tool or grep for violations:
   ```bash
   grep -r "from nxs.mcp_client" src/nxs/core/
   grep -r "from nxs.mcp_client" src/nxs/tui/
   ```
2. Should return NO results (except re-exports if needed)
3. Run full test suite
4. Run type checker

---

### Phase 3.2: Separate Connection Management from Artifacts (Week 2, 8-10 hours)

**Goal:** Split ArtifactManager dual responsibility

#### Step 3.2.1: Design New Architecture (2 hours)

**Current:**
```
ArtifactManager (314 lines)
  ├─ Client lifecycle
  ├─ Artifact access
  ├─ Cache management
  ├─ Change detection
  └─ Event publishing
```

**New Design:**

```
ConnectionOrchestrator (new)
  ├─ Client creation via ClientProvider
  ├─ Connection lifecycle (initialize, cleanup)
  ├─ Status tracking and events
  └─ Provides: Map[server_name, MCPClient]

ArtifactService (renamed from ArtifactManager)
  ├─ Artifact access (resources, prompts, tools)
  ├─ Delegates to ArtifactRepository
  ├─ Provides high-level API
  └─ Depends on: ConnectionOrchestrator.clients

ArtifactRepository
  ├─ Low-level fetch operations
  ├─ Retry logic
  └─ Depends on: clients dict

ArtifactCache
  └─ Caching logic

ArtifactChangeDetector
  └─ Change detection
```

**Rationale:**
- **ConnectionOrchestrator**: Single responsibility for MCP connection lifecycle
- **ArtifactService**: Single responsibility for artifact access (high-level API)
- **ArtifactRepository**: Data access layer (low-level fetch)
- **ArtifactCache**: Storage concern
- **ArtifactChangeDetector**: Comparison concern

---

#### Step 3.2.2: Create ConnectionOrchestrator (3-4 hours)

**File:** `core/connection/orchestrator.py`

```python
"""ConnectionOrchestrator - manages MCP client lifecycle."""

from typing import Dict, Mapping
from nxs.core.protocols import MCPClient, ClientProvider
from nxs.core.events import EventBus, ConnectionStatusChanged, ReconnectProgress
from nxs.core.types import ConnectionStatus
from nxs.core.mcp_config import MCPServersConfig, load_mcp_config


class ConnectionOrchestrator:
    """Manages MCP client connections and lifecycle."""

    def __init__(
        self,
        config: MCPServersConfig | None = None,
        client_provider: ClientProvider | None = None,
        event_bus: EventBus | None = None,
    ):
        self._config = config or load_mcp_config()
        self._client_provider = client_provider  # Protocol injection
        self._event_bus = event_bus or EventBus()
        self._clients: Dict[str, MCPClient] = {}
        self._previous_statuses: Dict[str, ConnectionStatus] = {}

    @property
    def clients(self) -> Mapping[str, MCPClient]:
        """Read-only access to connected clients."""
        return MappingProxyType(self._clients)

    async def initialize(self, use_auth: bool = False) -> None:
        """Create and connect all configured MCP clients."""
        # Move initialization logic from ArtifactManager
        ...

    async def cleanup(self) -> None:
        """Disconnect all clients."""
        # Move cleanup logic from ArtifactManager
        ...

    def _handle_status_change(self, server_name: str, status: ConnectionStatus):
        """Handle and publish status changes."""
        # Move from ArtifactManager
        ...

    def _handle_reconnect_progress(self, server_name: str, attempts: int, ...):
        """Handle and publish reconnection progress."""
        # Move from ArtifactManager
        ...
```

**Actions:**
1. Create `core/connection/` package
2. Create `core/connection/orchestrator.py`
3. Move client lifecycle logic from ArtifactManager
4. Move status tracking and event publishing
5. Add tests for ConnectionOrchestrator

---

#### Step 3.2.3: Refactor ArtifactManager → ArtifactService (2-3 hours)

**File:** Rename `core/artifact_manager.py` → `core/artifacts/service.py`

```python
"""ArtifactService - high-level API for artifact access."""

from typing import Mapping
from nxs.core.protocols import MCPClient
from nxs.core.artifacts import ArtifactRepository, ArtifactCache, ArtifactChangeDetector
from nxs.core.connection.orchestrator import ConnectionOrchestrator


class ArtifactService:
    """High-level facade for accessing MCP artifacts."""

    def __init__(
        self,
        connection_orchestrator: ConnectionOrchestrator,
        artifact_repository: ArtifactRepository | None = None,
        artifact_cache: ArtifactCache | None = None,
        change_detector: ArtifactChangeDetector | None = None,
    ):
        self._orchestrator = connection_orchestrator

        clients_provider = lambda: self._orchestrator.clients
        self._repository = artifact_repository or ArtifactRepository(clients_provider)
        self._cache = artifact_cache or ArtifactCache()
        self._change_detector = change_detector or ArtifactChangeDetector(self._cache)

    @property
    def clients(self) -> Mapping[str, MCPClient]:
        """Access to clients (delegated to orchestrator)."""
        return self._orchestrator.clients

    async def get_resources(self) -> dict[str, list[str]]:
        """Get all resources from all servers."""
        return await self._repository.get_resources()

    async def get_prompts(self) -> dict[str, list[str]]:
        """Get all prompts from all servers."""
        return await self._repository.get_prompts()

    # ... other high-level methods
```

**Actions:**
1. Remove connection lifecycle from ArtifactManager
2. Remove status tracking (now in ConnectionOrchestrator)
3. Keep only artifact access methods
4. Rename to ArtifactService
5. Update imports across codebase

**Files Modified:**
- Rename: `core/artifact_manager.py` → `core/artifacts/service.py`
- Update: `main.py`, `tui/app.py`, all services
- Update: `core/__init__.py` exports

---

#### Step 3.2.4: Update Dependents (1-2 hours)

**Update main.py:**
```python
# Create orchestrator
orchestrator = ConnectionOrchestrator(
    config=config,
    client_provider=ClientFactory(),
    event_bus=event_bus,
)

# Create artifact service
artifact_service = ArtifactService(
    connection_orchestrator=orchestrator,
)

# Initialize
await orchestrator.initialize(use_auth=use_auth)
```

**Update tui/app.py:**
- Accept both orchestrator and artifact_service
- Or just artifact_service (which has reference to orchestrator)

**Update all TUI services:**
- PromptService, MCPCoordinator, etc.
- Use artifact_service instead of artifact_manager

---

### Phase 3.3: Decompose NexusApp God Object (Week 3, 7-9 hours)

**Goal:** Reduce NexusApp to focused UI composition

#### Step 3.3.1: Extract Service Container (2-3 hours)

**Problem:**
App creates and manages 8+ services in `__init__`.

**Solution:**
Create ServiceContainer to manage service lifecycle:

**File:** `tui/services/container.py`

```python
"""ServiceContainer - manages TUI service lifecycle."""

from nxs.core.artifacts.service import ArtifactService
from nxs.core.connection.orchestrator import ConnectionOrchestrator
from nxs.core.events import EventBus
from nxs.tui.services import (
    PromptService,
    AutocompleteService,
    RefreshService,
    MCPCoordinator,
)
from nxs.tui.status_queue import StatusQueue


class ServiceContainer:
    """Container for all TUI services with dependency injection."""

    def __init__(
        self,
        artifact_service: ArtifactService,
        orchestrator: ConnectionOrchestrator,
        event_bus: EventBus,
        agent_loop,
    ):
        self.artifact_service = artifact_service
        self.orchestrator = orchestrator
        self.event_bus = event_bus
        self.agent_loop = agent_loop

        # Initialize services
        self._initialize_services()

    def _initialize_services(self):
        """Create all TUI services."""
        # StatusQueue, PromptService, etc.
        ...

    # Expose services as properties
    @property
    def status_queue(self) -> StatusQueue:
        return self._status_queue

    @property
    def prompt_service(self) -> PromptService:
        return self._prompt_service

    # ... etc
```

**Actions:**
1. Create ServiceContainer
2. Move service creation from NexusApp.__init__
3. Inject into NexusApp

---

#### Step 3.3.2: Extract Initialization Logic (2 hours)

**Problem:**
App has 50+ line `_initialize_mcp_connections_async()` method.

**Solution:**
Move to ServiceContainer or create InitializationService:

```python
class InitializationCoordinator:
    """Coordinates async initialization of MCP and TUI."""

    def __init__(
        self,
        orchestrator: ConnectionOrchestrator,
        services: ServiceContainer,
    ):
        self.orchestrator = orchestrator
        self.services = services

    async def initialize(self, use_auth: bool = False):
        """Initialize MCP connections and preload data."""
        # 1. Initialize connections
        await self.orchestrator.initialize(use_auth=use_auth)

        # 2. Load resources
        resources = await self.services.artifact_service.get_resource_list()

        # 3. Load commands
        commands = await self.services.artifact_service.get_command_names()

        # 4. Preload prompt schemas
        await self.services.prompt_service.preload_all(commands)

        return resources, commands
```

---

#### Step 3.3.3: Simplify NexusApp (2-3 hours)

**New Structure:**

```python
class NexusApp(App):
    """Nexus TUI application - UI composition only."""

    def __init__(
        self,
        services: ServiceContainer,
        initializer: InitializationCoordinator,
    ):
        super().__init__()
        self.services = services
        self.initializer = initializer

        # Widget references (set in compose)
        self._chat_panel = None
        self._status_panel = None
        self._input = None
        # ... etc

    def compose(self) -> ComposeResult:
        """Compose UI layout."""
        yield Header()
        # ... layout composition
        yield Footer()

    async def on_mount(self):
        """Initialize when app mounts."""
        resources, commands = await self.initializer.initialize()
        self._update_autocomplete(resources, commands)
```

**Actions:**
1. Move service management to ServiceContainer
2. Move initialization to InitializationCoordinator
3. Keep only UI composition in NexusApp
4. Reduce from 524 → ~200 lines

**Expected Reduction:** 524 lines → ~200 lines (62% reduction)

---

#### Step 3.3.4: Create Widget Registry (1 hour)

**Problem:**
5+ getter methods for widget access.

**Solution:**

```python
class WidgetRegistry:
    """Registry for accessing widgets by type."""

    def __init__(self, app: App):
        self._app = app

    def get_chat_panel(self) -> ChatPanel:
        return self._app.query_one("#chat", ChatPanel)

    def get_status_panel(self) -> StatusPanel:
        return self._app.query_one("#status", StatusPanel)

    # ... etc
```

Or pass widgets directly to services during composition.

---

### Phase 3.4: Fix State Management Issues (Week 4, 6-8 hours)

**Goal:** Eliminate mutable shared state

#### Step 3.4.1: Fix AgentLoop Message State (2-3 hours)

**Problem:**
```python
self.messages: list[MessageParam] = []  # Shared mutable state
```

**Solution 1: Make messages local to run()**

```python
class AgentLoop:
    def __init__(self, llm: Claude, clients: Mapping[str, MCPClient]):
        self.llm = llm
        self.tool_clients = clients
        # Remove: self.messages

    async def run(self, query: str, callbacks=None) -> str:
        messages: list[MessageParam] = []  # Local to this call
        messages.append({"role": "user", "content": query})

        while True:
            response = self.llm.chat(
                messages=messages,  # Use local list
                tools=await ToolManager.get_all_tools(self.tool_clients),
            )
            # ...
```

**Solution 2: Return messages for caller to manage**

```python
async def run(self, query: str, initial_messages: list[MessageParam] | None = None):
    messages = initial_messages.copy() if initial_messages else []
    # ...
    return final_text_response, messages  # Return final state
```

**Actions:**
1. Choose solution (recommend Solution 1)
2. Update AgentLoop.run() to use local messages
3. Update CommandControlAgent to not manipulate self.messages
4. Update tests

---

#### Step 3.4.2: Extract Message Conversion to Service (1-2 hours)

**Problem:**
Conversion functions in `command_control.py:208-242`.

**Solution:**

**File:** `core/messaging/converter.py`

```python
"""Message conversion utilities for MCP prompts."""

from typing import List
from mcp.types import PromptMessage
from anthropic.types import MessageParam


class MessageConverter:
    """Converts between MCP and Anthropic message formats."""

    @staticmethod
    def convert_prompt_message(prompt_message: PromptMessage) -> MessageParam:
        """Convert a single PromptMessage to MessageParam."""
        # Move logic from command_control.py
        ...

    @staticmethod
    def convert_prompt_messages(
        prompt_messages: List[PromptMessage]
    ) -> List[MessageParam]:
        """Convert list of PromptMessages to MessageParams."""
        return [
            MessageConverter.convert_prompt_message(msg)
            for msg in prompt_messages
        ]
```

**Actions:**
1. Create `core/messaging/` package
2. Create `converter.py` with MessageConverter
3. Move conversion functions
4. Update CommandControlAgent to use MessageConverter
5. Add tests for converter

---

#### Step 3.4.3: Remove Previous Status Tracking from ArtifactService (1 hour)

**Problem:**
```python
self._previous_statuses: Dict[str, ConnectionStatus] = {}
```

**Solution:**
Move to ConnectionOrchestrator (it manages status). Or let event subscribers track if needed.

**Actions:**
1. If status change detection needed, keep in ConnectionOrchestrator
2. Remove from ArtifactService (now ArtifactService doesn't need it)
3. Update tests

---

#### Step 3.4.4: Replace MCP Initialized Flag with State Machine (1-2 hours)

**Problem:**
```python
self._mcp_initialized = False  # Boolean flag
```

**Solution:**

```python
class AppState(Enum):
    STARTING = "starting"
    INITIALIZING_MCP = "initializing_mcp"
    READY = "ready"
    ERROR = "error"

class NexusApp(App):
    def __init__(self, ...):
        self._state = AppState.STARTING

    @property
    def is_ready(self) -> bool:
        return self._state == AppState.READY
```

Or use InitializationCoordinator to provide state.

---

### Phase 3.5: Replace String-Keyed Callbacks with Protocols (Week 4, 4-5 hours)

**Goal:** Type-safe callback mechanism

#### Step 3.5.1: Define Callback Protocols (2 hours)

**File:** `core/protocols.py`

```python
"""Callback protocols for agent loop."""

from typing import Protocol, Any


class AgentCallbacks(Protocol):
    """Protocol for agent loop callbacks."""

    async def on_start(self) -> None:
        """Called when agent loop starts."""
        ...

    async def on_stream_chunk(self, chunk: str) -> None:
        """Called for each streamed text chunk."""
        ...

    async def on_tool_call(self, tool_name: str, tool_input: dict) -> None:
        """Called when LLM requests tool execution."""
        ...

    async def on_tool_result(
        self, tool_name: str, result: str, success: bool
    ) -> None:
        """Called after tool execution completes."""
        ...

    async def on_stream_complete(self) -> None:
        """Called when streaming completes."""
        ...
```

**Or use dataclass with optional callables:**

```python
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Optional

@dataclass
class AgentCallbacks:
    """Callbacks for agent loop events."""

    on_start: Optional[Callable[[], Awaitable[None]]] = None
    on_stream_chunk: Optional[Callable[[str], Awaitable[None]]] = None
    on_tool_call: Optional[Callable[[str, dict], Awaitable[None]]] = None
    on_tool_result: Optional[Callable[[str, str, bool], Awaitable[None]]] = None
    on_stream_complete: Optional[Callable[[], Awaitable[None]]] = None
```

---

#### Step 3.5.2: Update AgentLoop to Use Protocol (2 hours)

```python
class AgentLoop:
    def __init__(
        self,
        llm: Claude,
        clients: Mapping[str, MCPClient],
        callbacks: AgentCallbacks | None = None,
    ):
        self.llm = llm
        self.tool_clients = clients
        self.callbacks = callbacks

    async def run(self, query: str) -> str:
        if self.callbacks and self.callbacks.on_start:
            await self.callbacks.on_start()

        # ... rest of logic with typed callbacks
```

**Actions:**
1. Define callback protocol/dataclass
2. Update AgentLoop to accept typed callbacks
3. Update all callback creation sites
4. Remove string-keyed dict pattern
5. Add type hints and IDE support

---

### Phase 3.6: Remove Technical Debt (Week 5, 5-6 hours)

**Goal:** Clean up debugging code, print statements, inconsistencies

#### Step 3.6.1: Remove Debugging Code (1 hour)

**Files to Update:**
- `core/command_control.py:159-160, 165-166`
- `tui/services/prompt_service.py:88-89`
- `mcp_client/storage.py`

**Replace:**
```python
import traceback
logger.error(traceback.format_exc())
```

**With:**
```python
logger.exception("Error message")  # Automatically includes traceback
```

**Actions:**
1. Search for `import traceback` in production code
2. Replace with `logger.exception()`
3. Remove traceback imports
4. Per CLAUDE.md: Add comments for any temporary debug code

---

#### Step 3.6.2: Replace Print Statements (1-2 hours)

**Files:**
- `core/tools.py:82` - `print(error_message)` → `logger.error(error_message)`
- `mcp_client/callback.py` - Print statements → logger.info()
- `mcp_client/auth.py` - Print statements → logger or UI callback

**Actions:**
1. Search for `print(` in src/
2. Replace with appropriate logger calls
3. For user-facing messages in auth, use UI callback or logger.info
4. Run tests to ensure behavior unchanged

---

#### Step 3.6.3: Fix ToolManager Error Handling Bug (1 hour)

**File:** `core/tools.py:80-87`

**Current (BUG):**
```python
try:
    tool_output: CallToolResult | None = await client.call_tool(...)
    # ...
except Exception as e:
    tool_result_part = cls._build_tool_result_part(
        tool_use_id,
        json.dumps({"error": error_message}),
        "error" if tool_output and tool_output.isError else "success",  # BUG
    )
```

**Fixed:**
```python
try:
    tool_output: CallToolResult | None = await client.call_tool(...)
    # ... success path
except Exception as e:
    # tool_output doesn't exist here, use "error" status directly
    tool_result_part = cls._build_tool_result_part(
        tool_use_id,
        json.dumps({"error": error_message}),
        "error",  # Always error in exception path
    )
```

---

#### Step 3.6.4: Consolidate Logging Patterns (1 hour)

**Actions:**
1. Choose standard: f-strings vs .format() vs %
2. Recommend: f-strings for readability, but logger uses % for performance
3. Update guidelines in CONTRIBUTING.md or CLAUDE.md
4. Update inconsistent usages

**Example:**
```python
# Prefer for logger (lazy evaluation):
logger.info("Processing %s items", count)

# OK for regular strings:
message = f"Processing {count} items"
```

---

#### Step 3.6.5: Add Runtime Protocol Checking (1 hour)

**File:** `core/protocols.py`

**Update:**
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class MCPClient(Protocol):
    """Protocol for MCP client implementations."""
    ...

@runtime_checkable
class Cache(Protocol):
    """Protocol for cache implementations."""
    ...
```

**Actions:**
1. Add `@runtime_checkable` to all protocols
2. Add explicit protocol checks where needed:
   ```python
   assert isinstance(client, MCPClient), "Must implement MCPClient protocol"
   ```
3. Document protocol assumptions in docstrings

---

### Phase 3.7: Optimize Package Structure (Week 5-6, 4-5 hours)

**Goal:** Improve cohesion and reduce over-engineering

#### Step 3.7.1: Reorganize Artifacts Package (1-2 hours)

**Current:**
```
core/artifacts/
├── repository.py (data access)
├── cache.py (storage)
├── change_detector.py (comparison)
└── __init__.py
```

**Option A: Keep together but document clearly**

Add `core/artifacts/README.md`:
```markdown
# Artifacts Package

This package handles all aspects of MCP artifact management:

- **repository.py**: Data access layer - fetches artifacts from MCP clients
- **cache.py**: Storage layer - caches artifact collections
- **change_detector.py**: Comparison layer - detects artifact changes
- **service.py**: High-level facade - coordinates repository, cache, change detection

While these are different concerns (access, storage, comparison), they're grouped
because they all relate to artifact management lifecycle.
```

**Option B: Distribute to different packages**
- Keep `repository.py` in `artifacts/`
- Move `cache.py` to `core/cache/`
- Move `change_detector.py` to `core/sync/` or `core/diff/`

**Recommendation:** Option A (document clearly) - they work together closely.

---

#### Step 3.7.2: Simplify Completion Package (2 hours)

**Current:** 843 lines across 8 files

**Simplifications:**

1. **Merge prompt_utils.py into strategies** - If utils are only used by one strategy
2. **Reduce CompletionApplier** - Extract helper methods to utility functions
3. **Remove schema_cache.py if redundant** - Use PromptService cache directly
4. **Keep strategy pattern** - It's good architecture

**Actions:**
1. Analyze usage of `prompt_utils.py` - can functions be moved to strategies?
2. Extract CompletionApplier private methods to module-level utilities
3. Check if `schema_cache.py` duplicates PromptService
4. Reduce from 843 → ~500 lines

---

#### Step 3.7.3: Consolidate or Remove Handlers (1 hour)

**Current:**
- `ConnectionHandler` - Thin wrapper
- `QueryHandler` - Thin wrapper
- `RefreshHandler` - Thin wrapper

**Options:**

**Option A: Merge into services**
If handlers don't add value, move logic directly to services.

**Option B: Give handlers clear responsibility**
Make handlers responsible for event→UI translation only:
```python
class ConnectionHandler:
    """Translates connection events to UI updates."""

    def __init__(self, mcp_panel: MCPPanel):
        self.panel = mcp_panel

    def handle_status_changed(self, event: ConnectionStatusChanged):
        """Update UI when status changes."""
        self.panel.update_server_status(event.server_name, event.status)
```

**Recommendation:** Option B - clear event→UI translation responsibility.

**Actions:**
1. Simplify handlers to focus only on UI updates
2. Move business logic to services
3. Document handler responsibility in README

---

### Phase 3.8: Polish and Documentation (Week 6, 3-4 hours)

**Goal:** Document new architecture, update guides

#### Step 3.8.1: Update CLAUDE.md (1-2 hours)

**Sections to Update:**

1. **Architecture Overview**
   - Document new layering
   - ConnectionOrchestrator + ArtifactService separation
   - ServiceContainer pattern

2. **Package Structure**
   - Update package descriptions
   - Document new `core/connection/`, `core/messaging/`, `core/types.py`

3. **Code Organization**
   - Update file purposes table
   - Document service container pattern
   - Document callback protocols

4. **Naming Conventions**
   - Clarify service vs orchestrator vs coordinator
   - Document when to use each pattern

---

#### Step 3.8.2: Create Architecture Decision Records (2 hours)

**ADRs to Create:**

1. **ADR-006: Layer Boundary Enforcement**
   - Decision to move ConnectionStatus to core
   - Protocol-based dependency injection for ClientProvider
   - Rationale for strict layering

2. **ADR-007: Separation of Connection and Artifact Management**
   - Split ArtifactManager into ConnectionOrchestrator + ArtifactService
   - Single Responsibility Principle
   - Rationale for the split

3. **ADR-008: Service Container Pattern**
   - Why use ServiceContainer instead of God Object
   - Dependency injection benefits
   - Testability improvements

4. **ADR-009: Typed Callbacks**
   - Replace string-keyed dicts with protocols/dataclasses
   - Type safety benefits
   - Migration strategy

5. **ADR-010: State Management**
   - Local vs instance state for AgentLoop
   - State machine for app initialization
   - Rationale for choices

---

#### Step 3.8.3: Add Package READMEs (1 hour)

**Create:**
- `core/connection/README.md` - Connection orchestration
- `core/artifacts/README.md` - Artifact management concerns
- `core/messaging/README.md` - Message conversion
- `tui/services/README.md` - Update with ServiceContainer info

---

## Success Metrics

### Quantitative Metrics

| Metric | Before Phase 3 | Phase 3 Goal | Target Reduction |
|--------|----------------|--------------|------------------|
| **NexusApp** | 524 lines | ~200 lines | 62% reduction |
| **ArtifactManager** | 314 lines | Split: 150+120 | N/A (separation) |
| **Core→Infrastructure imports** | 4+ violations | 0 violations | 100% elimination |
| **Print statements** | 7+ instances | 0 instances | 100% elimination |
| **Debugging code** | 6+ locations | 0 locations | 100% elimination |
| **String-keyed callbacks** | 5+ dict lookups | 0 (typed callbacks) | 100% elimination |
| **God Object methods** | 18+ methods | ~8 methods | 55% reduction |

**Total Expected:**
- ~400 lines removed/refactored
- 6 critical violations fixed
- 11 high-priority issues resolved

---

### Qualitative Metrics

**✅ MUST ACHIEVE:**

- [ ] **Zero Layer Violations**
  - Core imports only from protocols/types
  - TUI doesn't import from infrastructure
  - Clean dependency direction

- [ ] **Single Responsibility Classes**
  - ConnectionOrchestrator: connection lifecycle only
  - ArtifactService: artifact access only
  - NexusApp: UI composition only

- [ ] **Type Safety**
  - Typed callbacks (Protocol or dataclass)
  - Runtime-checkable protocols
  - No string-keyed lookups

- [ ] **No Technical Debt**
  - Zero print() statements in core/tui
  - Zero debugging code (traceback imports)
  - All error paths tested and correct

- [ ] **State Management**
  - No shared mutable state in AgentLoop
  - Clear state ownership
  - No state leaks between calls

**✅ SHOULD ACHIEVE:**

- [ ] **Clear Package Boundaries**
  - Cohesive packages with documented purpose
  - No circular dependencies
  - Minimal coupling between packages

- [ ] **Consistent Patterns**
  - Unified logging approach
  - Consistent error handling
  - Standard naming conventions

- [ ] **Comprehensive Documentation**
  - 5+ ADRs documenting key decisions
  - Package READMEs explaining purpose
  - Updated CLAUDE.md reflecting new structure

---

## Testing Strategy

### Unit Tests Required

**New Components:**
1. `ConnectionOrchestrator` - Lifecycle, status tracking, events
2. `ArtifactService` - High-level artifact access
3. `MessageConverter` - Prompt message conversion
4. `ServiceContainer` - Service lifecycle management
5. `InitializationCoordinator` - Async initialization
6. `AgentCallbacks` - Typed callback protocol usage

**Test Coverage Goals:**
- ConnectionOrchestrator: 90%+
- ArtifactService: 85%+
- MessageConverter: 95%+ (pure functions)
- ServiceContainer: 80%+

---

### Integration Tests

**Test Scenarios:**

1. **End-to-end Initialization**
   - Create ConnectionOrchestrator
   - Create ArtifactService
   - Initialize connections
   - Verify artifact access works

2. **Event Flow**
   - Connection status change
   - EventBus delivers to handlers
   - UI updates correctly

3. **Agent Loop State Isolation**
   - Multiple sequential calls to run()
   - Verify no state leakage
   - Messages don't accumulate

4. **Service Container Lifecycle**
   - Create all services
   - Verify dependencies wired correctly
   - Cleanup works

---

### Manual Testing Checklist

After each phase:

- [ ] Application starts without errors
- [ ] MCP servers connect successfully
- [ ] Status updates appear in real-time
- [ ] Autocomplete works for @resources and /commands
- [ ] Query processing executes correctly
- [ ] Tool calls succeed
- [ ] Reconnection works when server disconnects
- [ ] No console errors or warnings
- [ ] Type checker passes: `pixi run --environment dev type-check`
- [ ] All tests pass: `pixi run --environment test test`

---

## Migration Path and Risk Mitigation

### Migration Order (Dependency-Aware)

**Week 1: Foundation (Layer Violations)**
- Start with ConnectionStatus move (no dependents)
- Then ClientProvider protocol
- Low risk, high impact

**Week 2: Core Refactoring (Connection Split)**
- Create ConnectionOrchestrator
- Refactor ArtifactManager
- Medium risk, requires careful testing

**Week 3: App Decomposition**
- Create ServiceContainer
- Extract initialization
- Simplify NexusApp
- Medium risk, affects startup

**Week 4: State and Callbacks**
- Fix AgentLoop state
- Typed callbacks
- Low-medium risk

**Week 5-6: Polish**
- Technical debt removal
- Package optimization
- Documentation
- Low risk

---

### Risk Mitigation

**Risk 1: Breaking Existing Functionality**
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:**
  - Incremental changes with tests after each step
  - Feature flags for major refactors
  - Comprehensive integration tests
  - Manual smoke tests after each week
- **Rollback:** Git branches for each phase

**Risk 2: State Management Bugs**
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:**
  - Extensive tests for AgentLoop message isolation
  - Test concurrent calls
  - Test state cleanup
- **Detection:** Integration tests with multiple sequential queries

**Risk 3: Event Flow Changes**
- **Likelihood:** Low-Medium
- **Impact:** Medium
- **Mitigation:**
  - ConnectionOrchestrator maintains same event publishing
  - Handlers stay the same initially
  - Test event delivery
- **Detection:** Event flow integration tests

**Risk 4: Service Wiring Errors**
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:**
  - ServiceContainer with clear initialization order
  - Type hints and protocols
  - Dependency injection tests
- **Detection:** Startup integration tests

**Risk 5: Callback Migration Issues**
- **Likelihood:** Low
- **Impact:** Low-Medium
- **Mitigation:**
  - Define clear callback protocol
  - Migrate gradually (can support both during transition)
  - Type hints help catch errors
- **Detection:** Type checker, callback tests

---

## Rollback Strategy

### Per-Phase Rollback

**Phase 3.1 (Layer Violations):**
- Revert `core/types.py` creation
- Restore imports from `mcp_client`
- Independent, easy rollback

**Phase 3.2 (Connection Split):**
- Restore original `ArtifactManager`
- Remove `ConnectionOrchestrator`
- Medium complexity (update main.py, app.py)

**Phase 3.3 (App Decomposition):**
- Restore monolithic `NexusApp.__init__`
- Remove `ServiceContainer`, `InitializationCoordinator`
- Medium complexity

**Phase 3.4 (State Management):**
- Restore `self.messages` in AgentLoop
- Restore message conversion in CommandControlAgent
- Low complexity

**Phase 3.5 (Callbacks):**
- Restore string-keyed callback dicts
- Low complexity (backward compatible)

**Phase 3.6-3.8 (Polish):**
- Revert logging changes
- Restore print statements if needed
- Very low risk, easy rollback

---

## Implementation Timeline

### Week-by-Week Breakdown

**Week 1: Fix Critical Layer Violations (8-10 hours)**
- Mon-Tue: Step 3.1.1 - Move ConnectionStatus (2-3h)
- Wed: Step 3.1.2 - Extract ClientFactory protocol (2-3h)
- Thu: Step 3.1.3-3.1.4 - Fix TUI imports, verify (2h)
- **Deliverable:** Zero core→infrastructure imports

**Week 2: Separate Connection Management (8-10 hours)**
- Mon: Step 3.2.1 - Design new architecture (2h)
- Tue-Wed: Step 3.2.2 - Create ConnectionOrchestrator (3-4h)
- Thu: Step 3.2.3 - Refactor to ArtifactService (2-3h)
- Fri: Step 3.2.4 - Update dependents (1-2h)
- **Deliverable:** Clean separation of concerns

**Week 3: Decompose NexusApp (7-9 hours)**
- Mon-Tue: Step 3.3.1 - Extract ServiceContainer (2-3h)
- Wed: Step 3.3.2 - Extract initialization (2h)
- Thu: Step 3.3.3 - Simplify NexusApp (2-3h)
- Fri: Step 3.3.4 - Widget registry (1h)
- **Deliverable:** NexusApp 524→200 lines

**Week 4: Fix State Management + Callbacks (10-13 hours)**
- Mon: Step 3.4.1 - Fix AgentLoop state (2-3h)
- Tue: Step 3.4.2 - Extract message conversion (1-2h)
- Wed: Step 3.4.3-3.4.4 - Status tracking, state machine (2-3h)
- Thu-Fri: Step 3.5 - Typed callbacks (4-5h)
- **Deliverable:** Type-safe, stateless agent loop

**Week 5: Remove Technical Debt (5-6 hours)**
- Mon: Step 3.6.1 - Remove debugging code (1h)
- Tue: Step 3.6.2 - Replace print statements (1-2h)
- Wed: Step 3.6.3 - Fix ToolManager bug (1h)
- Thu: Step 3.6.4-3.6.5 - Logging patterns, protocols (2h)
- **Deliverable:** Clean, production-ready code

**Week 6: Optimize Packages + Documentation (7-9 hours)**
- Mon: Step 3.7.1 - Reorganize artifacts (1-2h)
- Tue: Step 3.7.2 - Simplify completion (2h)
- Wed: Step 3.7.3 - Consolidate handlers (1h)
- Thu-Fri: Step 3.8 - Documentation + ADRs (3-4h)
- **Deliverable:** Polished, well-documented architecture

---

## Appendix A: Proposed Package Structure (After Phase 3)

```
src/nxs/
├── core/                              # Domain layer
│   ├── types.py                       # NEW: ConnectionStatus, shared types
│   ├── protocols.py                   # MCPClient, Cache, ClientProvider, AgentCallbacks
│   ├── command_control.py             # CommandControlAgent (simplified)
│   ├── chat.py                        # AgentLoop (stateless)
│   ├── tools.py                       # ToolManager (bug fixed)
│   ├── claude.py                      # Anthropic SDK wrapper
│   ├── mcp_config.py                  # MCP configuration
│   │
│   ├── connection/                    # NEW: Connection management
│   │   ├── __init__.py
│   │   ├── orchestrator.py            # NEW: ConnectionOrchestrator
│   │   └── README.md                  # NEW: Package documentation
│   │
│   ├── artifacts/                     # Artifact management
│   │   ├── __init__.py
│   │   ├── service.py                 # NEW: ArtifactService (renamed from artifact_manager)
│   │   ├── repository.py              # ArtifactRepository
│   │   ├── cache.py                   # ArtifactCache
│   │   ├── change_detector.py         # ArtifactChangeDetector
│   │   └── README.md                  # NEW: Package documentation
│   │
│   ├── messaging/                     # NEW: Message conversion
│   │   ├── __init__.py
│   │   ├── converter.py               # NEW: MessageConverter
│   │   └── README.md                  # NEW: Package documentation
│   │
│   ├── events/                        # Event-driven architecture
│   │   ├── __init__.py
│   │   ├── bus.py                     # EventBus
│   │   └── types.py                   # Event types (fixed imports)
│   │
│   ├── cache/                         # Caching implementations
│   │   ├── __init__.py
│   │   ├── base.py                    # Cache protocol re-export (or remove)
│   │   ├── memory.py                  # MemoryCache
│   │   └── ttl.py                     # TTLCache
│   │
│   ├── parsers/                       # Argument parsing
│   │   ├── __init__.py
│   │   ├── base.py                    # ArgumentParser protocol (or remove)
│   │   ├── composite.py               # CompositeArgumentParser
│   │   ├── positional.py              # PositionalArgumentParser
│   │   ├── key_value.py               # KeyValueArgumentParser
│   │   ├── schema_adapter.py          # Schema handling
│   │   └── utils.py                   # Parsing utilities
│   │
│   └── suggestions/                   # Argument suggestions
│       ├── __init__.py
│       └── generator.py               # ArgumentSuggestionGenerator
│
├── mcp_client/                        # Infrastructure layer
│   ├── __init__.py
│   ├── client.py                      # MCPAuthClient wrapper
│   ├── factory.py                     # ClientFactory (implements ClientProvider)
│   ├── cli.py                         # Typer CLI
│   ├── auth.py                        # OAuth (print→logger)
│   ├── storage.py                     # State persistence (debug removed)
│   ├── callback.py                    # UI callbacks (print→logger)
│   │
│   ├── connection/                    # Connection management
│   │   ├── __init__.py
│   │   ├── manager.py                 # ConnectionManager
│   │   ├── lifecycle.py               # ConnectionLifecycle
│   │   ├── reconnect.py               # ExponentialBackoffStrategy
│   │   └── health.py                  # HealthChecker
│   │
│   └── operations/                    # MCP operations
│       ├── __init__.py
│       ├── base.py                    # OperationBase
│       ├── tools.py                   # ToolsOperations
│       ├── prompts.py                 # PromptsOperations
│       └── resources.py               # ResourcesOperations
│
└── tui/                               # Presentation layer
    ├── app.py                         # NexusApp (simplified, ~200 lines)
    ├── styles.tcss                    # Textual CSS
    ├── query_manager.py               # Async query manager
    ├── status_queue.py                # Async status queue
    │
    ├── services/                      # TUI services
    │   ├── __init__.py
    │   ├── container.py               # NEW: ServiceContainer
    │   ├── initialization.py          # NEW: InitializationCoordinator
    │   ├── mcp_coordinator.py         # MCPCoordinator
    │   ├── prompt_service.py          # PromptService
    │   ├── autocomplete_service.py    # AutocompleteService
    │   ├── mcp_refresher.py           # RefreshService
    │   └── README.md                  # Updated: ServiceContainer docs
    │
    ├── handlers/                      # Event handlers
    │   ├── __init__.py
    │   ├── connection_handler.py      # ConnectionHandler (simplified)
    │   ├── query_handler.py           # QueryHandler (simplified)
    │   ├── refresh_handler.py         # RefreshHandler (simplified)
    │   └── README.md                  # Updated: Handler responsibilities
    │
    ├── completion/                    # Completion strategies
    │   ├── __init__.py
    │   ├── strategy.py                # CompletionStrategy protocol
    │   ├── orchestrator.py            # CompletionOrchestrator
    │   ├── applier.py                 # CompletionApplier (simplified)
    │   ├── resource_completion.py     # ResourceCompletionStrategy
    │   ├── command_completion.py      # CommandCompletionStrategy
    │   ├── argument_completion.py     # ArgumentCompletionStrategy
    │   ├── prompt_utils.py            # Utilities (or merged)
    │   └── schema_cache.py            # SchemaCache (or removed if redundant)
    │
    ├── formatters/                    # Display formatters
    │   ├── __init__.py
    │   └── status.py                  # Status formatting
    │
    └── widgets/                       # Textual widgets
        ├── __init__.py
        ├── autocomplete.py            # NexusAutoComplete (~120 lines)
        ├── mcp_panel.py               # MCPPanel (~150 lines)
        ├── server_widget.py           # ServerWidget
        ├── artifact_item.py           # ArtifactItem
        ├── static_no_margin.py        # StaticNoMargin
        ├── chat_panel.py              # ChatPanel
        ├── status_panel.py            # StatusPanel
        ├── input_field.py             # NexusInput
        └── artifact_overlay.py        # ArtifactOverlay
```

**Key Changes:**
- ✅ `core/types.py` - NEW (ConnectionStatus)
- ✅ `core/connection/orchestrator.py` - NEW (ConnectionOrchestrator)
- ✅ `core/artifacts/service.py` - NEW (renamed from artifact_manager)
- ✅ `core/messaging/converter.py` - NEW (MessageConverter)
- ✅ `tui/services/container.py` - NEW (ServiceContainer)
- ✅ `tui/services/initialization.py` - NEW (InitializationCoordinator)
- ✅ All imports fixed (no core→infrastructure)
- ✅ Print statements removed
- ✅ Debugging code removed
- ✅ NexusApp simplified (524→~200 lines)

---

## Appendix B: Quick Reference - Phase 3 Steps

| Phase | Step | Description | Effort | Impact |
|-------|------|-------------|--------|--------|
| **3.1** | 3.1.1 | Move ConnectionStatus to core/types.py | 2-3h | **CRITICAL** |
| **3.1** | 3.1.2 | Extract ClientFactory protocol | 2-3h | **CRITICAL** |
| **3.1** | 3.1.3 | Fix TUI layer imports | 1h | HIGH |
| **3.1** | 3.1.4 | Verify layer boundaries | 1h | HIGH |
| **3.2** | 3.2.1 | Design connection/artifact split | 2h | **CRITICAL** |
| **3.2** | 3.2.2 | Create ConnectionOrchestrator | 3-4h | **CRITICAL** |
| **3.2** | 3.2.3 | Refactor to ArtifactService | 2-3h | **CRITICAL** |
| **3.2** | 3.2.4 | Update dependents | 1-2h | HIGH |
| **3.3** | 3.3.1 | Extract ServiceContainer | 2-3h | HIGH |
| **3.3** | 3.3.2 | Extract InitializationCoordinator | 2h | HIGH |
| **3.3** | 3.3.3 | Simplify NexusApp | 2-3h | **CRITICAL** |
| **3.3** | 3.3.4 | Create WidgetRegistry | 1h | MEDIUM |
| **3.4** | 3.4.1 | Fix AgentLoop message state | 2-3h | **CRITICAL** |
| **3.4** | 3.4.2 | Extract message conversion | 1-2h | HIGH |
| **3.4** | 3.4.3 | Remove previous status tracking | 1h | MEDIUM |
| **3.4** | 3.4.4 | Replace MCP flag with state machine | 1-2h | MEDIUM |
| **3.5** | 3.5.1 | Define callback protocols | 2h | HIGH |
| **3.5** | 3.5.2 | Update AgentLoop callbacks | 2h | HIGH |
| **3.6** | 3.6.1 | Remove debugging code | 1h | MEDIUM |
| **3.6** | 3.6.2 | Replace print statements | 1-2h | MEDIUM |
| **3.6** | 3.6.3 | Fix ToolManager bug | 1h | **CRITICAL** |
| **3.6** | 3.6.4 | Consolidate logging | 1h | LOW |
| **3.6** | 3.6.5 | Add protocol runtime checking | 1h | MEDIUM |
| **3.7** | 3.7.1 | Reorganize artifacts package | 1-2h | MEDIUM |
| **3.7** | 3.7.2 | Simplify completion package | 2h | MEDIUM |
| **3.7** | 3.7.3 | Consolidate/clarify handlers | 1h | MEDIUM |
| **3.8** | 3.8.1 | Update CLAUDE.md | 1-2h | LOW |
| **3.8** | 3.8.2 | Create ADRs | 2h | LOW |
| **3.8** | 3.8.3 | Add package READMEs | 1h | LOW |
| **Total** | | | **30-35h** | **HIGH** |

---

## Conclusion

Phase 3 refactoring addresses the **35+ architectural issues** identified in comprehensive analysis by:

1. **Fixing Critical Layer Violations** - Moving ConnectionStatus to core, using protocol-based dependency injection
2. **Separating Dual Responsibilities** - Splitting ArtifactManager into ConnectionOrchestrator + ArtifactService
3. **Decomposing God Objects** - Reducing NexusApp from 524→~200 lines via ServiceContainer pattern
4. **Establishing Clean State Management** - Making AgentLoop stateless, typed callbacks
5. **Removing Technical Debt** - Eliminating debugging code, print statements, fixing bugs

**Expected Outcomes:**
- ✅ **Zero layer violations** - Clean dependency direction
- ✅ **Single Responsibility** - Each class has one reason to change
- ✅ **Type Safety** - Protocols and typed callbacks
- ✅ **No Technical Debt** - Production-ready code
- ✅ **~400 lines refactored/removed** - Cleaner, more maintainable codebase

**Timeline:** 6 weeks, 30-35 hours
**Risk Level:** Medium (careful refactoring of core components with comprehensive testing)

The result will be a **truly clean architecture** with:
- Proper layering and dependency inversion
- Clear separation of concerns
- Type-safe interfaces
- Comprehensive documentation
- Production-ready code quality

---

**Document Version:** 1.0
**Date:** 2025-01-08
**Status:** Ready for Implementation
**Based On:** Comprehensive architectural analysis of post-Phase 1-3 codebase
