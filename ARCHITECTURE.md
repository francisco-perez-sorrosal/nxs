# Nexus (NXS) Architecture

## Introduction

**Nexus** is a full-screen terminal user interface (TUI) for conversational AI that integrates Claude with extensible tool support via the Model Context Protocol (MCP). Built with **Textual** and **Rich**, NXS provides a responsive chat interface with real-time streaming, adaptive reasoning, and comprehensive session management.

### Key Capabilities

- **Adaptive Reasoning**: Self-correcting agent that automatically analyzes query complexity and adapts execution strategy (DIRECT → LIGHT → DEEP) with quality guarantees
- **Progress Tracking**: Intelligent context preservation across reasoning escalations, eliminating redundant work through tool result caching (30-50% API call reduction)
- **Session Management**: Multi-session support with automatic persistence, conversation summaries, and cost tracking
- **MCP Integration**: Full Model Context Protocol support with multiple server connections, automatic reconnection, and health monitoring
- **Tool Ecosystem**: Pluggable tool architecture supporting MCP servers, local Python functions, and custom providers
- **Human-in-the-Loop**: Optional approval workflows for query analysis and tool execution
- **Cost Tracking**: Comprehensive token and cost tracking across conversation, reasoning, and summarization phases

### Architecture Philosophy

NXS follows **Clean Architecture** principles with four distinct layers and strict dependency rules:

1. **Domain Layer**: Pure business logic with zero external dependencies (all other layers depend on it)
2. **Infrastructure Layer**: External integration implementations (MCP clients, caching, storage)
3. **Application Layer**: Core orchestration and business workflows (sessions, agents, reasoning)
4. **Presentation Layer**: User interface with Textual/Rich (no business logic)

**Key Principles**:
- **Dependency Inversion**: High-level policies don't depend on low-level details; both depend on abstractions (protocols)
- **Event-Driven Communication**: Decoupled components communicate via domain events (EventBus)
- **Composition over Inheritance**: Complex behaviors built through composition (e.g., CommandControlAgent composes AdaptiveReasoningLoop)
- **Protocol-Based Design**: Interfaces defined as Python protocols for flexibility and testability

---

## Layered Architecture

### Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                        │
│  (TUI with Textual + Rich: NexusApp, Widgets, Services)     │
└────────────────────────┬────────────────────────────────────┘
                         │ depends on
┌────────────────────────▼────────────────────────────────────┐
│                    Application Layer                         │
│   (Sessions, Agents, Reasoning, Tools, Cost Tracking)        │
└────────────────────────┬────────────────────────────────────┘
                         │ depends on
┌────────────────────────▼────────────────────────────────────┐
│                  Infrastructure Layer                        │
│        (MCP Clients, Cache Implementations, Storage)         │
└────────────────────────┬────────────────────────────────────┘
                         │ depends on
