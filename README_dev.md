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
├── pyproject.toml           # Project configuration and dependencies
├── ruff.toml               # Ruff linting configuration
├── main.py                 # Main application entry point
├── mcp_server.py           # MCP server implementation
├── mcp_client.py           # MCP client implementation
├── core/                   # Core application modules
│   ├── __init__.py
│   ├── chat.py
│   ├── claude.py
│   ├── cli_chat.py
│   ├── cli.py
│   └── tools.py
├── tests/                  # Test suite
│   ├── __init__.py
│   └── test_main.py
└── README.md               # User guide
```

## Adding New Documents

Edit the `mcp_server.py` file to add new documents to the `docs` dictionary.

## Implementing MCP Features

To fully implement the MCP features:

1. Complete the TODOs in `mcp_server.py`
2. Implement the missing functionality in `mcp_client.py`

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
