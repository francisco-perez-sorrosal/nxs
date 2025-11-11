"""
NexusApp - Main Textual application for the Nexus TUI.
"""

import asyncio
from typing import Callable, Optional
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Container, Vertical, Horizontal
from textual.binding import Binding

from nxs.presentation.widgets.chat_panel import ChatPanel
from nxs.presentation.widgets.status_panel import StatusPanel
from nxs.presentation.widgets.reasoning_trace_panel import ReasoningTracePanel
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
    ┌─────────────────────────────────────────┬──────────┐
    │               Header                    │          │
    ├─────────────────────────────────────────┼──────────┤
    │                                         │          │
    │          Chat Panel                     │   MCP    │
    │         (scrollable)                    │  Panel   │
    │                                         │(servers, │
    ├─────────────────────────────────────────┤ artifacts│
    │    Reasoning Trace Panel (collapsible)  │)         │
    │         (scrollable, Ctrl+R to toggle)  │          │
    ├─────────────────────────────────────────┤          │
    │      Status Panel (tool execution)      │          │
    │           (scrollable)                  │          │
    ├─────────────────────────────────────────┤          │
    │          Input Field                    │          │
    ├─────────────────────────────────────────┼──────────┤
    │               Footer                    │          │
    └─────────────────────────────────────────┴──────────┘
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
        Binding("ctrl+r", "toggle_reasoning", "Toggle Reasoning", show=True),
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

        # Create ServiceContainer with all dependencies
        # Services are created lazily on first access via properties
        self.services = ServiceContainer(
            app=self,
            agent_loop=agent_loop,
            artifact_manager=artifact_manager,
            event_bus=self.event_bus,
            # Widget getters (lambdas that return widgets after compose())
            get_status_panel=self._get_status_panel,
            get_mcp_panel=self._get_mcp_panel,
            get_chat_panel=self._get_chat_panel,
            get_input=self._get_input,
            get_autocomplete=self._get_autocomplete,
            # Callbacks for MCP initialization
            on_resources_loaded=self._on_resources_loaded,
            on_commands_loaded=self._on_commands_loaded,
            focus_input=self._focus_input,
            mcp_initialized_getter=lambda: self._mcp_initialized,
            # Optional caches
            prompt_info_cache=prompt_info_cache,
            prompt_schema_cache=prompt_schema_cache,
        )

        # Subscribe to events (idempotent, can be called multiple times)
        self.services.subscribe_events()

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header()

        with Container(id="app-container"):
            with Horizontal(id="main-horizontal"):
                with Vertical(id="main-content"):
                    yield ChatPanel(id="chat")

                    # Reasoning trace panel (collapsible with Ctrl+R)
                    yield ReasoningTracePanel(id="reasoning-trace")

                    # Status panel for tool execution
                    yield StatusPanel(id="status")

                    # Create input widget
                    yield NexusInput(
                        resources=self.resources,
                        commands=self.commands,
                        artifact_manager=self.artifact_manager,
                        id="input",
                    )

                # MCP servers panel on the right
                yield MCPPanel(id="mcp-panel")

        yield Footer()

    async def on_mount(self) -> None:
        """Called when the app is mounted."""
        logger.info("Nexus TUI mounted and ready")

        # Start all services (QueryQueue, StatusQueue)
        # Services are created lazily on first access via properties
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
            style="green",
        )

        # Initialize MCP connections asynchronously in the background
        # This MUST run before autocomplete is used so resources/prompts are available
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

        # Use ServiceContainer to perform full MCP initialization
        # This includes: connections, resources/commands, prompt preloading,
        # panel refresh, and starting background periodic refresh task
        resources, commands = await self.services.initialize_mcp()

        # Store resources and commands
        self.resources = resources
        self.commands = commands

        # Mark MCP as initialized (also tracked in services)
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
                style="yellow",
            )

        try:
            assert self.services.query_queue is not None, "QueryQueue should be initialized"
            query_id = await self.services.query_queue.enqueue(query)
            logger.debug(f"Added user message to chat panel (query_id={query_id})")
        except RuntimeError as e:
            logger.error(f"QueryQueue not running: {e}")
            chat.add_panel("[bold red]Error:[/] Query queue not initialized", title="Error", style="red")

    async def action_quit(self) -> None:
        """Handle app quit - cleanup background tasks."""
        logger.info("Quitting application, cleaning up...")

        # Stop all services (QueryQueue, StatusQueue, etc.)
        await self.services.stop()

        # Exit the app
        self.exit()

    def action_clear_chat(self) -> None:
        """Clear the chat panel (Ctrl+L)."""
        chat = self._get_chat_panel()
        chat.clear_chat()
        chat.add_panel("Chat history cleared", style="dim")

    def action_toggle_reasoning(self) -> None:
        """Toggle the reasoning trace panel visibility (Ctrl+R)."""
        reasoning_panel = self.query_one("#reasoning-trace", ReasoningTracePanel)
        reasoning_panel.display = not reasoning_panel.display

    # ====================================================================
    # Reasoning Callback Routing
    # ====================================================================
    # These methods route reasoning events from AdaptiveReasoningLoop
    # to the ReasoningTracePanel widget
    # ====================================================================

    def _get_reasoning_trace_panel(self) -> ReasoningTracePanel:
        """Helper to get the reasoning trace panel widget."""
        return self.query_one("#reasoning-trace", ReasoningTracePanel)

    def get_reasoning_callbacks(self) -> dict[str, Callable]:
        """
        Get callbacks dict for routing reasoning events to the trace panel.

        Returns:
            Dictionary of callback functions for AdaptiveReasoningLoop
        """
        # Get the reasoning panel
        reasoning_panel = self._get_reasoning_trace_panel()

        # Return callback dictionary that routes events to the panel
        return {
            # Complexity analysis
            "on_analysis_start": lambda: reasoning_panel.on_analysis_start(),
            "on_analysis_complete": lambda complexity: reasoning_panel.on_analysis_complete(complexity),
            # Strategy selection
            "on_strategy_selected": lambda strategy, reason: reasoning_panel.on_strategy_selected(strategy, reason),
            # Planning
            "on_planning_start": lambda: reasoning_panel.on_planning_start(),
            "on_planning_complete": lambda count, mode: reasoning_panel.on_planning_complete(count, mode),
            # Quality evaluation
            "on_quality_check_start": lambda: reasoning_panel.on_quality_check_start(),
            "on_quality_check_complete": lambda evaluation: reasoning_panel.on_quality_check_complete(evaluation),
            # Auto-escalation
            "on_auto_escalation": lambda from_s, to_s, reason, conf: reasoning_panel.on_auto_escalation(
                from_s, to_s, reason, conf
            ),
            # Final response
            "on_final_response": lambda strategy, attempts, quality, escalated: reasoning_panel.on_final_response(
                strategy, attempts, quality, escalated
            ),
        }

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
