# Agentic Loop Integration Guide

## Quick Start

This guide provides step-by-step instructions for integrating the new agentic loop architecture (Phases 1-3) with the existing codebase (Phase 4).

## Prerequisites

Before integration:
- ✅ All Phase 1-3 code is implemented
- ✅ All 65 tests are passing
- ✅ ARCHITECTURE.md is updated
- ✅ Legacy code backed up (`chat_legacy.py`)

## Integration Steps

### Step 1: Add Backward Compatibility to AgentLoop

**File**: `src/nxs/application/agentic_loop.py`

**Goal**: Support both old (clients) and new (conversation + tool_registry) initialization

**Implementation**:

```python
from typing import Any, Callable, Optional
from collections.abc import Mapping

from nxs.application.claude import Claude
from nxs.application.conversation import Conversation
from nxs.application.tool_registry import ToolRegistry
from nxs.domain.protocols import MCPClient

class AgentLoop:
    def __init__(
        self,
        llm: Claude,
        conversation: Optional[Conversation] = None,
        tool_registry: Optional[ToolRegistry] = None,
        callbacks: Optional[dict[str, Callable]] = None,
        # Legacy parameter for backward compatibility
        clients: Optional[Mapping[str, MCPClient]] = None,
    ):
        """Initialize AgentLoop with backward compatibility.

        New mode: conversation + tool_registry
        Legacy mode: clients (auto-creates conversation + tool_registry)
        """
        self.llm = llm
        self.callbacks = callbacks or {}

        # Backward compatibility: create Conversation and ToolRegistry from clients
        if clients is not None and (conversation is None or tool_registry is None):
            from nxs.application.mcp_tool_provider import MCPToolProvider

            # Create default Conversation if not provided
            if conversation is None:
                conversation = Conversation(enable_caching=True)

            # Create ToolRegistry with MCPToolProvider if not provided
            if tool_registry is None:
                tool_registry = ToolRegistry(enable_caching=True)
                mcp_provider = MCPToolProvider(clients)
                tool_registry.register_provider(mcp_provider)

            # Store clients for CommandControlAgent compatibility
            self.tool_clients = clients

        # Validate required parameters
        if conversation is None or tool_registry is None:
            raise ValueError(
                "AgentLoop requires either (conversation + tool_registry) "
                "or (clients) parameters"
            )

        self.conversation = conversation
        self.tool_registry = tool_registry

    # Add property for backward compatibility with CommandControlAgent
    @property
    def messages(self):
        """Legacy property for CommandControlAgent compatibility."""
        return self.conversation._messages
```

**Test**: Verify both initialization modes work:

```python
# Test legacy mode
agent_old = AgentLoop(llm=claude, clients=mcp_clients)
assert agent_old.conversation is not None
assert agent_old.tool_registry is not None

# Test new mode
conversation = Conversation()
tool_registry = ToolRegistry()
agent_new = AgentLoop(llm=claude, conversation=conversation, tool_registry=tool_registry)
assert agent_new.conversation is conversation
assert agent_new.tool_registry is tool_registry
```

### Step 2: Update CommandControlAgent

**File**: `src/nxs/application/command_control.py`

**Goal**: Use Conversation methods instead of direct `self.messages` access

**Changes**:

```python
# OLD (direct messages access)
self.messages.append({"role": "user", "content": prompt})
self.messages += prompt_messages

# NEW (use Conversation methods)
self.conversation.add_user_message(prompt)
for msg in prompt_messages:
    if msg["role"] == "user":
        self.conversation.add_user_message(msg["content"])
    elif msg["role"] == "assistant":
        # Convert to Message-like object or add raw content
        # (depends on implementation details)
```

**Note**: The `messages` property in AgentLoop provides backward compatibility, so minimal changes may be needed.

### Step 3: Integrate SessionManager (Optional for MVP)

**File**: `src/nxs/main.py` or wherever initialization happens

