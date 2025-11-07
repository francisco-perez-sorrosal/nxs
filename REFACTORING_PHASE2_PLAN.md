# Nexus Phase 2 Refinement Plan - Holistic Consolidation & Polish

## Executive Summary

This document outlines the **Phase 2 refinement strategy** for the Nexus codebase following the successful completion of Phase 1-3 refactoring. While Phase 1-3 established excellent foundations (protocol abstractions, event-driven architecture, parser extraction, connection management decomposition), the incremental nature of that work left some redundancies, incomplete decompositions, and architectural inconsistencies.

**Phase 2 Goals:**
1. **Complete the decomposition** of the largest remaining files (AutoComplete: 905 lines, MCPPanel: 838 lines)
2. **Eliminate redundancies** introduced during incremental refactoring (fetching layers, legacy callbacks)
3. **Enforce clean architecture boundaries** (move business logic out of TUI, fix protocol violations)
4. **Polish and document** the final architecture with consistent patterns

**Timeline:** 4-5 weeks, 25-30 hours total effort
**Risk Level:** Low (building on proven Phase 1-3 patterns)

---

## 1. Post-Phase 1-3 Analysis

### 1.1 Achievements from Phase 1-3

✅ **Excellent protocol abstractions established:**
- `MCPClient`, `Cache`, `ArgumentParser` protocols provide clear contracts
- Structural typing enables easy mocking and testing
- Type safety improved across codebase

✅ **Event-driven architecture successfully implemented:**
- `EventBus` decouples core from UI layer
- Three event types: `ConnectionStatusChanged`, `ReconnectProgress`, `ArtifactsFetched`
- Handlers subscribe to events cleanly

✅ **Parser logic cleanly extracted:**
- `core/parsers/` package with 5 focused classes
- `CompositeArgumentParser` orchestrates strategies
- `CommandControlAgent` reduced from 471 → 241 lines (49% reduction)

✅ **Connection management well-decomposed:**
- `ConnectionManager`, `HealthChecker`, `ReconnectionStrategy`, `ConnectionLifecycle`
- `MCPAuthClient` reduced from 784 → 197 lines (75% reduction) - **best result**
- Clean separation of concerns

✅ **NexusApp decomposed into services and handlers:**
- `MCPCoordinator`, `PromptService`, `AutocompleteService`, `MCPRefresher`, `ArtifactFetcher`
- `ConnectionHandler`, `QueryHandler`, `RefreshHandler`
- `NexusApp` reduced from 993 → 529 lines (47% reduction)

---

### 1.2 Remaining Issues After Phase 1-3

**Phase 2 Progress Update:**
- ✅ **HIGH Priority Issues (H1-H4):** All 4 completed (~220 lines removed, zero new type errors)
- ✅ **MEDIUM Priority Issues (M1-M6):** All 6 completed (~515 lines removed, documentation added, architecture clarified)
- ✅ **LOW Priority Issues (L1-L2):** All 2 completed (type validation added, dead code removed)
- 🔄 **CRITICAL Issues (C1-C3):** In progress

---

#### CRITICAL Issues

**C1. AutoComplete Widget Too Large (905 lines) - Untouched**
- **File:** `tui/widgets/autocomplete.py`
- **Problem:** Giant widget class handling @resource and /command completions
- **Target:** Was supposed to be ~400 lines (55% reduction)
- **Actual:** Still 905 lines (0% reduction)
- **Impact:** Extremely difficult to test, hard to extend with new completion types
- **Root Cause:** Step 3.4 was never executed in Phase 1-3

**C2. MCPPanel Widget Too Large (838 lines) - Untouched**
- **File:** `tui/widgets/mcp_panel.py`
- **Problem:** Complex widget with module-level helpers, 3 nested classes
- **Target:** Was supposed to be ~400 lines (54% reduction)
- **Actual:** Still 838 lines (0% reduction)
- **Details:**
  - Module-level formatters (lines 20-172): 152 lines
  - `ServerWidget` nested class: 375 lines
  - Main `MCPPanel` class: 254 lines
- **Impact:** Difficult to maintain, poor separation of concerns
- **Root Cause:** Step 3.5 was never executed in Phase 1-3

**C3. ArtifactManager Incompletely Decomposed (523 lines)**
- **File:** `core/artifact_manager.py`
- **Problem:** Still a facade doing too much
- **Target:** Was supposed to be ~200 lines (68% reduction)
- **Actual:** 523 lines (only 17% reduction from 627)
- **Issues:**
  - Creates and manages `MCPAuthClient` instances directly (lines 97-130)
  - Handles legacy callbacks alongside EventBus (dual responsibility)
  - Has 15+ public methods mixing orchestration with client management
  - `_create_clients()` method with 33 lines of instantiation logic embedded
- **Impact:** Hard to test in isolation, mixing infrastructure with domain logic
- **Root Cause:** Step 3.2 stopped short of full decomposition

---

#### ~~HIGH Priority Issues~~ ✅ **COMPLETED**

**~~H1. Empty `core/connection/` Directory~~** ✅ **COMPLETED**
- **Location:** `/Users/fperez/dev/nxs/src/nxs/core/connection/`
- **Problem:** Directory exists but contains only `__pycache__`
- **Solution:** Removed empty directory
- **Status:** ✅ Complete

**~~H2. Redundant Artifact Fetching Logic~~** ✅ **COMPLETED**
- **Files:**
  - ~~`tui/services/artifact_fetcher.py` (167 lines)~~ **REMOVED**
  - `core/artifacts/repository.py` (updated with timeout support)
- **Problem:** Three-layer delegation chain (Fetcher → Manager → Repository)
- **Solution:**
  - Added `timeout` parameter to `ArtifactRepository.get_server_artifacts()` and `get_all_servers_artifacts()`
  - Updated `ArtifactManager` to pass timeout through
  - Updated `MCPRefresher` to call `ArtifactManager` directly with timeout
  - Removed `ArtifactFetcher` service (167 lines)
  - Removed from `tui/services/__init__.py` exports
- **Impact:** 167 lines removed, cleaner two-layer delegation
- **Status:** ✅ Complete

**~~H3. Legacy Callback Support Cluttering Code~~** ✅ **COMPLETED**
- **File:** `core/artifact_manager.py`
- **Problem:** Maintaining both EventBus and legacy callbacks
- **Solution:**
  - Removed `on_status_change` and `on_reconnect_progress` parameters from `ArtifactManager.__init__()`
  - Removed dual handling code from `_handle_status_change()` and `_handle_reconnect_progress()`
  - Removed unused `Callable` import
  - EventBus is now the single communication mechanism
- **Impact:** ~50 lines removed, cleaner code paths
- **Status:** ✅ Complete

**~~H4. `type: ignore` Comments Indicate Design Issues~~** ✅ **COMPLETED**
- **Files:** `tui/handlers/connection_handler.py`
- **Problem:** 3 instances of `type: ignore[attr-defined]` accessing `client.reconnect_info`
- **Solution:**
  - Added `_reconnect_info_cache` dictionary to `ConnectionHandler`
  - Updated `handle_reconnect_progress()` to cache reconnect info from `ReconnectProgress` events
  - Updated `handle_connection_status_changed()` to use cached info instead of client property
  - Removed all 3 `type: ignore` comments
  - Added automatic cache cleanup when successfully connected
- **Impact:** Type-safe, event-driven, no protocol violations
- **Status:** ✅ Complete

---

#### ~~MEDIUM Priority Issues~~ ✅ **M1-M3 COMPLETED**

**~~M1. Inconsistent Service Naming Patterns~~** ✅ **COMPLETED**
- **Solution Implemented:**
  - Renamed `MCPRefresher` → `RefreshService` for consistency
  - Services pattern: Handle stateful operations, lifecycle management
  - Handlers pattern: Process events from EventBus
  - Updated all imports in: `app.py`, `connection_handler.py`, `refresh_handler.py`, `__init__.py`
- **Result:** Consistent naming: `RefreshService`, `PromptService`, `AutocompleteService` vs `ConnectionHandler`, `QueryHandler`, `RefreshHandler`
- **Files Modified:** 5 files (~15 lines changed)

**~~M2. Argument Suggestions Split Across Files~~** ✅ **COMPLETED**
- **Solution Implemented:**
  - Created `core/suggestions/` package
  - Moved `ArgumentSuggestionGenerator` from `tui/widgets/argument_suggestions.py` → `core/suggestions/generator.py`
  - Updated imports in `autocomplete.py` to use `core.suggestions`
  - Deleted `tui/widgets/argument_suggestions.py` (283 lines removed)
- **Result:** Business logic properly separated from UI layer, can be reused and tested independently
- **Files Created:** `core/suggestions/__init__.py`, `core/suggestions/generator.py`
- **Files Deleted:** `tui/widgets/argument_suggestions.py`

**~~M3. Command Parser Duplicated~~** ✅ **COMPLETED**
- **Solution Implemented:**
  - Created `core/parsers/utils.py` with quote-aware parsing utilities
  - Moved all reusable parsing functions from `tui/widgets/command_parser.py`:
    - `parse_command_arguments()`, `extract_last_argument()`, `is_inside_quotes()`
    - `extract_value_part()`, `is_complete_quoted_argument()`, `extract_provided_arg_names()`
    - `ParsedArgument` NamedTuple
  - Updated `core/parsers/__init__.py` to export utilities
  - Updated `autocomplete.py` and `ArgumentSuggestionGenerator` to import from `core.parsers.utils`
  - Deleted `tui/widgets/command_parser.py` (186 lines removed)
- **Result:** Single source of truth for command parsing, eliminates duplication risk
- **Files Created:** `core/parsers/utils.py` (188 lines)
- **Files Deleted:** `tui/widgets/command_parser.py` (186 lines)
- **Net Change:** +2 lines (but proper layer separation achieved)

**~~M4. Unclear Distinction: Services vs Handlers~~** ✅ **COMPLETED**
- **Solution Implemented:**
  - Created comprehensive README documentation for both packages
  - **Services pattern**: Manage stateful operations and lifecycle (hold caches, coordinate operations)
  - **Handlers pattern**: Process events from EventBus (stateless coordinators between events and services)
  - Clear guidelines with examples and anti-patterns documented
- **Files Created:**
  - `tui/services/README.md` (103 lines) - Service pattern documentation
  - `tui/handlers/README.md` (125 lines) - Handler pattern documentation
- **Result:** Clear architectural pattern definition with testing guidelines and examples

