# Phase 3: Architectural Foundation - Package Structure & Layer Boundaries

## Executive Summary

This plan focuses on **establishing the correct architectural foundation** by:
1. **Fixing all layer violations** - Moving shared types to proper locations
2. **Reorganizing packages** - Clear separation by architectural layer
3. **Establishing clean boundaries** - Dependency direction enforcement
4. **Creating expansion points** - Flexible structure for future growth

**Philosophy:**
- Fix structure first, optimize later
- Clear separation of concerns by layer
- Simple, readable, non-over-engineered
- Easy to understand and extend

**Timeline:** 2-3 weeks, 15-20 hours
**Focus:** Structure and boundaries, NOT complexity reduction

---

## Current Architecture Problems (Focus Areas)

### 🔴 Critical: Layer Violations

**Problem 1: Core depends on Infrastructure**
```python
# core/artifact_manager.py
from nxs.mcp_client.client import ConnectionStatus        # WRONG LAYER
from nxs.mcp_client.factory import ClientFactory          # WRONG LAYER

# core/events/types.py
from nxs.mcp_client.connection.lifecycle import ConnectionStatus  # WRONG LAYER
```

**Problem 2: Shared types in wrong layer**
- `ConnectionStatus` lives in infrastructure but used by all layers
- No clear "shared types" location

**Problem 3: TUI imports from infrastructure**
```python
# tui/app.py
from nxs.mcp_client.client import ConnectionStatus        # SHOULD USE CORE
```

### 🔴 Critical: Package Organization Unclear

**Problem 4: Artifacts package mixes concerns**
- Repository (data access)
- Cache (storage)
- ChangeDetector (comparison)
- No clear organizing principle

**Problem 5: No clear layer boundaries**
```
Current:
  core/          (domain but imports infrastructure)
  mcp_client/    (infrastructure)
  tui/           (presentation but imports infrastructure)
```

---

## Proposed Architecture: Clean Layered Structure

### Architectural Layers (Dependency Direction)

```
┌─────────────────────────────────────────────────────┐
│  Presentation Layer (tui/)                          │
│  - UI widgets, event handlers, formatters           │
│  - Depends on: Application, Domain                  │
└────────────────┬────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────┐
│  Application Layer (core/)                          │
│  - Use cases, orchestration, services               │
│  - Depends on: Domain                               │
└────────────────┬────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────┐
│  Domain Layer (domain/)                             │
│  - Business rules, protocols, types                 │
│  - Depends on: NOTHING (pure domain)                │
└─────────────────────────────────────────────────────┘
                 ↑
                 │
┌────────────────┴────────────────────────────────────┐
│  Infrastructure Layer (infrastructure/)             │
│  - External systems (MCP, network, storage)         │
│  - Depends on: Domain (implements protocols)        │
└─────────────────────────────────────────────────────┘
```

**Key Principle:**
- Domain is the CENTER - no dependencies on anything
- All layers depend on Domain
- Infrastructure implements Domain protocols
- Application orchestrates Domain + Infrastructure
- Presentation uses Application + Domain

---

## New Package Structure

### Overview

```
src/nxs/
├── domain/                    # NEW: Pure domain layer (no dependencies)
│   ├── protocols/             # Interfaces for all implementations
│   ├── types/                 # Shared types (ConnectionStatus, etc.)
│   ├── events/                # Domain events
│   └── exceptions/            # Domain exceptions
│
├── application/               # RENAMED: core/ → application/
│   ├── artifacts/             # Artifact use cases
│   ├── agents/                # Agent loop, command control
│   ├── parsers/               # Argument parsing
│   ├── suggestions/           # Suggestion generation
│   └── services/              # Application services
│
├── infrastructure/            # RENAMED: mcp_client/ → infrastructure/
│   ├── mcp/                   # MCP client implementation
│   │   ├── client/            # Client implementations
│   │   ├── connection/        # Connection management
│   │   ├── operations/        # MCP operations
│   │   └── factory/           # Client factory
│   ├── cache/                 # Cache implementations
│   └── storage/               # Storage implementations
│
└── presentation/              # RENAMED: tui/ → presentation/
    ├── app/                   # Application shell
    ├── widgets/               # UI widgets
    ├── handlers/              # Event handlers
    ├── services/              # Presentation services
    ├── completion/            # Autocomplete
    └── formatters/            # Display formatters
```

### Detailed Structure

