# Nexus Phase 4 Refactoring Plan - Critical Fixes Only

## Executive Summary

**Status:** Phase 3 architectural foundation complete ✅
**Remaining:** 7 critical issues preventing production readiness
**Timeline:** 2 weeks, 12-15 hours total
**Focus:** Pragmatic fixes only - no over-engineering

### What Phase 3 Accomplished
✅ Domain layer with zero dependencies
✅ Clean package structure (domain/application/infrastructure/presentation)
✅ Fixed 99% of import violations
✅ Services are right-sized (100-300 lines each)
✅ No debugging code or print statements (except 1 bug)

### Critical Issues Remaining
🔴 **2 Runtime Bugs** - Will cause crashes in production
🔴 **3 Layer Violations** - Break architectural foundation
🔴 **1 God Object** - NexusApp at 524 lines blocks team scaling
🟡 **1 State Management** - ArtifactManager has dual responsibilities

**Good News:** No major refactoring needed - just targeted fixes.

---

## Phase 4 Critical Tasks (Priority Order)

### Week 1: Fix Critical Bugs & Violations (6-8 hours)

#### Task 4.1: Fix ToolManager Error Handling Bug ⚠️ CRASH RISK
**Priority:** CRITICAL
**Effort:** 30 minutes
**File:** `src/nxs/application/tools.py:80-87`

**Problem:**
```python
try:
    tool_output: CallToolResult | None = await client.call_tool(...)
    # ... use tool_output
except Exception as e:
    # BUG: tool_output may not exist if exception before assignment
    "error" if tool_output and tool_output.isError else "success"  # UnboundLocalError!
    print(error_message)  # Also: print() in production code
```

**Fix:**
1. Initialize `tool_output = None` before try block
2. Remove `print()` statement, use `logger.error()` instead
3. Simplify error path: always return `"error"` status in exception handler

**Impact:** Prevents crash on any tool execution error

---

#### Task 4.2: Fix AgentLoop Message State Leak ⚠️ DATA BUG
**Priority:** CRITICAL
**Effort:** 2-3 hours
**File:** `src/nxs/application/chat.py:15`

**Problem:**
```python
class AgentLoop:
    def __init__(self, ...):
        self.messages: list[MessageParam] = []  # SHARED STATE across all queries!
```

**Impact:**
- Messages accumulate across queries
- Context leaks between conversations
- Memory grows unbounded
- Cannot run concurrent queries

**Fix (Simple Approach):**
```python
class AgentLoop:
    def __init__(self, ...):
        # Remove: self.messages

    async def run(self, query: str, callbacks=None) -> str:
        messages: list[MessageParam] = []  # Local to each run() call
        messages.append({"role": "user", "content": query})
        # ... rest of logic
```

**Actions:**
1. Remove `self.messages` from `__init__`
2. Make `messages` local variable in `run()` method
3. Update CommandControlAgent to not access `self.messages`
4. Add test verifying messages don't leak between calls

---

#### Task 4.3: Fix Layer Violations - Cache Imports ⚠️ ARCHITECTURE
**Priority:** CRITICAL
**Effort:** 1-2 hours
**Files:**
- `application/artifact_manager.py:18`
- `application/artifacts/cache.py`
- `presentation/tui/nexus_app.py:36`
- `presentation/services/prompt_service.py`

**Problem:**
```python
# WRONG: Application/Presentation importing Infrastructure
from nxs.infrastructure.cache import Cache, MemoryCache
```

**Fix:**
```python
# CORRECT: Import protocol from domain
from nxs.domain.protocols import Cache

# In main.py only (for DI):
from nxs.infrastructure.cache import MemoryCache
```

**Actions:**
1. Update 4 files to import from `domain.protocols.Cache`
2. Keep concrete `MemoryCache` imports only in `main.py` for dependency injection
3. Verify with: `grep -r "from nxs.infrastructure.cache" src/nxs/application/ src/nxs/presentation/`

---

#### Task 4.4: Fix Layer Violation - ClientFactory Injection ⚠️ ARCHITECTURE
**Priority:** CRITICAL
**Effort:** 2-3 hours
**File:** `application/artifact_manager.py:29`