**~~M5. Prompt Schema Caching Duplication~~** ✅ **COMPLETED**
- **Solution Implemented:**
  - Modified `NexusAutoComplete` to reference `PromptService` directly instead of maintaining own caches
  - Created `CacheDict` wrapper class to provide dict-like interface to Cache protocol
  - `ArgumentSuggestionGenerator` now accesses PromptService cache via wrapper
  - Removed `copy_caches_to_dicts()` from PromptService (29 lines removed)
  - Removed `copy_prompt_caches()` from AutocompleteService (46 lines removed)
  - Updated `app.py` to remove cache copying logic
- **Result:** Single source of truth for prompt caching in PromptService
- **Files Modified:**
  - `autocomplete.py` (added CacheDict wrapper, updated all cache access)
  - `autocomplete_service.py` (removed copy_prompt_caches method)
  - `prompt_service.py` (removed copy_caches_to_dicts method)
  - `app.py` (removed cache copying call)
- **Lines Removed:** ~75 lines of duplication and conversion logic

**~~M6. Connection Status Tracking Duplication~~** ✅ **COMPLETED**
- **Analysis Result:** Architecture is actually correct - not duplication but proper layering:
  1. `ConnectionManager.status` - Per-connection status (infrastructure layer) ✓
  2. `ArtifactManager._server_statuses` - **Single source of truth** for all servers (domain layer) ✓
  3. `MCPPanel._connection_status` - Display state only (presentation layer) ✓
- **Solution Implemented:**
  - Added clarifying documentation to all three locations
  - `ArtifactManager._server_statuses` documented as "Single source of truth"
  - `ConnectionManager` documented as managing single connection (not all servers)
  - `ServerWidget` documented as display state updated via events from ArtifactManager
- **Result:** Architecture validated as correct, no code changes needed, documentation clarifies ownership
- **Files Modified:**
  - `artifact_manager.py` (added SSoT comment)
  - `connection/manager.py` (clarified scope)
  - `mcp_panel.py` (clarified display state)

---

#### ~~LOW Priority Issues~~ ✅ **L1-L2 COMPLETED**

**~~L1. Single TODO Comment~~** ✅ **COMPLETED**
- **Solution Implemented:**
  - Added `_validate_argument_type()` method to `CompositeArgumentParser`
  - Implements basic type validation for: `number`, `integer`, `boolean`, `string`
  - Validates format (not coercion) since user input comes as strings
  - Logs warnings for type mismatches while allowing execution to continue
  - Accepts common boolean representations: `true/false/yes/no/1/0`
- **Result:** TODO resolved with pragmatic type validation
- **Files Modified:** `core/parsers/composite.py` (added 39 lines)
- **Type Errors:** 0 new errors

**~~L2. Deprecated `get_oauth_client_provider` Function~~** ✅ **COMPLETED**
- **Solution Implemented:**
  - Removed entire deprecated function (23 lines removed)
  - Verified no usages in codebase (only in `mcp_client/auth.py` itself)
  - Function was already deprecated with warning, replaced by `oauth_context()`
- **Result:** Dead code eliminated
- **Files Modified:** `mcp_client/auth.py`
- **Lines Removed:** 23 lines

---

### 1.3 Architecture Violations

**AV1. Layer Boundary Violations**

- **Violation 1 – Resolved:** `ConnectionHandler` now pulls reconnect metadata exclusively from `ReconnectProgress` events. The file no longer touches `MCPAuthClient.reconnect_info`, and the remaining interactions stay within the `MCPClient` protocol (`client = self.artifact_manager.clients.get(server_name)` followed by `client.is_connected` checks).
- **Violation 2 – Still Outstanding:** `core/artifact_manager.py` continues to import and instantiate `MCPAuthClient` directly (`from nxs.mcp_client.client import ConnectionStatus, MCPAuthClient` + `_create_clients()`), leaving the core layer coupled to the concrete infrastructure client.
- **Violation 3 – Resolved:** `tui/widgets/argument_suggestions.py` has been deleted. The `ArgumentSuggestionGenerator` now lives in `core/suggestions/generator.py`, and the widget simply coordinates UI concerns.

---

**AV2. Inconsistent Abstraction Levels**

- **Status – Still Outstanding:** `ArtifactManager` still mixes concerns. Alongside delegating to `ArtifactRepository`, it maintains `_server_statuses`, tracks timestamps, and constructs `MCPAuthClient` instances in `_create_clients()`. The proposed split into a dedicated factory/service layer has not yet happened.

---

**AV3. Services in Wrong Layer**

- **Status – Resolved:** `tui/services/artifact_fetcher.py` has been removed. Timeout handling now resides in `core.artifacts.repository.ArtifactRepository.get_server_artifacts()`, so the presentation layer no longer owns this domain logic.

---

**AV4. Missing Adapter Pattern**

- **Status – Partially Addressed:** `PromptService.copy_caches_to_dicts()` has been removed, and downstream consumers receive the `Cache` protocol directly. `NexusAutoComplete` now wraps the cache with a minimal `CacheDict` shim to satisfy the third-party autocomplete API. Additional work could teach the completion strategies to consume the protocol directly and eliminate the inline adapter.

---

### 1.4 Success Metrics vs Goals

| Component | Phase 1-3 Goal | Actual Result | Status |
|-----------|----------------|---------------|--------|
| **NexusApp** | ~300 lines (70% reduction) | 529 lines (47% reduction) | ⚠️ Partial |
| **ArtifactManager** | ~200 lines (68% reduction) | 523 lines (17% reduction) | ❌ Miss |
| **MCPAuthClient** | ~250 lines (68% reduction) | 197 lines (75% reduction) | ✅ Exceeded |
| **AutoComplete** | ~400 lines (56% reduction) | 905 lines (0% reduction) | ❌ Not addressed |
| **MCPPanel** | ~400 lines (54% reduction) | 838 lines (0% reduction) | ❌ Not addressed |
| **CommandControlAgent** | N/A (no goal set) | 241 lines (49% reduction) | ✅ Good |

**Overall Assessment:**
- ✅ **Excellent:** Connection management, parsing, event bus, protocols
- ⚠️ **Partial:** NexusApp decomposition (stopped at services/handlers extraction)
- ❌ **Incomplete:** ArtifactManager, AutoComplete, MCPPanel

---

## 2. Phase 2 Refinement Strategy

### 2.1 Design Principles for Phase 2

**Principle 1: Holistic Over Incremental**
- Look at the entire system, not just individual files
- Identify and eliminate redundancies introduced during incremental refactoring
- Ensure consistent patterns across all layers

**Principle 2: Complete the Decomposition**
- Finish what Phase 1-3 started but didn't complete
- Meet or exceed original reduction targets
- No giant files left (all files < 400 lines)

**Principle 3: Enforce Clean Architecture**
- **Domain layer:** Pure business logic (no UI, no infrastructure)
- **Infrastructure layer:** MCP clients, connections, storage
- **Application layer:** Orchestration, use cases
- **Presentation layer:** TUI components only

**Principle 4: Remove Technical Debt**
- Eliminate legacy callback support (EventBus is proven)
- Remove dead code and empty directories
- Fix all `type: ignore` comments
- Complete TODOs

**Principle 5: Document the Architecture**
- Clear naming conventions (Service vs Handler vs Coordinator)
- Architecture Decision Records (ADRs) for key patterns
- Updated CLAUDE.md with final structure

---

### 2.2 Phase 2 Overview

**Timeline:** 4-5 weeks
**Total Effort:** 25-30 hours
**Risk Level:** Low (building on proven Phase 1-3 patterns)

**Phase Breakdown:**

| Phase | Focus | Duration | Effort |
|-------|-------|----------|--------|
| **Phase 2.1** | Critical Decomposition | Weeks 1-2 | 12-15 hours |
| **Phase 2.2** | Remove Redundancies | Week 3 | 6-8 hours |
| **Phase 2.3** | Fix Architecture Violations | Week 4 | 5-7 hours |
| **Phase 2.4** | Polish & Documentation | Week 5 | 3-4 hours |

---

## 3. Phase 2.1: Critical Decomposition (Weeks 1-2, 12-15 hours)

**Goal:** Complete the decomposition of the three largest remaining files to meet original reduction targets.

---

### Step 2.1.1: Decompose AutoComplete Widget (905 → ~300 lines) ✅ **Completed – 2025-11-07**

**Target:** `tui/widgets/autocomplete.py` (905 lines)
**Goal:** 67% reduction to ~300 lines
**Estimated Effort:** 5-6 hours

#### Outcome Summary

- Replaced the monolithic `NexusAutoComplete` with a slim orchestrator that wires `ResourceCompletionStrategy`, `CommandCompletionStrategy`, and `ArgumentCompletionStrategy`, reducing the widget to ~120 lines.
- Introduced the `tui/completion/` package with strategy protocol, orchestrator, schema mapping, prompt helpers, and a dedicated `CompletionApplier`.
- Added focused unit tests under `tests/tui/completion/` covering strategies, orchestrator, and applier.

#### Current Problems *(resolved)*

1. **Single giant class** handling multiple completion types:
   - @resource completions (lines 200-350)
   - /command completions (lines 350-500)
   - Argument suggestions (lines 500-700)
   - Fuzzy matching and filtering (lines 700-900)

2. **Complex `_get_candidates()` method** with nested conditionals

3. **Cache management** embedded in widget:
   ```python
   self._prompt_cache: dict[str, str | None] = {}
   self._prompt_schema_cache: dict[str, tuple] = {}
   ```

4. **Hard to test** individual completion strategies

#### Proposed Solution: Strategy Pattern

**Create new package:** `tui/completion/`

```
tui/completion/
├── __init__.py
├── strategy.py              # CompletionStrategy protocol
├── resource_completion.py   # ResourceCompletionStrategy
├── command_completion.py    # CommandCompletionStrategy
├── argument_completion.py   # ArgumentCompletionStrategy
└── orchestrator.py          # CompletionOrchestrator
```

**CompletionStrategy Protocol:**
```python
# tui/completion/strategy.py
from typing import Protocol

class CompletionCandidate:
    """Represents a single completion candidate."""
    def __init__(self, value: str, display: str, description: str = ""):
        self.value = value
        self.display = display
        self.description = description

class CompletionStrategy(Protocol):
    """Protocol for completion strategies."""

    def can_handle(self, text: str, cursor_pos: int) -> bool:
        """Check if this strategy can handle the current input."""
        ...

    async def get_candidates(
        self,
        text: str,
        cursor_pos: int,
        context: dict
    ) -> list[CompletionCandidate]:
        """Get completion candidates for the current input."""
        ...
```

