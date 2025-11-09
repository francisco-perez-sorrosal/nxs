"""
NexusApp - Main Textual application for the Nexus TUI.
"""

import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Container, Vertical, Horizontal
from textual.binding import Binding

from nxs.presentation.widgets.chat_panel import ChatPanel
from nxs.presentation.widgets.status_panel import StatusPanel
from nxs.presentation.widgets.input_field import NexusInput
from nxs.presentation.widgets.mcp_panel import MCPPanel
from nxs.presentation.services import ServiceContainer
from nxs.application.artifact_manager import ArtifactManager
from nxs.domain.events import EventBus
from nxs.domain.protocols import Cache
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
        self.event_bus = event_bus or artifact_manager.event_bus or EventBus()
        self.artifact_manager.event_bus = self.event_bus

        # Create ServiceContainer to manage all services, handlers, and dependencies
        self.services = ServiceContainer(
            app=self,
            agent_loop=agent_loop,
            artifact_manager=artifact_manager,
            event_bus=self.event_bus,
            prompt_info_cache=prompt_info_cache,
            prompt_schema_cache=prompt_schema_cache,
        )

        # Set widget getters for services that need them
        self.services.set_widget_getters(
            get_status_panel=self._get_status_panel,
            get_mcp_panel=self._get_mcp_panel,
            get_chat_panel=self._get_chat_panel,
            get_input=self._get_input,
            get_autocomplete=self._get_autocomplete,
            on_resources_loaded=self._on_resources_loaded,
            on_commands_loaded=self._on_commands_loaded,
            focus_input=self._focus_input,
            mcp_initialized_getter=lambda: self._mcp_initialized,
        )

        # Create handlers and query manager
        self.services.create_handlers()
        self.services.create_query_manager()

        # Subscribe to all events
        self.services.subscribe_events()

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

        # Verify services are initialized
        assert self.services.status_queue is not None, "Services should be initialized"
        assert self.services.autocomplete_service is not None, "Services should be initialized"

        # Start all services (QueryManager, StatusQueue, etc.)
        await self.services.start()

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
        await self.services.status_queue.add_info_message("Initializing MCP connections...")

        # Initialize MCP connections asynchronously in the background
        # This allows the TUI to appear immediately without blocking
        asyncio.create_task(self._initialize_mcp_connections_async())

        # Mount AutoComplete overlay after the app is fully mounted
        self.call_after_refresh(self.services.autocomplete_service.mount_autocomplete)

        # Focus the input field after the first render
        self.call_after_refresh(self._focus_input)

    async def _initialize_mcp_connections_async(self) -> None:
        """
        Initialize MCP connections asynchronously in the background.

        This runs after the TUI is displayed, allowing the UI to appear
        immediately without blocking on MCP connection setup.
        """
        logger.info("Starting asynchronous MCP connection initialization")

        # Verify services are initialized
        assert self.services.mcp_coordinator is not None, "Services should be initialized"

        # Use MCPCoordinator to perform full initialization
        # This includes: connections, resources/commands, prompt preloading,
        # panel refresh, and starting background tasks
        resources, commands = await self.services.mcp_coordinator.initialize_and_load()

        # Store resources and commands
        self.resources = resources
        self.commands = commands

        # Mark MCP as initialized
        self._mcp_initialized = True
        logger.info("MCP connection initialization completed")

    def _on_resources_loaded(self, resources: list[str]) -> None:
        """
        Callback when resources are loaded.

        Args:
            resources: List of resource URIs
        """
        assert self.services.autocomplete_service is not None, "Services should be initialized"
        self.resources = resources
        self.services.autocomplete_service.update_resources(resources)

    def _on_commands_loaded(self, commands: list[str]) -> None:
        """
        Callback when commands are loaded.

        Args:
            commands: List of command names
        """
        assert self.services.autocomplete_service is not None, "Services should be initialized"
        self.commands = commands
        self.services.autocomplete_service.update_commands(commands)

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
            from nxs.presentation.widgets.autocomplete import NexusAutoComplete
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
            # MCP connections are still initializing - show message
            # The query will proceed immediately, tools will be available when servers connect
            chat.add_panel(
                "[yellow]⏳ MCP tools are still loading in the background.[/]\n"
                "Your query is being processed now. Tools will be available once servers connect.",
                title="Tools Loading",
                style="yellow"
            )

        try:
            assert self.services.query_manager is not None, "QueryManager should be initialized"
            query_id = await self.services.query_manager.enqueue(query)
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

        # Stop all services (QueryManager, StatusQueue, etc.)
        await self.services.stop()

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
        assert self.services.autocomplete_service is not None, "Services should be initialized"
        self.resources = resources
        self.services.autocomplete_service.update_resources(resources)

    def update_commands(self, commands: list[str]):
        """
        Update the list of available commands.

        Args:
            commands: New list of command names
        """
        assert self.services.autocomplete_service is not None, "Services should be initialized"
        self.commands = commands
        self.services.autocomplete_service.update_commands(commands)

