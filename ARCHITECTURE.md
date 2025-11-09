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
- `ConnectionManager` translates MCP server configuration into live `MCPClient` instances, tracks lifecycle, and emits connection events.
- `ArtifactManager` composes repository, cache, and change-detection services to fetch MCP resources/prompts/tools and publishes `ArtifactsFetched` events.
- `command_control.py` wraps the agent loop with command parsing and context enrichment.
- Subpackages like `artifacts/`, `parsers/`, and `suggestions/` encapsulate reusable behaviours for formatting completions and validating user input.

### Infrastructure Layer — `src/nxs/infrastructure`
- Supplies concrete implementations for the domain protocols.
- `mcp/` wraps the `MCPAuthClient`, connection management, reconnection policy, storage, and CLI helpers.
- `cache/` includes baseline cache backends (in-memory, TTL) used by application services and the presentation layer.
- Acts as the integration point for remote MCP servers (currently remote HTTP endpoints via `ClientFactory` and `MCPAuthClient`).

### Presentation Layer — `src/nxs/presentation`
- Implements the **Textual-based TUI** (`tui/nexus_app.py`) and all widgets, styles, and interaction logic.
- `services/` encapsulate long-lived stateful workflows (autocomplete, MCP coordination, background tasks).
- `handlers/` subscribe to the domain `EventBus` and translate events into UI updates.
- `widgets/` render chat, MCP server status, autocomplete overlays, and status panels with Rich formatting.
- The presentation layer consumes only application-layer facades and domain events, remaining free of networking or storage concerns.

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
3. `NexusApp` mounts the TUI, starts background services (`QueryManager`, `StatusQueue`, autocomplete service), and schedules MCP initialization in the background.

### Query Processing
1. The user submits text through `NexusInput`; the `QueryManager` ensures sequential processing.
2. The application layer queues the query to `AgentLoop`.
3. `AgentLoop` appends the message history, calls Claude with available tools (fetched through `ToolManager`/`ArtifactManager`), and streams output via callbacks consumed by TUI services.
4. If Claude requests tool execution, `ToolManager` marshals tool calls back to the appropriate `MCPClient` and injects the results before continuing the conversation loop.
5. Final responses are streamed back to the chat panel; status updates appear in the status panel using the event bus.

### Artifact & Connection Updates
- `ConnectionManager` publishes `ConnectionStatusChanged` and `ReconnectProgress` events as MCP clients connect or retry.
- `ArtifactManager` fetches resources/prompts/tools and publishes `ArtifactsFetched` when caches change.
- Presentation handlers update the MCP panel, autocomplete lists, and status messages in response to these events.

## Event-Driven Coordination
- The **EventBus** (`domain/events/bus.py`) decouples background services from UI widgets.
- Handlers in `presentation/handlers/` subscribe to events and collaborate with services in `presentation/services/` to update widgets.
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