**ResourceCompletionStrategy:**
```python
# tui/completion/resource_completion.py
from .strategy import CompletionStrategy, CompletionCandidate

class ResourceCompletionStrategy:
    """Handles @resource completions."""

    def __init__(self, artifact_manager):
        self.artifact_manager = artifact_manager

    def can_handle(self, text: str, cursor_pos: int) -> bool:
        # Check if cursor is after @ trigger
        return "@" in text[:cursor_pos]

    async def get_candidates(
        self,
        text: str,
        cursor_pos: int,
        context: dict
    ) -> list[CompletionCandidate]:
        # Extract query after @
        # Fetch resources from artifact_manager
        # Filter and rank matches
        # Return candidates
        ...
```

**CommandCompletionStrategy:**
```python
# tui/completion/command_completion.py
from .strategy import CompletionStrategy, CompletionCandidate

class CommandCompletionStrategy:
    """Handles /command completions."""

    def __init__(self, prompt_cache, prompt_schema_cache):
        self.prompt_cache = prompt_cache
        self.prompt_schema_cache = prompt_schema_cache

    def can_handle(self, text: str, cursor_pos: int) -> bool:
        # Check if cursor is after / trigger
        return "/" in text[:cursor_pos]

    async def get_candidates(
        self,
        text: str,
        cursor_pos: int,
        context: dict
    ) -> list[CompletionCandidate]:
        # Extract command after /
        # Fetch prompts from cache
        # Filter and rank matches
        # Return candidates
        ...
```

**ArgumentCompletionStrategy:**
```python
# tui/completion/argument_completion.py
from .strategy import CompletionStrategy, CompletionCandidate

class ArgumentCompletionStrategy:
    """Handles argument completions for commands."""

    def __init__(self, suggestion_generator):
        self.suggestion_generator = suggestion_generator

    def can_handle(self, text: str, cursor_pos: int) -> bool:
        # Check if we're inside a command with arguments
        return "/" in text and " " in text[:cursor_pos]

    async def get_candidates(
        self,
        text: str,
        cursor_pos: int,
        context: dict
    ) -> list[CompletionCandidate]:
        # Parse command and current argument
        # Use suggestion_generator to get argument suggestions
        # Return candidates
        ...
```

**CompletionOrchestrator:**
```python
# tui/completion/orchestrator.py
from .strategy import CompletionStrategy

class CompletionOrchestrator:
    """Orchestrates multiple completion strategies."""

    def __init__(self, strategies: list[CompletionStrategy]):
        self.strategies = strategies

    async def get_completions(
        self,
        text: str,
        cursor_pos: int,
        context: dict
    ) -> list[CompletionCandidate]:
        """Get completions from the first matching strategy."""
        for strategy in self.strategies:
            if strategy.can_handle(text, cursor_pos):
                return await strategy.get_candidates(text, cursor_pos, context)
        return []
```

**Refactored AutoComplete Widget:**
```python
# tui/widgets/autocomplete.py (~300 lines)
from textual.widgets import Input
from ..completion import (
    CompletionOrchestrator,
    ResourceCompletionStrategy,
    CommandCompletionStrategy,
    ArgumentCompletionStrategy,
)

class NexusAutoComplete(Input):
    """AutoComplete input field with strategy-based completions."""

    def __init__(self, artifact_manager, prompt_cache, prompt_schema_cache, ...):
        super().__init__()

        # Create strategies
        resource_strategy = ResourceCompletionStrategy(artifact_manager)
        command_strategy = CommandCompletionStrategy(prompt_cache, prompt_schema_cache)
        argument_strategy = ArgumentCompletionStrategy(suggestion_generator)

        # Create orchestrator
        self.orchestrator = CompletionOrchestrator([
            argument_strategy,  # Check most specific first
            command_strategy,
            resource_strategy,
        ])

    async def on_key(self, event):
        # Delegate to orchestrator
        candidates = await self.orchestrator.get_completions(
            self.value,
            self.cursor_position,
            context={}
        )
        self._update_dropdown(candidates)
```

#### Benefits

✅ **Single Responsibility:** Each strategy handles one completion type
✅ **Easy to Test:** Mock strategies independently
✅ **Easy to Extend:** Add new strategies without modifying existing code
✅ **Reduced Complexity:** Main widget becomes thin orchestrator
✅ **Reusable:** Strategies can be used outside widget context

#### Migration Steps

1. Create `tui/completion/` package structure
2. Implement `CompletionStrategy` protocol and `CompletionCandidate` class
3. Extract resource completion logic → `ResourceCompletionStrategy`
4. Extract command completion logic → `CommandCompletionStrategy`
5. Extract argument completion logic → `ArgumentCompletionStrategy`
6. Implement `CompletionOrchestrator`
7. Refactor `NexusAutoComplete` to use orchestrator
8. Add unit tests for each strategy
9. Remove old completion code from widget

#### Testing Strategy

```python
# tests/tui/completion/test_resource_completion.py
async def test_resource_completion_after_at_symbol():
    strategy = ResourceCompletionStrategy(mock_artifact_manager)
    assert strategy.can_handle("@res", 4)
    candidates = await strategy.get_candidates("@res", 4, {})
    assert len(candidates) > 0
    assert all(c.value.startswith("@") for c in candidates)

# tests/tui/completion/test_orchestrator.py
async def test_orchestrator_selects_correct_strategy():
    orchestrator = CompletionOrchestrator([
        mock_resource_strategy,
        mock_command_strategy,
    ])
    candidates = await orchestrator.get_completions("@test", 5, {})
    # Should have called resource_strategy, not command_strategy
```

---

### Step 2.1.2: Decompose MCPPanel Widget (838 → ~300 lines)

**Target:** `tui/widgets/mcp_panel.py` (838 lines)
**Goal:** 64% reduction to ~300 lines
**Estimated Effort:** 4-5 hours

#### Current Problems

1. **Module-level helpers** (lines 20-172, 152 lines):
   - `sanitize_widget_id()`
   - `get_status_icon()`
   - `get_status_text()`
   - `_format_server_display()` (106 lines!)

2. **Three classes in one file:**
   - `ArtifactItem` (35 lines)
   - `ServerWidget` (375 lines!)
   - `MCPPanel` (254 lines)

3. **Complex update logic** with cache comparison

4. **Mixed concerns:** Formatting, state management, rendering

#### Proposed Solution: Extract Components

**Create new modules:**

```
tui/
├── formatters/
│   ├── __init__.py
│   └── status.py           # Status formatting functions
├── widgets/
│   ├── mcp_panel.py        # Main MCPPanel (~300 lines)
│   ├── server_widget.py    # ServerWidget (~400 lines, further decomposable)
│   └── artifact_item.py    # ArtifactItem (~50 lines)
```

**Extract Status Formatters:**
```python
# tui/formatters/status.py (~150 lines)
from rich.text import Text
from nxs.mcp_client.connection import ConnectionStatus

def sanitize_widget_id(name: str) -> str:
    """Sanitize server name for use as widget ID."""
    ...

def get_status_icon(status: ConnectionStatus) -> str:
    """Get icon for connection status."""
    if status == ConnectionStatus.CONNECTED:
        return "🟢"
    elif status == ConnectionStatus.CONNECTING:
        return "🟡"
    ...

def get_status_text(status: ConnectionStatus) -> str:
    """Get text description for connection status."""
    ...

def format_server_display(
    name: str,
    status: ConnectionStatus,
    has_error: bool,
    error_message: str | None,
    reconnect_info: dict | None,
) -> Text:
    """Format server display text with status and reconnection info."""
    ...
```

**Extract ArtifactItem:**
```python
# tui/widgets/artifact_item.py (~50 lines)
from textual.widgets import Static

class ArtifactItem(Static):
    """Widget representing a single artifact (resource/prompt/tool)."""

    def __init__(self, artifact_type: str, name: str, description: str = ""):
        super().__init__()
        self.artifact_type = artifact_type
        self.name = name
        self.description = description

    def render(self):
        # Render artifact with icon and name
        ...
```

**Extract ServerWidget:**
```python
# tui/widgets/server_widget.py (~400 lines)
from textual.containers import Vertical
from textual.widgets import Label, Collapsible
from ..formatters.status import format_server_display
from .artifact_item import ArtifactItem

class ServerWidget(Vertical):
    """Widget displaying a single MCP server and its artifacts."""

    def __init__(self, server_name: str, ...):
        super().__init__()
        self.server_name = server_name
        self._status_label = Label()
        self._artifacts_container = Vertical()

    def update_status(self, status: ConnectionStatus, reconnect_info=None):
        """Update server status display."""
        display_text = format_server_display(
            self.server_name, status, reconnect_info
        )
        self._status_label.update(display_text)

    def update_artifacts(self, resources, prompts, tools):
        """Update artifact display."""
        self._artifacts_container.clear()
        for resource in resources:
            self._artifacts_container.mount(ArtifactItem("resource", resource))
        ...
```

**Simplified MCPPanel:**
```python
# tui/widgets/mcp_panel.py (~300 lines)
from textual.containers import Vertical, VerticalScroll
from .server_widget import ServerWidget

class MCPPanel(Vertical):
    """Panel displaying all MCP servers and their artifacts."""

    def __init__(self):
        super().__init__()
        self._server_widgets: dict[str, ServerWidget] = {}
        self._server_container = VerticalScroll()

    def compose(self):
        yield self._server_container

    def update_servers(self, servers_data: dict):
        """Update all server displays."""
        for server_name, data in servers_data.items():
            if server_name not in self._server_widgets:
                widget = ServerWidget(server_name)
                self._server_widgets[server_name] = widget
                self._server_container.mount(widget)

            widget = self._server_widgets[server_name]
            widget.update_status(data["status"], data.get("reconnect_info"))
            widget.update_artifacts(
                data.get("resources", []),
                data.get("prompts", []),
                data.get("tools", [])
            )
```

#### Benefits

✅ **Separation of Concerns:** Formatting, widget logic, main panel separated
✅ **Reusable Formatters:** Status formatting can be used elsewhere
✅ **Testable Components:** Each widget can be tested independently
✅ **Cleaner Code:** Smaller, focused files instead of one giant file
✅ **Easier Maintenance:** Changes to formatting don't affect widget logic

#### Migration Steps

1. Create `tui/formatters/` package
2. Extract formatters → `tui/formatters/status.py`
3. Create `tui/widgets/artifact_item.py` with `ArtifactItem` class
4. Create `tui/widgets/server_widget.py` with `ServerWidget` class
5. Refactor `MCPPanel` to compose `ServerWidget` instances
6. Update imports throughout codebase
7. Add unit tests for formatters
8. Add widget tests for components

#### Testing Strategy

```python
# tests/tui/formatters/test_status.py
def test_get_status_icon_connected():
    assert get_status_icon(ConnectionStatus.CONNECTED) == "🟢"

def test_format_server_display_with_reconnect():
    text = format_server_display("server1", ConnectionStatus.RECONNECTING, ...)
    assert "Reconnecting" in str(text)

# tests/tui/widgets/test_server_widget.py
async def test_server_widget_updates_status():
    widget = ServerWidget("test-server")
    widget.update_status(ConnectionStatus.CONNECTED)
    # Assert status label updated correctly
```

