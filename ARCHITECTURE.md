# NXS Architecture Overview

NXS is a full-screen TUI chat application that orchestrates adaptive reasoning conversations between users and Anthropic's Claude while brokering Model Context Protocol (MCP) resources, prompts, and tools. The architecture follows a layered design with clean separation between UI, business logic, and infrastructure, featuring a sophisticated self-correcting reasoning system that automatically adapts execution strategy based on query complexity.

## Layered Design

```
┌───────────────┐
│ Presentation  │  Textual TUI, widgets, handlers, services
├───────────────┤
│ Application   │  Reasoning system, agent loops, session management
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

### Infrastructure Layer — `src/nxs/infrastructure`

- Supplies concrete implementations for the domain protocols.
- `mcp/` wraps the `MCPAuthClient`, connection management, reconnection policy, storage, and CLI helpers.
- `cache/` includes baseline cache backends (in-memory, TTL) used by application services and the presentation layer.
- Acts as the integration point for remote MCP servers (currently remote HTTP endpoints via `ClientFactory` and `MCPAuthClient`).

### Application Layer — `src/nxs/application`

Coordinates the core runtime use cases without UI or infrastructure details.

#### Adaptive Reasoning System (`reasoning/`)

The core intelligence layer providing self-correcting adaptive execution:

**Reasoning Components** (`reasoning/`):
- `QueryComplexityAnalyzer` (`analyzer.py`) - Analyzes query complexity and recommends execution strategy (DIRECT/LIGHT/DEEP)
- `Planner` (`planner.py`) - Decomposes complex queries into structured subtask plans
- `Evaluator` (`evaluator.py`) - Evaluates both research completeness and response quality for self-correction
- `Synthesizer` (`synthesizer.py`) - Combines multiple results into coherent responses with filtering and ranking
- `ReasoningConfig` (`config.py`) - Centralized configuration for thresholds, models, and behavior
- `Types` (`types.py`) - Shared types: `ComplexityAnalysis`, `ExecutionStrategy`, `ResearchPlan`, `EvaluationResult`

**Core Agent Orchestration**:
- `AdaptiveReasoningLoop` (`reasoning_loop.py`) - Self-correcting agent loop that extends `AgentLoop` with:
  - Automatic complexity analysis
  - Strategy selection (DIRECT → LIGHT → DEEP)
  - Quality evaluation after each execution
  - Auto-escalation when quality insufficient
  - Quality guarantees (never returns unvetted responses)
- `CommandControlAgent` (`command_control.py`) - High-level agent using composition (not inheritance) that:
  - Processes commands starting with `/` (executes MCP prompts)
  - Extracts resources starting with `@` (provides context)
  - Delegates all execution to `AdaptiveReasoningLoop`
  - Exposes `conversation` property for session management

**Conversation Management**:
- `Conversation` (`conversation.py`) - Manages message history with prompt caching support, enabling 90% cost reduction through strategic cache control markers on system messages, tools, and the last user message.
- `Session` (`session.py`) - Encapsulates a conversation with metadata (title, timestamps, tags) for persistence and lifecycle management.
- `SessionManager` (`session_manager.py`) - Handles session persistence, auto-save/restore, and multi-session management. Currently operates in single-session mode but architecturally supports multiple concurrent sessions (Dict[session_id, Session]).

**Tool Management**:
- `ToolRegistry` (`tool_registry.py`) - Provides a pluggable tool interface with the `ToolProvider` protocol, enabling multiple tool sources beyond MCP (web search, text editors, custom tools).
- `MCPToolProvider` (`mcp_tool_provider.py`) - Bridges existing MCP infrastructure with the ToolRegistry, aggregating tools from all MCP servers and routing execution to the correct client.

**MCP Integration**:
- `MCPConnectionManager` (`connection_manager.py`) - Translates MCP server configuration into live `MCPClient` instances, tracks lifecycle across ALL servers, and emits connection events.
- `ArtifactManager` (`artifact_manager.py`) - Composes repository and cache to fetch MCP resources/prompts/tools and publishes `ArtifactsFetched` events.

**Claude Integration**:
- `Claude` (`claude.py`) - Enhanced wrapper around the Anthropic SDK with support for real streaming (`stream_message()`), prompt caching, extended thinking, and both sync and async interfaces.

**Supporting Packages**:
- `artifacts/` - Resource and prompt repositories
- `parsers/` - Command and argument parsing with schema validation
- `suggestions/` - Completion generation for autocomplete

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
  - `QueryHandler` - Processes queries through agent loop with reasoning callbacks
  - Pattern: `handle_<event_type>` methods

**Queue-Based Components** (`tui/`):
- `QueryQueue` - FIFO queue for sequential query processing
- Both `StatusQueue` and `QueryQueue` use `AsyncQueueProcessor` to eliminate duplication

**Widgets** (`widgets/`):
- `ChatPanel` - Main conversation display with Rich formatting
- `StatusPanel` - High-level application status messages
- `ReasoningTracePanel` - Collapsible panel displaying detailed reasoning process (complexity analysis, strategy selection, quality checks, escalations)
- `MCPPanel` - MCP server status and artifacts
- `NexusInput` - Input field with autocomplete integration
- `NexusAutoComplete` - Autocomplete dropdown widget

**Architecture Flow**:
```
EventBus → Handlers → Services → Widgets
```

The presentation layer consumes only application-layer facades and domain events, remaining free of networking or storage concerns.

---

## Adaptive Reasoning System

The Adaptive Reasoning System is the core intelligence layer that provides self-correcting, quality-guaranteed responses through automatic complexity analysis and strategy adaptation.

### Architecture Overview

```
Query
  ↓
