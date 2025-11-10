# NXS – AI Chat Terminal

NXS is a full-screen Textual/Rich terminal interface that pairs Claude with Model Context Protocol (MCP) servers so you can chat, browse documents, and execute tools without leaving the terminal.

## Highlights
- Real-time streaming chat with markdown and syntax-highlighted responses.
- Smart completions for `@resources` and `/prompts`, including argument hints.
- Live MCP panel that tracks server health, artifacts, and reconnection progress.
- Integrated tool execution with visible status updates and results.
- Battery-included Pixi environment for reproducible installs and quality checks.

## Prerequisites
- Python 3.11 or newer.
- [Pixi](https://pixi.sh/) (recommended) or another environment manager.
- Anthropic API key with access to Claude models.
- Terminal that supports full-screen applications.

## Quick Start
1. **Install dependencies**  
   ```bash
   pixi install
   ```
2. **Configure environment variables**  
   ```bash
   cp .env.example .env
   ${HOME}/bin/create_dotenv.sh   # optional helper script
   ```
   Fill in at least `ANTHROPIC_API_KEY` and `CLAUDE_MODEL`.
3. **Run the TUI**  
   ```bash
   pixi run start
   ```
4. **After exiting the app**  
   Run `reset` (or `tput reset`) to restore a clean terminal session.

## Running the Application
- `pixi run start` launches `python -m nxs` with all wiring in place.
- Use `Ctrl+Q` or `Ctrl+C` to quit and `Ctrl+L` to clear the chat buffer.
- To run just the sample MCP server or client CLI:  
  `pixi run server` / `pixi run client`.

### Using the Interface
- Type messages in the input field at the bottom; results stream into the chat panel.
- Use `@` to insert MCP resources and `/` to trigger MCP prompts with autocomplete.
- Tool executions and background jobs post progress into the status panel.
- The MCP panel (right side) shows server status, available artifacts, and reconnect attempts.

## Configuration
- **Environment**: `.env` controls Anthropic credentials, default model, and toggles.
- **MCP servers**: Edit `src/nxs/config/nxs_mcp_config.json` to add or remove MCP endpoints. Remote servers are currently supported via HTTP transports.
- **Logging**: All components share the Loguru setup in `src/nxs/logger.py`; output is written to `nexus.log`.

## Troubleshooting
- **MCP connection issues**: Inspect `nexus.log`, confirm URLs/credentials, and ensure remote servers are reachable.
- **UI glitches**: Resize the terminal or try a Textual-compatible terminal emulator (iTerm2, Kitty, Alacritty, Windows Terminal).
- **Missing completions**: Wait for MCP initialization to finish; the status panel and MCP panel will indicate readiness.
- **Stuck terminal**: If you manually kill the process, always run `reset` (or `tput reset`) before continuing.

## Development

### Code Quality
- Run tests: `pixi run --environment test test`
- Type checking: `pixi run --environment dev type-check`
- Linting: `pixi run --environment dev lint`
- Full CI pipeline: `pixi run --environment dev ci`

### Architecture Highlights
- **Layered design**: Presentation → Application → Domain → Infrastructure
- **Event-driven coordination**: Synchronous EventBus with async work scheduled via `create_task()`
- **Services vs Handlers**: Complementary patterns for state management and event processing
- **Service consolidation**: `AsyncQueueProcessor<T>` pattern eliminates code duplication
- **Lazy initialization**: Services created on-demand via `ServiceContainer`

For detailed patterns, naming conventions, and design decisions, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Learn More
- Developer workflows and quality checks: see [`README_dev.md`](README_dev.md).
- Detailed component and event flow: see [`ARCHITECTURE.md`](ARCHITECTURE.md).
- Tests live under `tests/` and can be run with `pixi run --environment test test`.