```
src/nxs/
│
├── domain/                                    # Pure domain - no external deps
│   ├── __init__.py
│   │
│   ├── protocols/                             # All protocols/interfaces
│   │   ├── __init__.py
│   │   ├── mcp_client.py                      # MCPClient protocol
│   │   ├── cache.py                           # Cache protocol
│   │   ├── parser.py                          # ArgumentParser protocol
│   │   ├── callbacks.py                       # AgentCallbacks protocol
│   │   └── factory.py                         # ClientProvider protocol
│   │
│   ├── types/                                 # Shared types
│   │   ├── __init__.py
│   │   ├── connection.py                      # ConnectionStatus enum
│   │   ├── artifacts.py                       # ArtifactCollection, etc.
│   │   └── messages.py                        # Message types
│   │
│   ├── events/                                # Domain events
│   │   ├── __init__.py
│   │   ├── bus.py                             # EventBus
│   │   └── types.py                           # Event type definitions (fixed imports)
│   │
│   └── exceptions/                            # Domain exceptions
│       ├── __init__.py
│       └── errors.py                          # Custom exceptions
│
├── application/                               # Application/use case layer
│   ├── __init__.py
│   │
│   ├── artifacts/                             # Artifact management
│   │   ├── __init__.py
│   │   ├── manager.py                         # ArtifactManager (orchestrator)
│   │   ├── repository.py                      # ArtifactRepository
│   │   ├── cache.py                           # ArtifactCache
│   │   └── change_detector.py                 # ArtifactChangeDetector
│   │
│   ├── agents/                                # Agent implementations
│   │   ├── __init__.py
│   │   ├── base.py                            # AgentLoop base
│   │   ├── command_control.py                 # CommandControlAgent
│   │   └── messaging/                         # Message handling
│   │       ├── __init__.py
│   │       └── converter.py                   # Message conversion
│   │
│   ├── parsers/                               # Argument parsing
│   │   ├── __init__.py
│   │   ├── composite.py                       # CompositeArgumentParser
│   │   ├── positional.py                      # PositionalArgumentParser
│   │   ├── key_value.py                       # KeyValueArgumentParser
│   │   ├── schema_adapter.py                  # Schema handling
│   │   └── utils.py                           # Parsing utilities
│   │
│   ├── suggestions/                           # Suggestion generation
│   │   ├── __init__.py
│   │   └── generator.py                       # ArgumentSuggestionGenerator
│   │
│   ├── tools/                                 # Tool management
│   │   ├── __init__.py
│   │   └── manager.py                         # ToolManager
│   │
│   ├── config/                                # Configuration
│   │   ├── __init__.py
│   │   └── mcp_config.py                      # MCP configuration
│   │
│   └── claude/                                # Claude integration
│       ├── __init__.py
│       └── client.py                          # Claude client wrapper
│
├── infrastructure/                            # Infrastructure implementations
│   ├── __init__.py
│   │
│   ├── mcp/                                   # MCP implementation
│   │   ├── __init__.py
│   │   │
│   │   ├── client/                            # Client implementations
│   │   │   ├── __init__.py
│   │   │   ├── auth_client.py                 # MCPAuthClient
│   │   │   ├── auth.py                        # OAuth handling
│   │   │   └── callback.py                    # Callback helpers
│   │   │
│   │   ├── connection/                        # Connection management
│   │   │   ├── __init__.py
│   │   │   ├── manager.py                     # ConnectionManager
│   │   │   ├── lifecycle.py                   # ConnectionLifecycle
│   │   │   ├── reconnect.py                   # ReconnectionStrategy
│   │   │   └── health.py                      # HealthChecker
│   │   │
│   │   ├── operations/                        # MCP operations
│   │   │   ├── __init__.py
│   │   │   ├── base.py                        # OperationBase
│   │   │   ├── tools.py                       # ToolsOperations
│   │   │   ├── prompts.py                     # PromptsOperations
│   │   │   └── resources.py                   # ResourcesOperations
│   │   │
│   │   ├── factory/                           # Client factory
│   │   │   ├── __init__.py
│   │   │   └── client_factory.py              # ClientFactory
│   │   │
│   │   ├── storage/                           # MCP storage
│   │   │   ├── __init__.py
│   │   │   └── state.py                       # State persistence
│   │   │
│   │   └── cli/                               # CLI tools
│   │       ├── __init__.py
│   │       └── __main__.py                    # MCP CLI
│   │
│   └── cache/                                 # Cache implementations
│       ├── __init__.py
│       ├── memory.py                          # MemoryCache
│       └── ttl.py                             # TTLCache
│
└── presentation/                              # Presentation/UI layer
    ├── __init__.py
    │
    ├── app/                                   # Application shell
    │   ├── __init__.py
    │   ├── nexus_app.py                       # NexusApp (main app)
    │   ├── styles.tcss                        # Textual CSS
    │   └── query_manager.py                   # Query management
    │
    ├── widgets/                               # UI widgets
    │   ├── __init__.py
    │   ├── chat_panel.py                      # ChatPanel
    │   ├── status_panel.py                    # StatusPanel
    │   ├── mcp_panel.py                       # MCPPanel
    │   ├── server_widget.py                   # ServerWidget
    │   ├── artifact_item.py                   # ArtifactItem
    │   ├── input_field.py                     # NexusInput
    │   ├── autocomplete.py                    # NexusAutoComplete
    │   ├── artifact_overlay.py                # ArtifactOverlay
    │   └── static_no_margin.py                # StaticNoMargin
    │
    ├── handlers/                              # Event handlers
    │   ├── __init__.py
    │   ├── connection.py                      # ConnectionHandler
    │   ├── query.py                           # QueryHandler
    │   └── refresh.py                         # RefreshHandler
    │
    ├── services/                              # Presentation services
    │   ├── __init__.py
    │   ├── coordinator.py                     # MCPCoordinator
    │   ├── prompts.py                         # PromptService
    │   ├── autocomplete.py                    # AutocompleteService
    │   ├── refresh.py                         # RefreshService
    │   └── status_queue.py                    # StatusQueue
    │
    ├── completion/                            # Autocomplete strategies
    │   ├── __init__.py
    │   ├── strategy.py                        # Strategy protocol
    │   ├── orchestrator.py                    # Orchestrator
    │   ├── applier.py                         # CompletionApplier
    │   ├── resource.py                        # ResourceCompletionStrategy
    │   ├── command.py                         # CommandCompletionStrategy
    │   ├── argument.py                        # ArgumentCompletionStrategy
    │   ├── prompt_utils.py                    # Prompt utilities
    │   └── schema_cache.py                    # Schema cache
    │
    └── formatters/                            # Display formatters
        ├── __init__.py
        └── status.py                          # Status formatting
```