**Goal**: Use SessionManager to manage conversation sessions

**Implementation**:

```python
from pathlib import Path
from nxs.application.session_manager import SessionManager

# In your initialization code:
session_manager = SessionManager(
    llm=claude,
    tool_registry=tool_registry,
    storage_dir=Path("~/.nxs/sessions"),
    system_message="Your helpful system message here",
    enable_caching=True,
)

# Get or restore default session
session = await session_manager.get_or_create_default_session()

# Use session for queries
result = await session.run_query("Hello!", callbacks=your_callbacks)

# Save session on exit
session_manager.save_active_session()
```

**Alternative (Minimal Integration)**:

If you want to defer SessionManager integration:

```python
# Just use new AgentLoop directly with clients
conversation = Conversation(
    system_message="Your system message",
    enable_caching=True,
)

tool_registry = ToolRegistry(enable_caching=True)
mcp_provider = MCPToolProvider(clients)
tool_registry.register_provider(mcp_provider)

agent_loop = AgentLoop(
    llm=claude,
    conversation=conversation,
    tool_registry=tool_registry,
    callbacks=callbacks,
)

# Use as before
result = await agent_loop.run(query)
```

### Step 4: Update NexusApp (if using SessionManager)

**File**: `src/nxs/presentation/tui/nexus_app.py` (or equivalent)

**Goal**: Integrate SessionManager lifecycle with TUI

**Changes**:

```python
class NexusApp(App):
    def __init__(self, session_manager: SessionManager, ...):
        super().__init__()
        self.session_manager = session_manager
        # ...

    async def on_mount(self):
        """Restore session on startup."""
        self.session = await self.session_manager.get_or_create_default_session()
        # ...

    async def on_shutdown(self):
        """Save session on exit."""
        self.session_manager.save_active_session()
        # ...

    async def handle_query(self, query: str):
        """Process query through session."""
        result = await self.session.run_query(query, callbacks=self.callbacks)
        return result
```

### Step 5: Run Tests

**Verify everything works**:

```bash
# Run all tests
pixi run --environment test test

# Run specific test suites
pixi run --environment test test tests/test_conversation.py
pixi run --environment test test tests/test_session.py
pixi run --environment test test tests/test_session_manager.py
```

**Expected Results**:
- All 65 new tests pass
- All existing tests pass (or minimal breakage)

### Step 6: Type Checking

**Verify type safety**:

```bash
pixi run --environment dev type-check
```

**Address any type errors** that arise from integration.

## Testing the Integration

### Manual Testing Checklist

- [ ] Start the application
- [ ] Send a simple query (verify response)
- [ ] Send a query requiring tools (verify tool execution)
- [ ] Send multiple queries (verify conversation history)
- [ ] Restart application (verify session restoration if using SessionManager)
- [ ] Check session persistence file (`~/.nxs/sessions/session.json`)
- [ ] Verify streaming works (real-time chunks)
- [ ] Verify cost optimization (check Anthropic dashboard for cache hits)

### Integration Test Examples

```python
@pytest.mark.asyncio
async def test_backward_compatible_initialization():
    """Test that legacy initialization still works."""
    agent = AgentLoop(llm=mock_claude, clients=mock_clients)
    assert agent.conversation is not None
    assert agent.tool_registry is not None

@pytest.mark.asyncio
async def test_session_persistence():
    """Test that sessions persist across restarts."""
    # Create session and add messages
    manager = SessionManager(llm, tool_registry, tmp_path)
    session = await manager.get_or_create_default_session()
    await session.run_query("Test")
    manager.save_active_session()

    # Create new manager (simulate restart)
    manager2 = SessionManager(llm, tool_registry, tmp_path)
    session2 = await manager2.get_or_create_default_session()

    # Verify session restored
    assert session2.get_message_count() == session.get_message_count()
```

## Rollback Plan

If integration causes issues:

### Option 1: Quick Rollback

