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
from nxs.core.artifact_manager import ArtifactManager
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
        self._mcp_initialized = False  # Track MCP initialization status
        # Initialize QueryManager with the processor function
        self.query_manager = QueryManager(processor=self._process_query)
        # Initialize StatusQueue for asynchronous status updates
        self.status_queue = StatusQueue(status_panel_getter=self._get_status_panel)
        
        # Set up connection status change callback
        # Note: This will be set after artifact_manager is created in main.py
        # We'll set it in on_mount to ensure the TUI is ready

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

        # Set up connection status change callback
        # This must be done before initialization to catch all status changes
        self.artifact_manager.on_status_change = self._on_mcp_status_change
        self.artifact_manager.on_reconnect_progress = self._on_mcp_reconnect_progress

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
            await self._refresh_mcp_panel_with_status()
            
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
                await self._refresh_mcp_panel_with_status()
            except Exception as panel_error:
                logger.error(f"Failed to update MCP panel: {panel_error}")
    
    def _on_mcp_status_change(self, server_name: str, status: ConnectionStatus):
        """
        Handle connection status change for an MCP server.
        
        This callback is called whenever a server's connection status changes.
        It updates the MCP panel to reflect the new status and shows user-friendly messages.
        
        Args:
            server_name: Name of the server
            status: New connection status
        """
        logger.info(f"Connection status changed for {server_name}: {status.value}")
        
        # Update MCP panel with connection status (status messages are shown in MCP panel, not status panel)
        # No status queue messages for connection changes - they're shown in MCP panel
        
        # Check if this is a real status change (not just setting to already-connected)
        try:
            client = self.artifact_manager.clients.get(server_name)
            if client and status == ConnectionStatus.CONNECTED:
                # Check if already connected and has artifacts
                cached = self.artifact_manager.get_cached_artifacts(server_name)
                if cached and client.is_connected:
                    total_cached = len(cached.get("tools", [])) + len(cached.get("prompts", [])) + len(cached.get("resources", []))
                    if total_cached > 0:
                        # Already connected with artifacts, don't refresh unnecessarily
                        logger.debug(f"Server {server_name} already connected with {total_cached} artifact(s), skipping refresh")
                        # Still update reconnect info to clear any stale progress
                        try:
                            mcp_panel = self.query_one("#mcp-panel", MCPPanel)
                            if client:
                                reconnect_info = client.reconnect_info
                                mcp_panel.update_reconnect_info(server_name, reconnect_info)
                                asyncio.create_task(self._refresh_mcp_panel_with_status())
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
                reconnect_info = client.reconnect_info
                mcp_panel.update_reconnect_info(server_name, reconnect_info)
            
            # Update last check time when status changes
            self.artifact_manager.update_server_last_check(server_name)
            
            # Refresh the panel with current data
            # For CONNECTED status, add a small delay to ensure session is fully ready
            # This is especially important during reconnection when artifacts need to be re-fetched
            if status == ConnectionStatus.CONNECTED:
                # Delay refresh slightly to ensure session is ready after initialization
                asyncio.create_task(self._refresh_mcp_panel_with_status_delayed(server_name))
            elif status == ConnectionStatus.DISCONNECTED:
                # Clear fetch status and artifacts cache when disconnected
                mcp_panel.clear_fetch_status(server_name)
                self.artifact_manager.clear_artifacts_cache(server_name)
                # Refresh panel immediately to show artifacts are gone
                asyncio.create_task(self._refresh_mcp_panel_with_status())
            else:
                # For other statuses (CONNECTING, RECONNECTING, ERROR), refresh immediately
                asyncio.create_task(self._refresh_mcp_panel_with_status())
        except Exception as e:
            logger.error(f"Error updating MCP panel status: {e}")

    def _on_mcp_reconnect_progress(self, server_name: str, attempts: int, max_attempts: int, next_retry_delay: float):
        """
        Handle reconnection progress updates for an MCP server.
        
        This callback is called periodically during reconnection to update progress information.
        
        Args:
            server_name: Name of the server
            attempts: Current reconnection attempt number
            max_attempts: Maximum reconnection attempts
            next_retry_delay: Seconds until next retry attempt
        """
        logger.debug(f"Reconnection progress for {server_name}: attempt {attempts}/{max_attempts}, retry in {next_retry_delay:.1f}s")
        
        try:
            mcp_panel = self.query_one("#mcp-panel", MCPPanel)
            client = self.artifact_manager.clients.get(server_name)
            if client:
                reconnect_info = client.reconnect_info
                mcp_panel.update_reconnect_info(server_name, reconnect_info)
                # Refresh panel to show updated progress
                asyncio.create_task(self._refresh_mcp_panel_with_status())
        except Exception as e:
            logger.debug(f"Error updating reconnect progress for {server_name}: {e}")

    async def _refresh_mcp_panel_with_status_delayed(self, server_name: str) -> None:
        """
        Refresh the MCP panel with a small delay to ensure session is ready.
        
        This is used when status changes to CONNECTED to give the session
        time to be fully ready before fetching artifacts.
        
        Args:
            server_name: Name of the server being refreshed (for status messages)
        """
        # Small delay to ensure session is ready after initialization
        await asyncio.sleep(0.5)
        await self._refresh_mcp_panel_with_status(retry_on_empty=True, server_name=server_name)

    async def _refresh_mcp_panel_with_status(self, retry_on_empty: bool = False, server_name: str | None = None) -> None:
        """
        Refresh the MCP panel with current server data and statuses.
        
        Args:
            retry_on_empty: If True, retry fetching artifacts if they come back empty
                           for connected servers. This helps with reconnection scenarios.
            server_name: Optional specific server name to highlight in status messages
        """
        try:
            # Get current server statuses
            server_statuses = self.artifact_manager.get_server_statuses()
            
            # Track if we're specifically refreshing one server
            is_single_server_refresh = server_name is not None
            
            # Get artifacts for all servers or just one
            if is_single_server_refresh:
                # Fetch artifacts for all servers (preserve other servers' data)
                servers_data = await self.artifact_manager.get_all_servers_artifacts()
                
                # Show fetch status for the target server
                mcp_panel = self.query_one("#mcp-panel", MCPPanel)
                mcp_panel.set_fetch_status(server_name, "[dim]Fetching artifacts...[/]")
                await self._update_mcp_panel_display(mcp_panel, servers_data, server_statuses)
                
                # Fetch artifacts for the target server with retry
                artifacts = await self.artifact_manager.get_server_artifacts(
                    server_name,
                    retry_on_empty=retry_on_empty
                )
                servers_data[server_name] = artifacts
                
                # Check if artifacts changed
                if self.artifact_manager.have_artifacts_changed(server_name, artifacts):
                    # Cache the new artifacts
                    self.artifact_manager.cache_artifacts(server_name, artifacts)
                    
                    # Show success status
                    total_artifacts = len(artifacts.get("tools", [])) + len(artifacts.get("prompts", [])) + len(artifacts.get("resources", []))
                    if total_artifacts > 0:
                        mcp_panel.set_fetch_status(server_name, f"[green]✓ {total_artifacts} artifact(s)[/]")
                        # Clear status after 2 seconds
                        asyncio.create_task(self._clear_fetch_status_after_delay(server_name, 2.0))
                    else:
                        mcp_panel.set_fetch_status(server_name, "[dim]No artifacts[/]")
                    
                    await self._update_mcp_panel_display(mcp_panel, servers_data, server_statuses)
                    logger.debug(f"Artifacts changed for {server_name}, refreshed panel")
                else:
                    # Cache even if unchanged to keep it up to date
                    self.artifact_manager.cache_artifacts(server_name, artifacts)
                    logger.debug(f"Artifacts unchanged for {server_name}, skipping panel refresh")
            else:
                # Full refresh for all servers
                servers_data = await self.artifact_manager.get_all_servers_artifacts()
                
                # Cache all artifacts
                for name, artifacts in servers_data.items():
                    self.artifact_manager.cache_artifacts(name, artifacts)
                
                # Update panel
                mcp_panel = self.query_one("#mcp-panel", MCPPanel)
                await self._update_mcp_panel_display(mcp_panel, servers_data, server_statuses)
                logger.debug(f"Refreshed MCP panel with {len(servers_data)} server(s)")
                
        except Exception as e:
            logger.error(f"Error refreshing MCP panel: {e}")
            # Show error status if single server refresh
            if is_single_server_refresh and server_name:
                try:
                    mcp_panel = self.query_one("#mcp-panel", MCPPanel)
                    mcp_panel.set_fetch_status(server_name, f"[red]✗ Error: {str(e)[:30]}...[/]")
                except Exception:
                    pass
    
    async def _update_mcp_panel_display(
        self,
        mcp_panel: MCPPanel,
        servers_data: dict[str, dict[str, list[str]]],
        server_statuses: dict[str, ConnectionStatus]
    ) -> None:
        """
        Update the MCP panel display with server data and statuses.
        
        This is a helper method to avoid code duplication.
        """
        logger.debug(f"_update_mcp_panel_display: {len(servers_data)} servers in data, {len(server_statuses)} in statuses")
        
        # Get last check times from ArtifactManager
        # If servers_data is empty but we have server_statuses, use statuses to get check times
        server_names = set(servers_data.keys()) if servers_data else set(server_statuses.keys()) if server_statuses else set()
        server_last_check = {}
        for server_name in server_names:
            server_last_check[server_name] = self.artifact_manager.get_server_last_check(server_name)
        
        logger.debug(f"Calling update_servers with {len(servers_data)} servers, {len(server_statuses)} statuses")
        mcp_panel.update_servers(servers_data, server_statuses, server_last_check)
    
    async def _clear_fetch_status_after_delay(self, server_name: str, delay: float) -> None:
        """
        Clear the fetch status for a server after a delay.
        
        This runs asynchronously and doesn't block the UI.
        With the new per-server widget architecture, we only need to update that one server.
        
        Args:
            server_name: Name of the server
            delay: Delay in seconds before clearing status
        """
        await asyncio.sleep(delay)
        try:
            mcp_panel = self.query_one("#mcp-panel", MCPPanel)
            mcp_panel.clear_fetch_status(server_name)
            # No need to refresh entire panel - just that server widget is updated
        except Exception as e:
            logger.debug(f"Error clearing fetch status for {server_name}: {e}")
    
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
            
            # Update autocomplete widget cache if it's already mounted
            try:
                # Use query to find autocomplete widget
                from nxs.tui.widgets.autocomplete import NexusAutoComplete
                autocomplete_list = self.query(NexusAutoComplete)
                if autocomplete_list:
                    autocomplete = autocomplete_list[0]
                    if hasattr(self, '_prompt_info_cache') and self._prompt_info_cache:
                        autocomplete._prompt_cache = self._prompt_info_cache.copy()
                        logger.info(f"Updated autocomplete prompt cache with {len(self._prompt_info_cache)} items")
                    if hasattr(self, '_prompt_schema_cache') and self._prompt_schema_cache:
                        autocomplete._prompt_schema_cache = self._prompt_schema_cache.copy()
                        logger.info(f"Updated autocomplete prompt schema cache with {len(self._prompt_schema_cache)} items")
            except Exception as e:
                logger.debug(f"Autocomplete widget not found yet, will copy cache when mounted: {e}")
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
            
            # Copy preloaded prompt info cache to autocomplete (if available)
            # This may be called before prompts are loaded, so we check if cache exists
            if hasattr(self, '_prompt_info_cache') and self._prompt_info_cache:
                autocomplete._prompt_cache = self._prompt_info_cache.copy()
                logger.info(f"Copied {len(self._prompt_info_cache)} cached prompt info items to autocomplete")
            else:
                logger.debug("Prompt info cache not available yet when mounting autocomplete")
                
            if hasattr(self, '_prompt_schema_cache') and self._prompt_schema_cache:
                autocomplete._prompt_schema_cache = self._prompt_schema_cache.copy()
                logger.info(f"Copied {len(self._prompt_schema_cache)} cached prompt schemas to autocomplete")
            else:
                logger.warning("Prompt schema cache not available yet when mounting autocomplete - cache will be empty!")
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
                        status = client.connection_status
                        
                        # Handle ERROR status servers - retry connection periodically (every 60 seconds)
                        if status == ConnectionStatus.ERROR:
                            # Check if we should retry (every 60 seconds)
                            last_check = self.artifact_manager.get_server_last_check(server_name)
                            time_since_check = time.time() - last_check
                            if time_since_check >= 60.0:
                                logger.info(f"Retrying connection for ERROR status server: {server_name}")
                                try:
                                    await client.retry_connection(use_auth=False)
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
                                    asyncio.create_task(
                                        self._refresh_mcp_panel_with_status(server_name=server_name)
                                    )
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