---

## Key Architectural Decisions

### 1. Domain Layer - The Foundation

**Location:** `src/nxs/domain/`

**Purpose:** Pure business rules and abstractions with ZERO external dependencies

**Contains:**
- **Protocols** - All interfaces (MCPClient, Cache, ArgumentParser, etc.)
- **Types** - Shared types (ConnectionStatus, ArtifactCollection, etc.)
- **Events** - Domain events (EventBus, ConnectionStatusChanged, etc.)
- **Exceptions** - Domain-specific exceptions

**Rules:**
- ✅ No imports from application, infrastructure, or presentation
- ✅ No external library dependencies (except Python stdlib and typing)
- ✅ Only pure Python - no async/await in protocols if possible
- ✅ Defines WHAT the system does, not HOW

**Example:**
```python
# domain/types/connection.py
from enum import Enum

class ConnectionStatus(Enum):
    """Connection status for MCP clients."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
```

---

### 2. Application Layer - Use Cases & Orchestration

**Location:** `src/nxs/application/`

**Purpose:** Implements business logic and orchestrates domain + infrastructure

**Contains:**
- **Artifacts** - Artifact management use cases
- **Agents** - Agent loop implementations (base, command control)
- **Parsers** - Argument parsing implementations
- **Suggestions** - Suggestion generation logic
- **Tools** - Tool management
- **Config** - Configuration loading
- **Claude** - Claude API wrapper

**Dependencies:**
- ✅ Imports from `domain/`
- ✅ Uses domain protocols
- ❌ Does NOT import from `infrastructure/` or `presentation/`
- ❌ Only depends on abstractions, never concrete implementations

**Example:**
```python
# application/artifacts/manager.py
from nxs.domain.protocols import MCPClient, ClientProvider
from nxs.domain.types import ConnectionStatus
from nxs.domain.events import EventBus, ConnectionStatusChanged

class ArtifactManager:
    """Orchestrates artifact access across MCP clients."""

    def __init__(
        self,
        client_provider: ClientProvider,  # Protocol, not concrete
        event_bus: EventBus,
    ):
        self.client_provider = client_provider
        self.event_bus = event_bus
```

---

### 3. Infrastructure Layer - External Systems

**Location:** `src/nxs/infrastructure/`

**Purpose:** Implements connections to external systems (MCP, network, storage, cache)

**Contains:**
- **MCP** - All MCP client implementation
  - Client implementations (MCPAuthClient)
  - Connection management
  - Operations (tools, prompts, resources)
  - Factory (creates clients)
  - Storage (state persistence)
- **Cache** - Cache implementations (MemoryCache, TTLCache)

**Dependencies:**
- ✅ Imports from `domain/` (implements protocols)
- ✅ Uses external libraries (mcp SDK, httpx, etc.)
- ❌ Does NOT import from `application/` or `presentation/`

