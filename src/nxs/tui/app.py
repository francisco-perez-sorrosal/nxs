"""
NexusApp - Main Textual application for the Nexus TUI.
"""

import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Container, Vertical
from textual.binding import Binding

from .widgets.chat_panel import ChatPanel
from .widgets.status_panel import StatusPanel
from .widgets.input_field import NexusInput, NexusAutoComplete
from nxs.core.artifact_manager import ArtifactManager
from nxs.logger import get_logger

logger = get_logger("nexus_tui")


class NexusApp(App):
    """
    The main Nexus TUI application.

    Layout:
    ┌─────────────────────────────┐
    │         Header              │
    ├─────────────────────────────┤
    │                             │
    │      Chat Panel             │
    │     (scrollable)            │
    │                             │
    ├─────────────────────────────┤
    │    Status Panel             │
    │     (scrollable)            │
    ├─────────────────────────────┤
    │      Input Field            │
    ├─────────────────────────────┤
    │         Footer              │
    └─────────────────────────────┘
    """

    TITLE = "Nexus"
    SUB_TITLE = "AI Chat with Document Retrieval & MCP Tools"

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True, show=False),
        Binding("tab", "focus_next", "Next Field", show=False),
        Binding("shift+tab", "focus_previous", "Previous Field", show=False),
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
    ]

    def __init__(
        self,
        agent_loop,
        artifact_manager: ArtifactManager,
    ):
        """
        Initialize the Nexus TUI application.

        Args:
            agent_loop: The agent loop instance (core.chat.AgentLoop)
            artifact_manager: The ArtifactManager instance for accessing resources and commands
        """
        super().__init__()
        self.agent_loop = agent_loop
        self.artifact_manager = artifact_manager
        self.resources: list[str] = []
        self.commands: list[str] = []
        self._processing = False  # Track if we're processing a query

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header()

        with Container(id="app-container"):
            with Vertical(id="main-content"):
                yield ChatPanel(id="chat")
                
                # Create input widget
                yield NexusInput(
                    resources=self.resources,
                    commands=self.commands,
                    artifact_manager=self.artifact_manager,
                    id="input"
                )
                
                yield StatusPanel(id="status")

        yield Footer()

    async def on_mount(self) -> None:
        """Called when the app is mounted."""
        logger.info("Nexus TUI mounted and ready")

        # Load resources and commands from ArtifactManager
        try:
            self.resources = await self.artifact_manager.get_resource_list()
            self.commands = await self.artifact_manager.get_command_names()
            logger.info(f"Loaded {len(self.resources)} resources and {len(self.commands)} commands")
            
            # Update the input widget with loaded resources and commands
            input_widget = self.query_one("#input", NexusInput)
            input_widget.update_resources(self.resources)
            input_widget.update_commands(self.commands)
            
            # Preload prompt information for all commands BEFORE showing the UI
            # This ensures arguments are available when dropdown is shown
            await self._preload_all_prompt_info()
        except Exception as e:
            logger.error(f"Failed to load resources and commands: {e}")

        # Show welcome message in chat
        chat = self.query_one("#chat", ChatPanel)
        chat.add_panel(
            "[bold]Welcome to Nexus![/]\n\n"
            "Type [cyan]@[/] to reference documents\n"
            "Type [cyan]/[/] to execute commands\n"
            "Press [cyan]Ctrl+Q[/] to quit\n"
            "Press [cyan]Ctrl+L[/] to clear chat",
            title="Getting Started",
            style="green"
        )

        # Mount AutoComplete overlay after the app is fully mounted
        self.call_after_refresh(self._mount_autocomplete)
        
        # Focus the input field after the first render
        self.call_after_refresh(self._focus_input)
    
    async def _preload_all_prompt_info(self) -> None:
        """Preload prompt argument information for all commands directly."""
        try:
            logger.info(f"Preloading prompt information for {len(self.commands)} commands...")
            if not hasattr(self, '_prompt_info_cache'):
                self._prompt_info_cache = {}
            if not hasattr(self, '_prompt_schema_cache'):
                self._prompt_schema_cache = {}
                
            for command in self.commands:
                prompt_info = await self.artifact_manager.find_prompt(command)
                if prompt_info:
                    prompt, server_name = prompt_info
                    # Store full prompt object for argument expansion
                    self._prompt_schema_cache[command] = (prompt, server_name)
                    # Extract argument info string for display
                    arg_info = self._format_prompt_arguments(prompt)
                    self._prompt_info_cache[command] = arg_info
                    logger.debug(f"Preloaded info for '{command}': {arg_info}")
            logger.info(f"Successfully preloaded prompt information for {len(getattr(self, '_prompt_info_cache', {}))} commands")
        except Exception as e:
            logger.error(f"Failed to preload prompt info: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _format_prompt_arguments(self, prompt) -> str | None:
        """Format prompt arguments into a readable string (helper method)."""
        if not hasattr(prompt, 'arguments') or not prompt.arguments:
            return None
        
        schema = prompt.arguments
        arg_names: list[str] = []
        required_args: list[str] = []
        
        # Handle different schema formats
        if isinstance(schema, list):
            for arg in schema:
                if hasattr(arg, 'name'):
                    arg_names.append(arg.name)
                    if hasattr(arg, 'required') and arg.required:
                        required_args.append(arg.name)
                elif isinstance(arg, dict):
                    arg_name = arg.get('name', '')
                    if arg_name:
                        arg_names.append(arg_name)
                        if arg.get('required', False):
                            required_args.append(arg_name)
        elif isinstance(schema, dict):
            properties = schema.get('properties', {})
            arg_names = list(properties.keys())
            required_args = schema.get('required', [])
        else:
            if hasattr(schema, 'properties'):
                properties = getattr(schema, 'properties', {})
                if isinstance(properties, dict):
                    arg_names = list(properties.keys())
            if hasattr(schema, 'required'):
                required_args = getattr(schema, 'required', [])
        
        if not arg_names:
            return None
        
        arg_str = ", ".join(arg_names)
        if required_args:
            req_str = ", ".join(required_args)
            return f"{arg_str} | Required: {req_str}"
        
        return arg_str

    def _mount_autocomplete(self) -> None:
        """Mount the AutoComplete overlay after the app is mounted."""
        try:
            input_widget = self.query_one("#input", NexusInput)
            logger.info(f"Creating AutoComplete for input widget with {len(input_widget.resources)} resources and {len(input_widget.commands)} commands")
            autocomplete = NexusAutoComplete(input_widget)
            self.mount(autocomplete)
            logger.info("AutoComplete overlay mounted successfully")
            
            # Copy preloaded prompt info cache to autocomplete
            if hasattr(self, '_prompt_info_cache'):
                autocomplete._prompt_cache = self._prompt_info_cache.copy()
                logger.info(f"Copied {len(self._prompt_info_cache)} cached prompt info items to autocomplete")
            if hasattr(self, '_prompt_schema_cache'):
                autocomplete._prompt_schema_cache = self._prompt_schema_cache.copy()
                logger.info(f"Copied {len(self._prompt_schema_cache)} cached prompt schemas to autocomplete")
        except Exception as e:
            logger.error(f"Failed to mount AutoComplete overlay: {e}")

    def _focus_input(self) -> None:
        """Helper to focus the input field."""
        try:
            input_field = self.query_one("#input", NexusInput)
            input_field.focus()
        except Exception as e:
            logger.warning(f"Could not focus input field: {e}")

    async def on_input_submitted(self, event) -> None:
        """
        Handle input submission (Enter key pressed).

        Args:
            event: The Input.Submitted event
        """
        logger.debug(f"Input submitted event received: id={event.input.id}, value='{event.value}'")

        # Prevent processing if already processing
        if self._processing:
            logger.warning("Already processing a query, ignoring new submission")
            return

        # Get the query text
        query = event.value.strip()

        logger.info(f"Received user query: '{query[:50]}{'...' if len(query) > 50 else ''}'")

        # Ignore empty queries
        if not query:
            logger.debug("Empty query, ignoring")
            return

        # Clear the input field
        event.input.value = ""

        # Process the query
        await self._process_query(query)

    async def _process_query(self, query: str):
        """
        Process a user query through the agent loop.

        Args:
            query: User's input text
        """
        logger.info(f"Starting to process query: '{query[:50]}{'...' if len(query) > 50 else ''}'")
        self._processing = True

        try:
            # Add user message to chat
            chat = self.query_one("#chat", ChatPanel)
            chat.add_user_message(query)
            logger.debug("Added user message to chat panel")

            # Add assistant message start marker
            chat.add_assistant_message_start()
            logger.debug("Added assistant message start marker")

            # Run the agent loop with UI callbacks
            logger.info(f"Running agent loop with query: {query[:100]}...")

            await self.agent_loop.run(query, callbacks={
                'on_stream_chunk': self._on_stream_chunk,
                'on_stream_complete': self._on_stream_complete,
                'on_tool_call': self._on_tool_call,
                'on_tool_result': self._on_tool_result,
                'on_start': self._on_start,
            })

            logger.info("Query processing completed successfully")

        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            chat = self.query_one("#chat", ChatPanel)
            chat.add_panel(
                f"[bold red]Error:[/] {str(e)}",
                title="Error",
                style="red"
            )

        finally:
            logger.debug("Cleaning up after query processing")
            self._processing = False

            # Refocus the input field
            self._focus_input()

    async def _on_start(self):
        """Called when agent loop starts processing."""
        logger.debug("Agent loop started processing")
        status = self.query_one("#status", StatusPanel)
        status.add_info_message("Processing query...")

    async def _on_stream_chunk(self, chunk: str):
        """
        Handle streaming chunks from the agent.

        Args:
            chunk: A piece of the assistant's response
        """
        logger.debug(f"Received stream chunk: '{chunk[:30]}{'...' if len(chunk) > 30 else ''}'")
        chat = self.query_one("#chat", ChatPanel)
        chat.add_assistant_chunk(chunk)

    async def _on_stream_complete(self):
        """Called when streaming is complete."""
        logger.debug("Stream completed")
        chat = self.query_one("#chat", ChatPanel)
        chat.finish_assistant_message()  # Properly finish the assistant message

    async def _on_tool_call(self, tool_name: str, params: dict):
        """
        Handle tool call notifications.

        Args:
            tool_name: Name of the tool being called
            params: Tool parameters
        """
        logger.info(f"Tool call: {tool_name} with params: {params}")
        status = self.query_one("#status", StatusPanel)
        status.add_tool_call(tool_name, params)

    async def _on_tool_result(self, tool_name: str, result: str, success: bool = True):
        """
        Handle tool execution results.

        Args:
            tool_name: Name of the tool that was executed
            result: Result text/data
            success: Whether the tool executed successfully
        """
        logger.info(f"Tool result: {tool_name} - success={success}, result length={len(str(result))}")
        status = self.query_one("#status", StatusPanel)
        status.add_tool_result(tool_name, result, success)

    def action_clear_chat(self) -> None:
        """Clear the chat panel (Ctrl+L)."""
        chat = self.query_one("#chat", ChatPanel)
        chat.clear_chat()
        chat.add_panel(
            "Chat history cleared",
            style="dim"
        )

    def update_resources(self, resources: list[str]):
        """
        Update the list of available resources.

        Args:
            resources: New list of resource IDs
        """
        self.resources = resources
        input_field = self.query_one("#input", NexusInput)
        input_field.update_resources(resources)

    def update_commands(self, commands: list[str]):
        """
        Update the list of available commands.

        Args:
            commands: New list of command names
        """
        self.commands = commands
        input_field = self.query_one("#input", NexusInput)
        input_field.update_commands(commands)
