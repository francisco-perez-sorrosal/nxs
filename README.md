# NXS - MCP Chat Application

NXS is a modern, full-screen terminal user interface (TUI) application that enables interactive chat capabilities with AI models through the Anthropic API. The application features a rich, multi-panel interface with real-time streaming, document retrieval, command-based prompts, and extensible tool integrations via the MCP (Model Control Protocol) architecture.

## Features

- **Full-Screen TUI**: Modern terminal interface built with Textual and Rich
- **Real-Time Streaming**: Watch AI responses appear progressively as they're generated
- **MCP Server Management**: Connect to multiple MCP servers with automatic reconnection
- **Resource Browser**: Browse and reference documents with `@` completion
- **Prompt System**: Execute MCP prompts with `/` completion and auto-suggestions
- **Tool Integration**: Automatic tool discovery and execution from connected MCP servers
- **Server Status Panel**: Real-time monitoring of MCP server connections and artifacts
- **Artifact Browser**: Click on resources/prompts/tools to view detailed information
- **Tool Status Tracking**: Real-time visualization of tool execution and results
- **Chat History**: Conversation history with markdown rendering and syntax highlighting
- **Auto-Completion**: Smart completion for resources (`@`) and prompts (`/`)
- **Keyboard Navigation**: Full keyboard support with intuitive shortcuts

## Quick Start

1. **Install dependencies**: `pixi install`
2. **Set up environment**: `cp .env.example .env` and add your `ANTHROPIC_API_KEY`
3. **Run the application**: `pixi run start`
4. **Start chatting**: Type your message and press Enter
5. **Use completion**: Type `@` for resources or `/` for commands

## Prerequisites

- Python 3.11+
- Anthropic API Key
- [Pixi](https://pixi.sh/) (recommended for development)
- Terminal with support for full-screen applications (most modern terminals)

## TUI Features

### Real-Time Streaming
Watch AI responses appear character by character as they're generated, with visual indicators showing when streaming is active.

### Multi-Panel Layout
- **Chat Panel**: Main conversation area with markdown rendering and syntax highlighting
- **Status Panel**: Real-time tool execution status with structured data display
- **MCP Panel** (right sidebar):
  - Lists all connected MCP servers with connection status (🟢 Connected, 🟡 Connecting/Reconnecting, 🔴 Disconnected/Error)
  - Shows available artifacts (resources, prompts, tools) from each server
  - Click on artifacts to view detailed information in an overlay modal
  - Displays operational status and reconnection progress
- **Input Field**: Text input with autocomplete for `@` (resources) and `/` (prompts)

### Smart Completion
- **Automatic**: Completion menus appear as you type `@` or `/`
- **Filtered**: Continue typing to narrow down options
- **Descriptions**: See prompt descriptions and resource metadata
- **Keyboard Navigation**: Use arrow keys to navigate, Enter to select

### MCP Server Management
- **Automatic Connection**: Servers configured in `mcp_servers.json` are connected on startup
- **Reconnection**: Automatic reconnection with exponential backoff on connection loss
- **Status Tracking**: Real-time connection status with visual indicators
- **Error Reporting**: Clear error messages displayed in the MCP panel
- **Multiple Servers**: Connect to multiple local (stdio) and remote (HTTP) MCP servers simultaneously

### Message Formatting
- **User Messages**: Left-aligned with clear "▶ You:" indicator
- **Assistant Messages**: Right-aligned with "◀ Assistant:" indicator
- **Markdown Support**: Headers, lists, code blocks, tables, and inline formatting
- **Syntax Highlighting**: Code blocks with language-specific syntax highlighting
- **Auto-Scrolling**: Automatically scrolls to show new messages

## Setup

### Step 1: Configure the environment variables

1. Create or edit the `.env` file in the project root and verify that the required variables are set correctly:

```bash
# Copy the example environment file
cp .env.example .env

# Edit the .env file with your API key
ANTHROPIC_API_KEY=your_api_key_here
CLAUDE_MODEL=claude-3-5-sonnet-20241022
```

**Required Environment Variables:**
- `ANTHROPIC_API_KEY`: Your Anthropic API key for Claude access
- `CLAUDE_MODEL`: Claude model to use (e.g., `claude-3-5-sonnet-20241022`)

### Step 1.5: Configure MCP Servers (Optional)

MCP servers provide resources (documents), prompts (commands), and tools to the application. By default, the application includes an example server.

To add more servers, edit `src/nxs/config/mcp_servers.json`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/yourname/Documents"]
    },
    "sqlite": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sqlite", "/path/to/database.db"]
    },
    "remote-api": {
      "command": "npx",
      "args": ["mcp-remote", "https://example.com/mcp"]
    }
  }
}
```

**Configuration Format:**
- **Local servers** (stdio): Provide `command` and `args` to spawn a subprocess
- **Remote servers** (HTTP): Use `"mcp-remote"` as first arg, server URL as second arg

Popular MCP servers available via npm:
- `@modelcontextprotocol/server-filesystem` - File system access
- `@modelcontextprotocol/server-sqlite` - SQLite database access
- `@modelcontextprotocol/server-github` - GitHub repository access
- `@modelcontextprotocol/server-postgres` - PostgreSQL database access

See the [MCP servers directory](https://github.com/modelcontextprotocol/servers) for more options.

### Step 2: Install dependencies

#### Option 1: Setup with Pixi (Recommended)

[Pixi](https://pixi.sh/) is a fast, modern, and reproducible package management tool for Python.

1. Install Pixi, if not already installed:

```bash
# macOS/Linux
curl -fsSL https://pixi.sh/install.sh | bash