**Example:**
```python
# infrastructure/mcp/client/auth_client.py
from nxs.domain.protocols import MCPClient
from nxs.domain.types import ConnectionStatus

class MCPAuthClient:
    """MCP client with authentication support."""

    # Implements MCPClient protocol implicitly
    async def connect(self, use_auth: bool = False):
        ...
```

---

### 4. Presentation Layer - UI & User Interaction

**Location:** `src/nxs/presentation/`

**Purpose:** User interface and interaction logic

**Contains:**
- **App** - Main application shell
- **Widgets** - All Textual widgets
- **Handlers** - Event handlers
- **Services** - Presentation-specific services
- **Completion** - Autocomplete strategies
- **Formatters** - Display formatting

**Dependencies:**
- ✅ Imports from `domain/` and `application/`
- ✅ Uses Textual, Rich libraries
- ❌ Does NOT import from `infrastructure/`

**Example:**
```python
# presentation/app/nexus_app.py
from nxs.domain.events import EventBus
from nxs.domain.types import ConnectionStatus
from nxs.application.artifacts import ArtifactManager
from nxs.application.agents import AgentLoop

class NexusApp(App):
    """Main Nexus TUI application."""

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        agent_loop: AgentLoop,
        event_bus: EventBus,
    ):
        ...
```

---

## Migration Strategy

### Phase 1: Create Domain Layer (Week 1, 5-6 hours)

**Goal:** Establish pure domain with no dependencies

#### Step 1.1: Create Domain Structure (1 hour)

Create all domain packages:
```bash
mkdir -p src/nxs/domain/{protocols,types,events,exceptions}
touch src/nxs/domain/__init__.py
touch src/nxs/domain/protocols/__init__.py
touch src/nxs/domain/types/__init__.py
touch src/nxs/domain/events/__init__.py
touch src/nxs/domain/exceptions/__init__.py
```

---

#### Step 1.2: Move ConnectionStatus to Domain (2 hours)

**Create:** `domain/types/connection.py`

```python
"""Connection-related types."""

from enum import Enum

__all__ = ["ConnectionStatus"]


class ConnectionStatus(Enum):
    """Status of an MCP client connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
```

**Update all imports:**
```python
# OLD (wrong):
from nxs.mcp_client.client import ConnectionStatus
from nxs.mcp_client.connection.lifecycle import ConnectionStatus

# NEW (correct):
from nxs.domain.types import ConnectionStatus
```

**Files to update:**
- `core/artifact_manager.py`
- `core/events/types.py`
- `tui/app.py`
- `mcp_client/client.py`
- `mcp_client/connection/lifecycle.py`
- Any other files importing ConnectionStatus

---

#### Step 1.3: Move Protocols to Domain (2 hours)

**Create:** `domain/protocols/mcp_client.py`

```python
"""MCP client protocol."""

from typing import Protocol, Any

__all__ = ["MCPClient"]


class MCPClient(Protocol):
    """Protocol for MCP client implementations."""

    async def connect(self, use_auth: bool = False) -> None:
        """Establish connection to MCP server."""
        ...

    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        ...

    @property
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        ...

    async def list_resources(self) -> list[Any]:
        """List available resources."""
        ...

    async def list_prompts(self) -> list[Any]:
        """List available prompts."""
        ...

    async def list_tools(self) -> list[Any]:
        """List available tools."""
        ...

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Execute a tool."""
        ...

    async def get_prompt(self, name: str, arguments: dict | None = None) -> Any:
        """Get a prompt."""
        ...

    async def read_resource(self, uri: str) -> Any:
        """Read a resource."""
        ...
```

**Create:** `domain/protocols/cache.py`

```python
"""Cache protocol."""

from typing import Protocol, TypeVar, Generic

__all__ = ["Cache"]

K = TypeVar("K")
V = TypeVar("V")


class Cache(Protocol, Generic[K, V]):
    """Protocol for cache implementations."""

    def get(self, key: K) -> V | None:
        """Get value for key."""
        ...

    def set(self, key: K, value: V) -> None:
        """Set value for key."""
        ...

    def delete(self, key: K) -> None:
        """Delete key."""
        ...

    def clear(self) -> None:
        """Clear all entries."""
        ...

    def __contains__(self, key: K) -> bool:
        """Check if key exists."""
        ...
```

**Create:** `domain/protocols/parser.py`

```python
"""Argument parser protocol."""

from typing import Protocol, Any

__all__ = ["ArgumentParser"]


class ArgumentParser(Protocol):
    """Protocol for argument parsing strategies."""

    def parse(
        self,
        command_input: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Parse command input according to schema."""
        ...
```

**Create:** `domain/protocols/factory.py`

