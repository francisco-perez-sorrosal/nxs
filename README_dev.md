# NXS – Development Reference

This guide targets contributors who build and maintain NXS. It covers environment setup, quality tooling, useful commands, and contribution conventions. For architectural background, read [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Environment Setup

```bash
# Install everything (recommended)
pixi install

# Or install individual environments
pixi install --environment default   # runtime only
pixi install --environment test      # pytest + coverage
pixi install --environment dev       # linting, typing, CI bundle
```

### Environment Layout
- `default`: ships the runnable application plus helper tasks (`start`, `server`, `client`, `chat`, `clean`, `dev-install`).
- `test`: adds pytest tooling and exposes `test`, `test-cov`.
- `dev`: layers format, lint, type-check, and CI helpers on top of the test stack.

Use `pixi info` to inspect environments and `pixi task list` to discover available commands.

### Configuration

**Environment Variables** (`.env`):
```
ANTHROPIC_API_KEY=your_api_key
CLAUDE_MODEL=claude-3-5-sonnet-20241022
```

**MCP Configuration** (`src/nxs/config/mcp_servers.json`):
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    }
  }
}
```

Edit this file to point the TUI at your own MCP servers. Remote HTTP transports are currently supported through `MCPAuthClient`.

## Daily Workflow

```bash
# Activate full toolchain
pixi install --environment dev

# Format, lint, type-check, and run tests in one go
pixi run --environment dev ci

# Run only what you need
pixi run --environment dev format
pixi run --environment dev lint
pixi run --environment dev lint-fix
pixi run --environment dev type-check
pixi run --environment test test
pixi run --environment test test-cov
```

When you launch the TUI from a development shell, always run `reset` (or `tput reset`) after quitting or forcibly terminating the app. This restores a sane terminal state before continuing work.

## Code Quality Tooling
- **Ruff** (`pixi run --environment dev lint`) is the primary linter/formatter; `lint-fix` applies quick fixes.
- **Black** formatting is provided through the `format` task; settings live in `pyproject.toml`.
- **Mypy** runs via `pixi run --environment dev type-check` using relaxed-but-useful defaults configured in `pyproject.toml`.
- **Pytest** drives tests in `tests/` with verbose, short tracebacks; coverage reports land under `htmlcov/`.
- **Pre-commit** hooks can be installed manually if desired (`pixi run --environment dev dev-install`).

Configuration files:
- `pyproject.toml` — project metadata, Pixi tasks, Black, Mypy, pytest, coverage.
- `ruff.toml` — linting and formatting rules.
- `CLAUDE.md` — repository guidelines for AI coding agents.

## Testing

```bash
# Run all tests
pixi run --environment test test

# Run with coverage
pixi run --environment test test-cov

# Run specific test
pixi run --environment test pytest tests/test_session.py
```

Coverage reports are generated under `htmlcov/` when using `test-cov`.

## Project Map

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full layered breakdown and architectural philosophy. The codebase follows clean architecture principles with four distinct layers:

### Domain Layer
```
src/nxs/domain/
├── protocols/          # Interface definitions
├── events/             # Event types + EventBus
├── types/              # Value objects and enums
└── artifacts.py        # Domain models
```

Core abstractions and business logic. No dependencies on outer layers.

### Infrastructure Layer
```
src/nxs/infrastructure/
├── mcp/
│   ├── client.py       # MCPAuthClient
│   ├── connection/     # Connection management
│   └── auth.py         # OAuth
└── cache/              # Cache implementations
```

Concrete implementations of domain protocols (MCP clients, caching, persistence).

### Application Layer
```
src/nxs/application/
├── session.py          # Session + metadata
├── session_manager.py  # Multi-session management
├── conversation.py     # Message history + caching
├── agentic_loop.py     # Base agent orchestration
├── reasoning_loop.py   # Adaptive reasoning
├── progress_tracker.py # Execution context preservation
├── claude.py           # Claude SDK wrapper
├── tool_registry.py    # Pluggable tool sources
├── cost_tracker.py     # Cost tracking
├── approval.py         # Human-in-the-loop
├── artifact_manager.py # MCP facade
├── reasoning/          # Complexity analysis, planning, evaluation
├── strategies/         # Execution strategies
└── summarization/      # Conversation summarization
```

Orchestration services coordinating domain and infrastructure. Key features:
- **ResearchProgressTracker**: Context preservation across reasoning escalations
- **AdaptiveReasoningLoop**: Self-correcting agent with DIRECT → LIGHT → DEEP escalation
- **Tool Caching**: Smart caching policy for 30-50% API call reduction
- **Session Management**: Multi-session architecture with auto-save/restore
- **Cost Tracking**: Three-tracker architecture (conversation, reasoning, summarization)

### Presentation Layer
```
src/nxs/presentation/
├── tui/
│   └── nexus_app.py    # Main application
├── widgets/            # UI components
├── services/           # Background services
└── handlers/           # Request handlers
```

Textual/Rich TUI with widgets, handlers, and services for user interaction.

### Configuration & Tests
- `src/nxs/config/nxs_mcp_config.json` — MCP server definitions
- `tests/` — unit coverage for connection management, parsers, TUI widgets, MCP coordination

## MCP Utilities

Use Pixi tasks to exercise the bundled MCP tooling:
```bash
# Run example MCP client (no OAuth)
pixi run mcp_client --server-url https://syn-executor.wasmer.app

# Run MCP client with OAuth-friendly endpoint
pixi run mcp_client --server-url https://synx-francisco-perez-sorrosal.wasmer.app
```

## Extensibility

### Add MCP Server
1. Edit `src/nxs/config/mcp_servers.json`
2. Add server configuration with command and args
3. Restart application to load new server

### Add Local Tool
```python
# src/nxs/tools/my_tool.py
def my_tool(arg: str) -> str:
    """Tool description for LLM."""
    return f"Result: {arg}"
```

Register the tool in the tool registry to make it available to the agent.

### Modify Tool Caching
Edit `TOOL_CACHING_POLICY` in `src/nxs/application/progress_tracker.py`. Tools are categorized as:
- **Time-sensitive**: No caching (e.g., current time, file listing)
- **Stable**: Cached (e.g., file reading, calculations)

### Add Custom Widget
1. Create new widget in `src/nxs/presentation/widgets/`
2. Extend Textual widget classes (RichLog, Static, Input, etc.)
3. Add to `NexusApp` layout in `nexus_app.py`

## Contribution Checklist
1. Branch from `main` and keep changes focused.
2. Run `pixi run --environment dev ci` before committing.
3. Use conventional commits with version hints:
   - `feat:` → minor bump
   - `fix:` → patch bump
   - `BREAKING CHANGE:` → major bump
   - `docs:`, `style:`, `refactor:`, `test:`, `chore:` → no version change
4. Provide context in PR descriptions (what changed, why, testing evidence).

When authoring commits that touch runtime behaviour, mention any manual testing you performed (e.g., specific Pixi tasks or sample MCP endpoints).

## Further Reading
- [`README.md`](README.md) — user-facing quick start.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — layered design, event flow, extensibility notes.
- Source-level READMEs (e.g., `src/nxs/presentation/services/README.md`) for subsystem specifics.