---

### Step 2.1.3: Further Decompose ArtifactManager (523 → ~250 lines)

**Target:** `core/artifact_manager.py` (523 lines)
**Goal:** 52% reduction to ~250 lines
**Estimated Effort:** 3-4 hours

#### Current Problems

1. **Client creation logic embedded** (lines 97-130, 33 lines):
   ```python
   def _create_clients(self) -> list[tuple[str, MCPAuthClient]]:
       # Creates MCPAuthClient instances
       # Wires callbacks and event bus
       # 33 lines of instantiation logic
   ```

2. **Server status tracking** duplicated:
   ```python
   self._server_statuses: dict[str, ConnectionStatus] = {}
   self._server_last_check: dict[str, float] = {}
   ```
   - Should be in `ConnectionManager`, not `ArtifactManager`

3. **15+ public methods** mixing high-level and low-level concerns

4. **Legacy callback support** adds complexity

#### Proposed Solution: Extract ClientFactory

**Create new module:** `mcp_client/factory.py`

```python
# mcp_client/factory.py (~150 lines)
from typing import Callable, Optional
from .client import MCPAuthClient
from .connection import ConnectionManager
from nxs.core.events import EventBus
from nxs.core.mcp_config import MCPServerConfig

class ClientFactory:
    """Factory for creating and configuring MCPAuthClient instances."""

    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus

    def create_client(
        self,
        server_name: str,
        config: MCPServerConfig,
        on_status_change: Optional[Callable] = None,
        on_reconnect_progress: Optional[Callable] = None,
    ) -> MCPAuthClient:
        """Create a configured MCPAuthClient for a server."""

        # Create connection manager
        conn_manager = ConnectionManager(
            server_name=server_name,
            config=config,
            event_bus=self.event_bus,
        )

        # Wire callbacks if provided
        if on_status_change:
            conn_manager.on_status_change = on_status_change
        if on_reconnect_progress:
            conn_manager.on_reconnect_progress = on_reconnect_progress

        # Create and return client
        client = MCPAuthClient(
            server_name=server_name,
            connection_manager=conn_manager,
        )
        return client

    def create_clients(
        self,
        configs: dict[str, MCPServerConfig],
        status_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
    ) -> dict[str, MCPAuthClient]:
        """Create clients for all server configurations."""
        clients = {}
        for name, config in configs.items():
            # Wire per-server callbacks using partial
            server_status_callback = None
            if status_callback:
                server_status_callback = lambda status, n=name: status_callback(n, status)

            server_progress_callback = None
            if progress_callback:
                server_progress_callback = lambda *args, n=name: progress_callback(n, *args)

            clients[name] = self.create_client(
                name,
                config,
                server_status_callback,
                server_progress_callback,
            )
        return clients
```

**Refactored ArtifactManager:**
```python
# core/artifact_manager.py (~250 lines)
from nxs.mcp_client.factory import ClientFactory
from .artifacts import ArtifactRepository, ArtifactCache, ArtifactChangeDetector
from .events import EventBus, ConnectionStatusChanged, ArtifactsFetched

class ArtifactManager:
    """High-level facade for MCP artifact management."""

    def __init__(
        self,
        config_path: str,
        event_bus: Optional[EventBus] = None,
        client_factory: Optional[ClientFactory] = None,
        artifact_cache: Optional[Cache] = None,
    ):
        self.config_path = config_path
        self.event_bus = event_bus or EventBus()

        # Use provided factory or create default
        self._client_factory = client_factory or ClientFactory(self.event_bus)

        # Artifact components
        self._artifact_repository = ArtifactRepository()
        self._artifact_cache = ArtifactCache(artifact_cache or MemoryCache())
        self._change_detector = ArtifactChangeDetector(self._artifact_cache)

        # Clients (created during initialize)
        self.clients: dict[str, MCPClient] = {}

    async def initialize(self):
        """Initialize MCP connections."""
        # Load config
        config = load_mcp_config(self.config_path)

        # Create clients using factory
        self.clients = self._client_factory.create_clients(
            config.mcp_servers,
            status_callback=self._handle_status_change,
            progress_callback=self._handle_reconnect_progress,
        )

        # Connect all clients
        await asyncio.gather(*[
            client.connect() for client in self.clients.values()
        ])

    # High-level artifact access (delegates to repository)
    async def get_resource_list(self) -> list[str]:
        return await self._artifact_repository.get_resource_list(self.clients)

    async def get_server_artifacts(self, server_name: str) -> dict:
        artifacts = await self._artifact_repository.get_server_artifacts(
            server_name, self.clients[server_name]
        )

        # Check for changes and publish event
        changed = self._change_detector.has_changed(server_name, artifacts)
        if changed:
            self._artifact_cache.set(server_name, artifacts)
            self.event_bus.publish(ArtifactsFetched(
                server_name=server_name,
                artifacts=artifacts,
                changed=True,
            ))

        return artifacts

    def _handle_status_change(self, server_name: str, status: ConnectionStatus):
        """Handle connection status changes."""
        # Publish event
        self.event_bus.publish(ConnectionStatusChanged(
            server_name=server_name,
            status=status,
        ))

    def _handle_reconnect_progress(self, server_name: str, attempts: int, ...):
        """Handle reconnection progress."""
        # Publish event
        self.event_bus.publish(ReconnectProgress(
            server_name=server_name,
            attempts=attempts,
            ...
        ))
```

#### Benefits

✅ **Single Responsibility:** Factory handles client creation, Manager handles artifacts
✅ **Testability:** Can inject mock factory for testing
✅ **Status in Right Place:** ConnectionManager owns status, not ArtifactManager
✅ **Cleaner Code:** Removed 273 lines of complexity
✅ **Dependency Injection:** Easy to swap implementations

#### Migration Steps

1. Create `mcp_client/factory.py` with `ClientFactory` class
2. Move `_create_clients()` logic to factory
3. Remove `_server_statuses` and `_server_last_check` from `ArtifactManager`
4. Update `ArtifactManager.__init__()` to accept `ClientFactory`
5. Update `ArtifactManager.initialize()` to use factory
6. Add unit tests for `ClientFactory`
7. Update integration tests for `ArtifactManager`

#### Testing Strategy

```python
# tests/mcp_client/test_factory.py
def test_client_factory_creates_client():
    factory = ClientFactory(event_bus=mock_event_bus)
    client = factory.create_client("test-server", mock_config)
    assert isinstance(client, MCPAuthClient)
    assert client.server_name == "test-server"

async def test_factory_creates_multiple_clients():
    factory = ClientFactory()
    clients = factory.create_clients({
        "server1": mock_config1,
        "server2": mock_config2,
    })
    assert len(clients) == 2
    assert "server1" in clients
    assert "server2" in clients

# tests/core/test_artifact_manager.py
async def test_artifact_manager_with_mock_factory():
    mock_factory = Mock(spec=ClientFactory)
    mock_factory.create_clients.return_value = {"server1": mock_client}

    manager = ArtifactManager(
        config_path="test.json",
        client_factory=mock_factory,
    )
    await manager.initialize()

    mock_factory.create_clients.assert_called_once()
```

---

## 4. Phase 2.2: Remove Redundancies (Week 3, 6-8 hours)

**Goal:** Eliminate redundant code and layers introduced during incremental Phase 1-3 refactoring.

---

### Step 2.2.1: Eliminate ArtifactFetcher Service

**Target:** `tui/services/artifact_fetcher.py` (167 lines)
**Goal:** Remove entire file, move timeout logic to repository
**Estimated Effort:** 2 hours

#### Current Problem

Three-layer delegation chain:

```
ArtifactFetcher (TUI layer)
    ↓ wraps with timeout
ArtifactManager (Core layer)
    ↓ delegates
ArtifactRepository (Core layer)
    ↓ calls
MCPClient operations
```

**ArtifactFetcher duplicates logic:**
- Timeout handling
- Empty result handling
- Error logging

#### Proposed Solution

**Remove `ArtifactFetcher` entirely and move timeout to repository:**

```python
# core/artifacts/repository.py (add timeout parameter)
class ArtifactRepository:
    """Repository for fetching artifacts from MCP clients."""

    async def get_server_artifacts(
        self,
        server_name: str,
        client: MCPClient,
        timeout: float = 5.0,  # Add timeout parameter
    ) -> ArtifactCollection:
        """Fetch all artifacts from a server with timeout."""
        try:
            async with asyncio.timeout(timeout):  # Add timeout wrapper
                tools = await self._fetch_with_retry(
                    client.list_tools,
                    operation_name="list_tools",
                )
                prompts = await self._fetch_with_retry(
                    client.list_prompts,
                    operation_name="list_prompts",
                )
                resources = await self._fetch_with_retry(
                    client.list_resources,
                    operation_name="list_resources",
                )

                return {
                    "tools": tools or [],
                    "prompts": prompts or [],
                    "resources": resources or [],
                }
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching artifacts from {server_name}")
            return {"tools": [], "prompts": [], "resources": []}
```

**Update callers to use ArtifactManager directly:**

```python
# tui/services/mcp_refresher.py
class MCPRefresher:
    """Service for refreshing MCP artifacts."""

    def __init__(self, artifact_manager: ArtifactManager, ...):
        self.artifact_manager = artifact_manager
        # Remove self.artifact_fetcher

    async def refresh_server(self, server_name: str):
        """Refresh artifacts for a server."""
        # Direct call instead of going through fetcher
        artifacts = await self.artifact_manager.get_server_artifacts(
            server_name,
            timeout=5.0,  # Pass timeout directly
        )
        # ... rest of logic
```

#### Benefits

✅ **Simpler:** Two layers instead of three (Manager → Repository)
✅ **Single Source of Truth:** Timeout logic in one place (repository)
✅ **Less Code:** Remove 167 lines
✅ **Clearer Flow:** Direct delegation, no middle layer

#### Migration Steps

1. Add `timeout` parameter to `ArtifactRepository.get_server_artifacts()`
2. Add timeout wrapper in repository method
3. Update `ArtifactManager.get_server_artifacts()` to accept and pass timeout
4. Update `MCPRefresher` to call `ArtifactManager` directly
5. Remove `tui/services/artifact_fetcher.py`
6. Update imports and remove references
7. Update tests to reflect new flow

---

### Step 2.2.2: Remove Legacy Callback Support

**Target:** `core/artifact_manager.py` (deprecated callback parameters)
**Goal:** Remove ~50 lines of dual handling code
**Estimated Effort:** 2 hours

#### Current Problem

