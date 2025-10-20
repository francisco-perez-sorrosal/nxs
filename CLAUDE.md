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

The application has four main layers with clean separation between UI and core logic:

### 1. MCP Protocol Layer (`mcp_server.py`, `mcp_client.py`)

- **mcp_server.py**: Defines MCP resources (documents), tools, and prompts; runs as subprocess
- **mcp_client.py**: Async wrapper around MCP ClientSession; handles subprocess communication via stdio

Multiple MCP servers can be connected by passing additional server scripts to `main.py`.

### 2. Core Agent Loop (`core/` - UI-independent)

The agent loop implements the core Claude integration with **no UI dependencies**:

- **AgentLoop** (`core/chat.py`): Base class handling the chat/tool-use loop:
  1. Sends user query + tools to Claude
  2. If Claude calls tools, executes them via `ToolManager`
  3. Returns results to Claude
  4. Repeats until Claude returns final text response
  5. Supports callbacks for streaming chunks, tool calls, and completion

- **CommandControlAgent** (`core/command_control.py`): Extends AgentLoop with:
  - Resource extraction from `@document` mentions in queries
  - Command processing from `/command` prefixes
  - Document content fetching and context building

### 3. TUI Layer (`tui/` - Textual + Rich)

The **NexusApp** class provides the full-screen terminal interface built with **Textual** (framework) and **Rich** (formatting):

**Architecture:**
```
tui/
├── app.py              # Main NexusApp (Textual App)
├── styles.tcss         # Textual CSS styling
└── widgets/
    ├── chat_panel.py   # RichLog-based chat display
    ├── status_panel.py # RichLog-based status panel
    └── input_field.py  # AutoComplete input with dropdown
```

**Layout Structure:**
- **Header**: Application title and status (Textual Header widget)
- **Chat Panel** (RichLog): Scrollable conversation with Rich markup, markdown, and syntax highlighting
- **Status Panel** (RichLog): Real-time tool execution status with structured data display
- **Input Field** (AutoComplete): Text input with dropdown completions for @ and / triggers
- **Footer**: Keyboard shortcuts and mode indicators (Textual Footer widget)

**Key Features:**
- **Rich Markup**: Beautiful inline formatting with `[bold cyan]text[/]` syntax
- **Native Scrolling**: Automatic scrollbar management, no manual slicing required
- **Markdown Rendering**: Built-in Rich Markdown with syntax highlighting
- **Syntax Highlighting**: Rich Syntax widget for code blocks with themes
- **Tool Visualization**: Rich Panel and Table widgets for structured tool output
- **Auto-completion**: Dropdown menu triggered by `@` (resources) and `/` (commands)
- **Streaming**: Real-time chunk-by-chunk display via RichLog.write()
- **Focus Management**: Tab navigation between widgets (native Textual behavior)

**Key Bindings:**
- `@`: Triggers resource completion dropdown
- `/`: Triggers command completion dropdown
- `Tab`: Navigate between input fields
- `Enter`: Send message
- `Ctrl+Q`: Quit application
- `Ctrl+L`: Clear chat history
- **Automatic scrolling**: Chat and status panels auto-scroll to bottom

**Rich Integration Benefits:**
- Textual is built on top of Rich by the same author (Will McGugan)
- All Rich renderables work natively: Text, Markdown, Syntax, Table, Panel, JSON
- Clean markup syntax: `[bold cyan]` instead of formatted text tuples
- Superior formatting capabilities compared to previous prompt-toolkit implementation

### 4. Tool Management (`core/tools.py`)

**ToolManager** aggregates tools from multiple MCP clients and routes execution:
- `get_all_tools()`: Discovers and collects tools from all connected clients
- `execute_tool_requests()`: Routes tool calls to the correct client and executes them

### 5. Supporting Services

- **core/claude.py**: Thin Anthropic SDK wrapper with message helpers
- **core/logger.py**: Loguru-based logging configured to file only (prevents TUI interference)
- **mcp_server.py**: Defines documents, tools, resources, and prompts; can be extended

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

## Adding Documents or Resources

Edit `mcp_server.py` to add new resources:
```python
docs = {
    "example.md": "Your document content here",
}
```

Resources are automatically discovered and available for completion with `@`.

## Code Organization

### Core Packages

| File | Purpose |
|------|---------|
| `main.py` | Entry point; manages MCP client lifecycle and launches Textual TUI |
| `mcp_server.py` | MCP server: documents, resources, tools, prompts definitions |
| `mcp_client.py` | Async MCP client wrapper for subprocess communication |

### Core Layer (UI-independent agent logic)

| File | Purpose |
|------|---------|
| `core/chat.py` | Base `AgentLoop` class: Claude integration, tool execution loop, streaming callbacks |
| `core/command_control.py` | Agent extending AgentLoop with resource extraction and command handling |
| `core/claude.py` | Anthropic SDK wrapper with message construction helpers |
| `core/tools.py` | `ToolManager` for aggregating and routing tool execution |
| `core/logger.py` | Loguru configuration (file-only output to avoid TUI interference) |

### TUI Layer (Textual + Rich)

| File | Purpose |
|------|---------|
| `tui/app.py` | Main `NexusApp` (Textual App): layout, callbacks, event handling |
| `tui/styles.tcss` | Textual CSS for styling widgets and layout |
| `tui/widgets/chat_panel.py` | `ChatPanel` (RichLog): scrollable chat with Rich markup/markdown |
| `tui/widgets/status_panel.py` | `StatusPanel` (RichLog): tool execution status with structured display |
| `tui/widgets/input_field.py` | `NexusInput` (AutoComplete): input with dropdown for @ and / completions |

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