```python
"""Client factory protocol."""

from typing import Protocol, Callable
from nxs.domain.protocols.mcp_client import MCPClient
from nxs.domain.types import ConnectionStatus

__all__ = ["ClientProvider"]


class ClientProvider(Protocol):
    """Protocol for creating MCP clients."""

    def create_clients(
        self,
        servers_config: dict,
        status_callback: Callable[[str, ConnectionStatus], None],
        progress_callback: Callable,
    ) -> dict[str, MCPClient]:
        """Create clients for configured servers."""
        ...
```

**Update:** `domain/protocols/__init__.py`

```python
"""Domain protocols - interfaces for all implementations."""

from nxs.domain.protocols.mcp_client import MCPClient
from nxs.domain.protocols.cache import Cache
from nxs.domain.protocols.parser import ArgumentParser
from nxs.domain.protocols.factory import ClientProvider

__all__ = [
    "MCPClient",
    "Cache",
    "ArgumentParser",
    "ClientProvider",
]
```

**Update all imports:**
```python
# OLD:
from nxs.core.protocols import MCPClient, Cache, ArgumentParser

# NEW:
from nxs.domain.protocols import MCPClient, Cache, ArgumentParser, ClientProvider
```

---

#### Step 1.4: Move Events to Domain (1 hour)

**Create:** `domain/types/artifacts.py`

```python
"""Artifact-related types."""

from typing import TypedDict

__all__ = ["ArtifactCollection"]


class ArtifactCollection(TypedDict):
    """Collection of artifacts from an MCP server."""

    tools: list
    prompts: list
    resources: list
```

**Move:** `core/events/` → `domain/events/`

**Update:** `domain/events/types.py` (fix imports)

```python
"""Domain event types."""

from dataclasses import dataclass
from nxs.domain.types import ConnectionStatus, ArtifactCollection

__all__ = [
    "Event",
    "ConnectionStatusChanged",
    "ReconnectProgress",
    "ArtifactsFetched",
]


@dataclass
class Event:
    """Base class for domain events."""
    pass


@dataclass
class ConnectionStatusChanged(Event):
    """Event fired when connection status changes."""
    server_name: str
    status: ConnectionStatus


@dataclass
class ReconnectProgress(Event):
    """Event fired during reconnection attempts."""
    server_name: str
    attempts: int
    max_attempts: int
    next_retry_delay: float


@dataclass
class ArtifactsFetched(Event):
    """Event fired when artifacts are fetched."""
    server_name: str
    artifacts: ArtifactCollection
```

**Update:** `domain/events/__init__.py`

```python
"""Domain events - event bus and event types."""

from nxs.domain.events.bus import EventBus
from nxs.domain.events.types import (
    Event,
    ConnectionStatusChanged,
    ReconnectProgress,
    ArtifactsFetched,
)

__all__ = [
    "EventBus",
    "Event",
    "ConnectionStatusChanged",
    "ReconnectProgress",
    "ArtifactsFetched",
]
```

**Update all imports:**
```python
# OLD:
from nxs.core.events import EventBus, ConnectionStatusChanged

# NEW:
from nxs.domain.events import EventBus, ConnectionStatusChanged
```

---

### Phase 2: Rename and Reorganize Packages (Week 1-2, 6-8 hours)

**Goal:** Establish clear layer structure

#### Step 2.1: Rename core/ → application/ (2-3 hours)

**Action:**
```bash
git mv src/nxs/core src/nxs/application
```

**Update imports across entire codebase:**
```python
# OLD:
from nxs.core.artifact_manager import ArtifactManager
from nxs.core.chat import AgentLoop
from nxs.core.protocols import MCPClient

# NEW:
from nxs.application.artifacts import ArtifactManager
from nxs.application.agents import AgentLoop
from nxs.domain.protocols import MCPClient
```

**Use find/replace:**
```bash
find src/nxs -type f -name "*.py" -exec sed -i '' 's/from nxs\.core\./from nxs.application./g' {} +
```

---

#### Step 2.2: Reorganize application/ Structure (2-3 hours)

**Create subpackages:**

```bash
# Create new structure
mkdir -p src/nxs/application/{artifacts,agents,parsers,suggestions,tools,config,claude}

# Move files
mv src/nxs/application/artifact_manager.py src/nxs/application/artifacts/manager.py
mv src/nxs/application/artifacts/*.py src/nxs/application/artifacts/
mv src/nxs/application/chat.py src/nxs/application/agents/base.py
mv src/nxs/application/command_control.py src/nxs/application/agents/command_control.py
mv src/nxs/application/parsers/*.py src/nxs/application/parsers/
mv src/nxs/application/suggestions/*.py src/nxs/application/suggestions/
mv src/nxs/application/tools.py src/nxs/application/tools/manager.py
mv src/nxs/application/mcp_config.py src/nxs/application/config/mcp_config.py
mv src/nxs/application/claude.py src/nxs/application/claude/client.py
```