┌────────────────────────▼────────────────────────────────────┐
│                      Domain Layer                            │
│      (Protocols, Events, Types, Business Rules)              │
│              (NO external dependencies)                      │
└─────────────────────────────────────────────────────────────┘
```

### Domain Layer

**Location**: `src/nxs/domain/`

**Pure business logic with zero external dependencies.** All other layers depend on domain; domain depends on nothing.

**Protocols** (`protocols/`): Define interfaces without implementation
- `Cache`: get, set, clear, has_changed
- `MCPClient`: list_tools, call_tool, list_resources, list_prompts
- `Parser`: parse arguments
- `ClientProvider`: factory for client creation

**Events** (`events/`): Domain events for decoupled communication
- `ConnectionStatusChanged`: MCP server connection status updates
- `ReconnectProgress`: Reconnection attempt progress
- `ArtifactsFetched`: Tools/resources/prompts discovered
- `EventBus`: Pub/sub mechanism for event distribution

**Types** (`types/`): Value objects and enums
- `ConnectionStatus`: DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING, ERROR
- `ComplexityLevel`: SIMPLE, MEDIUM, COMPLEX
- `ExecutionStrategy`: DIRECT, LIGHT_PLANNING, DEEP_REASONING

**Models** (`artifacts.py`): Domain entities
- `Tool`, `Resource`, `Prompt`: MCP artifact representations
- `ArtifactCollection`: Aggregates artifacts by type

### Infrastructure Layer

**Location**: `src/nxs/infrastructure/`

**External integration implementations.** Provides concrete implementations of domain protocols.

**MCP Client** (`mcp/client.py`): `MCPAuthClient`
- Async MCP protocol client supporting stdio and HTTP transports
- OAuth authentication for remote servers
- Automatic reconnection with exponential backoff
- State persistence for long-running sessions

**Connection Management** (`mcp/connection/`):
- `ConnectionManager`: Orchestrates multiple MCP server connections
- `LifecycleManager`: Handles initialization and reconnection logic
- `HealthChecker`: Monitors connection health with periodic pings
- `ReconnectionStrategy`: Exponential backoff with configurable limits

**Cache** (`cache/`):
- `MemoryCache`: In-memory TTL-based cache implementation
- `BaseTTLCache`: Abstract base for cache implementations

### Application Layer

**Location**: `src/nxs/application/`

**Core orchestration and business workflows.** This is the heart of NXS, containing all business logic organized into several key subsystems.

#### Session & Conversation Management

**Conversation** (`conversation.py`):
- Manages message history (user, assistant, tool use/result messages)
- Implements Anthropic prompt caching for 90% cost reduction on repeated context
- Applies cache control directives to appropriate message boundaries
- Serializes/deserializes conversation state for persistence

**Session** (`session.py`):
- Encapsulates: `Conversation` + `AgentLoop` + `SessionMetadata`
- Provides `run_query()` method delegating to agent loop
- Maintains three separate cost trackers:
  - `conversation_cost_tracker`: Main conversation costs
  - `reasoning_cost_tracker`: Reasoning/planning/evaluation costs
  - `summarization_cost_tracker`: Summary generation costs
- Stores `ResearchProgressTracker` instances by query ID for debugging

**SessionManager** (`session_manager.py`):
- Multi-session management with `Dict[session_id, Session]`
- Default session: "default" (auto-created if none exist)
- Auto-save on session switch and application exit
- Auto-restore on startup
- Per-session JSON files: `~/.nxs/sessions/{session_id}.json`
- Legacy migration: `session.json` → `default.json`
- Tracker cleanup: Removes trackers older than 1 hour from sessions before save

#### Agent Orchestration

**AgentLoop** (`agentic_loop.py`): Base agent orchestration
- Core agent loop: query → Claude API → tool execution → loop until text response
- Streams responses chunk-by-chunk via callbacks
- Manages conversation state (adds user query, tool results, assistant response)
- Implements prompt caching for cost efficiency
- Delegates tool discovery to `ToolRegistry`
- Delegates tool execution to `ToolManager`
- Intercepts tool execution for progress tracking integration
- Provides callback hooks: `on_chunk`, `on_tool_start`, `on_tool_complete`

**CommandControlAgent** (`command_control.py`): Command-aware agent
- **Composition Pattern**: Wraps `AdaptiveReasoningLoop` (not inheritance)
- Preprocessing layer for special syntax:
  - `/command`: Execute MCP prompt with given name
  - `@resource`: Reference MCP resources in query
- Delegates actual execution to wrapped `AdaptiveReasoningLoop`
- Extracts referenced resources and builds enhanced context

#### Adaptive Reasoning System

The reasoning system provides **self-correcting adaptive execution** with quality guarantees.

**AdaptiveReasoningLoop** (`reasoning_loop.py`): Self-correcting agent
- Extends `AgentLoop` with complexity analysis and quality evaluation
- **Automatic Complexity Analysis**: Classifies queries (SIMPLE/MEDIUM/COMPLEX)
- **Strategy Routing**: Selects execution strategy based on complexity
- **Quality Evaluation**: ALWAYS evaluates response quality
- **Automatic Escalation**: If quality insufficient, escalates to next strategy
- **Quality Guarantee**: No response sent without passing evaluation
- **Progress Preservation**: Uses `ResearchProgressTracker` to preserve context across escalations

**Execution Flow**:
```
Query Input
  ↓
