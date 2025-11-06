# NXS - Development Guide

This document covers development setup, testing, code quality tools, and contribution guidelines for the NXS project.

## Development Setup

### Pixi Environments

This project uses Pixi to manage multiple environments for different development workflows:

#### Environment Structure

```
dev (dev + test + default)
├── test (test + default)
│   └── default (base)
└── default (base)
```

#### Available Environments

##### `default` Environment
- **Purpose**: Main application runtime
- **Tasks**: `start`, `chat`, `server`, `client`, `clean`, `dev-install`

##### `test` Environment
- **Purpose**: Testing and quality assurance
- **Tasks**: `test`, `test-cov`

##### `dev` Environment
- **Purpose**: Full development workflow
- **Tasks**: `lint`, `lint-fix`, `format`, `type-check`, `ci`

#### Environment Usage

```bash
# Install specific environments
pixi install --environment default    # Main application
pixi install --environment test       # Testing tools
pixi install --environment dev        # Development tools

# Run tasks in specific environments
pixi run --environment test test      # Run tests
pixi run --environment dev lint       # Run linting
pixi run --environment dev ci         # Run full CI pipeline

# Check environment information
pixi info                             # Show all environments
pixi list                             # List installed packages
```

## Development Workflow

1. **Setup development environment**:
   ```bash
   pixi install --environment dev
   ```

2. **Run code quality checks**:
   ```bash
   pixi run --environment dev ci      # Full pipeline
   pixi run --environment dev format  # Format code
   pixi run --environment dev lint    # Check linting issues
   pixi run --environment dev lint-fix # Fix linting issues automatically
   pixi run --environment dev type-check  # Type checking
   ```

3. **Run tests**:
   ```bash
   pixi run --environment test test       # Run tests
   pixi run --environment test test-cov   # Run with coverage
   ```

4. **Development tasks**:
   ```bash
   pixi run --environment dev dev-install  # Install in editable mode
   pixi run clean                         # Clean build artifacts
   ```

## Available Pixi Tasks

| Task | Environment | Description |
|------|-------------|-------------|
| `start` | default | Start the main application |
| `chat` | default | Start chat interface |
| `server` | default | Start MCP server |
| `client` | default | Start MCP client |
| `test` | test | Run pytest tests |
| `test-cov` | test | Run tests with coverage |
| `lint` | dev | Run ruff linting |
| `lint-fix` | dev | Fix linting issues automatically |
| `format` | dev | Format code with black |
| `type-check` | dev | Run mypy type checking |
| `ci` | dev | Run full CI pipeline |
| `dev-install` | default | Install package in editable mode |
| `clean` | default | Clean build artifacts |

## Code Quality

This project includes comprehensive code quality tools:

- **Formatting**: Black for consistent code formatting
- **Linting**: Ruff for fast Python linting with automatic fixing
- **Type Checking**: MyPy for static type analysis
- **Testing**: Pytest with coverage reporting
- **Git Hooks**: Pre-commit for automated quality checks

### Quick Development Workflow

```bash
# Fix common linting issues automatically
pixi run --environment dev lint-fix

# Format code
pixi run --environment dev format

# Run full quality pipeline
pixi run --environment dev ci

# Run mcp client without Oauth
pixi run mcp_client --server-url https://syn-executor.wasmer.app 

# Run mcp client test with Oauth
pixi run mcp_client --server-url https://synx-francisco-perez-sorrosal.wasmer.app 

```

### Configuration Files

- **Ruff**: Configuration in `ruff.toml` for linting rules and settings
- **Black**: Configuration in `pyproject.toml` for code formatting
- **MyPy**: Configuration in `pyproject.toml` for type checking
- **Pytest**: Configuration in `pyproject.toml` for testing

## Project Structure

```
nxs/
├── pyproject.toml              # Project configuration and dependencies
├── ruff.toml                   # Ruff linting configuration
├── src/nxs/                    # Source code (src-layout)
│   ├── __main__.py            # Module entry point
│   ├── main.py                # Application entry point
│   ├── logger.py              # Logging configuration
│   ├── utils.py               # Utility functions
│   ├── mcp_server.py          # Example MCP server
│   ├── mcp_client.py          # Legacy MCP client wrapper
│   ├── config/                # Configuration files
│   │   └── mcp_servers.json   # MCP server configurations
│   ├── core/                  # Core application modules (UI-independent)
│   │   ├── artifact_manager.py    # MCP artifact manager
│   │   ├── mcp_config.py          # MCP config parser
│   │   ├── chat.py                # Base agent loop
│   │   ├── command_control.py     # Command/resource processing agent
│   │   ├── claude.py              # Anthropic SDK wrapper
│   │   └── tools.py               # Tool management
│   ├── mcp_client/            # MCP client package
│   │   ├── client.py          # Main MCP client with reconnection
│   │   ├── auth.py            # Authentication handler
│   │   ├── storage.py         # Storage handler
│   │   └── callback.py        # UI callback helpers
│   ├── tui/                   # TUI layer (Textual + Rich)
│   │   ├── app.py             # Main NexusApp
│   │   ├── styles.tcss        # Textual CSS styling
│   │   ├── query_manager.py   # Async query processing
│   │   ├── status_queue.py    # Async status updates
│   │   └── widgets/           # TUI widgets
│   │       ├── chat_panel.py          # Chat display
│   │       ├── status_panel.py        # Status display
│   │       ├── mcp_panel.py           # MCP server/artifact panel
│   │       ├── artifact_overlay.py    # Artifact detail overlay
│   │       ├── input_field.py         # Input field
│   │       ├── autocomplete.py        # Autocomplete dropdown
│   │       ├── command_parser.py      # Command parsing
│   │       └── argument_suggestions.py # Argument suggestions
│   └── prompts/               # Prompt templates
└── tests/                     # Test suite
    ├── __init__.py
    └── test_main.py
```

## Adding Resources, Prompts, or Tools

### Option 1: Modify the example MCP server
Edit `src/nxs/mcp_server.py` to add new documents to the `docs` dictionary, or add new tools/prompts.

### Option 2: Create a new MCP server
1. Create a new Python file implementing the MCP server protocol (use `mcp_server.py` as a template)
2. Add it to `src/nxs/config/mcp_servers.json`:
   ```json
   {
     "mcpServers": {
       "my-server": {
         "command": "python",
         "args": ["-m", "path.to.my_server"]
       }
     }
   }
   ```
3. Restart the application

### Option 3: Use existing MCP servers
Add community MCP servers to your configuration:
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/directory"]
    }
  }
}
```

## Contributing

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Setup development environment**: `pixi install --environment dev`
4. **Make your changes**
5. **Run quality checks**: `pixi run --environment dev ci`
6. **Commit your changes**: `git commit -m "Add your feature"`
7. **Push to your fork**: `git push origin feature/your-feature-name`
8. **Create a Pull Request**

### Commit Message Guidelines

Use conventional commit messages with version bump prefixes:

- `feat:` - New features (Minor version bump)
- `fix:` - Bug fixes (Patch version bump)
- `BREAKING CHANGE:` - Breaking changes (Major version bump)
- `docs:`, `style:`, `refactor:`, `test:`, `chore:` - No version bump

Examples:
- `feat: add new logging feature`
- `fix: resolve debug mode issue`
- `docs: update README with new setup instructions`