QueryComplexityAnalyzer (analyze complexity)
  ↓
AdaptiveReasoningLoop (select strategy)
  ↓
┌─────────────────────────────────────────┐
│ ExecutionStrategy                        │
├─────────────────────────────────────────┤
│ DIRECT      → Fast-path (1-3s typical)  │
│ LIGHT       → Light planning (5-10s)    │
│ DEEP        → Full reasoning (15-30s)   │
└─────────────────────────────────────────┘
  ↓
Execute → Buffer response
  ↓
Evaluator (check quality)
  ↓
Quality Sufficient? ──No──> Escalate to next strategy
  │                         (DIRECT→LIGHT→DEEP)
  Yes
  ↓
Stream to user (quality approved)
```

### Core Components

#### 1. QueryComplexityAnalyzer

**Purpose**: Automatic query complexity analysis and strategy recommendation.

**Responsibilities**:
- Analyze query structure and content
- Detect multi-part questions
- Assess information requirements
- Determine if research/iteration needed
- Recommend execution strategy

**Complexity Levels**:
- **SIMPLE**: Single direct question, answerable with general knowledge or 1 tool call (→ DIRECT execution)
- **MEDIUM**: 2-3 related parts, needs multiple tool calls (→ LIGHT_PLANNING)
- **COMPLEX**: Multi-step research, multiple sources, requires synthesis (→ DEEP_REASONING)

**Example**:
```python
analyzer = QueryComplexityAnalyzer(claude, config)
complexity = await analyzer.analyze(
    query="What is quantum computing?",
    available_tools=["search", "wikipedia"],
)
# Returns: ComplexityAnalysis(level=SIMPLE, strategy=DIRECT, confidence=0.95)
```

#### 2. Planner

**Purpose**: Strategic query planning and task decomposition.

**Responsibilities**:
- Generate initial research queries
- Decompose complex tasks into subtasks
- Prioritize execution order
- Suggest tool hints for each subtask

**Modes**:
- **Light Mode**: Minimal planning, 1-2 subtasks, quick execution
- **Deep Mode**: Full planning, 3-5 subtasks, detailed coordination

#### 3. Evaluator

**Purpose**: Dual-purpose evaluation for research completeness and response quality.

**Responsibilities**:
1. **Research Evaluation**: Assess if accumulated results answer the query
2. **Response Quality Evaluation** (self-correction):
   - Assess response completeness, accuracy, depth, coherence
   - Determine if escalation needed
   - Identify missing aspects

**Quality Criteria**:
- Completeness: Answers all parts of query?
- Accuracy: Information correct and reliable?
- Depth: Appropriate detail level for complexity?
- Coherence: Well-structured and clear?

#### 4. Synthesizer

**Purpose**: Result synthesis and answer generation.

**Responsibilities**:
- Filter results by relevance
- Rank information by importance
- Combine multiple sources coherently
- Generate final comprehensive answer

#### 5. AdaptiveReasoningLoop

**Purpose**: Self-correcting agent loop with quality guarantees.

**Key Innovations**:
1. Automatically analyzes query complexity
2. ALWAYS evaluates responses (even "simple" queries)
3. Self-corrects: Auto-escalates if quality insufficient
4. Guarantees quality: No unvetted response reaches users
5. Buffers responses during evaluation

**Execution Flow**:
```
1. Analyze Complexity
   ↓