Complexity Analysis
  ├─ SIMPLE    → DIRECT execution
  ├─ MEDIUM    → LIGHT_PLANNING
  └─ COMPLEX   → DEEP_REASONING
  ↓
Strategy Execution (with progress tracker)
  ↓
Quality Evaluation
  ├─ Pass (≥0.6 score) → Return response
  └─ Fail (<0.6 score) → Escalate to next strategy
  ↓
Final Response (quality-approved)
```

**Reasoning Components** (`reasoning/`):

**QueryComplexityAnalyzer** (`analyzer.py`):
- Analyzes query to determine complexity level
- Considers: question type, domain specificity, tool requirements, multi-part queries
- Recommends execution strategy
- Uses fast model (Haiku) to minimize analysis cost
- Returns `ComplexityAnalysis` with confidence score and rationale

**Planner** (`planner.py`):
- Decomposes complex queries into structured subtask plans
- Creates `ResearchPlan` with ordered `SubTask` list
- Identifies dependencies between subtasks
- Supports plan refinement based on execution feedback

**Evaluator** (`evaluator.py`):
- Assesses response quality and completeness
- Returns `EvaluationResult` with quality score (0.0 to 1.0)
- Identifies missing aspects and suggests improvements
- Enables self-correction through automatic escalation

**Synthesizer** (`synthesizer.py`):
- Combines multiple partial results into coherent response
- Filters redundant information
- Ranks findings by relevance
- Resolves conflicts between sources

**Execution Strategies** (`strategies/`):

- **DirectExecutionStrategy**: Fast-path with minimal overhead
- **LightPlanningStrategy**: Quick planning with 1-2 iterations
- **DeepReasoningStrategy**: Full reasoning with multiple iterations

#### Progress Tracking

**ResearchProgressTracker** (`progress_tracker.py`):
- **Purpose**: Preserves execution context across strategy escalations to eliminate redundant work
- **Integration**: Created at query start, passed through all strategies

**Core Responsibilities**:
1. **Execution Tracking**: Records each strategy attempt with quality scores
2. **Tool Execution Logging**: Tracks all tool calls with result caching
3. **Plan Management**: Maintains research plan skeleton with step progress
4. **Insight Accumulation**: Aggregates knowledge gaps, quality feedback, confirmed facts
5. **Context Serialization**: Generates natural language context for LLM consumption

**Tool Caching Policy**:
- Time-sensitive tools (date/time): Always execute fresh
- Stable tools (web_search): Cache results
- Non-deterministic tools (random): Always execute fresh

**Context Verbosity Levels**:
- **MINIMAL**: First attempt (~100 tokens)
- **COMPACT**: DIRECT escalation (~500 tokens)
- **MEDIUM**: LIGHT_PLANNING (~2000 tokens)
- **FULL**: DEEP_REASONING (~10000 tokens)

**Benefits**:
- 30-50% reduction in API calls through intelligent caching
- Progressive refinement across escalations
- Detailed debugging support

#### Tool Management

**ToolRegistry** (`tool_registry.py`):
- Pluggable architecture supporting multiple tool sources
- Discovery: `get_tool_names()`, `get_tool(name)`
- Integration: Used by `AgentLoop` for tool discovery

**ToolProvider Protocol**:
- `get_tools() → List[Tool]`: Discover available tools
- `call_tool(name, arguments) → str`: Execute tool and return result

**MCPToolProvider** (`mcp_tool_provider.py`):
- Integrates MCP server tools into ToolRegistry
- Routes tool execution to correct MCP client
- Handles errors gracefully

**LocalToolProvider** (`local_tool_provider.py`):
- Wraps Python functions as tools
- Auto-generates JSON schemas from function signatures
- Built-in tools: date/time, location, weather

**ToolManager** (`tools.py`):
- Aggregates tools from all providers
- Routes tool execution to appropriate provider
- Executes tools in parallel when possible

#### Cost Tracking

**CostTracker** (`cost_tracker.py`):
- Accumulates token usage and costs per conversation round
- Tracks: input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens
- Calculates total cost based on model pricing

**Three-Tracker Architecture**:
Each session maintains three separate cost trackers:
1. **conversation_cost_tracker**: Main conversation API calls
2. **reasoning_cost_tracker**: Complexity analysis, planning, evaluation, synthesis
3. **summarization_cost_tracker**: Conversation summary generation

**Display**: Chat panel shows all three costs:
```
Chat - Session: default | Conv: $0.45 | Reasoning: $0.12 | Summary: $0.03
```

#### Human-in-the-Loop

**ApprovalManager** (`approval.py`):
- Coordinates approval requests and responses
- Two workflow types:
  - `QUERY_ANALYSIS`: Approve complexity analysis before execution
  - `TOOL_EXECUTION`: Approve tool calls before execution
- Blocking workflow ensures agent waits for decision

**TUI Integration**:
- `ApprovalOverlay` modal displays approval requests
- User can approve/reject with modifications

#### Conversation Summarization

**SummarizationService** (`summarization/service.py`):
- **Incremental Summarization**: Only summarizes new messages since last summary
- **Chunk-Based Processing**: Handles long conversations in manageable chunks
- **Corruption Detection**: Identifies and cleans up malformed summaries
- **Cost Integration**: Uses session's `summarization_cost_tracker`

#### MCP Integration

**ArtifactManager** (`artifact_manager.py`):
- **Facade Pattern**: Simplified interface for MCP artifact access
- Manages MCP server connections via `MCPConnectionManager`
- Provides unified artifact access: `get_all_tools()`, `get_all_resources()`, `get_all_prompts()`
- Event publishing: Fires `ArtifactsFetched` when artifacts change

**MCPConnectionManager** (`connection_manager.py`):
- Manages multiple MCP server connections
- Handles connection lifecycle (connect, disconnect, reconnect)
- Publishes connection events via EventBus
- Health monitoring with periodic checks

### Presentation Layer

**Location**: `src/nxs/presentation/`

**User interface with Textual & Rich.** No business logic.

**NexusApp** (`tui/nexus_app.py`): Main TUI application
- Textual-based full-screen chat interface
- Layout: Header + Horizontal (Main + Artifact Panel) + Footer
- Service initialization via `ServiceContainer`
- Event subscription to domain events

**Core Widgets**:

**ChatPanel** (`widgets/chat_panel.py`):
- `RichLog`-based scrollable chat display
- Rich markup, Markdown, Syntax highlighting
- Session name + cost display in border title
- Streaming support

**StatusPanel** (`widgets/status_panel.py`):
- Tool execution status display
- Structured data with Rich Tables and Panels
- Real-time updates via `StatusQueue`

**ReasoningTracePanel** (`widgets/reasoning_trace_panel.py`):
- Collapsible reasoning visualization (Ctrl+R)
- Shows complexity analysis, plan skeleton, insights
- Real-time updates during reasoning

**ArtifactPanel** (`widgets/artifact_panel.py`):
- MCP servers with connection status
- Tools/resources/prompts browser
- Click to view details in overlay

**NexusInput** (`widgets/input_field.py`):
- Text input with autocomplete
- `@` for resources, `/` for commands
- Submits to `QueryQueue` on Enter

**Services**:

**ServiceContainer** (`services/container.py`):
- Lazy initialization of all services
- Lifecycle management

**QueryQueue** (`tui/query_queue.py`):
- FIFO queue for sequential query processing
- Auto-generates query IDs

**StatusQueue** (`services/status_queue.py`):
- Buffers status updates from agent callbacks
- Feeds to `StatusPanel` in order

---

## Runtime Flows

### Application Startup

```
main.py
  ↓
