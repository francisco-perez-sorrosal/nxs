# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Nexus** (NXS) is a full-screen TUI chat application that integrates Claude AI with document retrieval and extensible tool support via the Model Context Protocol (MCP). The application provides a modern terminal interface built with **Textual** and **Rich**, featuring real-time streaming, command auto-completion, and resource management with beautiful formatting.

## Development Setup

The project uses **Pixi** for environment and dependency management (recommended), with fallback support for `uv` and pip.

**Quick Start:**
```bash
pixi install              # Install all environments
pixi run start           # Start the application
```

**For development:**
```bash
pixi install --environment dev    # Full dev environment with linting/type checking
pixi run --environment dev lint   # Check code quality
pixi run --environment dev ci     # Run full CI pipeline (format, lint, type-check, test)
```

## Environment Configuration

Create a `.env` file in the project root:
```
ANTHROPIC_API_KEY=""           # Required: Your Anthropic API key
CLAUDE_MODEL="claude-3-5-sonnet-20241022"  # Required: Model to use (or similar)
USE_UV=1                       # Set to 0 if using pixi instead
```

## Architecture

The application has five main layers with clean separation between UI and core logic:

### 1. MCP Configuration & Management (`core/mcp_config.py`, `core/artifact_manager.py`)

- **mcp_config.py**: Parses MCP server configurations from JSON files (e.g., `mcp_servers.json`)
  - `MCPServerConfig`: Pydantic model for individual server configuration (command, args)
  - `MCPServersConfig`: Container for all server configurations
  - Supports both local (stdio) and remote (HTTP) MCP servers
- **artifact_manager.py**: Central manager for all MCP artifacts and connections
  - Loads server configs and initializes MCP client connections asynchronously
  - Aggregates resources, prompts, and tools from all connected servers
  - Provides callbacks for connection status changes and reconnection progress
  - Manages lifecycle: `initialize()`, `cleanup()`, and automatic reconnection
  - Used by both TUI (for resources/prompts) and agent loop (for tools)

### 2. MCP Client Layer (`mcp_client/` package)

A full MCP client implementation with authentication and storage support:

- **client.py**: `MCPAuthClient` - Main async client with stdio/HTTP transports
  - Connection management with automatic reconnection and exponential backoff
  - Status tracking: CONNECTED, DISCONNECTED, CONNECTING, RECONNECTING, ERROR
  - Status change and reconnection progress callbacks
