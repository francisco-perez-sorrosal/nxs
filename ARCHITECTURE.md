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

Coordinates the core runtime use cases without UI or infrastructure details.

**Conversation Management**:
- `Conversation` (`conversation.py`) manages message history with prompt caching support, enabling 90% cost reduction through strategic cache control markers on system messages, tools, and the last user message.
- `Session` (`session.py`) encapsulates a conversation with metadata (title, timestamps, tags) for persistence and lifecycle management.
- `SessionManager` (`session_manager.py`) handles session persistence, auto-save/restore, and multi-session management with pragmatic auto-save on switch and exit.

**Agent Orchestration**:
- `AgentLoop` (`chat.py`) orchestrates the conversation loop with Claude, handling tool execution and real-time streaming via callbacks. Supports both new (conversation + tool_registry) and legacy (clients) initialization patterns for backward compatibility.
- `CommandControlAgent` (`command_control.py`) extends AgentLoop with command parsing (`/command`) and resource extraction (`@resource`) capabilities.

**Tool Management**:
- `ToolRegistry` (`tool_registry.py`) provides a pluggable tool interface with the `ToolProvider` protocol, enabling multiple tool sources beyond MCP (web search, text editors, custom tools).
- `MCPToolProvider` (`mcp_tool_provider.py`) bridges existing MCP infrastructure with the ToolRegistry, aggregating tools from all MCP servers and routing execution to the correct client.

**MCP Integration**:
- `MCPConnectionManager` (`connection_manager.py`) translates MCP server configuration into live `MCPClient` instances, tracks lifecycle across ALL servers, and emits connection events.
- `ArtifactManager` (`artifact_manager.py`) composes repository and cache to fetch MCP resources/prompts/tools and publishes `ArtifactsFetched` events.

**Claude Integration**:
- `Claude` (`claude.py`) provides an enhanced wrapper around the Anthropic SDK with support for real streaming (`stream_message()`), prompt caching, extended thinking, and both sync and async interfaces.

**Supporting Packages**:
- `artifacts/` - Resource and prompt repositories
- `parsers/` - Command and argument parsing with schema validation
- `suggestions/` - Completion generation for autocomplete

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
2. `QueryHandler` processes the query through `CommandControlAgent` (which extends `AgentLoop`).
3. If the query starts with `/`, `CommandControlAgent` processes it as a command; if it contains `@mentions`, it extracts referenced resources from MCP servers.
4. `AgentLoop` adds the user message to the `Conversation`, retrieves messages with cache control applied, gets tools from `ToolRegistry`, and streams the Claude API call via real-time streaming.
5. If Claude requests tool execution, `ToolRegistry` routes tool calls to the appropriate `ToolProvider` (e.g., `MCPToolProvider` for MCP tools), executes them, and adds results to the conversation before continuing the loop.
6. Final text responses stream chunk-by-chunk to the chat panel via callbacks; status updates appear in the status panel via `StatusQueue` which ensures FIFO ordering.
7. The `SessionManager` auto-saves the conversation state after each interaction for persistence across restarts.

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
- Claude communication is abstracted behind `application/claude.py`, providing real streaming via async generators, prompt caching for 90% cost reduction, and support for extended thinking mode.
- MCP clients rely on `nxs.infrastructure.mcp.client.MCPAuthClient` for authenticated HTTP transport, automatic reconnects, and tool execution.
- Logging is centralized via `nxs.logger.get_logger`, ensuring consistent, colorized output across layers and simplifying traceability during debugging.
- Session persistence uses JSON files in `~/.nxs/sessions/` for human-readable, git-friendly conversation history.

This architecture enables the TUI to stay responsive while background tasks connect to remote services, fetch artifacts, and execute tools, all without hard-coupling UI components to networking or storage concerns. The layered design with protocols and events allows developers to extend or replace each layer independently.

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

## Enhanced Agentic Loop Architecture

The agentic loop follows a comprehensive architecture that separates concerns, enables session persistence, and provides real streaming with prompt caching for 90% cost reduction. This architecture replaced the legacy fake-chunking approach with proper streaming and cost optimization.

### Architecture Overview

```
SessionManager (manages single session for now)
    ↓
Session (encapsulates conversation + metadata)
    ↓
AgentLoop (orchestration)
    ↓
Conversation (message state) + ToolRegistry (uniform tool interface)
    ↓
Claude (enhanced with streaming + caching)
```

### Core Components

The enhanced architecture consists of six core components working together:

#### 1. **Conversation** (`application/conversation.py`)

The foundation of message state management with prompt caching:
- **State Management**: Maintains message history independent of orchestration
- **Prompt Caching**: Applies `cache_control` markers for 90% cost reduction
  - System messages: Always cached (stable, long-lived)
  - Tools: Always cached (stable across conversation)
  - Messages: Caches last user message (enables retries, streaming, tool calls)
- **Persistence**: `to_dict()` / `from_dict()` for session serialization
- **History Management**: Optional message limit with truncation
- **Token Estimation**: Rough token counting for conversation size

**Cache Processing Order** (per Anthropic API requirements):
1. Tools
2. System message
3. Conversation messages (chronological)