```bash
# Restore legacy AgentLoop
cp src/nxs/application/chat_legacy.py src/nxs/application/agentic_loop.py

# Revert any other changes
git checkout src/nxs/application/command_control.py
git checkout src/nxs/main.py
```

### Option 2: Gradual Rollback

Keep new code but disable features:

```python
# Use legacy initialization path
agent = AgentLoop(llm=claude, clients=clients)  # Auto-creates internals

# Don't use SessionManager yet
# agent = AgentLoop(llm=claude, conversation=..., tool_registry=...)
```

## Common Issues and Solutions

### Issue: CommandControlAgent breaks

**Symptom**: `AttributeError: 'AgentLoop' object has no attribute 'messages'`

**Solution**: Add `messages` property to AgentLoop:

```python
@property
def messages(self):
    return self.conversation._messages
```

### Issue: Type errors with MessageParam

**Symptom**: `Argument has incompatible type`

**Solution**: Use `cast(Any, content)` for flexible content:

```python
from typing import cast, Any

message: MessageParam = {"role": "user", "content": cast(Any, content)}
```

### Issue: Session file corrupt/missing

**Symptom**: `JSONDecodeError` or session not restoring

**Solution**: SessionManager already handles this gracefully - creates new session. Check logs for error details.

### Issue: Streaming not working

**Symptom**: No real-time chunks, still feels chunky

**Solution**: Ensure `use_streaming=True` and callbacks are async:

```python
result = await agent.run(query, use_streaming=True, callbacks={
    "on_stream_chunk": async_callback_function
})
```

## Performance Verification

### Verify Prompt Caching Works

Check Anthropic API dashboard or logs for:
- Cache creation events
- Cache hit events
- Cost reduction metrics

### Verify Real Streaming Works

Check that:
- First chunk arrives quickly (< 1s)
- Chunks arrive continuously (no artificial delays)
- No blocking between chunks

### Verify Session Persistence Works

Check:
- Session file exists: `~/.nxs/sessions/session.json`
- File contains conversation history
- File size grows with conversation
- Session restores on restart

## Post-Integration Cleanup

After successful integration:

1. **Remove Legacy Code** (optional, keep for reference):
   ```bash
   # rm src/nxs/application/chat_legacy.py
   ```

2. **Update Documentation**:
   - Mark Phase 4 as complete in AGENTIC_LOOP_IMPLEMENTATION_SUMMARY.md
   - Update README.md with new features
   - Update any developer onboarding docs

3. **Add Integration Tests**:
   - End-to-end tests with real queries
   - Session persistence tests
   - Cost optimization verification tests

4. **Monitor Production**:
   - Watch for errors in logs
   - Monitor Anthropic API costs (should see reduction)
   - Collect user feedback on streaming experience

## Success Criteria

Integration is successful when:

- ✅ All tests pass (new + existing)
- ✅ Application starts without errors
- ✅ Queries work as before
- ✅ Streaming feels natural (real-time)
- ✅ Sessions persist across restarts
- ✅ Costs are reduced (cache hits visible)
- ✅ No regression in functionality
- ✅ Type checking passes

## Support

If you encounter issues during integration:

1. Check `nexus.log` for detailed error messages
2. Review ARCHITECTURE.md for architecture details
3. Review test files for usage examples
4. Check Anthropic SDK documentation for API details
5. Use `git diff` to see what changed

## Next Steps After Integration

Once Phase 4 is complete:

1. **Monitor and Optimize**:
   - Watch cache hit rates
   - Optimize cache placement if needed
   - Monitor session file sizes

2. **Add Features**:
   - Session search
   - Session export
   - Session tags
   - Multiple sessions (TUI tabs)

3. **Enhance UX**:
   - Session rename UI
   - Session deletion UI
   - Session metadata display
   - Cost tracking display

4. **Scale Testing**:
   - Long conversation testing
   - Multiple session testing
   - Large file session testing
   - Concurrent query testing