**Problem:**
```python
# WRONG: Application importing Infrastructure
from nxs.infrastructure.mcp.factory import ClientFactory
```

**Fix:**
```python
# In artifact_manager.py
from nxs.domain.protocols import ClientProvider  # Already exists!

class ArtifactManager:
    def __init__(
        self,
        config: Optional[MCPServersConfig] = None,
        event_bus: Optional[EventBus] = None,
        client_provider: Optional[ClientProvider] = None,  # Protocol injection
        ...
    ):
        self._client_factory = client_provider or ClientFactory()  # Remove direct import
```

**Actions:**
1. Change ArtifactManager to accept `ClientProvider` protocol
2. Update `main.py` to inject concrete `ClientFactory`
3. Remove direct import of `ClientFactory` from application layer
4. Verify: `grep -r "from nxs.infrastructure.mcp" src/nxs/application/`

---

### Week 2: Fix God Object (8-10 hours)

#### Task 4.5: Create ServiceContainer
**Priority:** HIGH (blocks testing/scaling)
**Effort:** 4-5 hours
**New File:** `presentation/services/container.py`

**Problem:** NexusApp creates 9 dependencies directly in `__init__` (85 lines of setup code)

**Solution:**
```python
# presentation/services/container.py
class ServiceContainer:
    """Manages all TUI service lifecycle and dependencies."""

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        event_bus: EventBus,
        agent_loop: AgentLoop,
    ):
        # Create all services here
        self.status_queue = StatusQueue(...)
        self.mcp_refresher = RefreshService(...)
        self.prompt_service = PromptService(...)
        self.autocomplete_service = AutocompleteService(...)
        self.mcp_coordinator = MCPCoordinator(...)

        # Create all handlers here
        self.connection_handler = ConnectionHandler(...)
        self.query_handler = QueryHandler(...)
        self.refresh_handler = RefreshHandler(...)

    def subscribe_events(self, event_bus: EventBus):
        """Wire up all event subscriptions."""
        event_bus.subscribe(ConnectionStatusChanged, self.connection_handler.handle_...)
        # ... etc
```

**Actions:**
1. Create ServiceContainer class
2. Move service creation from NexusApp.__init__ (lines 115-163)
3. Move event subscriptions from NexusApp.__init__ (lines 166-174)
4. NexusApp receives ServiceContainer in `__init__`
5. **Result:** NexusApp.__init__ reduces from 85 lines → ~20 lines

---

#### Task 4.6: Extract NexusApp Initialization Logic
**Priority:** HIGH
**Effort:** 3-4 hours
**File:** `presentation/tui/nexus_app.py`

**Problem:**
- `_initialize_mcp_connections_async()` is 85 lines (lines 234-318)
- `_periodic_artifact_refresh()` is 87 lines (lines 437-524)
- Mixed concerns in single class

**Solution:**
1. **Move to MCPCoordinator** (already exists at 145 lines):
   - `_initialize_mcp_connections_async()` logic → `MCPCoordinator.initialize_and_load()`

2. **Create BackgroundTaskService**:
   - `_periodic_artifact_refresh()` → `BackgroundTaskService.start_periodic_refresh()`

3. **Simplify NexusApp.on_mount()**:
```python
async def on_mount(self) -> None:
    # Show welcome message
    chat = self.query_one("#chat", ChatPanel)
    chat.add_panel(...)

    # Start services (delegated)
    await self.services.initialize()  # ServiceContainer handles complexity

    # Focus input
    self.call_after_refresh(self._focus_input)
```

**Actions:**
1. Move initialization to MCPCoordinator
2. Create BackgroundTaskService for periodic tasks
3. Simplify on_mount to ~15 lines
4. **Result:** NexusApp reduces from 524 lines → ~200 lines (62% reduction)

---

## Optional (Week 3): Split ArtifactManager

#### Task 4.7: Extract ConnectionManager from ArtifactManager
**Priority:** MEDIUM (nice-to-have)
**Effort:** 4-5 hours
**File:** `application/artifact_manager.py` (314 lines)

**Problem:** Two responsibilities:
1. Connection lifecycle (lines 69-137): create/cleanup clients, track status
2. Artifact access (lines 142-237): get resources/prompts/tools, caching