**Create __init__.py files for each subpackage**

**Update imports:**
```python
# OLD:
from nxs.application.artifact_manager import ArtifactManager
from nxs.application.chat import AgentLoop
from nxs.application.tools import ToolManager

# NEW:
from nxs.application.artifacts import ArtifactManager
from nxs.application.agents import AgentLoop
from nxs.application.tools import ToolManager
```

---

#### Step 2.3: Rename mcp_client/ → infrastructure/ (1-2 hours)

**Action:**
```bash
git mv src/nxs/mcp_client src/nxs/infrastructure/mcp
```

**Create infrastructure structure:**
```bash
mkdir -p src/nxs/infrastructure/{mcp,cache}

# Move cache implementations
mv src/nxs/application/cache/* src/nxs/infrastructure/cache/
```

**Reorganize MCP structure:**
```bash
cd src/nxs/infrastructure/mcp
mkdir -p client connection operations factory storage cli

# Move files to proper locations
mv client.py client/auth_client.py
mv auth.py client/auth.py
mv callback.py client/callback.py
mv factory.py factory/client_factory.py
mv storage.py storage/state.py
mv cli.py cli/__main__.py
# connection/ and operations/ already organized
```

**Update imports:**
```python
# OLD:
from nxs.mcp_client.client import MCPAuthClient
from nxs.mcp_client.factory import ClientFactory

# NEW:
from nxs.infrastructure.mcp.client import MCPAuthClient
from nxs.infrastructure.mcp.factory import ClientFactory
```

---

#### Step 2.4: Rename tui/ → presentation/ (1 hour)

**Action:**
```bash
git mv src/nxs/tui src/nxs/presentation
```

**Reorganize presentation structure:**
```bash
cd src/nxs/presentation
mkdir -p app

# Move app-level files
mv app.py app/nexus_app.py
mv styles.tcss app/styles.tcss
mv query_manager.py app/query_manager.py
mv status_queue.py services/status_queue.py

# Rename service files for clarity
mv services/mcp_coordinator.py services/coordinator.py
mv services/prompt_service.py services/prompts.py
mv services/autocomplete_service.py services/autocomplete.py
mv services/mcp_refresher.py services/refresh.py

# Rename handler files
mv handlers/connection_handler.py handlers/connection.py
mv handlers/query_handler.py handlers/query.py
mv handlers/refresh_handler.py handlers/refresh.py

# Rename completion files
mv completion/resource_completion.py completion/resource.py
mv completion/command_completion.py completion/command.py
mv completion/argument_completion.py completion/argument.py
```

**Update imports:**
```python
# OLD:
from nxs.tui.app import NexusApp
from nxs.tui.services.mcp_coordinator import MCPCoordinator

# NEW:
from nxs.presentation.app import NexusApp
from nxs.presentation.services import MCPCoordinator
```

---

### Phase 3: Fix All Import Statements (Week 2, 3-4 hours)

**Goal:** Ensure all imports follow new structure and dependency rules

#### Step 3.1: Update Application Layer Imports (1-2 hours)

**Files in `application/`:**

All files should import:
- ✅ From `domain/` (protocols, types, events)
- ❌ NEVER from `infrastructure/` or `presentation/`

**Example fixes:**

```python
# application/artifacts/manager.py

# BEFORE:
from nxs.core.protocols import MCPClient
from nxs.mcp_client.client import ConnectionStatus
from nxs.mcp_client.factory import ClientFactory

# AFTER:
from nxs.domain.protocols import MCPClient, ClientProvider
from nxs.domain.types import ConnectionStatus
from nxs.domain.events import EventBus, ConnectionStatusChanged
```

```python
# application/agents/base.py

# BEFORE:
from nxs.core.protocols import MCPClient
from nxs.core.tools import ToolManager

# AFTER:
from nxs.domain.protocols import MCPClient
from nxs.application.tools import ToolManager
```

**Run automated check:**
```bash
# Check for violations
grep -r "from nxs.infrastructure" src/nxs/application/
grep -r "from nxs.presentation" src/nxs/application/
# Should return NOTHING
```

---

#### Step 3.2: Update Infrastructure Layer Imports (1 hour)

**Files in `infrastructure/`:**

All files should import:
- ✅ From `domain/` (implement protocols)
- ❌ NEVER from `application/` or `presentation/`

**Example fixes:**

```python
# infrastructure/mcp/client/auth_client.py

# BEFORE:
from mcp.types import Resource, Prompt, Tool

# AFTER:
from nxs.domain.protocols import MCPClient
from nxs.domain.types import ConnectionStatus
from mcp.types import Resource, Prompt, Tool
```