- **auth.py**: Authentication handler for remote MCP servers
- **storage.py**: Storage handler for MCP server state persistence
- **callback.py**: UI callback helpers for progress/completion tracking
- **cli/**: Typer-based interactive CLI (e.g., `python -m nxs.mcp_client`)

**Note**: `mcp_server.py` is an example MCP server implementation showing how to define resources, tools, and prompts.

### 3. Core Agent Loop (`core/` - UI-independent)

The agent loop implements the core Claude integration with **no UI dependencies**:

- **AgentLoop** (`core/agentic_loop.py`): Base class handling the chat/tool-use loop:
  1. Sends user query + tools to Claude
  2. If Claude calls tools, executes them via `ToolManager`
  3. Returns results to Claude
  4. Repeats until Claude returns final text response
  5. Supports callbacks for streaming chunks, tool calls, and completion

- **CommandControlAgent** (`core/command_control.py`): Extends AgentLoop with:
  - Receives `ArtifactManager` for accessing resources, prompts, and tools
  - Resource extraction from `@resource` mentions in queries
  - Command/prompt processing from `/command` prefixes
  - Document content fetching and context building via `ArtifactManager`
  - Tool discovery through `ArtifactManager.get_tools()`

### 4. TUI Layer (`tui/` - Textual + Rich)

The **NexusApp** class provides the full-screen terminal interface built with **Textual** (framework) and **Rich** (formatting):

**Architecture:**
```
tui/
├── app.py                    # Main NexusApp (Textual App)
├── styles.tcss               # Textual CSS styling
├── query_manager.py          # Async query processing manager
├── status_queue.py           # Async status update queue
└── widgets/
    ├── chat_panel.py         # RichLog-based chat display
    ├── status_panel.py       # RichLog-based status panel
    ├── mcp_panel.py          # MCP servers & artifacts panel
    ├── artifact_overlay.py   # Artifact detail overlay modal
    ├── input_field.py        # Input with dropdown completions
    ├── autocomplete.py       # AutoComplete dropdown logic
    ├── command_parser.py     # Command parsing utilities
    └── argument_suggestions.py # Command argument suggestions
```

**Layout Structure:**
- **Header**: Application title and status (Textual Header widget)
- **Main Horizontal Container**:
  - **Left Vertical Panel (Main)**:
    - **Chat Panel** (RichLog): Scrollable conversation with Rich markup, markdown, and syntax highlighting
    - **Status Panel** (RichLog): Real-time tool execution status with structured data display
    - **Input Field** (AutoComplete): Text input with dropdown completions for @ and / triggers
  - **Right Panel**: **MCP Panel** - Displays connected MCP servers, their status, and artifacts (resources, prompts, tools)
- **Footer**: Keyboard shortcuts and mode indicators (Textual Footer widget)
- **Artifact Overlay** (Modal): Displays detailed artifact information when clicked in MCP panel

**Key Features:**
- **Rich Markup**: Beautiful inline formatting with `[bold cyan]text[/]` syntax
- **Native Scrolling**: Automatic scrollbar management, no manual slicing required
- **Markdown Rendering**: Built-in Rich Markdown with syntax highlighting
- **Syntax Highlighting**: Rich Syntax widget for code blocks with themes
- **Tool Visualization**: Rich Panel and Table widgets for structured tool output
- **Auto-completion**: Dropdown menu triggered by `@` (resources) and `/` (prompts/commands)
- **Streaming**: Real-time chunk-by-chunk display via RichLog.write()
- **Focus Management**: Tab navigation between widgets (native Textual behavior)
- **MCP Server Monitoring**: Real-time connection status with reconnection progress and error messages
- **Artifact Browser**: Click on resources/prompts/tools in MCP panel to view full details in overlay

**Key Bindings:**
- `@`: Triggers resource completion dropdown
- `/`: Triggers prompt/command completion dropdown
- `Tab`: Navigate between input fields
- `Enter`: Send message or select autocomplete suggestion
- `Ctrl+Q` or `Ctrl+C`: Quit application
- `Ctrl+L`: Clear chat history
- `Click` on artifacts in MCP panel: View detailed information in overlay
- **Automatic scrolling**: Chat and status panels auto-scroll to bottom

**Supporting Services:**
- **QueryQueue** (`query_queue.py`): FIFO queue for sequential query processing
- **StatusQueue** (`status_queue.py`): FIFO queue for status updates from agent callbacks to TUI
- Both use **AsyncQueueProcessor<T>** pattern to eliminate code duplication

**Rich Integration Benefits:**
- Textual is built on top of Rich by the same author (Will McGugan)
- All Rich renderables work natively: Text, Markdown, Syntax, Table, Panel, JSON
- Clean markup syntax: `[bold cyan]` instead of formatted text tuples
- Superior formatting capabilities compared to previous prompt-toolkit implementation

### 5. Tool Management & Supporting Services

**ToolManager** (`core/tools.py`):
- Aggregates tools from `ArtifactManager`
- Routes tool execution to the correct MCP client
- `get_all_tools()`: Discovers and collects tools from all connected servers
- `execute_tool_requests()`: Routes tool calls to the correct client and executes them

**Supporting Services:**
- **core/claude.py**: Thin Anthropic SDK wrapper with message helpers
- **logger.py**: Loguru-based logging configured to file only (prevents TUI interference)
- **utils.py**: Utility functions (time formatting, etc.)
- **mcp_server.py**: Example MCP server implementation defining documents, tools, resources, and prompts

## MCP Server Configuration

MCP servers are configured in a JSON file (default: `src/nxs/config/mcp_servers.json`). The `ArtifactManager` loads this configuration on startup.

**Example configuration:**
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/directory"]
    },
    "remote-api": {
      "command": "npx",
      "args": ["mcp-remote", "https://example.com/mcp"]
    }
  }
}
```

The configuration supports:
- **Local servers** (stdio transport): command + args to spawn subprocess
- **Remote servers** (HTTP transport): Use `mcp-remote` as first arg, URL as second arg

To add/remove servers, edit the configuration file and restart the application.

## Common Development Tasks

### Running the application
```bash
pixi run start               # Default environment
pixi run python main.py      # Direct execution
```

### Running tests
```bash
pixi run --environment test test        # Run pytest
pixi run --environment test test-cov    # Run with coverage report
```

### Code quality
```bash
pixi run --environment dev format       # Format with black
pixi run --environment dev lint-fix     # Fix linting issues with ruff
pixi run --environment dev type-check   # Type checking with mypy
pixi run --environment dev ci           # Full pipeline (all checks + tests)
```

### Debugging
- Check `nexus.log` for application logs (file-based to avoid interfering with TUI)
- Use `pixi run --environment dev type-check` to catch type issues early
- Tests are in `tests/test_main.py`; run with `pixi run --environment test test`

## Adding Resources, Prompts, or Tools

There are two ways to extend the application:

### 1. Create a new MCP server
Create a new Python file that implements the MCP server protocol (see `mcp_server.py` as an example), then add it to your `mcp_servers.json` configuration.

### 2. Modify the example server
Edit `mcp_server.py` to add new resources:
```python
docs = {
    "example.md": "Your document content here",
}
```

Resources and prompts are automatically discovered and available for completion with `@` and `/` respectively.

## Code Organization

All source code is located in `src/nxs/` following the Python src-layout pattern.

### Entry Points

| File | Purpose |
|------|---------|
| `__main__.py` | Module entry point: `python -m nxs` |
| `main.py` | Main application logic; creates `ArtifactManager`, `CommandControlAgent`, and launches `NexusApp` |

### Core Layer (UI-independent)

| File | Purpose |
|------|---------|
| `core/artifact_manager.py` | Central manager for MCP artifacts: loads configs, manages connections, aggregates resources/prompts/tools |
| `core/mcp_config.py` | MCP configuration parser: loads and validates `mcp_servers.json` |
| `core/agentic_loop.py` | Base `AgentLoop` class: Claude integration, tool execution loop, streaming callbacks |
| `core/command_control.py` | `CommandControlAgent`: extends AgentLoop with resource/prompt extraction and processing |
| `core/claude.py` | Anthropic SDK wrapper with message construction helpers |
| `core/tools.py` | `ToolManager`: aggregates and routes tool execution across MCP clients |

### MCP Client Layer

| File | Purpose |
|------|---------|
| `mcp_client/client.py` | `MCPAuthClient`: main async client with connection management and reconnection logic |
| `mcp_client/auth.py` | Authentication handler for remote MCP servers |
| `mcp_client/storage.py` | Storage handler for MCP server state persistence |
| `mcp_client/callback.py` | UI callback helpers for progress/completion tracking |
| `mcp_client.py` | Legacy simple async wrapper (backwards compatibility) |

### TUI Layer (Textual + Rich)

| File | Purpose |
|------|---------|
| `tui/app.py` | `NexusApp` (Textual App): main layout, event handling, MCP status callbacks |
| `tui/styles.tcss` | Textual CSS for styling widgets and layout |
| `tui/query_queue.py` | `QueryQueue`: FIFO queue for sequential query processing |
| `services/status_queue.py` | `StatusQueue`: FIFO queue for status updates from agent to TUI |
| `services/queue_processor.py` | `AsyncQueueProcessor<T>`: Generic async FIFO queue processor pattern |
| `services/container.py` | `ServiceContainer`: Lazy service initialization and lifecycle management |
| `tui/widgets/chat_panel.py` | `ChatPanel` (RichLog): scrollable chat with Rich markup/markdown |
| `tui/widgets/status_panel.py` | `StatusPanel` (RichLog): tool execution status with structured display |
| `tui/widgets/mcp_panel.py` | `MCPPanel`: displays MCP servers, connection status, and artifacts |
| `tui/widgets/artifact_overlay.py` | `ArtifactOverlay`: modal for viewing artifact details |
| `tui/widgets/input_field.py` | `NexusInput`: input field with autocomplete integration |
| `tui/widgets/autocomplete.py` | `NexusAutoComplete`: dropdown autocomplete widget |
| `tui/widgets/command_parser.py` | Command parsing utilities |
| `tui/widgets/argument_suggestions.py` | Command argument suggestion logic |

### Supporting Files

| File | Purpose |
|------|---------|
| `logger.py` | Loguru configuration (file-only output to avoid TUI interference) |
| `utils.py` | Utility functions (time formatting, etc.) |
| `mcp_server.py` | Example MCP server implementation |
| `config/mcp_servers.json` | MCP server configurations |

### Tests

| File | Purpose |
|------|---------|
| `tests/test_main.py` | Basic integration tests |

## Git Workflow

Follow conventional commits with optional version bump prefixes:
- `feat:` - New features (Minor version bump)
- `fix:` - Bug fixes (Patch version bump)
- `BREAKING CHANGE:` - Breaking changes (Major version bump)
- `docs:`, `style:`, `refactor:`, `test:`, `chore:` - No version bump

Example: `feat: add document export functionality`

Note: Do not include Claude authorship in commit messages; pre-commit hooks may modify commits.
- the current application is a terminal application. when you run it in a bash pixi terminal is disturbing the output of claude code due to mouse events sent to the terminal. after you kill the app when you test it, remember to always to reset the terminal with the `reset` command or `tput reset`