Dual handling of EventBus and legacy callbacks:

```python
# Lines 33-35, 61-62: Deprecated parameters
def __init__(
    self,
    ...,
    on_status_change: Optional[Callable] = None,  # DEPRECATED
    on_reconnect_progress: Optional[Callable] = None,  # DEPRECATED
):
    ...

# Lines 152-168: Dual handling
def _handle_status_change(self, status: ConnectionStatus, server_name: str):
    # Publish event
    if self.event_bus:
        self.event_bus.publish(ConnectionStatusChanged(...))

    # Legacy callback support (deprecated)
    if self.on_status_change:
        try:
            self.on_status_change(server_name, status)
        except Exception as e:
            logger.warning("Legacy status change callback error...")
```

#### Proposed Solution

**Remove all legacy callback support:**

```python
# core/artifact_manager.py (simplified __init__)
def __init__(
    self,
    config_path: str,
    event_bus: EventBus,  # Required, not optional
    client_factory: Optional[ClientFactory] = None,
    artifact_cache: Optional[Cache] = None,
):
    self.event_bus = event_bus  # No fallback
    # Remove: self.on_status_change
    # Remove: self.on_reconnect_progress

# Simplified handlers (no dual handling)
def _handle_status_change(self, server_name: str, status: ConnectionStatus):
    """Handle connection status changes."""
    self.event_bus.publish(ConnectionStatusChanged(
        server_name=server_name,
        status=status,
    ))
    # Remove: Legacy callback code

def _handle_reconnect_progress(self, server_name: str, attempts: int, ...):
    """Handle reconnection progress."""
    self.event_bus.publish(ReconnectProgress(
        server_name=server_name,
        attempts=attempts,
        ...
    ))
    # Remove: Legacy callback code
```

**Update all callers to use EventBus:**

```python
# main.py (ensure EventBus is created)
event_bus = EventBus()

artifact_manager = ArtifactManager(
    config_path=config_path,
    event_bus=event_bus,  # Required
    # Remove: on_status_change=...
    # Remove: on_reconnect_progress=...
)
```

#### Benefits

✅ **Simpler:** Single code path (EventBus only)
✅ **Consistent:** All components use events
✅ **Less Code:** Remove ~50 lines of dual handling
✅ **Clearer:** No deprecated parameters

#### Migration Steps

1. Remove `on_status_change` and `on_reconnect_progress` parameters from `ArtifactManager.__init__()`
2. Make `event_bus` required (not optional)
3. Remove legacy callback code from `_handle_status_change()` and `_handle_reconnect_progress()`
4. Remove deprecated warnings and comments
5. Update `main.py` and other instantiation sites
6. Update tests to ensure EventBus is always provided
7. Remove any remaining legacy callback references

---

### Step 2.2.3: Clean Up Dead Code

**Targets:** Multiple files
**Goal:** Remove dead code, empty directories, fix type issues
**Estimated Effort:** 1-2 hours

#### Items to Remove

**1. Empty `core/connection/` Directory**
```bash
rm -rf src/nxs/core/connection/
```

**2. Deprecated `get_oauth_client_provider()` Function**
```python
# mcp_client/auth.py - Remove lines ~XX-XX
def get_oauth_client_provider() -> ...:
    """DEPRECATED: Use oauth_context() instead..."""
    logger.warning("⚠️  deprecated...")
    # Remove entire function
```

**3. Fix `type: ignore` Comments**

**Problem:** `tui/handlers/connection_handler.py` (3 instances)
```python
reconnect_info = client.reconnect_info  # type: ignore[attr-defined]
```

**Solution Option 1: Add to Protocol (if needed everywhere)**
```python
# core/protocols.py
class MCPClient(Protocol):
    ...
    @property
    def reconnect_info(self) -> dict | None:
        """Reconnection information (attempts, delay, etc.)."""
        ...
```

**Solution Option 2: Access via Event (preferred - more decoupled)**
```python
# mcp_client/connection/manager.py
# Publish reconnect info in event instead of storing on client

# tui/handlers/connection_handler.py
def _on_reconnect_progress(self, event: ReconnectProgress):
    # Get reconnect info from event, not from client
    reconnect_info = {
        "attempts": event.attempts,
        "max_attempts": event.max_attempts,
        "next_retry_delay": event.next_retry_delay,
    }
```

**Solution Option 3: Create Separate Protocol**
```python
# core/protocols.py
class ReconnectInfoProvider(Protocol):
    """Protocol for components that provide reconnect information."""
    @property
    def reconnect_info(self) -> dict | None: ...

# tui/handlers/connection_handler.py
if isinstance(client, ReconnectInfoProvider):
    reconnect_info = client.reconnect_info
```

**Recommended:** Option 2 (access via event) - most decoupled

**4. Address TODO Comment**
```python
# core/parsers/composite.py:118
# TODO: Add type validation if needed

# Either:
# - Implement type validation
# - Or remove TODO if validation isn't needed
```

#### Migration Steps

1. Remove empty `core/connection/` directory
2. Remove deprecated `get_oauth_client_provider()` function
3. Choose approach for reconnect_info access (recommend: via event)
4. Implement chosen approach and remove `type: ignore` comments
5. Address TODO in composite.py
6. Run type checker to ensure no new issues: `pixi run --environment dev type-check`
7. Run tests to ensure nothing broke

---

### Step 2.2.4: Consolidate Status Tracking

**Target:** Multiple files tracking connection status
**Goal:** Single source of truth in ConnectionManager
**Estimated Effort:** 1-2 hours

#### Current Problem

Status tracked in three places:

1. **ConnectionManager** (mcp_client/connection/manager.py):
   ```python
   self._lifecycle = ConnectionLifecycle()  # Has status
   ```

2. **ArtifactManager** (core/artifact_manager.py):
   ```python
   self._server_statuses: dict[str, ConnectionStatus] = {}
   ```

3. **MCPPanel** (tui/widgets/mcp_panel.py):
   ```python
   # Caches status in widget state for display
   ```

#### Proposed Solution

**ConnectionManager as single source of truth:**

```python
# mcp_client/connection/manager.py
class ConnectionManager:
    """Manages connection lifecycle and status."""

    @property
    def status(self) -> ConnectionStatus:
        """Current connection status."""
        return self._lifecycle.status

    def get_status_info(self) -> dict:
        """Get detailed status information."""
        return {
            "status": self.status,
            "connected_at": self._lifecycle.connected_at,
            "error": self._lifecycle.last_error,
        }
```

**Remove status tracking from ArtifactManager:**

```python
# core/artifact_manager.py
class ArtifactManager:
    # Remove: self._server_statuses
    # Remove: self._server_last_check

    def get_server_status(self, server_name: str) -> ConnectionStatus:
        """Get current status for a server."""
        client = self.clients.get(server_name)
        if not client:
            return ConnectionStatus.DISCONNECTED
        # Delegate to connection manager
        return client.connection_manager.status
```

**UI subscribes to events instead of caching:**

```python
# tui/handlers/connection_handler.py
class ConnectionHandler:
    """Handles connection status events."""

    def __init__(self, mcp_panel: MCPPanel):
        self.mcp_panel = mcp_panel

    def handle_status_changed(self, event: ConnectionStatusChanged):
        """Update UI when status changes."""
        # UI updates from event, doesn't need to cache
        self.mcp_panel.update_server_status(
            event.server_name,
            event.status,
        )
```

#### Benefits

✅ **Single Source of Truth:** ConnectionManager owns status
✅ **Event-Driven:** UI reacts to changes, doesn't poll
✅ **Simpler:** No redundant status tracking
✅ **Consistent:** All status queries go to ConnectionManager

#### Migration Steps

1. Ensure `ConnectionManager.status` property exists
2. Add `get_status_info()` method to ConnectionManager
3. Remove `_server_statuses` from ArtifactManager
4. Update `get_server_status()` to delegate to ConnectionManager
5. Update UI handlers to use events for status updates
6. Remove any status caching in widgets (except for display)
7. Update tests to reflect single source of truth

---

## 5. Phase 2.3: Fix Architecture Violations (Week 4, 5-7 hours)

**Goal:** Enforce clean architecture boundaries and fix layer violations.

---

### Step 2.3.1: Move Business Logic Out of TUI

**Targets:**
- `tui/widgets/argument_suggestions.py` (283 lines)
- `tui/widgets/command_parser.py` (186 lines)

**Goal:** Move business logic to core layer
**Estimated Effort:** 2-3 hours

#### Current Problem

**Business logic in presentation layer:**

```python
# tui/widgets/argument_suggestions.py
class ArgumentSuggestionGenerator:
    """Generates argument suggestions for commands."""
    # 283 lines of business logic
    # Should be in core, not widgets
```

```python
# tui/widgets/command_parser.py
def parse_command_arguments(command_input: str, schema_dict: dict) -> dict:
    """Parse command arguments for autocomplete."""
    # Similar to core/parsers but in TUI layer
```

#### Proposed Solution

**Move ArgumentSuggestionGenerator to core:**

```
core/
├── suggestions/
│   ├── __init__.py
│   └── generator.py    # ArgumentSuggestionGenerator
```

```python
# core/suggestions/generator.py
class ArgumentSuggestionGenerator:
    """Generates argument suggestions based on command schemas."""

    def __init__(self, prompt_schema_cache: Cache):
        self.prompt_schema_cache = prompt_schema_cache

    def get_suggestions(self, command: str, current_arg: str) -> list[str]:
        """Get argument suggestions for a command."""
        # Business logic for generating suggestions
        ...
```

**Unify command parsing:**

Instead of having separate parsing in `tui/widgets/command_parser.py`, reuse `core/parsers/`:

```python
# tui/completion/command_completion.py
from nxs.core.parsers import CompositeArgumentParser  # Reuse core parser

class CommandCompletionStrategy:
    """Handles /command completions."""

    def __init__(self, parser: CompositeArgumentParser):
        self.parser = parser  # Use core parser

    async def get_candidates(self, text: str, ...) -> list[CompletionCandidate]:
        # Use core parser instead of duplicating logic
        try:
            parsed = self.parser.parse(text, ...)
        except ParseError:
            # Handle incomplete input for autocomplete context
            ...
```

**Remove TUI-specific command parser:**

Delete `tui/widgets/command_parser.py` entirely and use core parser.

#### Benefits

✅ **Clean Layers:** Business logic in core, UI logic in TUI
✅ **Reusable:** Suggestion generator can be used outside TUI
✅ **Consistent:** Single parsing implementation
✅ **Testable:** Test business logic without UI dependencies

#### Migration Steps