```python
# infrastructure/mcp/factory/client_factory.py

# BEFORE:
from nxs.mcp_client.client import MCPAuthClient

# AFTER:
from nxs.domain.protocols import MCPClient, ClientProvider
from nxs.domain.types import ConnectionStatus
from nxs.infrastructure.mcp.client import MCPAuthClient
```

---

#### Step 3.3: Update Presentation Layer Imports (1 hour)

**Files in `presentation/`:**

All files should import:
- ✅ From `domain/` and `application/`
- ❌ NEVER from `infrastructure/`

**Example fixes:**

```python
# presentation/app/nexus_app.py

# BEFORE:
from nxs.core.artifact_manager import ArtifactManager
from nxs.mcp_client.client import ConnectionStatus
from nxs.tui.services.mcp_coordinator import MCPCoordinator

# AFTER:
from nxs.domain.types import ConnectionStatus
from nxs.domain.events import EventBus
from nxs.application.artifacts import ArtifactManager
from nxs.application.agents import AgentLoop
from nxs.presentation.services import MCPCoordinator
```

**Run automated check:**
```bash
# Check for violations
grep -r "from nxs.infrastructure" src/nxs/presentation/
# Should return NOTHING
```

---

### Phase 4: Update Entry Points and Main (Week 2, 1-2 hours)

**Goal:** Update main.py and __main__.py to use new structure

#### Step 4.1: Update main.py (1 hour)

```python
# src/nxs/main.py

"""Main entry point for Nexus application."""

from nxs.domain.events import EventBus
from nxs.domain.types import ConnectionStatus

from nxs.application.artifacts import ArtifactManager
from nxs.application.agents import CommandControlAgent
from nxs.application.claude import Claude
from nxs.application.config import load_mcp_config

from nxs.infrastructure.mcp.factory import ClientFactory

from nxs.presentation.app import NexusApp


async def main():
    """Initialize and run Nexus application."""

    # Create domain layer
    event_bus = EventBus()

    # Create infrastructure
    client_factory = ClientFactory()

    # Create application layer
    config = load_mcp_config()
    artifact_manager = ArtifactManager(
        config=config,
        client_provider=client_factory,  # Inject via protocol
        event_bus=event_bus,
    )

    llm = Claude()
    agent_loop = CommandControlAgent(
        llm=llm,
        artifact_manager=artifact_manager,
    )

    # Create presentation layer
    app = NexusApp(
        agent_loop=agent_loop,
        artifact_manager=artifact_manager,
        event_bus=event_bus,
    )

    await app.run_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

---

### Phase 5: Update Tests (Week 2-3, 2-3 hours)

**Goal:** Update all test imports

**Strategy:**
1. Update test imports to use new structure
2. Ensure tests still pass
3. Add import validation tests

**Example:**

```python
# tests/test_artifact_manager.py

# BEFORE:
from nxs.core.artifact_manager import ArtifactManager
from nxs.core.protocols import MCPClient

# AFTER:
from nxs.domain.protocols import MCPClient
from nxs.application.artifacts import ArtifactManager
```

**Add architectural test:**

```python
# tests/test_architecture.py

"""Test architectural boundaries."""

import ast
import os
from pathlib import Path


def test_domain_has_no_external_dependencies():
    """Domain layer should not import from application, infrastructure, or presentation."""

    domain_path = Path("src/nxs/domain")
    violations = []

    for py_file in domain_path.rglob("*.py"):
        with open(py_file) as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("nxs."):
                    if any(x in node.module for x in ["application", "infrastructure", "presentation"]):
                        violations.append(f"{py_file}: {node.module}")

    assert not violations, f"Domain layer has forbidden imports: {violations}"


def test_application_does_not_import_infrastructure():
    """Application layer should not import from infrastructure or presentation."""

    app_path = Path("src/nxs/application")
    violations = []

    for py_file in app_path.rglob("*.py"):
        with open(py_file) as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("nxs."):
                    if any(x in node.module for x in ["infrastructure", "presentation"]):
                        violations.append(f"{py_file}: {node.module}")

    assert not violations, f"Application layer has forbidden imports: {violations}"


def test_presentation_does_not_import_infrastructure():
    """Presentation layer should not import from infrastructure."""

    pres_path = Path("src/nxs/presentation")
    violations = []

    for py_file in pres_path.rglob("*.py"):
        with open(py_file) as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("nxs.infrastructure"):
                    violations.append(f"{py_file}: {node.module}")

    assert not violations, f"Presentation layer has forbidden imports: {violations}"
