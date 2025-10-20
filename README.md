# NXS - MCP Chat Application

NXS is a modern, full-screen terminal user interface (TUI) application that enables interactive chat capabilities with AI models through the Anthropic API. The application features a rich, multi-panel interface with real-time streaming, document retrieval, command-based prompts, and extensible tool integrations via the MCP (Model Control Protocol) architecture.

## Features

- **Full-Screen TUI**: Modern terminal interface with split-panel layout
- **Real-Time Streaming**: Watch AI responses appear progressively as they're generated
- **Document Management**: Browse and reference documents with `@` completion
- **Command System**: Execute MCP commands with `/` completion and auto-suggestions
- **Tool Status Tracking**: Real-time visualization of tool execution and results
- **Chat History**: Persistent conversation history with markdown rendering
- **Auto-Completion**: Smart completion for resources (`@`) and commands (`/`)
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
- **Resources Panel**: Browse available documents and files with `@` completion
- **Commands Panel**: Access MCP commands with `/` completion and descriptions
- **Chat History**: View conversation with proper message alignment and markdown rendering
- **Tool Status**: Monitor tool executions in real-time with success/error indicators

### Smart Completion
- **Automatic**: Completion menus appear as you type `@` or `/`
- **Filtered**: Continue typing to narrow down options
- **Descriptions**: See command descriptions and resource metadata
- **Keyboard Navigation**: Use arrow keys to navigate, Enter to select

### Message Formatting
- **User Messages**: Left-aligned with clear "▶ You:" indicator
- **Assistant Messages**: Right-aligned with "◀ Assistant:" indicator, starting from center
- **Markdown Support**: Headers, lists, code blocks, and inline formatting
- **Auto-Scrolling**: Automatically scrolls to show new messages

## Setup

### Step 1: Configure the environment variables

1. Create or edit the `.env` file in the project root and verify that the required variables are set correctly:

```bash
# Copy the example environment file
cp .env.example .env

# Edit the .env file with your API key
ANTHROPIC_API_KEY=your_api_key_here
```

**Required Environment Variables:**
- `ANTHROPIC_API_KEY`: Your Anthropic API key for Claude access

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

The NXS TUI features a multi-panel layout:

- **Left Sidebar**: Lists available resources (`@`) and commands (`/`)
- **Main Chat Area**: Displays conversation history with real-time streaming
- **Tool Status Panel**: Shows active tool executions and results
- **Input Area**: Type your queries with auto-completion support

### Basic Interaction

1. **Start the application**: `pixi run start` or `pixi run python main.py`
2. **Type your message** in the input area at the bottom
3. **Press Enter** to send your message
4. **Watch the response** stream in real-time in the chat area

### Document Retrieval

Use the `@` symbol followed by a document ID to include document content:

1. **Type `@`** - A completion menu will appear showing available resources
2. **Select a document** using arrow keys or continue typing to filter
3. **Press Enter** to accept the completion

Example:
```
> Tell me about @deposition.md
```

### Commands

Use the `/` prefix to execute MCP commands:

1. **Type `/`** - A completion menu will appear showing available commands
2. **Select a command** using arrow keys or continue typing to filter
3. **Press Enter** to accept the completion
4. **Add arguments** as needed

Example:
```
> /format deposition.md
```

### Keyboard Shortcuts

- **Enter**: Send message
- **Ctrl+Q**: Quit application
- **Tab/Ctrl+Space**: Trigger completion manually
- **↑/↓**: Scroll chat history
- **Page Up/Page Down**: Fast scroll through chat
- **Ctrl+C**: Cancel streaming or quit

### Auto-Completion

- **`@`**: Shows available resources (documents, files)
- **`/`**: Shows available commands
- **Space**: Triggers completion after commands
- **Tab**: Manual completion trigger
- **Arrow Keys**: Navigate completion menu
- **Enter**: Accept highlighted completion

## Troubleshooting

### Common Issues

**Completion not working:**
- Ensure your terminal supports full-screen applications
- Try pressing `Tab` or `Ctrl+Space` to manually trigger completion
- Check that resources and commands are loaded (visible in sidebars)

**TUI not displaying properly:**
- Ensure your terminal window is large enough (minimum 80x24 characters)
- Try resizing your terminal window
- Some terminals may not support all TUI features

**Streaming not working:**
- Check your internet connection
- Verify your Anthropic API key is valid
- Check the logs in `nexus.log` for error details

### Logs

Application logs are written to `nexus.log` in the project root. Check this file for detailed error information and debugging.

## Development

For development setup, testing, code quality tools, and contribution guidelines, see [README_dev.md](README_dev.md).
