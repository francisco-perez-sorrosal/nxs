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

## Project Map

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full layered breakdown. Quick pointers:
- `src/nxs/application/` — orchestration services (agent loop, connections, artifacts).
- `src/nxs/domain/` — protocols, events, shared types.
- `src/nxs/infrastructure/` — concrete MCP client + cache implementations.
- `src/nxs/presentation/` — Textual/Rich TUI, handlers, services, widgets.
- `src/nxs/config/nxs_mcp_config.json` — MCP server definitions.
- `tests/` — unit coverage for connection management, parsers, TUI widgets, MCP coordination.

## MCP Utilities

Use Pixi tasks to exercise the bundled MCP tooling:
```bash
# Run example MCP client (no OAuth)
pixi run mcp_client --server-url https://syn-executor.wasmer.app

# Run MCP client with OAuth-friendly endpoint
pixi run mcp_client --server-url https://synx-francisco-perez-sorrosal.wasmer.app
```

Edit `src/nxs/config/nxs_mcp_config.json` to point the TUI at your own MCP servers. Remote HTTP transports are currently supported through `MCPAuthClient`.

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