# Or via conda/mamba
conda install -c conda-forge pixi
```

2. Install dependencies:

```bash
# Install all environments
pixi install

# Or install just the main application
pixi install --environment default
```

3. Run the application:

```bash
# Using pixi tasks
pixi run start    # Start the main application
pixi run chat     # Start chat interface
pixi run server   # Start MCP server
pixi run client   # Start MCP client

# Or run directly
pixi run python main.py
```

#### Option 2: Setup without package managers

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install anthropic python-dotenv prompt-toolkit "mcp[cli]>=1.18.0"
```

3. Run the project:

```bash
python main.py
```

## Usage

### Interface Overview

The NXS TUI features a horizontal split layout:

**Left Panel (Main)**:
- **Chat Panel**: Displays conversation history with real-time streaming
- **Status Panel**: Shows active tool executions and results
- **Input Field**: Type your queries with auto-completion support

**Right Panel**:
- **MCP Panel**: Lists all connected MCP servers with their connection status and artifacts (resources, prompts, tools)

### Basic Interaction

1. **Start the application**: `pixi run start` or `pixi run python main.py`
2. **Type your message** in the input area at the bottom
3. **Press Enter** to send your message
4. **Watch the response** stream in real-time in the chat area

### Resource Retrieval

Use the `@` symbol to reference resources (documents, files) from connected MCP servers:

1. **Type `@`** - A completion menu will appear showing available resources
2. **Select a resource** using arrow keys or continue typing to filter
3. **Press Enter** to accept the completion

Example:
```
> Tell me about @deposition.md
```

The resource content will be fetched from the MCP server and included in your query.

### Prompts

Use the `/` prefix to execute MCP prompts:

1. **Type `/`** - A completion menu will appear showing available prompts
2. **Select a prompt** using arrow keys or continue typing to filter
3. **Press Enter** to accept the completion
4. **Add arguments** as needed (some prompts require arguments)

Example:
```
> /summarize document.txt
```

Prompts are pre-defined templates from MCP servers that can accept arguments and perform specific tasks.

### MCP Server Status

The right panel displays all connected MCP servers with:
- **Connection Status**: 🟢 Connected, 🟡 Connecting/Reconnecting, 🔴 Disconnected/Error
- **Available Artifacts**: Count of resources, prompts, and tools from each server
- **Operational Status**: Current server operation (e.g., "Fetching artifacts...")
- **Reconnection Progress**: Shows retry attempts during reconnection
- **Last Check Time**: When the server was last contacted

Click on any artifact (resource/prompt/tool) to view its full details in an overlay modal.

### Keyboard Shortcuts

- **Enter**: Send message or accept completion
- **Ctrl+Q** or **Ctrl+C**: Quit application
- **Ctrl+L**: Clear chat history
- **Tab**: Navigate between input fields
- **Shift+Tab**: Navigate backwards between fields
- **↑/↓**: Navigate completion menu (when shown)
- **Esc**: Close overlays or cancel completion
- **Mouse Click**: Click on artifacts in MCP panel to view details

### Auto-Completion

- **`@`**: Shows available resources (documents, files) from all connected MCP servers
- **`/`**: Shows available prompts from all connected MCP servers
- **Continue typing**: Filter completion options in real-time
- **Arrow Keys**: Navigate completion menu
- **Enter**: Accept highlighted completion
- **Esc**: Cancel completion

## Troubleshooting

### Common Issues

**MCP servers not connecting:**
- Check `nexus.log` for connection errors
- Verify your `mcp_servers.json` configuration is valid JSON
- For remote servers, check network connectivity
- For local servers, ensure the command exists (e.g., `npx` for Node.js servers)
- The MCP panel will show connection status and error messages

**Completion not working:**
- Ensure MCP servers are connected (check the MCP panel for 🟢 status)
- Resources and prompts are only available from connected servers
- Check that the server actually provides resources/prompts (visible in MCP panel)

**TUI not displaying properly:**
- Ensure your terminal window is large enough (minimum 80x24 characters recommended)
- Try resizing your terminal window
- Some older terminals may not support all TUI features
- Modern terminals (iTerm2, Windows Terminal, Alacritty, Kitty) work best

**Streaming not working:**
- Check your internet connection
- Verify your `ANTHROPIC_API_KEY` is valid in `.env`
- Check the logs in `nexus.log` for API errors

**Tools not executing:**
- Check that MCP servers providing tools are connected
- Tool execution errors are displayed in the Status Panel
- Check `nexus.log` for detailed error messages

### Logs

Application logs are written to `nexus.log` in the project root. Check this file for detailed error information and debugging. The log includes:
- MCP connection/disconnection events
- Tool execution details
- API request/response information
- Error stack traces

## Development

For development setup, testing, code quality tools, and contribution guidelines, see [README_dev.md](README_dev.md).
