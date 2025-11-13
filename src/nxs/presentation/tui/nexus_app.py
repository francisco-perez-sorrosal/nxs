"""
NexusApp - Main Textual application for the Nexus TUI.
"""

import asyncio
from typing import Callable, Optional, Sequence
from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Header, Footer
from textual.containers import Container, Vertical, Horizontal
from textual.binding import Binding

from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from nxs.presentation.widgets.chat_panel import ChatPanel
from nxs.presentation.widgets.status_panel import StatusPanel
from nxs.presentation.widgets.reasoning_trace_panel import ReasoningTracePanel
from nxs.presentation.widgets.input_field import NexusInput
from nxs.presentation.widgets.mcp_panel import MCPPanel
from nxs.presentation.widgets.approval_overlay import ApprovalOverlay
from nxs.presentation.services import ServiceContainer
from nxs.application.artifact_manager import ArtifactManager
from nxs.application.approval import ApprovalManager, ApprovalRequest
from nxs.application.session import Session
from nxs.application.session_manager import SessionManager
from nxs.application.summarization import SummarizationService
from nxs.domain.events import EventBus
from nxs.domain.protocols import Cache
from nxs.logger import get_logger

logger = get_logger("nexus_tui")


class ShowApprovalRequest(Message):
    """Message to show an approval request dialog."""

    def __init__(self, request: ApprovalRequest) -> None:
        super().__init__()
        self.request = request


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
        approval_manager: ApprovalManager | None = None,
        event_bus: EventBus | None = None,
        prompt_info_cache: Cache[str, str | None] | None = None,
        prompt_schema_cache: Cache[str, tuple] | None = None,
        session_name: str = "default",
        session: Session | None = None,
        session_manager: SessionManager | None = None,
    ):
        """
        Initialize the Nexus TUI application.

        Args:
            agent_loop: The agent loop instance (core.chat.AgentLoop)
            artifact_manager: The ArtifactManager instance for accessing resources and commands
            approval_manager: Optional ApprovalManager for human-in-the-loop approvals.
                            If None, a new ApprovalManager will be created.
            event_bus: Optional EventBus instance. If None, a new EventBus will be created.
                      The EventBus is used for decoupled event-driven communication between
                      the core layer (ArtifactManager) and the UI layer (NexusApp).
            prompt_info_cache: Optional Cache instance for caching prompt argument info strings.
                              If None, a MemoryCache will be created.
            prompt_schema_cache: Optional Cache instance for caching prompt schema tuples.
                                If None, a MemoryCache will be created.
            session_name: Name of the active session (default: "default")
            session: Optional Session instance for metadata persistence
            session_manager: Optional SessionManager for summary management
        """
        super().__init__()
        self.agent_loop = agent_loop
        self.artifact_manager = artifact_manager
        self.approval_manager = approval_manager or ApprovalManager()
        self.resources: list[str] = []
        self.commands: list[str] = []
        self._mcp_initialized = False  # Track MCP initialization status
        self._session_name = session_name
        self.session = session
        self._summary_tasks: set[asyncio.Task] = set()
        self._last_displayed_summary: tuple[str, int] | None = None
        self._session_info_displayed = False
        self.session_manager = session_manager

        # Register approval callback
        self.approval_manager.set_callback(self._handle_approval_request)

        summarization_service = (
            session_manager.summarizer
            if session_manager is not None
            else SummarizationService(llm=agent_loop.llm)
        )
        self._summarization_service = summarization_service

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
            summarization_service=summarization_service,
        )

        # Subscribe to events (idempotent, can be called multiple times)
        self.services.subscribe_events()

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header()

        with Container(id="app-container"):
            with Horizontal(id="main-horizontal"):
                with Vertical(id="main-content"):
                    yield ChatPanel(session_name=self._session_name, id="chat")

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

        # Set up summarization cost tracking callback
        # This connects summarization costs to the session and reasoning trace panel
        self._setup_summarization_cost_tracking()

        # Get chat panel
        chat = self.query_one("#chat", ChatPanel)

        # Set up reasoning cost tracking callback
        self._setup_reasoning_cost_tracking()

        # Update chat panel with cost information if session exists
        if self.session:
            chat.update_cost_display(
                conversation_summary=self.session.get_conversation_cost_summary(),
                reasoning_summary=self.session.get_reasoning_cost_summary(),
                summarization_summary=self.session.get_summarization_cost_summary(),
            )

        # Check if there's existing conversation history
        existing_messages = self.agent_loop.conversation.get_messages()
        conversation_msg_count = len(existing_messages)

        if conversation_msg_count == 0:
            # New session - show welcome message
            chat.add_panel(
                "[bold]Welcome to Nexus![/]\n\n"
                "Type [cyan]@[/] to reference documents\n"
                "Type [cyan]/[/] to execute commands\n"
                "Press [cyan]Ctrl+Q[/] to quit\n"
                "Press [cyan]Ctrl+L[/] to clear chat\n"
                "Press [cyan]Ctrl+R[/] to toggle reasoning trace",
                title="Getting Started",
                style="green",
            )
            self._session_info_displayed = True
        else:
            logger.info("Loading session with %s existing messages", conversation_msg_count)

            metadata = self.session.metadata if self.session else None
            session_header = f"[bold cyan]Session Loaded:[/] {self._session_name}"
            if metadata and metadata.conversation_summary:
                summarised_up_to = min(metadata.summary_last_message_index or 0, conversation_msg_count)
                if metadata.summary_last_message_index and metadata.summary_last_message_index > conversation_msg_count:
                    metadata.summary_last_message_index = conversation_msg_count
                footer_notes: list[str] = []
                if summarised_up_to < conversation_msg_count:
                    footer_notes.append("[dim]⏳ Updating summary with the latest messages...[/]")
                self._display_summary(
                    metadata.conversation_summary,
                    summarized_messages=summarised_up_to,
                    total_messages=conversation_msg_count,
                    updated=False,
                    force_display=True,
                    session_header=session_header,
                    extra_footer_lines=footer_notes,
                )

                if summarised_up_to < conversation_msg_count:
                    self._start_summary_update()
            else:
                basic_summary = self._generate_basic_summary()
                self._display_summary(
                    basic_summary,
                    summarized_messages=0,
                    total_messages=conversation_msg_count,
                    updated=False,
                    force_display=True,
                    session_header=session_header,
                    status_override="[dim]⏳ Generating conversation summary...[/]",
                )
                self._start_summary_update(force=True)

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

        # Ensure summary metadata is synced before shutting down
        await self.ensure_summary_synced()

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
    
    def _setup_reasoning_cost_tracking(self) -> None:
        """Set up callback to track reasoning costs in session and chat panel.
        
        This callback:
        - Updates the session's reasoning_cost_tracker (separate from conversation/summarization)
        - Updates the chat panel header with all cost types
        """
        # Check if agent_loop is AdaptiveReasoningLoop
        if not hasattr(self.agent_loop, "set_reasoning_cost_callback"):
            logger.debug("Agent loop does not support reasoning cost tracking")
            return
        
        def on_reasoning_usage(usage: dict, cost: float) -> None:
            """Track reasoning API usage in the active session and update UI."""
            try:
                # Update session reasoning cost tracker (separate from conversation/summarization)
                if self.session and hasattr(self.session, "reasoning_cost_tracker"):
                    self.session.reasoning_cost_tracker.add_usage(
                        usage.get("input_tokens", 0),
                        usage.get("output_tokens", 0),
                        cost,
                    )
                
                # Update chat panel with all cost summaries
                try:
                    chat_panel = self._get_chat_panel()
                    if chat_panel and self.session:
                        chat_panel.update_cost_display(
                            conversation_summary=self.session.get_conversation_cost_summary(),
                            reasoning_summary=self.session.get_reasoning_cost_summary(),
                            summarization_summary=self.session.get_summarization_cost_summary(),
                        )
                except Exception as e:
                    logger.debug(f"Could not update chat panel: {e}")
                
                logger.debug(
                    f"Reasoning cost tracked: {usage.get('input_tokens', 0)} input, "
                    f"{usage.get('output_tokens', 0)} output tokens, ${cost:.6f}"
                )
            except Exception as e:
                logger.warning(f"Error tracking reasoning cost: {e}")
        
        # Set the callback on all reasoning components
        self.agent_loop.set_reasoning_cost_callback(on_reasoning_usage)
        logger.debug("Reasoning cost tracking callback configured")
    
    def _setup_summarization_cost_tracking(self) -> None:
        """Set up callback to track summarization costs in session and chat panel.
        
        This callback:
        - Updates the session's cost tracker (for total costs)
        - Updates the chat panel header with summarization costs separately
        """
        if not self._summarization_service:
            return
        
        # Track summarization costs separately for the chat panel
        summarization_totals = {
            "total_cost": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }
        
        def on_summarization_usage(usage: dict, cost: float) -> None:
            """Track summarization API usage in the active session and update UI."""
            try:
                # Update session summarization cost tracker (separate from conversation/reasoning)
                if self.session and hasattr(self.session, "summarization_cost_tracker"):
                    self.session.summarization_cost_tracker.add_usage(
                        usage.get("input_tokens", 0),
                        usage.get("output_tokens", 0),
                        cost,
                    )
                
                # Update chat panel with all cost summaries
                try:
                    chat_panel = self._get_chat_panel()
                    if chat_panel and self.session:
                        chat_panel.update_cost_display(
                            conversation_summary=self.session.get_conversation_cost_summary(),
                            reasoning_summary=self.session.get_reasoning_cost_summary(),
                            summarization_summary=self.session.get_summarization_cost_summary(),
                        )
                except Exception as e:
                    logger.debug(f"Could not update chat panel: {e}")
                
                logger.debug(
                    f"Summarization cost tracked: {usage.get('input_tokens', 0)} input, "
                    f"{usage.get('output_tokens', 0)} output tokens, ${cost:.6f}"
                )
            except Exception as e:
                logger.warning(f"Error tracking summarization cost: {e}")
        
        # Set the callback on the summarization service
        self._summarization_service.on_usage = on_summarization_usage
        logger.debug("Summarization cost tracking callback configured")

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
            "on_response_for_judgment": lambda response, strategy: reasoning_panel.on_response_for_judgment(response, strategy),
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
            # Phase 6: Tracker completion for persistence
            "on_tracker_complete": lambda tracker, query: self._on_tracker_complete(tracker, query),
            # Phase 6: Real-time progress updates
            "on_step_progress": lambda step_id, status, description: self._on_step_progress(
                step_id, status, description
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

    def _generate_basic_summary(self) -> str:
        """Generate a quick basic summary without AI (just stats)."""
        try:
            messages = self.agent_loop.conversation.get_messages()
            msg_count = len(messages)

            if msg_count == 0:
                return "No messages in conversation"

            user_msgs = sum(1 for m in messages if m.get("role") == "user")
            assistant_msgs = sum(1 for m in messages if m.get("role") == "assistant")
            return f"[bold]Messages:[/] {msg_count} total ({user_msgs} user, {assistant_msgs} assistant)"
        except Exception as e:
            logger.error("Failed to generate basic summary: %s", e, exc_info=True)
            return f"[yellow]{self.agent_loop.conversation.get_message_count()} messages in conversation[/]"

    def _start_summary_update(self, force: bool = False) -> None:
        """Schedule a background summary update task."""
        if not self.session or not self.session_manager:
            logger.debug("Session manager unavailable; skipping summary update.")
            return

        task = asyncio.create_task(self._run_summary_update(force=force))
        self._summary_tasks.add(task)

        def _cleanup(completed: asyncio.Task) -> None:
            self._summary_tasks.discard(completed)
            if completed.cancelled():
                return
            try:
                exc = completed.exception()
                if exc:
                    logger.error("Summary update task failed: %s", exc, exc_info=True)
            except Exception as error:  # pragma: no cover - defensive
                logger.error("Error processing summary task completion: %s", error, exc_info=True)

        task.add_done_callback(_cleanup)

    async def _run_summary_update(self, force: bool = False) -> None:
        """Run summary update via the session manager and display the result."""
        if not self.session or not self.session_manager:
            return

        result = await self.session_manager.update_session_summary(self.session, force=force)
        if result is None:
            return

        if result.summary:
            self._display_summary(
                result.summary,
                summarized_messages=result.messages_summarized,
                total_messages=result.total_messages,
                updated=bool(self._last_displayed_summary),
                force_display=force,
            )
        elif result.skipped:
            logger.debug(
                "Summary update skipped for session %s (messages=%s).",
                self.session.session_id,
                result.total_messages,
            )
        elif result.error and not result.skipped:
            self._show_summary_error(
                "Conversation summary unavailable at the moment. "
                "Try continuing the conversation to refresh it."
            )

    def _display_summary(
        self,
        summary_text: str,
        *,
        summarized_messages: int,
        total_messages: int,
        updated: bool = False,
        force_display: bool = False,
        session_header: str | None = None,
        status_override: str | None = None,
        extra_footer_lines: Sequence[str] | None = None,
    ) -> None:
        """Render the summary in the chat panel."""
        if not summary_text:
            return

        key = (summary_text, summarized_messages)
        if self._last_displayed_summary == key and not force_display:
            return

        if self._session_info_displayed and not force_display:
            self._last_displayed_summary = key
            return

        chat = self._get_chat_panel()
        status_line = status_override or (
            "[yellow]Summary pending update for recent messages[/]"
            if total_messages > summarized_messages
            else "[dim]Summary includes all messages so far[/]"
        )

        header_markup = session_header or f"[bold cyan]Session: {self._session_name}[/]"
        header = Text.from_markup(header_markup)
        stats = Text.from_markup(
            f"[dim]Messages summarised: {summarized_messages} of {total_messages}[/]"
        )
        summary_renderable = Markdown(summary_text, justify="left")
        status_text = Text.from_markup(status_line)
        additional_footer = [
            Text.from_markup(line) for line in (extra_footer_lines or [])
        ]
        prompt = Text.from_markup("[dim]Type your next message to continue...[/]")

        panel_content = Group(
            header,
            stats,
            Text(),
            summary_renderable,
            Text(),
            status_text,
            *additional_footer,
            prompt,
        )

        panel = Panel(
            panel_content,
            title="💡 Updated Conversation Summary" if updated else "💡 Conversation Summary",
            border_style="cyan",
            padding=(1, 2),
        )

        chat.write(panel)
        chat.write("\n")
        self._last_displayed_summary = key
        self._session_info_displayed = True

    def _show_summary_error(self, message: str) -> None:
        """Display summary error/info message in the chat panel."""
        chat = self._get_chat_panel()
        chat.add_panel(
            f"[yellow]{message}[/]",
            title="⚠️ Summary",
            style="yellow",
        )

    async def handle_conversation_updated(self) -> None:
        """Callback invoked when the conversation history changes."""
        if self.session and self.session_manager:
            self._start_summary_update()

    async def _wait_for_summary_tasks(self) -> None:
        """Wait for any in-flight summary tasks to complete."""
        if not self._summary_tasks:
            return

        pending = list(self._summary_tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def ensure_summary_synced(self) -> None:
        """Ensure conversation summary metadata is up to date."""
        await self._wait_for_summary_tasks()
        if self.session and self.session_manager:
            await self.session_manager.update_session_summary(self.session, force=False)

    def _on_tracker_complete(self, tracker, query: str) -> None:
        """
        Phase 6: Handle tracker completion for persistence.

        Saves the tracker to the session for persistence and displays
        progress information in the status panel.

        Args:
            tracker: ResearchProgressTracker instance
            query: Original user query
        """
        from nxs.utils import generate_query_id
        from nxs.application.progress_tracker import ResearchProgressTracker

        try:
            # Generate query ID for tracking
            query_id = generate_query_id(query)

            # Save tracker to session if available
            if self.session:
                self.session.save_tracker(query_id, tracker)
                logger.debug(f"Saved tracker for query: {query_id}")

                # Auto-save session with tracker
                if self.session_manager:
                    self.session_manager.save_active_session()
                    logger.debug("Auto-saved session with tracker")

            # Phase 6: Display progress in status panel
            status_queue = self.services.status_queue
            if status_queue:
                # Display progress summary
                asyncio.create_task(
                    self._display_tracker_progress(tracker, status_queue)
                )

        except Exception as e:
            logger.error(f"Error saving tracker: {e}", exc_info=True)

    async def _display_tracker_progress(self, tracker, status_queue) -> None:
        """
        Phase 6: Display tracker progress in status panel.

        Args:
            tracker: ResearchProgressTracker instance
            status_queue: StatusQueue for status updates
        """
        try:
            # Build tracker data for display (use Any to avoid type checking issues)
            from typing import Any

            tracker_data: dict[str, Any] = {
                "attempts": [
                    {
                        "strategy": a.strategy.value,
                        "quality_score": a.quality_score,
                        "status": a.status,
                    }
                    for a in tracker.attempts
                ],
            }

            # Add plan progress if available
            if tracker.plan:
                completed = len(tracker.plan.get_completed_steps())
                total = len(tracker.plan.steps)
                tracker_data["plan_progress"] = {
                    "completed": completed,
                    "total": total,
                }
                # Display plan progress with completed/pending steps
                completed_steps = [s.description for s in tracker.plan.get_completed_steps()]
                pending_steps = [s.description for s in tracker.plan.get_pending_steps()]
                await status_queue.add_plan_progress(completed_steps, pending_steps)

            # Add tool summary
            if tracker.tool_executions:
                successful = len([e for e in tracker.tool_executions if e.success])
                total_tools = len(tracker.tool_executions)
                tracker_data["tool_summary"] = {
                    "successful": successful,
                    "total": total_tools,
                }
                # Display tool execution log
                tool_exec_data = [
                    {
                        "tool_name": e.tool_name,
                        "success": e.success,
                        "execution_time_ms": e.execution_time_ms,
                        "result": (e.result[:100] + "..." if e.result and len(e.result) > 100 else e.result or ""),
                    }
                    for e in tracker.tool_executions
                ]
                await status_queue.add_tool_execution_log(tool_exec_data)

            # Add knowledge gaps
            if tracker.insights.knowledge_gaps:
                tracker_data["knowledge_gaps"] = tracker.insights.knowledge_gaps

            # Display progress summary
            await status_queue.add_divider()
            await status_queue.add_progress_summary(tracker_data)

        except Exception as e:
            logger.error(f"Error displaying tracker progress: {e}", exc_info=True)

    def _on_step_progress(self, step_id: str, status: str, description: str) -> None:
        """
        Phase 6: Handle real-time step progress updates.

        Args:
            step_id: Step ID
            status: Step status (pending, in_progress, completed, skipped, failed)
            description: Step description
        """
        try:
            status_queue = self.services.status_queue
            if status_queue:
                status_icon = {
                    "pending": "[yellow]○[/]",
                    "in_progress": "[cyan]⟳[/]",
                    "completed": "[green]✓[/]",
                    "skipped": "[dim]⊘[/]",
                    "failed": "[red]✗[/]",
                }.get(status, "○")

                asyncio.create_task(
                    status_queue.add_info_message(
                        f"{status_icon} Step: {description[:50]}... [{status}]"
                    )
                )
        except Exception as e:
            logger.debug(f"Error displaying step progress: {e}")

    def _handle_approval_request(self, request: ApprovalRequest) -> None:
        """Handle approval request by posting a message to show the dialog.

        This callback is invoked by ApprovalManager when approval is requested.
        It posts a message to the app to show the modal in the proper event loop context.

        Args:
            request: The approval request to handle
        """
        logger.info(f"=== APPROVAL CALLBACK TRIGGERED ===")
        logger.info(f"Posting ShowApprovalRequest message for: {request.id} - {request.title}")

        # Post a message to the app to handle in the main event loop
        self.post_message(ShowApprovalRequest(request))

    async def on_show_approval_request(self, message: ShowApprovalRequest) -> None:
        """Handle the ShowApprovalRequest message by displaying the unified approval dialog.

        This runs in the main Textual event loop. Since push_screen_wait requires a worker
        context, we spawn a worker to handle the modal dialog.

        Args:
            message: The approval request message
        """
        request = message.request

        logger.info(f"=== HANDLING APPROVAL REQUEST IN MAIN LOOP ===")
        logger.info(f"Request: {request.id} - {request.title}")
        logger.info(f"Request type: {request.type}")

        # Define worker function to show dialog and wait for response
        async def show_approval_worker() -> None:
            """Worker function to show approval dialog and handle response."""
            logger.info("Worker: Showing unified ApprovalOverlay...")

            try:
                response = await self.push_screen_wait(ApprovalOverlay(request))
                logger.info(f"=== DIALOG RETURNED ===")
                logger.info(f"Response approved: {response.approved}")
                logger.info(f"Response selected_option: {response.selected_option}")
                logger.info(f"Response metadata: {response.metadata}")

            except Exception as e:
                logger.error(f"Exception in push_screen_wait: {e}", exc_info=True)
                # Create a cancelled response
                from nxs.application.approval import ApprovalResponse

                response = ApprovalResponse(
                    request_id=request.id,
                    approved=False,
                    selected_option="Cancel",
                    metadata={"error": str(e)},
                )

            # Submit the response back to the approval manager
            logger.info(f"Worker: Submitting response to approval manager")
            self.approval_manager.submit_response(response)
            logger.info("Worker: Response submitted successfully")

        # Run the approval dialog in a worker (allows push_screen_wait to work)
        logger.info("Spawning worker to show approval dialog...")
        self.run_worker(show_approval_worker(), exclusive=True)