1. Load environment (.env: API key, model)
2. Initialize domain (EventBus)
3. Initialize infrastructure (MCP client factory)
4. Initialize application layer
   - SessionManager (load/create default session)
   - ArtifactManager (MCP facade)
   - ToolRegistry + providers
   - Reasoning components
5. Create agent
   - AdaptiveReasoningLoop
   - CommandControlAgent (wraps loop)
6. Initialize presentation
   - NexusApp
   - ServiceContainer
   - Widgets
7. Start background tasks
   - MCP connections
   - Queue processing
8. Run TUI
9. On exit: save sessions, cleanup
```

### Query Processing

```
User Input → NexusInput
  ↓
QueryQueue.enqueue(query)
  ↓
QueryHandler.process(query)
  ↓
Session.run_query(query)
  ↓
CommandControlAgent (preprocessing)
  ├─ /command → Execute MCP prompt
  ├─ @resource → Extract resource content
  └─ else → Pass through
  ↓
AdaptiveReasoningLoop.run(query)
  ├─ Check reasoning enabled
  ├─ QueryComplexityAnalyzer.analyze()
  ├─ Initialize ResearchProgressTracker
  ├─ Attempt Loop (with escalation):
  │  ├─ tracker.start_attempt(strategy)
  │  ├─ Execute strategy
  │  ├─ During execution:
  │  │  ├─ tracker.should_execute_tool() checks cache
  │  │  ├─ If cached: Return result (skip API call)
  │  │  └─ If not: Execute tool
  │  ├─ Evaluator.evaluate(response)
  │  ├─ tracker.end_attempt(outcome, evaluation)
  │  ├─ If quality >= 0.6: Return
  │  └─ Else: Escalate with context
  ├─ Add response to conversation
  └─ Update cost trackers
  ↓