```

---

## Success Metrics

### Quantitative

| Metric | Before | After | Status |
|--------|--------|-------|--------|
| **Domain layer dependencies** | N/A | 0 external | ✅ Target |
| **Core→Infrastructure imports** | 4+ violations | 0 violations | ✅ Target |
| **TUI→Infrastructure imports** | 2+ violations | 0 violations | ✅ Target |
| **Package depth** | 2-3 levels | 3-4 levels | ✅ Clear structure |
| **Shared types location** | Infrastructure | Domain | ✅ Correct layer |

### Qualitative

**✅ MUST ACHIEVE:**

- [ ] **Zero Layer Violations**
  - Domain imports nothing from app/infra/presentation
  - Application imports only from domain
  - Infrastructure imports only from domain
  - Presentation imports from domain + application

- [ ] **Clear Package Organization**
  - `domain/` - Pure abstractions, no dependencies
  - `application/` - Use cases and business logic
  - `infrastructure/` - External system implementations
  - `presentation/` - UI and user interaction

- [ ] **Dependency Direction**
  - All arrows point toward domain
  - No circular dependencies
  - Clear, enforceable rules

- [ ] **Expansion Ready**
  - Easy to add new protocols to domain
  - Easy to add new use cases to application
  - Easy to add new implementations to infrastructure
  - Easy to add new UI to presentation

**✅ SHOULD ACHIEVE:**

- [ ] **Automated Testing**
  - Tests verify architectural boundaries
  - CI fails on layer violations
  - Import checks automated

- [ ] **Clear Documentation**
  - README in each major package
  - Dependency rules documented
  - Examples of where to add new features

---

## Testing Strategy

### Automated Architecture Tests

Add to CI pipeline:

```python
# tests/test_architecture.py - Already shown above
```

### Manual Verification

After migration:

```bash
# 1. Check no forbidden imports
grep -r "from nxs.infrastructure" src/nxs/domain/
grep -r "from nxs.application" src/nxs/domain/
grep -r "from nxs.infrastructure" src/nxs/application/
grep -r "from nxs.infrastructure" src/nxs/presentation/

# Should all return NOTHING

# 2. Run type checker
pixi run --environment dev type-check

# 3. Run tests
pixi run --environment test test

# 4. Run application
pixi run start
```

---

## Migration Checklist

### Week 1: Domain Layer
- [ ] Step 1.1: Create domain structure
- [ ] Step 1.2: Move ConnectionStatus to domain/types
- [ ] Step 1.3: Move all protocols to domain/protocols
- [ ] Step 1.4: Move events to domain/events
- [ ] Verify: Domain has zero external dependencies
- [ ] Run tests

### Week 2: Rename Packages
- [ ] Step 2.1: Rename core → application
- [ ] Step 2.2: Reorganize application structure
- [ ] Step 2.3: Rename mcp_client → infrastructure
- [ ] Step 2.4: Rename tui → presentation
- [ ] Verify: All files moved correctly
- [ ] Run tests

### Week 2: Fix Imports
- [ ] Step 3.1: Fix application layer imports
- [ ] Step 3.2: Fix infrastructure layer imports
- [ ] Step 3.3: Fix presentation layer imports
- [ ] Verify: No layer violations
- [ ] Run automated architecture tests

### Week 2-3: Update Entry Points & Tests
- [ ] Step 4.1: Update main.py
- [ ] Step 4.2: Update __main__.py
- [ ] Step 5: Update all test imports
- [ ] Add architecture tests
- [ ] Verify: Full test suite passes
- [ ] Verify: Application runs correctly

---

## Appendix: Quick Reference

### Import Rules

```python
# ✅ DOMAIN (no external dependencies)
from enum import Enum
from typing import Protocol
# NO imports from nxs.* except internal domain

# ✅ APPLICATION (imports domain only)
from nxs.domain.protocols import MCPClient, Cache
from nxs.domain.types import ConnectionStatus
from nxs.domain.events import EventBus
# NO imports from infrastructure or presentation

# ✅ INFRASTRUCTURE (imports domain only)
from nxs.domain.protocols import MCPClient
from nxs.domain.types import ConnectionStatus
from mcp import ClientSession  # External library OK
# NO imports from application or presentation

# ✅ PRESENTATION (imports domain + application)
from nxs.domain.types import ConnectionStatus
from nxs.domain.events import EventBus
from nxs.application.artifacts import ArtifactManager
from textual.app import App  # External library OK
# NO imports from infrastructure
```

### Where to Add New Code

**New business rule?** → `domain/`
**New use case?** → `application/`
**New external integration?** → `infrastructure/`
**New UI feature?** → `presentation/`

---

**Document Version:** 1.0
**Date:** 2025-01-08
**Status:** Ready for Implementation
**Focus:** Structure & Boundaries, Not Optimization
