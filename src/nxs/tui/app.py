"""
NexusApp - Main Textual application for the Nexus TUI.
"""

import asyncio
import time
from typing import Callable
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Container, Vertical, Horizontal
from textual.binding import Binding

from .widgets.chat_panel import ChatPanel
from .widgets.status_panel import StatusPanel
from .widgets.input_field import NexusInput
from .widgets.autocomplete import NexusAutoComplete
from .widgets.mcp_panel import MCPPanel
from .query_manager import QueryManager
from .status_queue import StatusQueue
from .services.mcp_refresher import MCPRefresher
from nxs.core.artifact_manager import ArtifactManager
from nxs.core.events import (
    ArtifactsFetched,
    ConnectionStatusChanged,
    EventBus,
    ReconnectProgress,
)
from nxs.core.cache import Cache, MemoryCache
from nxs.mcp_client.client import ConnectionStatus
from nxs.logger import get_logger

logger = get_logger("nexus_tui")


class NexusApp(App):
    """
    The main Nexus TUI application.

    Layout:
    ┌─────────────────────────────┬──────────┐
    │         Header              │          │
    ├─────────────────────────────┼──────────┤
    │                             │          │
    │      Chat Panel             │   MCP    │
    │     (scrollable)            │  Panel   │
    │                             │(servers, │
    ├─────────────────────────────┤ artifacts│
    │    Status Panel             │)         │
    │     (scrollable)            │          │
    ├─────────────────────────────┤          │
    │      Input Field            │          │
    ├─────────────────────────────┼──────────┤
    │         Footer              │          │
    └─────────────────────────────┴──────────┘
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
        event_bus: EventBus | None = None,
        prompt_info_cache: Cache[str, str | None] | None = None,
        prompt_schema_cache: Cache[str, tuple] | None = None,
    ):
        """
        Initialize the Nexus TUI application.

        Args:
            agent_loop: The agent loop instance (core.chat.AgentLoop)
            artifact_manager: The ArtifactManager instance for accessing resources and commands
            event_bus: Optional EventBus instance. If None, a new EventBus will be created.
                      The EventBus is used for decoupled event-driven communication between
                      the core layer (ArtifactManager) and the UI layer (NexusApp).
            prompt_info_cache: Optional Cache instance for caching prompt argument info strings.
                              If None, a MemoryCache will be created.
            prompt_schema_cache: Optional Cache instance for caching prompt schema tuples.
                                If None, a MemoryCache will be created.
        """
        super().__init__()
        self.agent_loop = agent_loop
        self.artifact_manager = artifact_manager
        self.resources: list[str] = []
        self.commands: list[str] = []
        self._mcp_initialized = False  # Track MCP initialization status

        # Create or use provided event bus
        self.event_bus = event_bus or EventBus()

        # Set up event bus in ArtifactManager if not already set
        if self.artifact_manager.event_bus is None:
            self.artifact_manager.event_bus = self.event_bus

        # Initialize prompt caches
        self._prompt_info_cache: Cache[str, str | None] = (
            prompt_info_cache or MemoryCache[str, str | None]()
        )
        self._prompt_schema_cache: Cache[str, tuple] = (
            prompt_schema_cache or MemoryCache[str, tuple]()
        )

        # Subscribe to events
        self.event_bus.subscribe(ConnectionStatusChanged, self._on_connection_status_changed)
        self.event_bus.subscribe(ReconnectProgress, self._on_reconnect_progress)
        self.event_bus.subscribe(ArtifactsFetched, self._on_artifacts_fetched)

        # Initialize QueryManager with the processor function
        self.query_manager = QueryManager(processor=self._process_query)
        # Initialize StatusQueue for asynchronous status updates
        self.status_queue = StatusQueue(status_panel_getter=self._get_status_panel)
        # Initialize MCPRefresher for managing panel refresh operations
        self.mcp_refresher = MCPRefresher(
            artifact_manager=artifact_manager,
            mcp_panel_getter=self._get_mcp_panel
        )

        # Debounce reconnect progress updates
        self._last_reconnect_progress_update: dict[str, float] = {}
        self._reconnect_progress_debounce_interval = 1.0  # Minimum 1 second between updates

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header()

        with Container(id="app-container"):
            with Horizontal(id="main-horizontal"):
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
                
                # MCP servers panel on the right
                yield MCPPanel(id="mcp-panel")

        yield Footer()

    async def on_mount(self) -> None:
        """Called when the app is mounted."""
        logger.info("Nexus TUI mounted and ready")

        # Start the QueryManager to begin processing queries
        await self.query_manager.start()
        # Start the StatusQueue for asynchronous status updates
        await self.status_queue.start()

        # Show welcome message immediately (TUI is ready)
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

        # Show loading message in status panel
        await self.status_queue.add_info_message("Initializing MCP connections...")

        # Note: Event subscriptions are set up in __init__ via event_bus.subscribe()
        # This ensures we catch all events published during initialization

        # Initialize MCP connections asynchronously in the background
        # This allows the TUI to appear immediately without blocking
        asyncio.create_task(self._initialize_mcp_connections_async())

        # Mount AutoComplete overlay after the app is fully mounted
        self.call_after_refresh(self._mount_autocomplete)
        
        # Focus the input field after the first render
        self.call_after_refresh(self._focus_input)

    async def _initialize_mcp_connections_async(self) -> None:
        """
        Initialize MCP connections asynchronously in the background.
        
        This runs after the TUI is displayed, allowing the UI to appear
        immediately without blocking on MCP connection setup.
        """
        logger.info("Starting asynchronous MCP connection initialization")
        
        try:
            # Initialize MCP connections
            await self.status_queue.add_info_message("Connecting to MCP servers...")
            await self.artifact_manager.initialize()
            
            server_count = len(self.artifact_manager.clients)
            if server_count > 0:
                await self.status_queue.add_success_message(
                    f"Connected to {server_count} MCP server(s)"
                )
            else:
                await self.status_queue.add_info_message("No MCP servers configured")
            
            # Load resources and commands from ArtifactManager
            await self.status_queue.add_info_message("Loading resources and commands...")
            
            try:
                self.resources = await self.artifact_manager.get_resource_list()
                self.commands = await self.artifact_manager.get_command_names()
                logger.info(f"Loaded {len(self.resources)} resources and {len(self.commands)} commands")
                
                # Update the input widget with loaded resources and commands
                input_widget = self.query_one("#input", NexusInput)
                input_widget.update_resources(self.resources)
                input_widget.update_commands(self.commands)
                
                # Preload prompt information for all commands
                # This ensures arguments are available when dropdown is shown
                await self._preload_all_prompt_info()
                
                if self.resources or self.commands:
                    await self.status_queue.add_success_message(
                        f"Loaded {len(self.resources)} resource(s) and {len(self.commands)} command(s)"
                    )
                else:
                    await self.status_queue.add_info_message("No resources or commands found")
                    
            except Exception as e:
                logger.error(f"Failed to load resources and commands: {e}")
                await self.status_queue.add_error_message(
                    f"Failed to load resources/commands: {str(e)}"
                )
            
            # Mark MCP as initialized
            self._mcp_initialized = True
            logger.info("MCP connection initialization completed")

            # Update MCP panel with server information
            await self.mcp_refresher.refresh()

            # Start periodic refresh task to check for missing artifacts
            asyncio.create_task(self._periodic_artifact_refresh())
            
        except Exception as e:
            logger.error(f"Error during MCP connection initialization: {e}", exc_info=True)
            await self.status_queue.add_error_message(f"MCP initialization error: {str(e)}")
            
            # Still try to update UI even if initialization failed
            # (some servers might have connected successfully)
            try:
                self.resources = await self.artifact_manager.get_resource_list()
                self.commands = await self.artifact_manager.get_command_names()
                input_widget = self.query_one("#input", NexusInput)
                input_widget.update_resources(self.resources)
                input_widget.update_commands(self.commands)
            except Exception as load_error:
                logger.error(f"Failed to load resources after initialization error: {load_error}")
            
            # Try to update MCP panel even if initialization had errors
            try:
                await self.mcp_refresher.refresh()
            except Exception as panel_error:
                logger.error(f"Failed to update MCP panel: {panel_error}")
    
    def _on_connection_status_changed(self, event: ConnectionStatusChanged) -> None:
        """
        Handle connection status change event from ArtifactManager.
        
        This event handler is called whenever a server's connection status changes.
        It updates the MCP panel to reflect the new status.
        
        Args:
            event: ConnectionStatusChanged event
        """
        server_name = event.server_name
        status = event.status
        logger.info(f"Connection status changed for {server_name}: {status.value}")
        
        # Check if this is a real status change (not just setting to already-connected)
        try:
            client = self.artifact_manager.clients.get(server_name)
            if client and status == ConnectionStatus.CONNECTED:
                # Check if already connected and has artifacts
                cached = self.artifact_manager.get_cached_artifacts(server_name)
                if cached and client.is_connected:
                    total_cached = (
                        len(cached.get("tools", []))
                        + len(cached.get("prompts", []))
                        + len(cached.get("resources", []))
                    )
                    if total_cached > 0:
                        # Already connected with artifacts, don't refresh unnecessarily
                        logger.debug(
                            f"Server {server_name} already connected with {total_cached} artifact(s), skipping refresh"
                        )
                        # Still update reconnect info to clear any stale progress
                        try:
                            mcp_panel = self.query_one("#mcp-panel", MCPPanel)
                            if client:
                                # reconnect_info is implementation-specific, not in protocol
                                reconnect_info = client.reconnect_info  # type: ignore[attr-defined]
                                mcp_panel.update_reconnect_info(server_name, reconnect_info)
                                self.mcp_refresher.schedule_refresh()
                        except Exception:
                            pass
                        return
        except Exception:
            pass  # Continue with refresh if check fails
        
        # Update MCP panel status
        try:
            mcp_panel = self.query_one("#mcp-panel", MCPPanel)
            mcp_panel.update_server_status(server_name, status)
            
            # Update reconnect info from client
            client = self.artifact_manager.clients.get(server_name)
            if client:
                # reconnect_info is implementation-specific, not in protocol
                reconnect_info = client.reconnect_info  # type: ignore[attr-defined]
                mcp_panel.update_reconnect_info(server_name, reconnect_info)
            
            # Update last check time when status changes
            self.artifact_manager.update_server_last_check(server_name)
            
            # Refresh the panel with current data
            # For CONNECTED status, add a small delay to ensure session is fully ready
            # This is especially important during reconnection when artifacts need to be re-fetched
            if status == ConnectionStatus.CONNECTED:
                # Delay refresh slightly to ensure session is ready after initialization
                self.mcp_refresher.schedule_refresh(server_name=server_name, delay=0.5)
            elif status == ConnectionStatus.DISCONNECTED:
                # Clear fetch status and artifacts cache when disconnected
                mcp_panel.clear_fetch_status(server_name)
                self.artifact_manager.clear_artifacts_cache(server_name)
                # Refresh panel immediately to show artifacts are gone
                self.mcp_refresher.schedule_refresh()
            else:
                # For other statuses (CONNECTING, RECONNECTING, ERROR), refresh immediately
                self.mcp_refresher.schedule_refresh()
        except Exception as e:
            logger.error(f"Error updating MCP panel status: {e}")

    def _on_reconnect_progress(self, event: ReconnectProgress) -> None:
        """
        Handle reconnection progress event from ArtifactManager.
        
        This event handler is called periodically during reconnection to update progress information.
        Debounced to prevent creating too many refresh tasks.
        
        Args:
            event: ReconnectProgress event
        """
        server_name = event.server_name
        current_time = time.time()
        
        # Debounce: only update if enough time has passed since last update for this server
        last_update = self._last_reconnect_progress_update.get(server_name, 0)
        if current_time - last_update < self._reconnect_progress_debounce_interval:
            return  # Skip this update to avoid too many refresh tasks
        
        self._last_reconnect_progress_update[server_name] = current_time
        logger.debug(
            f"Reconnection progress for {server_name}: attempt {event.attempts}/{event.max_attempts}, "
            f"retry in {event.next_retry_delay:.1f}s"
        )
        
        try:
            mcp_panel = self.query_one("#mcp-panel", MCPPanel)
            client = self.artifact_manager.clients.get(server_name)
            if client:
                # reconnect_info is implementation-specific, not in protocol
                reconnect_info = client.reconnect_info  # type: ignore[attr-defined]
                mcp_panel.update_reconnect_info(server_name, reconnect_info)
                # Schedule refresh with task management to prevent accumulation
                self.mcp_refresher.schedule_refresh()
        except Exception as e:
            logger.debug(f"Error updating reconnect progress for {server_name}: {e}")

    def _on_artifacts_fetched(self, event: ArtifactsFetched) -> None:
        """
        Handle artifacts fetched event from ArtifactManager.
        
        This event handler is called when artifacts are fetched for a server.
        It schedules a refresh of the MCP panel if artifacts changed.
        
        Args:
            event: ArtifactsFetched event
        """
        if event.changed:
            logger.debug(
                f"Artifacts changed for {event.server_name}, scheduling refresh"
            )
            self.mcp_refresher.schedule_refresh(server_name=event.server_name)
        else:
            logger.debug(
                f"Artifacts fetched for {event.server_name} (no changes)"
            )

    
    async def _preload_all_prompt_info(self) -> None:
        """Preload prompt argument information for all commands directly."""
        try:
            logger.info(f"Preloading prompt information for {len(self.commands)} commands...")
            loaded_count = 0
                
            for command in self.commands:
                prompt_info = await self.artifact_manager.find_prompt(command)
                if prompt_info:
                    prompt, server_name = prompt_info
                    # Store full prompt object for argument expansion
                    self._prompt_schema_cache.set(command, (prompt, server_name))
                    # Extract argument info string for display
                    arg_info = self._format_prompt_arguments(prompt)
                    self._prompt_info_cache.set(command, arg_info)
                    loaded_count += 1
                    logger.debug(f"Preloaded info for '{command}': {arg_info}")
            logger.info(f"Successfully preloaded prompt information for {loaded_count} commands")
            
            # Update autocomplete widget cache if it's already mounted
            try:
                # Use query to find autocomplete widget
                from nxs.tui.widgets.autocomplete import NexusAutoComplete
                autocomplete_list = self.query(NexusAutoComplete)
                if autocomplete_list:
                    autocomplete = autocomplete_list[0]
                    # Copy cache entries to autocomplete widget (which uses dicts)
                    self._copy_prompt_caches_to_autocomplete(autocomplete)
            except Exception as e:
                logger.debug(f"Autocomplete widget not found yet, will copy cache when mounted: {e}")
        except Exception as e:
            logger.error(f"Failed to preload prompt info: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _copy_prompt_caches_to_autocomplete(self, autocomplete) -> None:
        """Copy prompt caches to autocomplete widget.
        
        The autocomplete widget uses dict-based caches, so we need to convert
        from Cache instances to dicts by getting all known command entries.
        
        Args:
            autocomplete: The NexusAutoComplete widget instance
        """
        # Build dicts from cache by iterating through known commands
        prompt_info_dict: dict[str, str | None] = {}
        prompt_schema_dict: dict[str, tuple] = {}
        
        for command in self.commands:
            info = self._prompt_info_cache.get(command)
            if info is not None:
                prompt_info_dict[command] = info
            
            schema = self._prompt_schema_cache.get(command)
            if schema is not None:
                prompt_schema_dict[command] = schema
        
        if prompt_info_dict:
            autocomplete._prompt_cache = prompt_info_dict
            logger.info(f"Updated autocomplete prompt cache with {len(prompt_info_dict)} items")
        
        if prompt_schema_dict:
            autocomplete._prompt_schema_cache = prompt_schema_dict
            logger.info(f"Updated autocomplete prompt schema cache with {len(prompt_schema_dict)} items")
    
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
            
            # Copy preloaded prompt info cache to autocomplete (if available)
            # This may be called before prompts are loaded, so we check if cache has entries
            self._copy_prompt_caches_to_autocomplete(autocomplete)
        except Exception as e:
            logger.error(f"Failed to mount AutoComplete overlay: {e}")

    def _focus_input(self) -> None:
        """Helper to focus the input field."""
        try:
            input_field = self.query_one("#input", NexusInput)
            input_field.focus()
        except Exception as e:
            logger.warning(f"Could not focus input field: {e}")

    def _get_status_panel(self) -> StatusPanel:
        """Helper to get the status panel widget."""
        return self.query_one("#status", StatusPanel)

    def _get_mcp_panel(self) -> MCPPanel:
        """Helper to get the MCP panel widget."""
        return self.query_one("#mcp-panel", MCPPanel)

    async def on_input_submitted(self, event) -> None:
        """
        Handle input submission (Enter key pressed).

        Args:
            event: The Input.Submitted event
        """
        logger.debug(f"Input submitted event received: id={event.input.id}, value='{event.value}'")

        # Get the query text
        query = event.value.strip()

        logger.info(f"Received user query: '{query[:50]}{'...' if len(query) > 50 else ''}'")

        # Ignore empty queries
        if not query:
            logger.debug("Empty query, ignoring")
            return

        # Clear the input field immediately so user can continue typing
        event.input.value = ""

        # Refocus the input field immediately
        self._focus_input()

        # Add user message to chat immediately (in submission order)
        chat = self.query_one("#chat", ChatPanel)
        chat.add_user_message(query)

        # Enqueue the query for processing
        # Note: Assistant message start will be added when processing begins
        # to ensure correct buffer assignment for each query
        # The worker will process queries sequentially and display results in order
        
        # Check if MCP connections are ready (non-blocking check)
        if not self._mcp_initialized:
            # MCP connections are still initializing - show message but allow queuing
            # The query will wait in queue until connections are ready
            chat.add_panel(
                "[yellow]⏳ MCP connections are still initializing...[/]\n"
                "Your query will be processed once connections are ready.",
                title="Initializing",
                style="yellow"
            )
        
        try:
            query_id = await self.query_manager.enqueue(query)
            logger.debug(f"Added user message to chat panel (query_id={query_id})")
        except RuntimeError as e:
            logger.error(f"QueryManager not running: {e}")
            chat.add_panel(
                "[bold red]Error:[/] Query manager not initialized",
                title="Error",
                style="red"
            )

    async def _process_query(self, query: str, query_id: int):
        """
        Process a user query through the agent loop.

        Args:
            query: User's input text
            query_id: Sequential ID of the query for ordering
        """
        logger.info(f"Starting to process query (query_id={query_id}): '{query[:50]}{'...' if len(query) > 50 else ''}'")

        # Wait for MCP connections to be ready if they're still initializing
        if not self._mcp_initialized:
            logger.info("MCP connections not ready yet, waiting...")
            await self.status_queue.add_info_message("Waiting for MCP connections to be ready...")
            # Wait up to 30 seconds for MCP initialization
            for _ in range(300):  # 300 * 0.1s = 30s timeout
                await asyncio.sleep(0.1)
                if self._mcp_initialized:
                    break
            
            if not self._mcp_initialized:
                logger.warning("MCP connections still not ready after timeout")
                chat = self.query_one("#chat", ChatPanel)
                chat.add_panel(
                    "[bold red]Error:[/] MCP connections not ready. Please try again.",
                    title="Error",
                    style="red"
                )
                return

        try:
            # Add assistant message start marker when processing begins
            # This ensures the correct buffer is active when chunks arrive
            chat = self.query_one("#chat", ChatPanel)
            chat.add_assistant_message_start()
            logger.debug(f"Added assistant message start marker (query_id={query_id})")

            # Run the agent loop with UI callbacks
            # Note: User message was already added in on_input_submitted to ensure
            # it appears in submission order
            logger.info(f"Running agent loop with query (query_id={query_id}): {query[:100]}...")

            await self.agent_loop.run(query, callbacks={
                'on_stream_chunk': self._on_stream_chunk,
                'on_stream_complete': self._on_stream_complete,
                'on_tool_call': self._on_tool_call,
                'on_tool_result': self._on_tool_result,
                'on_start': self._on_start,
            })

            logger.info(f"Query processing completed successfully (query_id={query_id})")

        except Exception as e:
            logger.error(f"Error processing query (query_id={query_id}): {e}", exc_info=True)
            chat = self.query_one("#chat", ChatPanel)
            chat.add_panel(
                f"[bold red]Error:[/] {str(e)}",
                title="Error",
                style="red"
            )
        finally:
            logger.debug(f"Cleaning up after query processing (query_id={query_id})")
            
            # Refocus the input field so user can continue typing
            self._focus_input()

    async def _on_start(self):
        """Called when agent loop starts processing."""
        logger.debug("Agent loop started processing")
        await self.status_queue.add_info_message("Processing query...")

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
        await self.status_queue.add_tool_call(tool_name, params)

    async def _on_tool_result(self, tool_name: str, result: str, success: bool = True):
        """
        Handle tool execution results.

        Args:
            tool_name: Name of the tool that was executed
            result: Result text/data
            success: Whether the tool executed successfully
        """
        logger.info(f"Tool result: {tool_name} - success={success}, result length={len(str(result))}")
        await self.status_queue.add_tool_result(tool_name, result, success)

    async def action_quit(self) -> None:
        """Handle app quit - cleanup background tasks."""
        logger.info("Quitting application, cleaning up...")
        
        # Stop the QueryManager and StatusQueue
        await self.query_manager.stop()
        await self.status_queue.stop()
        
        # Exit the app
        self.exit()

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
    
    async def _periodic_artifact_refresh(self) -> None:
        """
        Periodically check for connected servers with no artifacts and refresh them.
        
        This helps catch cases where artifacts weren't loaded initially but are
        now available, or when reconnection happens but artifacts weren't refreshed.
        Also retries ERROR status servers periodically to allow recovery.
        
        Runs asynchronously every 30 seconds without blocking the UI.
        Only refreshes if artifacts have changed or if server had no artifacts before.
        """
        await asyncio.sleep(5.0)  # Initial delay before first check
        
        while self._mcp_initialized:
            try:
                # Check all servers asynchronously
                for server_name, client in self.artifact_manager.clients.items():
                    try:
                        # connection_status is implementation-specific, not in protocol
                        status = client.connection_status  # type: ignore[attr-defined]
                        
                        # Handle ERROR status servers - retry connection periodically (every 60 seconds)
                        if status == ConnectionStatus.ERROR:
                            # Check if we should retry (every 60 seconds)
                            last_check = self.artifact_manager.get_server_last_check(server_name)
                            time_since_check = time.time() - last_check
                            if time_since_check >= 60.0:
                                logger.info(f"Retrying connection for ERROR status server: {server_name}")
                                try:
                                    # retry_connection is implementation-specific, not in protocol
                                    await client.retry_connection(use_auth=False)  # type: ignore[attr-defined]
                                    # Update last check time
                                    self.artifact_manager.update_server_last_check(server_name)
                                except Exception as e:
                                    logger.debug(f"Error retrying connection for {server_name}: {e}")
                                    # Update last check time even on failure to avoid retrying too frequently
                                    self.artifact_manager.update_server_last_check(server_name)
                            continue
                        
                        # Handle connected servers - check for artifacts
                        if client.is_connected:
                            logger.debug(f"Periodic refresh check for {server_name}")
                            
                            # Update last check time
                            self.artifact_manager.update_server_last_check(server_name)
                            
                            # Get cached artifacts
                            cached_artifacts = self.artifact_manager.get_cached_artifacts(server_name)
                            cached_total = 0
                            if cached_artifacts:
                                cached_total = (
                                    len(cached_artifacts.get("tools", [])) +
                                    len(cached_artifacts.get("prompts", [])) +
                                    len(cached_artifacts.get("resources", []))
                                )
                            
                            # Only fetch if we don't have artifacts cached (to avoid unnecessary work)
                            if cached_total == 0:
                                # Fetch artifacts to see if they're available
                                artifacts = await self.artifact_manager.get_server_artifacts(server_name)
                                total = (
                                    len(artifacts.get("tools", [])) +
                                    len(artifacts.get("prompts", [])) +
                                    len(artifacts.get("resources", []))
                                )
                                
                                if total > 0:
                                    # Server has artifacts but we didn't have them cached, refresh the panel
                                    logger.info(f"Found {total} artifact(s) for {server_name} during periodic check (was 0) - refreshing panel")
                                    # Cache the artifacts
                                    self.artifact_manager.cache_artifacts(server_name, artifacts)
                                    # Refresh asynchronously without blocking
                                    self.mcp_refresher.schedule_refresh(server_name=server_name)
                            else:
                                # Already have artifacts cached, skip fetching to avoid unnecessary refresh
                                logger.debug(f"Server {server_name} already has {cached_total} artifact(s) cached, skipping periodic fetch")
                    except Exception as e:
                        logger.debug(f"Error during periodic refresh check for {server_name}: {e}")
                
                # Wait 30 seconds before next check (asynchronous sleep)
                await asyncio.sleep(30.0)
            except asyncio.CancelledError:
                logger.info("Periodic artifact refresh task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic artifact refresh: {e}")
                # Wait 30 seconds before retrying (asynchronous sleep)
                await asyncio.sleep(30.0)