**Key Methods**:
- `add_user_message(content)`: Add user message to history
- `add_assistant_message(message)`: Add Claude's response
- `add_tool_results(tool_blocks, results)`: Add tool execution results
- `get_messages_for_api()`: Get messages with cache control applied
- `get_system_message_for_api()`: Get system message with cache control

#### 2. **ToolRegistry & ToolProvider** (`application/tool_registry.py`)

Provides pluggable tool sources with uniform interface:
- **ToolProvider Protocol**: Defines interface for tool sources
  - `provider_name`: String identifier
  - `get_tool_definitions()`: Returns tool definitions
  - `execute_tool(name, args)`: Executes tool
- **ToolRegistry**: Central hub managing multiple providers
  - Tool aggregation from all providers
  - Tool execution routing to correct provider
  - Duplicate tool name detection
  - Cache control for tool definitions
  - Concurrent tool fetching from all providers

**Extensibility**: Easy to add new tool sources beyond MCP:
- Text editor tools
- Web search tools
- Custom business logic tools
- Database query tools
- etc.

#### 3. **MCPToolProvider** (`application/mcp_tool_provider.py`)

Bridges existing MCP infrastructure with new ToolRegistry:
- Wraps multiple `MCPClient` instances
- Aggregates tools from all MCP servers
- Routes execution to correct MCP client
- Handles MCP-specific types (`Tool`, `CallToolResult`, `TextContent`)
- JSON formatting of results

#### 4. **Enhanced Claude Wrapper** (`application/claude.py`)

Comprehensive API wrapper with streaming and caching:
- **Synchronous**: `chat()` - Legacy compatibility
- **Async Streaming**: `stream_message()` - Real streaming via async generators
- **Async Non-Streaming**: `create_message()` - Async without streaming
- **Full Type Safety**: Proper Anthropic SDK types throughout
- **Cache Control Support**: Passes through cache_control markers
- **Extended Thinking**: Support for thinking mode
- **Backward Compatible**: Legacy methods preserved

**Streaming Benefits**:
- Real-time chunk-by-chunk updates (not fake chunking)
- Lower latency to first token
- Better user experience
- Proper error recovery

#### 5. **Refactored AgentLoop** (`application/chat.py`)

Clean orchestration with separated concerns:
- **State**: Delegates to `Conversation` (not `self.messages`)
- **Tools**: Delegates to `ToolRegistry` (not just MCP)
- **Streaming**: Real streaming via `Claude.stream_message()` with proper event handling
- **Callbacks**: Comprehensive callback interface for UI integration
- **Backward Compatible**: Supports both old (clients) and new (conversation + tool_registry) constructors
- **Parameter Handling**: Properly omits optional parameters (tools, system) when empty, per Anthropic API requirements

**Agent Loop Flow**:
1. User query → Add to conversation
2. Get messages, system, tools (all with cache control)
3. Build API parameters, including only non-empty values
4. Call Claude API (streaming or non-streaming)
5. If tool use:
   - Execute tools via ToolRegistry
   - Add results to conversation
   - Loop back to step 2
6. If text response:
   - Stream chunks via callbacks
   - Return final text to user

**Key Methods**:
- `run(query, callbacks, use_streaming)`: Execute query
- `_run_with_streaming()`: Real streaming path with proper event type checking
- `_run_without_streaming()`: Legacy compatibility path
- `_execute_tools()`: Tool execution with error handling

**Streaming Implementation**:
The streaming implementation properly handles Anthropic SDK's typed event objects (`ContentBlockDeltaEvent`) rather than treating them as dictionaries, and only includes API parameters (tools, system) when they have values to avoid validation errors.

#### 6. **Session** (`application/session.py`)

Encapsulates conversation with metadata for persistence:
- **SessionMetadata**: ID, title, timestamps, tags, model, description
- **Session**: Combines Conversation + AgentLoop + Metadata
- **Persistence**: Full serialization to/from JSON
- **Lifecycle**: `run_query()`, `clear_history()`, property accessors

**Session Benefits**:
- Unit of persistence (save/restore conversations)
- Metadata tracking (created, last active, tags)
- Clean abstraction for session management
- Ready for multi-session support

#### 7. **SessionManager** (`application/session_manager.py`)

Manages session lifecycle with persistence:
- **Current**: Single session only (battle-test architecture)
- **Future**: Multi-session support (scaffolding in place)
- **Auto-save**: Persist session on updates
- **Auto-restore**: Restore session on startup
- **Storage**: JSON files in `~/.nxs/sessions/`

**Key Methods**:
- `get_or_create_default_session()`: Get or restore session
- `save_active_session()`: Persist to disk
- `get_active_session()`: Get current session
- `clear_active_session_history()`: Clear conversation
- `get_session_info()`: Get session metadata

**Future Enhancements** (commented out, ready to implement):
- `create_session(id, title)`: Create new session
- `switch_session(id)`: Switch active session
- `delete_session(id)`: Delete session
- `list_sessions()`: List all sessions
- `save_all_sessions()`: Persist all

### Benefits of New Architecture