2. Select Strategy (DIRECT/LIGHT/DEEP)
   ↓
3. Execute with strategy → Buffer response
   ↓
4. Evaluate Quality
   ↓
5. Quality Check:
   - Sufficient? → Stream to user
   - Insufficient? → Escalate to next strategy, retry
```

**Execution Strategies**:

| Strategy | When Used | Typical Latency | Features |
|----------|-----------|-----------------|----------|
| **DIRECT** | Simple queries | 1-3s | Fast-path, minimal overhead, quality-checked |
| **LIGHT_PLANNING** | Medium complexity | 5-10s | 1-2 iterations, light planning, structured execution |
| **DEEP_REASONING** | Complex research | 15-30s | Full planning, multiple iterations, comprehensive synthesis |

**Self-Correction Example**:
```
Query: "Explain quantum computing"

Phase 0: Analysis
  → Complexity: SIMPLE (initial assessment)
  → Strategy: DIRECT

Phase 1: Execute (DIRECT)
  → Quick response via base AgentLoop
  → Response buffered (not shown to user)

Phase 2: Quality Check
  → Evaluator: "Response too superficial, lacks key concepts"
  → Confidence: 0.4 (below threshold)
  → Decision: Insufficient quality

Phase 3: Auto-Escalation
  → Discard buffered response
  → Escalate: DIRECT → LIGHT_PLANNING

Phase 1 (retry): Execute (LIGHT)
  → Generate 2 subtasks
  → Execute with light planning
  → Response buffered

Phase 2 (retry): Quality Check
  → Evaluator: "Now comprehensive and accurate"
  → Confidence: 0.85 (passes threshold)
  → Decision: Quality approved

Final: Stream to User
  → Quality-approved response delivered
  → Response added to conversation history
```

**Message Management**:
- User query added to conversation once at start
- Execution attempts buffered (NOT added during attempts)
- Only final quality-approved response added to conversation
- Failed attempts logged but not persisted

**Configuration** (`ReasoningConfig`):
- Complexity thresholds (for initial routing)
- Quality thresholds (for self-correction):
  - `min_quality_direct`: 0.6 (DIRECT responses)
  - `min_quality_light`: 0.7 (LIGHT responses)
  - `min_quality_deep`: 0.5 (DEEP final attempt)
- Model selection per component (can use cheaper models for analysis)
- Max iterations, caching settings, prompt paths

### TUI Integration

**ReasoningTracePanel** (`widgets/reasoning_trace_panel.py`):
- Collapsible panel displaying detailed reasoning process
- Shows: complexity analysis, strategy selection, planning, quality checks, escalations
- Keyboard shortcut: `Ctrl+R` to toggle visibility
- Auto-scrolling with rich formatting

**Callback Interface**:
The reasoning system provides comprehensive callbacks for UI integration:
- `on_analysis_start` / `on_analysis_complete` - Complexity analysis phase
- `on_strategy_selected` - Strategy selection
- `on_planning_start` / `on_planning_complete` - Planning phase
- `on_quality_check_start` / `on_quality_check_complete` - Quality evaluation
- `on_auto_escalation` - Strategy escalation event
- `on_final_response` - Final quality-approved response

**Callback Routing** (in `NexusApp`):
- **StatusPanel**: High-level summaries only (mode changes, completion)
- **ReasoningTracePanel**: Detailed reasoning trace (all phases, tools, evaluations)
- **ChatPanel**: Final streaming response (unchanged)

### Benefits

**Quality Guarantees**:
- No response sent without passing evaluation
- Automatic escalation ensures quality over speed
- Self-correcting system that learns from initial attempts

**Adaptive Intelligence**:
- Fast when possible (simple queries use DIRECT)
- Thorough when needed (complex queries get full reasoning)
- No manual configuration required

**Cost Optimization**:
- Fast-path for simple queries minimizes cost
- Quality thresholds prevent over-processing
- Can use cheaper models for analysis (Haiku vs Sonnet)

**User Experience**:
- Transparent reasoning process (optional trace panel)
- Consistent quality across query types
- Real-time feedback on reasoning mode

---

## Enhanced Agentic Loop Architecture

The agentic loop architecture provides conversation management, session persistence, and the reasoning system foundation. This architecture replaced the legacy fake-chunking approach with proper streaming and 90% cost reduction through prompt caching.

### Architecture Overview

```
SessionManager (manages sessions)
    ↓
