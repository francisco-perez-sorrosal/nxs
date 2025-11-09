"""
ServiceContainer - Manages lifecycle and dependencies for TUI services.

This container centralizes the creation and wiring of all TUI services and handlers,
reducing complexity in NexusApp and improving testability.
"""

from typing import Callable, TYPE_CHECKING

from nxs.presentation.services.status_queue import StatusQueue
from nxs.presentation.services import (
    MCPCoordinator,
    PromptService,
    AutocompleteService,
    RefreshService,
)
from nxs.presentation.services.background_tasks import BackgroundTaskService
from nxs.presentation.handlers import (
    ConnectionHandler,
    QueryHandler,
    RefreshHandler,
)
from nxs.presentation.tui.query_manager import QueryManager
from nxs.application.artifact_manager import ArtifactManager
from nxs.domain.events import (
    EventBus,
    ConnectionStatusChanged,
    ReconnectProgress,
    ArtifactsFetched,
)
from nxs.domain.protocols import Cache
from nxs.infrastructure.cache import MemoryCache

if TYPE_CHECKING:
    from textual.app import App


class ServiceContainer:
    """
    Manages all TUI service lifecycle and dependencies.

    This container creates and wires together:
    - Services (StatusQueue, RefreshService, PromptService, etc.)
    - Handlers (ConnectionHandler, QueryHandler, RefreshHandler)
    - QueryManager
    - Event subscriptions

    Benefits:
    - Centralized dependency management
    - Easier testing (can inject mock container)
    - Reduced complexity in NexusApp
    """

    def __init__(
        self,
        app: "App",
        agent_loop,
        artifact_manager: ArtifactManager,
        event_bus: EventBus,
        *,
        prompt_info_cache: Cache[str, str | None] | None = None,
        prompt_schema_cache: Cache[str, tuple] | None = None,
    ):
        """
        Initialize the service container.

        Args:
            app: The Textual App instance (for accessing widgets)
            agent_loop: The agent loop instance
            artifact_manager: The ArtifactManager instance
            event_bus: The EventBus for event-driven communication
            prompt_info_cache: Optional cache for prompt info
            prompt_schema_cache: Optional cache for prompt schemas
        """
        self.app = app
        self.agent_loop = agent_loop
        self.artifact_manager = artifact_manager
        self.event_bus = event_bus

        # Initialize caches
        self.prompt_info_cache = prompt_info_cache or MemoryCache[str, str | None]()
        self.prompt_schema_cache = prompt_schema_cache or MemoryCache[str, tuple]()

        # Create all services and handlers
        self._create_services()
        self._create_handlers()
        self._create_query_manager()

    def _create_services(self) -> None:
        """Create all TUI services."""
        # Helper functions to get widgets (will be set by NexusApp)
        self._get_status_panel: Callable | None = None
        self._get_mcp_panel: Callable | None = None
        self._get_chat_panel: Callable | None = None
        self._get_input: Callable | None = None
        self._get_autocomplete: Callable | None = None
        self._on_resources_loaded: Callable | None = None
        self._on_commands_loaded: Callable | None = None
        self._focus_input: Callable | None = None
        self._mcp_initialized_getter: Callable | None = None

        # Create services (will be initialized fully after widget getters are set)
        self.status_queue: StatusQueue | None = None
        self.mcp_refresher: RefreshService | None = None
        self.prompt_service: PromptService | None = None
        self.autocomplete_service: AutocompleteService | None = None
        self.mcp_coordinator: MCPCoordinator | None = None
        self.background_tasks: BackgroundTaskService | None = None

    def set_widget_getters(
        self,
        get_status_panel: Callable,
        get_mcp_panel: Callable,
        get_chat_panel: Callable,
        get_input: Callable,
        get_autocomplete: Callable,
        on_resources_loaded: Callable,
        on_commands_loaded: Callable,
        focus_input: Callable,
        mcp_initialized_getter: Callable,
    ) -> None:
        """
        Set widget getter functions and create services that depend on them.

        This must be called after NexusApp.__init__ but before services are used.
        """
        self._get_status_panel = get_status_panel
        self._get_mcp_panel = get_mcp_panel
        self._get_chat_panel = get_chat_panel
        self._get_input = get_input
        self._get_autocomplete = get_autocomplete
        self._on_resources_loaded = on_resources_loaded
        self._on_commands_loaded = on_commands_loaded
        self._focus_input = focus_input
        self._mcp_initialized_getter = mcp_initialized_getter

        # Now create services with proper dependencies
        self.status_queue = StatusQueue(status_panel_getter=get_status_panel)

        self.mcp_refresher = RefreshService(
            artifact_manager=self.artifact_manager,
            mcp_panel_getter=get_mcp_panel,
        )

        self.prompt_service = PromptService(
            artifact_manager=self.artifact_manager,
            prompt_info_cache=self.prompt_info_cache,
            prompt_schema_cache=self.prompt_schema_cache,
        )

        self.autocomplete_service = AutocompleteService(
            app=self.app,
            input_getter=get_input,
            prompt_service=self.prompt_service,
            autocomplete_getter=get_autocomplete,
        )

        self.background_tasks = BackgroundTaskService(
            artifact_manager=self.artifact_manager,
            mcp_refresher=self.mcp_refresher,
        )

        self.mcp_coordinator = MCPCoordinator(
            artifact_manager=self.artifact_manager,
            status_queue=self.status_queue,
            on_resources_loaded=on_resources_loaded,
            on_commands_loaded=on_commands_loaded,
            prompt_service=self.prompt_service,
            mcp_refresher=self.mcp_refresher,
            on_background_task_start=lambda: self.background_tasks.start(mcp_initialized_getter),  # type: ignore[union-attr]
        )

    def _create_handlers(self) -> None:
        """Create all event handlers (after services are created)."""
        # Handlers will be created after widget getters are set
        self.connection_handler: ConnectionHandler | None = None
        self.refresh_handler: RefreshHandler | None = None
        self.query_handler: QueryHandler | None = None

    def create_handlers(self) -> None:
        """Create handlers after services are ready."""
        assert self.mcp_refresher is not None, "Services must be initialized first"
        assert self.status_queue is not None, "Services must be initialized first"
        assert self._get_chat_panel is not None, "Widget getters must be set first"

        self.connection_handler = ConnectionHandler(
            artifact_manager=self.artifact_manager,
            mcp_panel_getter=self._get_mcp_panel,  # type: ignore
            mcp_refresher=self.mcp_refresher,
        )

        self.refresh_handler = RefreshHandler(
            mcp_refresher=self.mcp_refresher,
        )

        self.query_handler = QueryHandler(
            agent_loop=self.agent_loop,
            chat_panel_getter=self._get_chat_panel,  # type: ignore
            status_queue=self.status_queue,
            mcp_initialized_getter=self._mcp_initialized_getter,  # type: ignore
            focus_input=self._focus_input,  # type: ignore
        )

    def _create_query_manager(self) -> None:
        """Create QueryManager (after handlers are created)."""
        self.query_manager: QueryManager | None = None

    def create_query_manager(self) -> None:
        """Create QueryManager after handlers are ready."""
        assert self.query_handler is not None, "Handlers must be created first"
        self.query_manager = QueryManager(processor=self.query_handler.process_query)

    def subscribe_events(self) -> None:
        """Wire up all event subscriptions."""
        assert self.connection_handler is not None, "Handlers must be created first"
        assert self.refresh_handler is not None, "Handlers must be created first"

        self.event_bus.subscribe(
            ConnectionStatusChanged,
            self.connection_handler.handle_connection_status_changed,
        )
        self.event_bus.subscribe(
            ReconnectProgress,
            self.connection_handler.handle_reconnect_progress,
        )
        self.event_bus.subscribe(
            ArtifactsFetched,
            self.refresh_handler.handle_artifacts_fetched,
        )

    async def start(self) -> None:
        """Start all services that need initialization."""
        assert self.query_manager is not None, "QueryManager must be created first"
        assert self.status_queue is not None, "Services must be initialized first"

        await self.query_manager.start()
        await self.status_queue.start()

    async def stop(self) -> None:
        """Stop all services gracefully."""
        if self.background_tasks:
            await self.background_tasks.stop()
        if self.query_manager:
            await self.query_manager.stop()
        if self.status_queue:
            await self.status_queue.stop()