**1. Separation of Concerns**
- State management (Conversation) separate from orchestration (AgentLoop)
- Tool discovery/execution abstracted (ToolRegistry)
- Session metadata separate from conversation history

**2. Extensibility**
- Add new tool sources via ToolProvider protocol
- Support multiple tool types (MCP, custom, built-in)
- Easy to add new session features (tags, search, export)

**3. Cost Optimization**
- 90% savings via prompt caching
- Cache system messages (stable)
- Cache tools (stable)
- Cache last user message (enables retries)

**4. Real Streaming**
- Anthropic SDK's async streaming (not fake chunking)
- Lower latency, better UX
- Proper error handling

**5. Persistence Ready**
- Sessions serialize to JSON
- Restore conversations across restarts
- Metadata tracking (created, last active, etc.)

**6. Testability**
- Clean interfaces enable unit testing
- Mocked dependencies via protocols
- 65+ comprehensive tests (all passing)

**7. Battle-Tested Architecture**
- Single session now, multi-session ready
- Scaffolding in place for future features
- Migration path clear

### Implementation Status

**Completed (Phases 1-4)**:
- ✅ Conversation class with prompt caching
- ✅ ToolRegistry with ToolProvider protocol
- ✅ MCPToolProvider for MCP integration
- ✅ Enhanced Claude wrapper with real streaming
- ✅ Refactored AgentLoop with proper event handling
- ✅ Session and SessionManager with persistence
- ✅ Backward compatibility layer in AgentLoop constructor
- ✅ CommandControlAgent working with new architecture
- ✅ main.py using SessionManager (single session mode)
- ✅ Session auto-save after each interaction
- ✅ Session auto-restore on startup
- ✅ Streaming fix for API parameter validation
- ✅ 65+ unit tests (all passing)

**Current Integration**:
The system currently operates in **single-session mode** with full persistence. The architecture supports multi-session capabilities but the TUI displays one active session at a time. The `CommandControlAgent` uses the backward-compatible initialization pattern (`clients` parameter), which internally creates a `Conversation` and `ToolRegistry` with prompt caching enabled.

**Future Enhancements** (Multi-Session UI):
- Session tabs/selector widget
- Session switching keyboard shortcuts (Ctrl+T, Ctrl+Tab)
- Session rename/labeling UI
- Visual indicator of active session
- Session list overlay (like Ctrl+Tab in VS Code)

### Design Decisions

**1. Why separate Conversation from AgentLoop?**
- AgentLoop is stateless orchestration
- Conversation is stateful message history
- Enables session persistence
- Improves testability

**2. Why ToolRegistry instead of direct MCP?**
- Extensibility: support non-MCP tools
- Abstraction: AgentLoop doesn't know about MCP
- Flexibility: easy to add new tool sources

**3. Why single session first?**
- Battle-test architecture
- Simpler initial implementation
- Full multi-session scaffolding ready
- Clear migration path

**4. Why prompt caching?**
- 90% cost reduction (massive savings)
- System messages stable (always cached)
- Tools stable (always cached)
- Last user message enables retries

**5. Why real streaming?**
- Better user experience (lower latency)
- Proper error handling
- Anthropic SDK best practice
- Character-by-character updates (not fake chunking)

**6. Why proper API parameter handling?**
- Anthropic API rejects `None` for optional parameters
- Must either pass valid values or omit parameters entirely
- Prevents validation errors during streaming
- Follows SDK requirements and best practices

### Testing Coverage

**Unit Tests** (65 tests, all passing):
- `test_conversation.py`: 29 tests - Message management, caching, persistence
- `test_session.py`: 18 tests - Session lifecycle, serialization, metadata
- `test_session_manager.py`: 18 tests - Session management, persistence, restoration

**Test Coverage Areas**:
- Message addition (user, assistant, tool results)
- Cache control application
- Conversation persistence (to_dict/from_dict)
- Session metadata management
- SessionManager lifecycle
- Session save/restore
- Error handling (corrupt files, missing data)

### File Locations

**New Files**:
- `src/nxs/application/conversation.py` - Conversation class
- `src/nxs/application/tool_registry.py` - ToolRegistry + ToolProvider
- `src/nxs/application/mcp_tool_provider.py` - MCP bridge
- `src/nxs/application/session.py` - Session + SessionMetadata
- `src/nxs/application/session_manager.py` - SessionManager
- `tests/test_conversation.py` - Conversation tests
- `tests/test_session.py` - Session tests
- `tests/test_session_manager.py` - SessionManager tests

**Modified Files**:
- `src/nxs/application/claude.py` - Enhanced with real streaming and caching
- `src/nxs/application/chat.py` - Refactored with new abstractions and proper API parameter handling
- `src/nxs/main.py` - Integrated with SessionManager

**Legacy Files** (for reference):
- `src/nxs/application/chat_legacy.py` - Original AgentLoop (preserved for comparison)

**Integration Notes**:
The integration maintains full backward compatibility. The `CommandControlAgent` in production uses the legacy initialization pattern (`clients` parameter), which the `AgentLoop` automatically converts to the new pattern by creating a `Conversation` and `ToolRegistry` internally. This allows the new architecture to work seamlessly with existing code while providing all benefits (caching, streaming, persistence).