Session (encapsulates conversation + metadata)
    ↓
CommandControlAgent (command/resource processing)
    ↓
AdaptiveReasoningLoop (self-correcting reasoning)
    ↓
AgentLoop (base orchestration)
    ↓
Conversation (message state) + ToolRegistry (uniform tool interface)
    ↓
Claude (streaming + caching)
```

### Core Components

#### 1. Conversation (`application/conversation.py`)

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
- `add_user_message(content)` - Add user message to history
- `add_assistant_message(message)` - Add Claude's response
- `add_tool_results(tool_blocks, results)` - Add tool execution results
- `get_messages_for_api()` - Get messages with cache control applied
- `get_system_message_for_api()` - Get system message with cache control

#### 2. ToolRegistry & ToolProvider (`application/tool_registry.py`)

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

**Extensibility**: Easy to add new tool sources beyond MCP (text editors, web search, custom business logic, database queries, etc.)

#### 3. MCPToolProvider (`application/mcp_tool_provider.py`)

Bridges existing MCP infrastructure with new ToolRegistry:
- Wraps multiple `MCPClient` instances
- Aggregates tools from all MCP servers
- Routes execution to correct MCP client
- Handles MCP-specific types (`Tool`, `CallToolResult`, `TextContent`)
- JSON formatting of results

#### 4. Enhanced Claude Wrapper (`application/claude.py`)

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

#### 5. AgentLoop (`application/agentic_loop.py`)

Clean orchestration with separated concerns (base class for AdaptiveReasoningLoop):
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
- `run(query, callbacks, use_streaming)` - Execute query
- `_run_with_streaming()` - Real streaming path with proper event type checking
- `_run_without_streaming()` - Legacy compatibility path
- `_execute_tools()` - Tool execution with error handling

**Streaming Implementation**: Properly handles Anthropic SDK's typed event objects (`ContentBlockDeltaEvent`) rather than treating them as dictionaries, and only includes API parameters when they have values to avoid validation errors.

#### 6. Session (`application/session.py`)

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

#### 7. SessionManager (`application/session_manager.py`)

Manages session lifecycle with persistence:
- **Multi-Session Architecture**: Internally uses `Dict[session_id, Session]` for multiple sessions
- **Current Mode**: Single session (default session) for TUI simplicity
- **Future Ready**: Multi-session UI scaffolding in place
- **Auto-save Strategy**:
  - Auto-save on session switch
  - Auto-save on application exit
  - Manual save available via `save_active_session()`
- **Storage**: JSON files in `~/.nxs/sessions/` (one file per session: `{session_id}.json`)

**Key Methods** (Current - Single Session):
- `get_or_create_default_session()` - Get or restore default session
- `save_active_session()` - Persist to disk
- `get_active_session()` - Get current session
- `clear_active_session_history()` - Clear conversation
- `get_session_info()` - Get session metadata

**Multi-Session Methods** (Implemented, Future TUI Integration):
- `create_session(id, title)` - Create new session
- `switch_session(id)` - Switch active session (auto-saves current)
- `delete_session(id)` - Delete session (memory + disk)
- `list_sessions()` - List all sessions with metadata
- `save_all_sessions()` - Persist all sessions

**AgentProtocol**: Defines common interface for agent types, allowing `SessionManager` to work with both `AgentLoop` and `CommandControlAgent` (which uses composition).

### Implementation Status

**Completed**:
- ✅ Conversation class with prompt caching
- ✅ ToolRegistry with ToolProvider protocol
- ✅ MCPToolProvider for MCP integration
- ✅ Enhanced Claude wrapper with real streaming
- ✅ Refactored AgentLoop with proper event handling
- ✅ Session and SessionManager with persistence
- ✅ Multi-session support (Dict-based architecture)
- ✅ Single-session mode for TUI (default session)
- ✅ Session auto-save on switch and exit
- ✅ Session auto-restore on startup
- ✅ Adaptive reasoning system (QueryComplexityAnalyzer, Planner, Evaluator, Synthesizer)
- ✅ AdaptiveReasoningLoop with self-correction
- ✅ CommandControlAgent using composition with AdaptiveReasoningLoop
- ✅ ReasoningTracePanel for TUI reasoning display
- ✅ Comprehensive callback interface for reasoning events
- ✅ 65+ unit tests (conversation, session, session_manager)
- ✅ Integration tests for adaptive reasoning
- ✅ Performance benchmarks for reasoning strategies

**Current Integration**:
The system operates in **single-session mode** with full persistence. Multi-session architecture is implemented (Dict[session_id, Session]) but TUI displays one active session. The `CommandControlAgent` uses composition with `AdaptiveReasoningLoop` for all query execution, providing adaptive reasoning with quality guarantees.

**Future Enhancements** (Multi-Session UI):
- Session tabs/selector widget
- Session switching keyboard shortcuts (Ctrl+T, Ctrl+Tab, Ctrl+W)
- Session rename/labeling UI
- Visual indicator of active session
- Session list overlay (like Ctrl+Tab in VS Code)

### Benefits of Architecture

**1. Separation of Concerns**:
- State management (Conversation) separate from orchestration (AgentLoop)
- Reasoning logic (AdaptiveReasoningLoop) separate from preprocessing (CommandControlAgent)
- Tool discovery/execution abstracted (ToolRegistry)
- Session metadata separate from conversation history

**2. Extensibility**:
- Add new tool sources via ToolProvider protocol
- Support multiple tool types (MCP, custom, built-in)
- Easy to add new session features (tags, search, export)
- Pluggable reasoning strategies

**3. Cost Optimization**:
- 90% savings via prompt caching
- Cache system messages (stable)
- Cache tools (stable)
- Cache last user message (enables retries)
- Fast-path for simple queries minimizes LLM calls

**4. Quality Guarantees**:
- Self-correcting reasoning system
- Automatic escalation for quality
- No unvetted responses reach users

**5. Real Streaming**:
- Anthropic SDK's async streaming (not fake chunking)
- Lower latency, better UX
- Proper error handling

**6. Persistence Ready**:
- Sessions serialize to JSON
- Restore conversations across restarts
- Metadata tracking (created, last active, etc.)
- Human-readable, git-friendly format

**7. Testability**:
- Clean interfaces enable unit testing
- Mocked dependencies via protocols
- 65+ comprehensive tests (all passing)

**8. Battle-Tested Architecture**:
- Single session now, multi-session ready
- Scaffolding in place for future features
- Clear migration path

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

**6. Why composition over inheritance for CommandControlAgent?**
- Simpler architecture (one execution path)
- Clearer separation of concerns (preprocessing vs execution)
- All queries benefit from adaptive reasoning
- Easier to test and maintain

**7. Why self-correcting reasoning?**
- Quality guarantee for users
- Automatic adaptation to query complexity
- No manual configuration required
- Fast when possible, thorough when needed

---

## Runtime Flow

### Startup

1. `python -m nxs` (Pixi task `start`) loads environment variables and configures logging.
2. `SessionManager` initializes with agent factory (creates `CommandControlAgent` with `AdaptiveReasoningLoop`).
3. `SessionManager` restores default session from `~/.nxs/sessions/default.json` or creates new.
4. `ArtifactManager` builds MCP clients via `ConnectionManager` and initiates asynchronous connections.
5. `NexusApp` mounts the TUI, `ServiceContainer` starts background services (`QueryQueue`, `StatusQueue`) with lazy initialization.
6. MCP initialization scheduled in background, autocomplete preloaded.

### Query Processing

1. User submits text through `NexusInput`; `QueryQueue` ensures sequential FIFO processing.
2. `QueryHandler` processes the query through `CommandControlAgent`.
3. `CommandControlAgent` preprocessing:
   - If query starts with `/`, process as command (execute MCP prompt)
   - If contains `@mentions`, extract referenced resources
4. `CommandControlAgent` delegates to `AdaptiveReasoningLoop.run()`:
   - **Phase 0: Complexity Analysis** - Analyze query, recommend strategy
   - **Phase 1: Strategy Execution** - Execute with selected strategy (DIRECT/LIGHT/DEEP)
   - **Phase 2: Quality Evaluation** - Evaluate response quality
   - **Phase 3: Self-Correction** - If quality insufficient, escalate and retry
5. `AdaptiveReasoningLoop` delegates to base `AgentLoop` for execution:
   - Adds user message to `Conversation`
   - Retrieves messages with cache control
   - Gets tools from `ToolRegistry`
   - Streams Claude API call
6. If Claude requests tool execution:
   - `ToolRegistry` routes tool calls to appropriate `ToolProvider`
   - `MCPToolProvider` executes via correct MCP client
   - Results added to conversation
   - Loop continues
7. Final text responses:
   - Quality-approved response streams chunk-by-chunk to chat panel via callbacks
   - Status updates appear in status panel via `StatusQueue`
   - Reasoning trace updates appear in reasoning trace panel (if visible)
8. `SessionManager` auto-saves conversation state for persistence.

### Artifact & Connection Updates

- `ConnectionManager` publishes `ConnectionStatusChanged` and `ReconnectProgress` events as MCP clients connect or retry.
- `ArtifactManager` fetches resources/prompts/tools and publishes `ArtifactsFetched` when caches change.
- Presentation handlers update the MCP panel, autocomplete lists, and status messages in response to these events.

---

## Supporting Modules

- `src/nxs/main.py` - Boots the application: loads environment, creates `SessionManager` with `CommandControlAgent` factory, initializes `ArtifactManager`, and launches TUI with reasoning callbacks.
- `src/nxs/config/` - Contains MCP server configuration (`nxs_mcp_config.json`) consumed by `ConnectionManager`.
- `src/nxs/prompts/` - Stores Claude prompt templates used by the agent and reasoning system.
- `src/nxs/prompts/reasoning/` - Specialized prompts for reasoning components (complexity analysis, quality check, planning, evaluation, synthesis, filtering).
- `src/nxs/logger.py` - Centralized Loguru configuration shared across modules.
- `src/nxs/utils.py` - Utility helpers (formatting, time utilities, etc.).

---

## Event-Driven Coordination

- The **EventBus** (`domain/events/bus.py`) decouples background services from UI widgets using a synchronous fire-and-forget pattern.
- Event handlers are synchronous but schedule async work via `asyncio.create_task()`, allowing non-blocking event propagation.
- Handlers in `presentation/handlers/` subscribe to events and delegate work to services in `presentation/services/` to update widgets.
- This keeps event handling declarative and makes it easy to plug in new listeners or services without touching the data producers.

---

## Naming Conventions

To maintain consistency and clarity across the codebase, the following naming conventions are established:

### Class Suffixes and Their Meanings

**Manager**
- **Purpose**: Owns lifecycle and state of specific resources
- **Scope**: Resource creation, destruction, tracking, and state queries
- **Examples**:
  - `MCPConnectionManager`: Manages ALL MCP server connections (aggregate)
  - `SessionManager`: Manages conversation sessions
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

**Loop**
- **Purpose**: Iterative execution patterns, typically conversational loops
- **Scope**: Coordinate iterative interactions with Claude or reasoning phases
- **Examples**:
  - `AgentLoop`: Base conversational loop with tool execution
  - `AdaptiveReasoningLoop`: Self-correcting reasoning loop with quality checks
- **When to use**: For iterative execution patterns that require multiple rounds of interaction

### Connection Management Naming

The codebase uses two distinct connection managers with clear scopes:

- **`MCPConnectionManager`** (application layer): Manages ALL MCP server connections (aggregate/global scope)
- **`SingleConnectionManager`** (infrastructure layer): Manages a SINGLE connection's lifecycle (per-client scope)

This naming makes the scope distinction immediately clear without reading implementation details.

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

---

## Recent Architectural Improvements

### Service Consolidation (2025-11-09)

**Problem**: `StatusQueue` and `QueryQueue` (formerly `QueryManager`) were nearly identical implementations of the same async queue pattern, resulting in ~200 lines of code duplication.

**Solution**: Created `AsyncQueueProcessor<T>` - a generic, reusable async FIFO queue processor that both services now wrap.

**Benefits**:
- ✅ **Eliminated ~200 lines of duplication** between StatusQueue and QueryQueue
- ✅ **Established reusable pattern** for future queue-based services
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

### Composition Over Inheritance (Reasoning System)

**Design Decision**: `CommandControlAgent` uses composition with `AdaptiveReasoningLoop` instead of inheriting from `AgentLoop`.

**Rationale**:
- Clearer separation of concerns (preprocessing vs execution)
- Single execution path (all queries use adaptive reasoning)
- Simpler architecture (no dual paths or fallback modes)
- Easier to test and maintain

**Benefits**:
- ✅ All queries benefit from self-correction
- ✅ No manual configuration for reasoning modes
- ✅ Clean architecture without inheritance complexity

---

## Extensibility Points

- **MCP integrations**: Add or modify server entries in `src/nxs/config/nxs_mcp_config.json`. New server types can be supported by extending `ClientFactory`.
- **Artifacts & prompts**: Extend repository logic inside `application/artifacts/` or add prompt templates in `src/nxs/prompts/`.
- **TUI behaviour**: Create new widgets under `presentation/widgets/`, register handlers/services, and subscribe to events.
- **Caching strategies**: Provide alternate cache implementations by fulfilling the `Cache` protocol (`domain/protocols/cache.py`).
- **Reasoning strategies**: Add new complexity analysis logic or execution strategies in `application/reasoning/`.
- **Tool providers**: Implement new `ToolProvider` for custom tool sources (web search, databases, APIs, etc.).
- **Testing**: Use the `tests/` suite as examples for mocking protocols and verifying handlers/services in isolation.

---

## Interaction with External Services

- **Claude communication** is abstracted behind `application/claude.py`, providing real streaming via async generators, prompt caching for 90% cost reduction, and support for extended thinking mode.
- **MCP clients** rely on `nxs.infrastructure.mcp.client.MCPAuthClient` for authenticated HTTP transport, automatic reconnects, and tool execution.
- **Logging** is centralized via `nxs.logger.get_logger`, ensuring consistent, colorized output across layers and simplifying traceability during debugging.
- **Session persistence** uses JSON files in `~/.nxs/sessions/` for human-readable, git-friendly conversation history with per-session files (`{session_id}.json`).
- **Reasoning prompts** are loaded from `src/nxs/prompts/reasoning/` for complexity analysis, quality evaluation, planning, and synthesis.

---

## Testing Coverage

### Unit Tests (65+ tests, all passing)

**Conversation** (`tests/test_conversation.py`):
- 29 tests covering message management, caching, persistence

**Session** (`tests/test_session.py`):
- 18 tests covering session lifecycle, serialization, metadata

**SessionManager** (`tests/test_session_manager.py`):
- 18 tests covering session management, persistence, restoration

**Reasoning Components** (`tests/reasoning/`):
- `test_analyzer.py` - QueryComplexityAnalyzer tests (simple, medium, complex queries)
- `test_planner.py` - Planner tests (light and deep modes)
- `test_evaluator.py` - Evaluator tests (both research and quality evaluation)
- `test_synthesizer.py` - Synthesizer tests (filtering and synthesis)
- `test_reasoning_loop.py` - AdaptiveReasoningLoop tests (strategies, escalation, quality checks)

**Integration Tests** (`tests/integration/`):
- `test_adaptive_reasoning_integration.py` - Full system stack testing
- CommandControlAgent with reasoning
- Resource extraction with reasoning
- Callback routing and TUI integration

**Performance Tests** (`tests/performance/`):
- `test_reasoning_benchmarks.py` - Latency measurements, escalation overhead
- Strategy distribution analysis
- Comparative latency across strategies

**Test Coverage Areas**:
- Message addition (user, assistant, tool results)
- Cache control application
- Conversation persistence (to_dict/from_dict)
- Session metadata management
- SessionManager lifecycle
- Session save/restore
- Complexity analysis accuracy
- Execution strategy selection
- Quality evaluation and escalation
- Self-correction mechanisms
- Error handling (corrupt files, missing data, LLM failures)

---

## File Locations

### Core Application Files

**Session Management**:
- `src/nxs/application/conversation.py` - Conversation class with caching
- `src/nxs/application/session.py` - Session + SessionMetadata
- `src/nxs/application/session_manager.py` - SessionManager with multi-session support
- `src/nxs/application/agentic_loop.py` - Base AgentLoop orchestration
- `src/nxs/application/claude.py` - Enhanced Claude wrapper

**Reasoning System**:
- `src/nxs/application/reasoning_loop.py` - AdaptiveReasoningLoop
- `src/nxs/application/reasoning/analyzer.py` - QueryComplexityAnalyzer
- `src/nxs/application/reasoning/planner.py` - Planner
- `src/nxs/application/reasoning/evaluator.py` - Evaluator
- `src/nxs/application/reasoning/synthesizer.py` - Synthesizer
- `src/nxs/application/reasoning/config.py` - ReasoningConfig
- `src/nxs/application/reasoning/types.py` - Shared types
- `src/nxs/application/reasoning/utils.py` - Utility functions
- `src/nxs/application/reasoning/metrics.py` - Metrics collection
- `src/nxs/application/reasoning/tuning.py` - Threshold tuning utilities

**Agent & Tools**:
- `src/nxs/application/command_control.py` - CommandControlAgent (composition)
- `src/nxs/application/tool_registry.py` - ToolRegistry + ToolProvider
- `src/nxs/application/mcp_tool_provider.py` - MCP bridge
- `src/nxs/application/artifact_manager.py` - ArtifactManager

### Presentation Layer

**Widgets**:
- `src/nxs/presentation/widgets/reasoning_trace_panel.py` - ReasoningTracePanel
- `src/nxs/presentation/widgets/chat_panel.py` - ChatPanel
- `src/nxs/presentation/widgets/status_panel.py` - StatusPanel
- `src/nxs/presentation/widgets/mcp_panel.py` - MCPPanel
- `src/nxs/presentation/widgets/input_field.py` - NexusInput
- `src/nxs/presentation/widgets/autocomplete.py` - NexusAutoComplete

**TUI & Services**:
- `src/nxs/presentation/tui/nexus_app.py` - Main NexusApp with reasoning callbacks
- `src/nxs/presentation/services/container.py` - ServiceContainer
- `src/nxs/presentation/handlers/query_handler.py` - QueryHandler

### Prompts

**Reasoning Prompts**:
- `src/nxs/prompts/reasoning/complexity_analysis.txt` - Query complexity analysis
- `src/nxs/prompts/reasoning/quality_check.txt` - Response quality evaluation
- `src/nxs/prompts/reasoning/planning.txt` - Task decomposition
- `src/nxs/prompts/reasoning/evaluation.txt` - Research completeness
- `src/nxs/prompts/reasoning/synthesis.txt` - Result synthesis
- `src/nxs/prompts/reasoning/filter.txt` - Result filtering

### Tests

**Unit Tests**:
- `tests/test_conversation.py` - Conversation tests
- `tests/test_session.py` - Session tests
- `tests/test_session_manager.py` - SessionManager tests
- `tests/reasoning/test_analyzer.py` - Analyzer tests
- `tests/reasoning/test_planner.py` - Planner tests
- `tests/reasoning/test_evaluator.py` - Evaluator tests
- `tests/reasoning/test_synthesizer.py` - Synthesizer tests
- `tests/reasoning/test_reasoning_loop.py` - AdaptiveReasoningLoop tests

**Integration & Performance**:
- `tests/integration/test_adaptive_reasoning_integration.py` - Full stack tests
- `tests/performance/test_reasoning_benchmarks.py` - Performance benchmarks

### Documentation

- `ARCHITECTURE.md` - This document (comprehensive architecture overview)
- `docs/REASONING_SYSTEM.md` - Detailed reasoning system documentation

---

This architecture enables the TUI to stay responsive while background tasks connect to remote services, fetch artifacts, execute tools, and perform adaptive reasoning with quality guarantees—all without hard-coupling UI components to networking, storage, or reasoning concerns. The layered design with protocols, events, and composition allows developers to extend or replace each layer independently while maintaining a self-correcting system that automatically adapts to query complexity and guarantees response quality.