**Solution:**
```python
# application/connection_manager.py (NEW)
class ConnectionManager:
    """Manages MCP client lifecycle."""

    async def initialize(self, use_auth: bool = False) -> None:
        # Lines 69-88 from ArtifactManager

    async def cleanup(self) -> None:
        # Lines 90-107 from ArtifactManager

    @property
    def clients(self) -> Mapping[str, MCPClient]:
        return MappingProxyType(self._clients)

# application/artifact_manager.py (SIMPLIFIED)
class ArtifactManager:
    def __init__(self, connection_manager: ConnectionManager, ...):
        self._connection_manager = connection_manager
        # Delegates lifecycle to ConnectionManager
        # Focuses only on artifact access
```

**Note:** Only do this if time permits. Not critical since Phase 3 already improved organization.

---

## Success Criteria

### After Week 1 (Critical Fixes):
✅ Zero runtime bugs (ToolManager fixed, AgentLoop fixed)
✅ Zero layer violations (Cache + ClientFactory use protocols)
✅ Type checker passes with same 21 pre-existing errors
✅ Application starts and runs without crashes

### After Week 2 (God Object Fix):
✅ NexusApp reduced to ~200 lines (from 524)
✅ ServiceContainer manages all dependencies
✅ NexusApp focuses only on UI composition
✅ Easier to test (can inject mock ServiceContainer)

### Optional Week 3:
✅ ArtifactManager focuses on single concern
✅ ConnectionManager handles lifecycle separately

---

## Verification Steps

After each task:

1. **Run type checker:**
   ```bash
   pixi run --environment dev type-check
   # Should show 21 errors (same as before)
   ```

2. **Run application:**
   ```bash
   pixi run start --debug
   # Should start without errors
   # Should connect to MCP servers
   # Should handle queries correctly
   ```

3. **Test specific fix:**
   - Task 4.1: Try tool execution with error → should log, not crash
   - Task 4.2: Run multiple queries → verify no context leakage
   - Task 4.3-4.4: Verify imports with grep (no infrastructure in app/presentation)
   - Task 4.5-4.6: Verify NexusApp line count reduction

4. **Manual smoke tests:**
   - Connect to MCP servers ✓
   - Type @ for autocomplete ✓
   - Type / for commands ✓
   - Execute a query ✓
   - Call a tool ✓
   - Clear chat (Ctrl+L) ✓
   - Quit (Ctrl+Q) ✓

---

## What We're NOT Doing (Pragmatic Scope)

❌ **Not touching** completion package (843 lines) - already works fine
❌ **Not touching** handlers - they're thin wrappers, good enough
❌ **Not touching** services - all under 300 lines, well-sized
❌ **Not creating** elaborate testing framework - focus on functionality
❌ **Not writing** ADRs or extensive docs - code is self-documenting
❌ **Not optimizing** package structure beyond critical fixes

**Rationale:** Phase 3 already improved structure significantly. Focus only on bugs and blockers.

---

## Timeline Summary

| Week | Focus | Hours | Outcome |
|------|-------|-------|---------|
| **Week 1** | Critical bugs + violations | 6-8h | Production-ready code |
| **Week 2** | NexusApp god object | 8-10h | Maintainable codebase |
| **Week 3** | (Optional) ArtifactManager split | 4-5h | Further polish |
| **Total** | | **12-15h** (18-23h with optional) | Clean architecture |

---

## Conclusion

**Phase 4 is focused and pragmatic:**
- Fix 2 critical bugs that will crash in production (3 hours)
- Fix 3 layer violations that break architecture (4 hours)
- Fix 1 god object that blocks team scaling (8 hours)

**Total: 15 hours over 2 weeks to achieve production-ready, maintainable code.**

Everything else can wait. The codebase is already in good shape after Phase 3.

**Ready to execute? Start with Task 4.1 (ToolManager bug) - 30 minutes to eliminate crash risk.**

---

**Document Version:** 1.0
**Date:** 2025-01-08
**Status:** Ready for Implementation
**Based on:** Phase 3 completion analysis and pragmatic prioritization