1. Create `core/suggestions/` package
2. Move `ArgumentSuggestionGenerator` from `tui/widgets/argument_suggestions.py` to `core/suggestions/generator.py`
3. Update `ArgumentSuggestionGenerator` to use `Cache` protocol instead of dict
4. Update `ArgumentCompletionStrategy` to use core suggestion generator
5. Refactor command completion to reuse `core/parsers/` instead of `command_parser.py`
6. Delete `tui/widgets/command_parser.py`
7. Delete `tui/widgets/argument_suggestions.py`
8. Update all imports
9. Add tests for suggestion generator in core tests

---

### Step 2.3.2: Fix Protocol Violations (Remove type: ignore)

**Target:** `tui/handlers/connection_handler.py`
**Goal:** Remove all `type: ignore` comments by fixing architecture
**Estimated Effort:** 2 hours

#### Current Problem

```python
# tui/handlers/connection_handler.py:92, 110, 163
client = self.artifact_manager.clients.get(server_name)
reconnect_info = client.reconnect_info  # type: ignore[attr-defined]
```

**Issue:** `reconnect_info` is not in `MCPClient` protocol, but handler needs it.

#### Proposed Solution: Publish Reconnect Info in Events

**Enhance ReconnectProgress event:**

```python
# core/events/types.py
@dataclass
class ReconnectProgress(Event):
    """Reconnection progress event."""
    server_name: str
    attempts: int
    max_attempts: int
    next_retry_delay: float
    status: ConnectionStatus  # Add status

    def to_display_dict(self) -> dict:
        """Convert to display-friendly dictionary."""
        return {
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "next_retry_delay": self.next_retry_delay,
            "status": self.status,
        }
```

**Handler uses event data instead of client property:**

```python
# tui/handlers/connection_handler.py
class ConnectionHandler:
    """Handles connection events."""

    def __init__(self, mcp_panel: MCPPanel):
        self.mcp_panel = mcp_panel
        # Cache reconnect info from events
        self._reconnect_info: dict[str, dict] = {}

    def handle_reconnect_progress(self, event: ReconnectProgress):
        """Handle reconnection progress event."""
        # Store info from event
        self._reconnect_info[event.server_name] = event.to_display_dict()

        # Update panel
        self.mcp_panel.update_reconnect_info(
            event.server_name,
            self._reconnect_info[event.server_name]
        )

    def handle_status_changed(self, event: ConnectionStatusChanged):
        """Handle status change event."""
        # Get cached reconnect info (from events)
        reconnect_info = self._reconnect_info.get(event.server_name)

        self.mcp_panel.update_server_status(
            event.server_name,
            event.status,
            reconnect_info,  # From event cache, not client property
        )
```

**Remove `reconnect_info` access from client:**

```python
# tui/handlers/connection_handler.py
# Remove all lines like:
# client = self.artifact_manager.clients.get(server_name)
# reconnect_info = client.reconnect_info  # type: ignore[attr-defined]

# Replace with:
# reconnect_info = self._reconnect_info.get(server_name)
```

#### Benefits

✅ **Type Safe:** No `type: ignore` comments
✅ **Decoupled:** Handler doesn't access client implementation details
✅ **Event-Driven:** Consistent with architecture
✅ **Protocol Compliant:** Only uses protocol interfaces

#### Migration Steps

1. Enhance `ReconnectProgress` event with `to_display_dict()` method
2. Add `_reconnect_info` cache to `ConnectionHandler`
3. Update `handle_reconnect_progress()` to cache info from event
4. Update `handle_status_changed()` to use cached info
5. Remove all `client.reconnect_info` accesses
6. Remove all `type: ignore` comments
7. Run type checker: `pixi run --environment dev type-check`
8. Ensure no type errors

---

### Step 2.3.3: Unify Cache Usage in AutoComplete

**Target:** `tui/widgets/autocomplete.py` and `tui/services/prompt_service.py`
**Goal:** Use Cache protocol consistently, remove dict conversion
**Estimated Effort:** 1-2 hours

#### Current Problem

**Inconsistent cache usage:**

```python
# tui/services/prompt_service.py
class PromptService:
    def __init__(
        self,
        prompt_info_cache: Optional[Cache[str, str | None]] = None,
        prompt_schema_cache: Optional[Cache[str, tuple]] = None,
    ):
        self._prompt_info_cache = prompt_info_cache or MemoryCache()
        self._prompt_schema_cache = prompt_schema_cache or MemoryCache()

    def copy_caches_to_dicts(self, commands: list[str]) -> tuple[dict, dict]:
        """Copy cache entries to dicts for components that use dict-based caches."""
        # Converts Cache → dict for AutoComplete
        ...
```

```python
# tui/widgets/autocomplete.py
class NexusAutoComplete:
    def __init__(self, ...):
        self._prompt_cache: dict[str, str | None] = {}  # Uses dict
        self._prompt_schema_cache: dict[str, tuple] = {}  # Uses dict
```

#### Proposed Solution

**AutoComplete uses Cache protocol directly:**

```python
# tui/widgets/autocomplete.py (or tui/completion/command_completion.py)
class CommandCompletionStrategy:
    """Handles /command completions."""

    def __init__(
        self,
        prompt_info_cache: Cache[str, str | None],
        prompt_schema_cache: Cache[str, tuple],
    ):
        self.prompt_info_cache = prompt_info_cache  # Use Cache protocol
        self.prompt_schema_cache = prompt_schema_cache  # Use Cache protocol

    async def get_candidates(self, text: str, ...) -> list[CompletionCandidate]:
        # Use cache.get() instead of dict access
        commands = await self._get_available_commands()

        candidates = []
        for cmd in commands:
            info = self.prompt_info_cache.get(cmd)  # Cache protocol
            schema = self.prompt_schema_cache.get(cmd)  # Cache protocol

            if self._matches_query(cmd, query):
                candidates.append(CompletionCandidate(
                    value=f"/{cmd}",
                    display=cmd,
                    description=info or "",
                ))

        return candidates
```

**Remove conversion method:**

```python
# tui/services/prompt_service.py
class PromptService:
    # Remove: copy_caches_to_dicts() method

    # Instead, expose caches directly
    @property
    def prompt_info_cache(self) -> Cache[str, str | None]:
        return self._prompt_info_cache

    @property
    def prompt_schema_cache(self) -> Cache[str, tuple]:
        return self._prompt_schema_cache
```

**Wire caches in NexusApp:**

```python
# tui/app.py
class NexusApp:
    def __init__(self):
        # Create prompt service
        self.prompt_service = PromptService()

        # Create completion strategies with shared caches
        command_strategy = CommandCompletionStrategy(
            prompt_info_cache=self.prompt_service.prompt_info_cache,
            prompt_schema_cache=self.prompt_service.prompt_schema_cache,
        )

        # No conversion needed - both use Cache protocol
```

#### Benefits

✅ **Consistent Abstraction:** All components use Cache protocol
✅ **Simpler:** No conversion between Cache and dict
✅ **Type Safe:** Protocol ensures correct interface
✅ **Flexible:** Easy to swap cache implementations

#### Migration Steps

1. Update `CommandCompletionStrategy` (or AutoComplete) to accept `Cache` parameters
2. Update cache access from dict syntax to `.get()` and `.set()` methods
3. Remove `copy_caches_to_dicts()` from `PromptService`
4. Add cache properties to `PromptService`
5. Update `NexusApp` to wire caches directly
6. Update tests to use Cache protocol
7. Remove any dict-specific code

---

## 6. Phase 2.4: Polish & Documentation (Week 5, 3-4 hours)

**Goal:** Apply consistent naming, update documentation, create ADRs.

---

### Step 2.4.1: Consistent Naming Conventions

**Goal:** Establish and apply clear naming patterns
**Estimated Effort:** 1 hour

#### Establish Patterns

**Services: Manage lifecycle, state, provide capabilities**
- **Pattern:** `<Noun>Service` or `<Noun>Coordinator`
- **Characteristics:**
  - Stateful (owns data, caches, connections)
  - Manages lifecycle (initialization, cleanup)
  - Provides capabilities to other components
- **Examples:**
  - ✅ `PromptService` - Manages prompt caching
  - ✅ `AutocompleteService` - Manages autocomplete lifecycle
  - ✅ `MCPCoordinator` - Coordinates MCP initialization
  - ✅ `RefreshService` - Manages refresh orchestration (rename from MCPRefresher)

**Handlers: React to events, stateless or minimal state**
- **Pattern:** `<Event>Handler` or `<Noun>Handler`
- **Characteristics:**
  - React to events
  - Minimal or no state (except event-sourced cache)
  - Orchestrate updates to other components
- **Examples:**
  - ✅ `ConnectionHandler` - Handles connection events
  - ✅ `QueryHandler` - Handles query processing
  - ✅ `RefreshHandler` - Handles artifact refresh events

**Managers: High-level facades coordinating multiple components**
- **Pattern:** `<Noun>Manager`
- **Characteristics:**
  - Facade pattern
  - Coordinates multiple lower-level components
  - Provides unified interface
- **Examples:**
  - ✅ `ArtifactManager` - Coordinates clients, repository, cache
  - ✅ `ConnectionManager` - Coordinates lifecycle, health, reconnect

**Repositories: Data access layer**
- **Pattern:** `<Noun>Repository`
- **Characteristics:**
  - Encapsulates data access
  - No business logic
  - Returns domain objects
- **Examples:**
  - ✅ `ArtifactRepository` - Fetches artifacts from clients

**Factories: Create and configure objects**
- **Pattern:** `<Noun>Factory`
- **Characteristics:**
  - Creates complex objects
  - Wires dependencies
  - Encapsulates construction logic
- **Examples:**
  - ✅ `ClientFactory` - Creates and configures MCPAuthClient instances

#### Renames Required

| Current Name | New Name | Reason |
|--------------|----------|--------|
| `MCPRefresher` | `RefreshService` or `RefreshCoordinator` | Inconsistent suffix, doesn't follow pattern |
| ~~`ArtifactFetcher`~~ | (removed) | Redundant, removed in Step 2.2.1 |

#### Migration Steps

1. Rename `MCPRefresher` → `RefreshService` (or `RefreshCoordinator`)
2. Update all imports
3. Update file name: `mcp_refresher.py` → `refresh_service.py`
4. Update documentation to reflect naming patterns
5. Run tests to ensure nothing broke

---

### Step 2.4.2: Update Documentation

**Goal:** Update CLAUDE.md and create ADRs
**Estimated Effort:** 2-3 hours

#### Update CLAUDE.md

**Sections to update:**

1. **Architecture Overview** - Reflect final package structure after Phase 2
2. **Package Structure** - Document new packages:
   - `tui/completion/` - Completion strategies
   - `tui/formatters/` - Status formatters
   - `core/suggestions/` - Argument suggestion generator
   - `mcp_client/factory.py` - Client factory
