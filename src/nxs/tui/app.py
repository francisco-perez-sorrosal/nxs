"""
NexusApp - Main Textual application for the Nexus TUI.
"""

import asyncio
import time
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Container, Vertical, Horizontal
from textual.binding import Binding

from .widgets.chat_panel import ChatPanel
from .widgets.status_panel import StatusPanel
from .widgets.input_field import NexusInput
from .widgets.mcp_panel import MCPPanel
from .query_manager import QueryManager
from .status_queue import StatusQueue
from .services import (
    MCPCoordinator,
    PromptService,
    AutocompleteService,
    RefreshService,
)
from .handlers import (
    ConnectionHandler,
    QueryHandler,
    RefreshHandler,
)
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
        prompt_info_cache = prompt_info_cache or MemoryCache[str, str | None]()
        prompt_schema_cache = prompt_schema_cache or MemoryCache[str, tuple]()

        # Initialize StatusQueue for asynchronous status updates
        self.status_queue = StatusQueue(status_panel_getter=self._get_status_panel)

        # Initialize RefreshService for managing panel refresh operations
        self.mcp_refresher = RefreshService(
            artifact_manager=artifact_manager,
            mcp_panel_getter=self._get_mcp_panel
        )

        # Initialize services
        self.prompt_service = PromptService(
            artifact_manager=artifact_manager,
            prompt_info_cache=prompt_info_cache,
            prompt_schema_cache=prompt_schema_cache,
        )

        self.autocomplete_service = AutocompleteService(
            app=self,
            input_getter=self._get_input,
            autocomplete_getter=self._get_autocomplete,
        )

        self.mcp_coordinator = MCPCoordinator(
            artifact_manager=artifact_manager,
            status_queue=self.status_queue,
            on_resources_loaded=self._on_resources_loaded,
            on_commands_loaded=self._on_commands_loaded,
        )

        # Initialize handlers
        self.connection_handler = ConnectionHandler(
            artifact_manager=artifact_manager,
            mcp_panel_getter=self._get_mcp_panel,
            mcp_refresher=self.mcp_refresher,
        )

        self.refresh_handler = RefreshHandler(mcp_refresher=self.mcp_refresher)

        self.query_handler = QueryHandler(
            agent_loop=agent_loop,
            chat_panel_getter=self._get_chat_panel,
            status_queue=self.status_queue,
            mcp_initialized_getter=lambda: self._mcp_initialized,
            focus_input=self._focus_input,
        )

        # Initialize QueryManager with the processor function
        self.query_manager = QueryManager(processor=self.query_handler.process_query)

        # Subscribe to events via handlers
        self.event_bus.subscribe(
            ConnectionStatusChanged, self.connection_handler.handle_connection_status_changed
        )
        self.event_bus.subscribe(
            ReconnectProgress, self.connection_handler.handle_reconnect_progress
        )
        self.event_bus.subscribe(
            ArtifactsFetched, self.refresh_handler.handle_artifacts_fetched
        )

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

        # Initialize MCP connections asynchronously in the background
        # This allows the TUI to appear immediately without blocking
        asyncio.create_task(self._initialize_mcp_connections_async())

        # Mount AutoComplete overlay after the app is fully mounted
        self.call_after_refresh(self.autocomplete_service.mount_autocomplete)

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
            # Use MCPCoordinator to initialize connections and load resources/commands
            resources, commands = await self.mcp_coordinator.initialize()

            # Store resources and commands
            self.resources = resources
            self.commands = commands

            # Preload prompt information for all commands
            # This ensures arguments are available when dropdown is shown
            await self.prompt_service.preload_all(commands)

            # Copy prompt caches to autocomplete widget if it's already mounted
            prompt_info_dict, prompt_schema_dict = self.prompt_service.copy_caches_to_dicts(commands)
            self.autocomplete_service.copy_prompt_caches(prompt_info_dict, prompt_schema_dict)

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
                self._on_resources_loaded(self.resources)
                self._on_commands_loaded(self.commands)
            except Exception as load_error:
                logger.error(f"Failed to load resources after initialization error: {load_error}")

            # Try to update MCP panel even if initialization had errors
            try:
                await self.mcp_refresher.refresh()
            except Exception as panel_error:
                logger.error(f"Failed to update MCP panel: {panel_error}")

    def _on_resources_loaded(self, resources: list[str]) -> None:
        """
        Callback when resources are loaded.

        Args:
            resources: List of resource URIs
        """
        self.resources = resources
        self.autocomplete_service.update_resources(resources)

    def _on_commands_loaded(self, commands: list[str]) -> None:
        """
        Callback when commands are loaded.

        Args:
            commands: List of command names
        """
        self.commands = commands
        self.autocomplete_service.update_commands(commands)

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

    def _get_chat_panel(self) -> ChatPanel:
        """Helper to get the chat panel widget."""
        return self.query_one("#chat", ChatPanel)

    def _get_input(self) -> NexusInput:
        """Helper to get the input widget."""
        return self.query_one("#input", NexusInput)

    def _get_autocomplete(self):
        """Helper to get the autocomplete widget if mounted."""
        try:
            from nxs.tui.widgets.autocomplete import NexusAutoComplete
            autocomplete_list = self.query(NexusAutoComplete)
            if autocomplete_list:
                return autocomplete_list[0]
        except Exception:
            pass
        return None

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
        chat = self._get_chat_panel()
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
        chat = self._get_chat_panel()
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
        self.autocomplete_service.update_resources(resources)

    def update_commands(self, commands: list[str]):
        """
        Update the list of available commands.

        Args:
            commands: New list of command names
        """
        self.commands = commands
        self.autocomplete_service.update_commands(commands)

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