Callbacks fire:
  ├─ on_chunk → ChatPanel
  ├─ on_tool_start/complete → StatusPanel
  └─ reasoning events → ReasoningTracePanel
  ↓
Session auto-saved on exit
```

### Session Persistence

```
SessionManager manages: Dict[session_id, Session]

On session switch:
  1. Save current session to JSON
  2. Load new session from JSON
  3. Update active pointer

On startup:
  - Check ~/.nxs/sessions/
  - Load default.json or create new

On exit:
  - Save all sessions
  - Cleanup old trackers
```

---

## Future Enhancements

### Multi-Session UI

**Current**: Multi-session architecture implemented, TUI shows one session.

**Planned**:
- Session tabs/selector widget
- Session switching shortcuts (Ctrl+T, Ctrl+Tab)
- Session rename UI
- Session list overlay

### SessionState System

**Current**: Session stores only conversation messages.

**Planned** (see `SESSION_STATE_ARCHITECTURE.md`):
- **UserProfile** extraction: name, expertise, preferences
- **KnowledgeBase**: Persistent facts across queries
- **InteractionContext**: Conversation flow tracking
- **Cross-Query Learning**: Session-level memory
- **Semantic Search**: Retrieve relevant facts
- **Integration**: Combine with ResearchProgressTracker

**Benefits**:
- Persistent memory across session lifetime
- Smarter context selection
- Reduced token usage
- Personalized interactions

---

## Architecture Benefits

**Clean Separation**:
- Domain layer is pure, testable, reusable
- Infrastructure can be swapped
- Application logic independent of UI
- Presentation can be replaced

**Quality Guarantees**:
- No response without passing evaluation
- Automatic escalation ensures quality
- Self-correcting system

**Cost Efficiency**:
- Prompt caching: 90% cost reduction
- Tool caching: 30-50% API call reduction
- Fast-path for simple queries
- Cheaper models for analysis

**Extensibility**:
- Protocol-based design
- Event-driven architecture
- Pluggable tool providers
- Composition pattern

**User Experience**:
- Real-time streaming
- Transparent reasoning
- Consistent quality
- Multi-session support

---

This architecture enables NXS to deliver high-quality conversational AI with adaptive reasoning, comprehensive session management, and extensible tool integration—all while maintaining clean separation of concerns and testability.