3. **Code Organization** - Update file purposes table
4. **Naming Conventions** - Document Service vs Handler vs Manager patterns
5. **Architecture Principles** - Add section on layer boundaries

**Example update:**

```markdown
## Architecture Layers

Nexus follows a clean architecture with clear layer boundaries:

### Domain Layer (`core/`)
Pure business logic with no UI or infrastructure dependencies:
- **Protocols** (`protocols.py`) - Abstract interfaces
- **Events** (`events/`) - Domain events
- **Parsers** (`parsers/`) - Argument parsing strategies
- **Suggestions** (`suggestions/`) - Argument suggestion generation
- **Artifacts** (`artifacts/`) - Artifact repository, cache, change detection

### Infrastructure Layer (`mcp_client/`)
External concerns (MCP, network, storage):
- **Client** (`client.py`) - MCPAuthClient wrapper
- **Factory** (`factory.py`) - Client creation and configuration
- **Connection** (`connection/`) - Connection management components
- **Operations** (`operations/`) - MCP protocol operations

### Application Layer (`core/artifact_manager.py`, `core/tools.py`)
Use cases and orchestration:
- **ArtifactManager** - Facade coordinating clients, artifacts, caching
- **ToolManager** - Tool discovery and execution

### Presentation Layer (`tui/`)
Terminal user interface:
- **App** (`app.py`) - Main orchestrator
- **Services** (`services/`) - UI-specific lifecycle management
- **Handlers** (`handlers/`) - Event handlers for UI updates
- **Widgets** (`widgets/`) - Textual UI components
- **Completion** (`completion/`) - Autocomplete strategies
- **Formatters** (`formatters/`) - Display formatting utilities

### Component Naming Patterns

- **Services** (`<Noun>Service`, `<Noun>Coordinator`) - Manage lifecycle and state
- **Handlers** (`<Event>Handler`) - React to events, minimal state
- **Managers** (`<Noun>Manager`) - High-level facades
- **Repositories** (`<Noun>Repository`) - Data access layer
- **Factories** (`<Noun>Factory`) - Object creation
```

#### Create Architecture Decision Records (ADRs)

**Create `docs/adr/` directory:**

```
docs/
└── adr/
    ├── 001-event-driven-architecture.md
    ├── 002-protocol-based-abstractions.md
    ├── 003-service-handler-pattern.md
    ├── 004-strategy-pattern-for-completion.md
    └── 005-cache-abstraction.md
```

**ADR Template:**

```markdown
# ADR-XXX: [Title]

**Status:** Accepted
**Date:** 2025-01-XX
**Decision Makers:** [Names]

## Context

[What is the issue we're facing? What forces are at play?]

## Decision

[What is the change we're proposing and why?]

## Consequences

### Positive
- [Benefit 1]
- [Benefit 2]

### Negative
- [Trade-off 1]
- [Trade-off 2]

### Neutral
- [Impact 1]

## Implementation

[How will this be implemented? Link to relevant code.]

## Alternatives Considered

### Alternative 1: [Name]
[Description and why rejected]

### Alternative 2: [Name]
[Description and why rejected]
```

**Example ADR:**

```markdown
# ADR-001: Event-Driven Architecture with EventBus

**Status:** Accepted
**Date:** 2025-01-07
**Decision Makers:** Phase 2 Refactoring Team

## Context

Previously, core components (like `ArtifactManager`) depended directly on UI callbacks, creating tight coupling between layers. This made it difficult to:
- Test core logic without UI dependencies
- Swap UI implementations
- Add new event subscribers without modifying publishers

## Decision

Implement event-driven architecture using an `EventBus`:
- Core layer publishes domain events (`ConnectionStatusChanged`, `ReconnectProgress`, `ArtifactsFetched`)
- UI layer subscribes to events via handlers
- EventBus decouples publishers from subscribers

## Consequences

### Positive
- **Decoupling:** Core has no knowledge of UI
- **Extensibility:** Easy to add new event subscribers
- **Testability:** Can test core and UI independently
- **Clarity:** Event types document system behavior

### Negative
- **Indirection:** More layers between publisher and subscriber
- **Debugging:** Event flow may be harder to trace than direct calls

### Neutral
- **Learning Curve:** Team needs to understand event-driven patterns

## Implementation

- `core/events/bus.py` - EventBus implementation
- `core/events/types.py` - Event type definitions
- `tui/handlers/` - Event handlers subscribing to events

See `core/artifact_manager.py` for event publishing, `tui/handlers/connection_handler.py` for subscription.

## Alternatives Considered

### Alternative 1: Observer Pattern
Direct observer registration on publishers. Rejected because:
- Still couples publishers to observer interface
- Less flexible than EventBus (single event bus vs many observables)

### Alternative 2: Message Queue (e.g., asyncio.Queue)
Asynchronous message queue for events. Rejected because:
- Overkill for in-process communication
- More complex than needed
- EventBus provides synchronous delivery which is sufficient
```

#### Migration Steps

1. Create `docs/adr/` directory
2. Write ADR-001: Event-Driven Architecture
3. Write ADR-002: Protocol-Based Abstractions
4. Write ADR-003: Service vs Handler Pattern
5. Write ADR-004: Strategy Pattern for Completion
6. Write ADR-005: Cache Abstraction
7. Update CLAUDE.md with:
   - Final architecture overview
   - Package structure
   - Naming conventions
   - Layer boundaries
   - Link to ADRs
8. Update REFACTORING_PLAN.md to mark Phase 2 as complete

---

## 7. Success Metrics

### Quantitative Metrics

| Metric | Phase 1-3 Result | Phase 2 Goal | Status After Phase 2 |
|--------|------------------|--------------|---------------------|
| **AutoComplete** | 905 lines (0%) | ~300 lines (67% reduction) | ⏳ TBD |
| **MCPPanel** | 838 lines (0%) | ~300 lines (64% reduction) | ⏳ TBD |
| **ArtifactManager** | 523 lines (17%) | ~250 lines (52% reduction) | ⏳ TBD |
| **Remove Dead Code** | N/A | 167+ lines removed | ⏳ TBD |
| **type: ignore Comments** | 3 instances | 0 instances | ⏳ TBD |
| **Empty Directories** | 1 (`core/connection/`) | 0 | ⏳ TBD |
| **Legacy Callback Support** | Dual handling | Removed (~50 lines) | ⏳ TBD |

**Total Line Reduction Target:** ~1,500+ lines

### Qualitative Metrics

- [ ] **Clear Layer Boundaries**
  - No TUI accessing implementation details
  - Business logic in core, not widgets
  - Clean import dependencies (core ← application ← infrastructure/presentation)

- [ ] **Single Source of Truth**
  - Status tracked only in ConnectionManager
  - Timeout logic only in repository
  - Cache abstraction used consistently

- [ ] **Consistent Abstraction Usage**
  - All components use Cache protocol (no dicts)
  - All components use MCPClient protocol (no concrete classes in type hints)
  - All communication via events (no callbacks)

- [ ] **No Architecture Violations**
  - Zero `type: ignore` comments
  - No business logic in TUI layer
  - No circular dependencies

- [ ] **Clear Naming Patterns**
  - Service vs Handler distinction clear
  - All components follow naming conventions
  - Consistent terminology across codebase

- [ ] **Complete Documentation**
  - CLAUDE.md reflects final structure
  - ADRs document key patterns and decisions
  - Architecture principles clearly stated

---

## 8. Implementation Timeline

### Week-by-Week Breakdown

**Week 1: Critical Decomposition (Part 1)**
- Mon-Tue: Step 2.1.1 - Decompose AutoComplete (5-6 hours)
- Wed-Thu: Step 2.1.2 - Decompose MCPPanel (4-5 hours)
- **Deliverable:** Two largest widgets decomposed

**Week 2: Critical Decomposition (Part 2)**
- Mon-Tue: Step 2.1.3 - Further Decompose ArtifactManager (3-4 hours)
- Wed: Testing and validation
- **Deliverable:** All critical decomposition complete

**Week 3: Remove Redundancies**
- Mon: Step 2.2.1 - Eliminate ArtifactFetcher (2 hours)
- Tue: Step 2.2.2 - Remove Legacy Callbacks (2 hours)
- Wed: Step 2.2.3 - Clean Up Dead Code (1-2 hours)
- Thu: Step 2.2.4 - Consolidate Status Tracking (1-2 hours)
- **Deliverable:** Redundancies eliminated, cleaner codebase

**Week 4: Fix Architecture Violations**
- Mon-Tue: Step 2.3.1 - Move Business Logic Out of TUI (2-3 hours)
- Wed: Step 2.3.2 - Fix Protocol Violations (2 hours)
- Thu: Step 2.3.3 - Unify Cache Usage (1-2 hours)
- **Deliverable:** Clean architecture boundaries enforced

**Week 5: Polish & Documentation**
- Mon: Step 2.4.1 - Consistent Naming (1 hour)
- Tue-Thu: Step 2.4.2 - Update Documentation and ADRs (2-3 hours)
- Fri: Final review and testing
- **Deliverable:** Polished, well-documented codebase

---

## 9. Risk Mitigation

### Risks & Mitigation Strategies

**Risk 1: Breaking Existing Functionality**
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:**
  - Incremental changes with tests after each step
  - Run full test suite after each phase
  - Use type checker to catch issues early: `pixi run type-check`
  - Manual testing of critical flows (connection, completion, query)
- **Detection:** CI/CD with automated testing (if available), manual smoke tests

**Risk 2: Performance Regression**
- **Likelihood:** Low
- **Impact:** Medium
- **Mitigation:**
  - Strategy pattern may add minimal overhead (negligible)
  - Cache protocol uses same underlying implementation (no change)
  - Event bus already proven in Phase 1-3
- **Detection:** Profile before and after if concerns arise

**Risk 3: Introducing New Bugs**
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:**
  - Comprehensive unit tests for new components
  - Integration tests for refactored flows
  - Code review of changes
- **Detection:** Increased test coverage, manual testing

**Risk 4: Scope Creep**
- **Likelihood:** Low
- **Impact:** Medium
- **Mitigation:**
  - Stick to plan, defer new features
  - Focus on consolidation and polish, not new functionality
  - Regular progress reviews against plan
- **Detection:** Weekly progress check against timeline

**Risk 5: Merge Conflicts (if working with colleague)**
- **Likelihood:** Medium (if parallel work)
- **Impact:** Medium
- **Mitigation:**
  - Coordinate on which files to work on
  - Frequent commits and merges
  - Clear communication about changes
- **Detection:** Git status checks, proactive communication

---

## 10. Testing Strategy

### Unit Tests

**New components requiring tests:**

**Phase 2.1:**
- `tui/completion/resource_completion.py` - Resource completion strategy
- `tui/completion/command_completion.py` - Command completion strategy
- `tui/completion/argument_completion.py` - Argument completion strategy
- `tui/completion/orchestrator.py` - Completion orchestrator
- `tui/formatters/status.py` - Status formatting functions
- `mcp_client/factory.py` - Client factory

**Test Coverage Goals:**
- Strategy pattern: 90%+ coverage
- Formatters: 80%+ coverage
- Factory: 85%+ coverage

**Example tests:**

```python
# tests/tui/completion/test_resource_completion.py
async def test_can_handle_detects_at_symbol():
    strategy = ResourceCompletionStrategy(mock_artifact_manager)
    assert strategy.can_handle("@res", 4)
    assert not strategy.can_handle("res", 3)

async def test_filters_resources_by_query():
    strategy = ResourceCompletionStrategy(mock_artifact_manager)
    candidates = await strategy.get_candidates("@doc", 4, {})
    assert all("doc" in c.value.lower() for c in candidates)

# tests/mcp_client/test_factory.py
def test_factory_creates_client_with_event_bus():
    event_bus = EventBus()
    factory = ClientFactory(event_bus)
    client = factory.create_client("test", mock_config)
    assert client.connection_manager.event_bus is event_bus
```

### Integration Tests

**Test scenarios:**

1. **End-to-end completion flow:**
   - User types "@" → resource completion triggered
   - User types "/" → command completion triggered
   - User types "/cmd " → argument completion triggered

2. **End-to-end artifact fetching:**
   - ArtifactManager → ArtifactRepository → MCPClient
   - Timeout handling works correctly
   - Cache updates correctly

3. **Event flow:**
   - ConnectionManager publishes status change
   - EventBus delivers to handlers
   - UI updates correctly

4. **Client creation:**
   - Factory creates client with correct configuration
   - EventBus wired correctly
   - Connection lifecycle works

### Manual Testing Checklist

After each phase, test:

- [ ] Application starts without errors
- [ ] MCP servers connect successfully
- [ ] Autocomplete works for @ and / triggers
- [ ] Argument suggestions appear for commands
- [ ] MCP panel displays servers and artifacts
- [ ] Connection status updates in real-time
- [ ] Reconnection works when server disconnects
- [ ] Query processing and tool execution work
- [ ] No console errors or warnings

---

## 11. Rollback Strategy

If critical issues arise, rollback strategy by phase:

### Phase 2.1 Rollback

**If AutoComplete decomposition fails:**
1. Revert `tui/completion/` package
2. Restore original `tui/widgets/autocomplete.py` from git
3. Update imports back to original
4. Keep other decompositions (MCPPanel, ArtifactManager may be independent)

**If MCPPanel decomposition fails:**
1. Revert `tui/formatters/` and extracted widgets
2. Restore original `tui/widgets/mcp_panel.py`
3. Independent of AutoComplete decomposition

**If ArtifactManager decomposition fails:**
1. Revert `mcp_client/factory.py`
2. Restore original `core/artifact_manager.py`
3. May impact Phase 2.2 (check dependencies)

### Phase 2.2 Rollback

**If ArtifactFetcher removal fails:**
1. Restore `tui/services/artifact_fetcher.py`
2. Revert `MCPRefresher` changes
3. Revert timeout logic in repository

**If legacy callback removal fails:**
1. Restore deprecated parameters in `ArtifactManager`
2. Restore dual handling code
3. Revert caller changes

### Phase 2.3 Rollback

**If business logic move fails:**
1. Restore `tui/widgets/argument_suggestions.py`
2. Restore `tui/widgets/command_parser.py`
3. Revert `core/suggestions/` package

### Phase 2.4 Rollback

**Low risk - documentation only, no code changes**

---

## 12. Conclusion

Phase 2 refactoring builds on the excellent foundations established in Phase 1-3:
- Protocol abstractions
- Event-driven architecture
- Parser extraction
- Connection management decomposition

**What Phase 2 Completes:**

✅ **Finish the decomposition** - AutoComplete, MCPPanel, ArtifactManager meet reduction targets

✅ **Eliminate redundancies** - Remove duplicate fetching layers, legacy callbacks, dead code

✅ **Enforce clean architecture** - Business logic in core, clear layer boundaries, no violations

✅ **Polish and document** - Consistent naming, comprehensive ADRs, updated documentation

**Expected Outcomes:**

- **~1,500+ lines removed** through decomposition and redundancy elimination
- **Zero architecture violations** - No `type: ignore`, no business logic in TUI
- **Consistent abstractions** - Cache, protocols, events used uniformly
- **Clear patterns** - Service vs Handler, documented in ADRs
- **Maintainable codebase** - Small, focused files with single responsibilities

**Timeline:** 4-5 weeks, 25-30 hours
**Risk Level:** Low (building on proven patterns)

The result will be a clean, well-architected codebase ready for future feature development with clear boundaries, consistent patterns, and comprehensive documentation.

---

## Appendix A: Final Package Structure (After Phase 2)

```
src/nxs/
├── core/                           # Domain layer
│   ├── protocols.py                # MCPClient, Cache, ArgumentParser protocols
│   ├── artifact_manager.py         # Facade (~250 lines)
│   ├── command_control.py          # CommandControlAgent
│   ├── chat.py                     # Base AgentLoop
│   ├── tools.py                    # ToolManager
│   ├── claude.py                   # Anthropic SDK wrapper
│   ├── mcp_config.py               # MCP configuration
│   ├── events/
│   │   ├── bus.py                  # EventBus
│   │   └── types.py                # Event types
│   ├── cache/
│   │   ├── base.py                 # Cache protocol re-export
│   │   ├── memory.py               # MemoryCache
│   │   └── ttl.py                  # TTLCache
│   ├── artifacts/
│   │   ├── repository.py           # ArtifactRepository (with timeout)
│   │   ├── cache.py                # ArtifactCache
│   │   └── change_detector.py     # ArtifactChangeDetector
│   ├── parsers/
│   │   ├── base.py                 # ArgumentParser protocol
│   │   ├── composite.py            # CompositeArgumentParser
│   │   ├── key_value.py            # KeyValueArgumentParser
│   │   ├── positional.py           # PositionalArgumentParser
│   │   └── schema_adapter.py      # SchemaAdapter
│   └── suggestions/                # NEW
│       └── generator.py            # ArgumentSuggestionGenerator
│
├── mcp_client/                     # Infrastructure layer
│   ├── client.py                   # MCPAuthClient wrapper
│   ├── factory.py                  # ClientFactory (NEW)
│   ├── cli.py                      # Typer CLI
│   ├── auth.py                     # OAuth handling
│   ├── storage.py                  # State persistence
│   ├── callback.py                 # UI callback helpers
│   ├── connection/
│   │   ├── manager.py              # ConnectionManager
│   │   ├── lifecycle.py            # ConnectionLifecycle
│   │   ├── reconnect.py            # ExponentialBackoffStrategy
│   │   └── health.py               # HealthChecker
│   └── operations/
│       ├── base.py                 # OperationBase
│       ├── tools.py                # ToolsOperations
│       ├── prompts.py              # PromptsOperations
│       └── resources.py            # ResourcesOperations
│
└── tui/                            # Presentation layer
    ├── app.py                      # NexusApp orchestrator (~530 lines)
    ├── query_manager.py            # Async query manager
    ├── status_queue.py             # Async status queue
    ├── services/
    │   ├── mcp_coordinator.py      # MCP initialization
    │   ├── prompt_service.py       # Prompt caching
    │   ├── autocomplete_service.py # Autocomplete lifecycle
    │   └── refresh_service.py      # Refresh orchestration (renamed)
    ├── handlers/
    │   ├── connection_handler.py   # Connection events
    │   ├── query_handler.py        # Query processing
    │   └── refresh_handler.py      # Artifact refresh events
    ├── completion/                 # NEW
    │   ├── strategy.py             # CompletionStrategy protocol
    │   ├── resource_completion.py  # ResourceCompletionStrategy
    │   ├── command_completion.py   # CommandCompletionStrategy
    │   ├── argument_completion.py  # ArgumentCompletionStrategy
    │   └── orchestrator.py         # CompletionOrchestrator
    ├── formatters/                 # NEW
    │   └── status.py               # Status formatting functions
    └── widgets/
        ├── autocomplete.py         # Main widget (~300 lines)
        ├── mcp_panel.py            # Main panel (~300 lines)
        ├── server_widget.py        # ServerWidget (extracted)
        ├── artifact_item.py        # ArtifactItem (extracted)
        ├── chat_panel.py           # Chat display
        ├── status_panel.py         # Status display
        ├── artifact_overlay.py     # Artifact detail modal
        └── input_field.py          # Input field
```

**Files Removed:**
- ❌ `core/connection/` (empty directory)
- ❌ `tui/services/artifact_fetcher.py` (redundant)
- ❌ `tui/widgets/argument_suggestions.py` (moved to core)
- ❌ `tui/widgets/command_parser.py` (merged with core parsers)

**Net Change:** ~1,500 lines removed, better organized

---

## Appendix B: Quick Reference - Phase 2 Steps

| Phase | Step | Description | Effort | Files Changed |
|-------|------|-------------|--------|---------------|
| **2.1** | 2.1.1 | Decompose AutoComplete (905→300) | 5-6h | +5 files, -1 file |
| **2.1** | 2.1.2 | Decompose MCPPanel (838→300) | 4-5h | +3 files, -1 file |
| **2.1** | 2.1.3 | Decompose ArtifactManager (523→250) | 3-4h | +1 file, ~1 file |
| **2.2** | 2.2.1 | Eliminate ArtifactFetcher | 2h | -1 file, ~2 files |
| **2.2** | 2.2.2 | Remove Legacy Callbacks | 2h | ~2 files |
| **2.2** | 2.2.3 | Clean Up Dead Code | 1-2h | -2 items, ~3 files |
| **2.2** | 2.2.4 | Consolidate Status Tracking | 1-2h | ~3 files |
| **2.3** | 2.3.1 | Move Business Logic Out of TUI | 2-3h | +1 package, -2 files |
| **2.3** | 2.3.2 | Fix Protocol Violations | 2h | ~2 files |
| **2.3** | 2.3.3 | Unify Cache Usage | 1-2h | ~3 files |
| **2.4** | 2.4.1 | Consistent Naming | 1h | ~2 files |
| **2.4** | 2.4.2 | Update Documentation | 2-3h | +5 ADRs, ~2 docs |
| **Total** | | | **25-30h** | **~40 files** |

---

**Document Version:** 1.0
**Last Updated:** 2025-01-07
**Status:** Ready for Implementation
