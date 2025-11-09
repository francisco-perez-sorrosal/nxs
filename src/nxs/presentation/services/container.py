"""
ServiceContainer - Manages lifecycle and dependencies for TUI services.

This container uses lazy initialization for services (created on first access)
while ensuring MCP connections are initialized eagerly so resources/prompts
are available immediately for autocomplete.
"""

from typing import Callable, TYPE_CHECKING

from nxs.presentation.services.status_queue import StatusQueue
from nxs.presentation.services import (
    PromptService,
    AutocompleteService,
    RefreshService,
)
from nxs.presentation.handlers import QueryHandler
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
from nxs.logger import get_logger

if TYPE_CHECKING:
    from textual.app import App

logger = get_logger("service_container")


class ServiceContainer:
    """
    Manages all TUI service lifecycle with lazy initialization.
    
    Services are created on first access (lazy), except MCP initialization
    which must be eager to ensure resources/prompts are available for
    autocomplete when users press @ or /.
    
    Benefits:
    - No multi-step initialization ceremony
    - Services created only when needed
    - Clear dependency order (enforced by properties)
    - MCP eagerly initialized for immediate availability
    """

    def __init__(
        self,
        app: "App",
        agent_loop,
        artifact_manager: ArtifactManager,
        event_bus: EventBus,
        *,
        # Widget getters (lambdas that return widgets)
        get_status_panel: Callable,
        get_mcp_panel: Callable,
        get_chat_panel: Callable,
        get_input: Callable,
        get_autocomplete: Callable,
        # Callbacks for MCP initialization
        on_resources_loaded: Callable[[list[str]], None],
        on_commands_loaded: Callable[[list[str]], None],
        focus_input: Callable[[], None],
        mcp_initialized_getter: Callable[[], bool],
        # Optional caches
        prompt_info_cache: Cache[str, str | None] | None = None,
        prompt_schema_cache: Cache[str, tuple] | None = None,
    ):
        """
        Initialize the service container.
        
        All widget getters and callbacks are provided at construction.
        Services are created lazily on first access via properties.
        
        Args:
            app: The Textual App instance
            agent_loop: The agent loop instance
            artifact_manager: The ArtifactManager instance
            event_bus: The EventBus for event-driven communication
            get_status_panel: Lambda to get status panel widget
            get_mcp_panel: Lambda to get MCP panel widget
            get_chat_panel: Lambda to get chat panel widget
            get_input: Lambda to get input widget
            get_autocomplete: Lambda to get autocomplete widget
            on_resources_loaded: Callback when resources are loaded
            on_commands_loaded: Callback when commands are loaded
            focus_input: Callback to focus input field
            mcp_initialized_getter: Lambda to check if MCP is initialized
            prompt_info_cache: Optional cache for prompt info
            prompt_schema_cache: Optional cache for prompt schemas
        """
        # Core dependencies
        self.app = app
        self.agent_loop = agent_loop
        self.artifact_manager = artifact_manager
        self.event_bus = event_bus
        
        # Widget getters (stored as lambdas)
        self._get_status_panel = get_status_panel
        self._get_mcp_panel = get_mcp_panel
        self._get_chat_panel = get_chat_panel
        self._get_input = get_input
        self._get_autocomplete = get_autocomplete
        
        # Callbacks
        self._on_resources_loaded = on_resources_loaded
        self._on_commands_loaded = on_commands_loaded
        self._focus_input = focus_input
        self._mcp_initialized_getter = mcp_initialized_getter
        
        # Caches
        self._prompt_info_cache = prompt_info_cache or MemoryCache[str, str | None]()
        self._prompt_schema_cache = prompt_schema_cache or MemoryCache[str, tuple]()
        
        # Services (created lazily via properties)
        self._status_queue: StatusQueue | None = None
        self._mcp_refresher: RefreshService | None = None
        self._prompt_service: PromptService | None = None
        self._autocomplete_service: AutocompleteService | None = None
        self._query_handler: QueryHandler | None = None
        self._query_manager: QueryManager | None = None
        
        # MCP initialization state
        self._mcp_initialized = False
        self._events_subscribed = False

    # -------------------------------------------------------------------------
    # Lazy Service Properties
    # -------------------------------------------------------------------------

    @property
    def status_queue(self) -> StatusQueue:
        """Get StatusQueue, creating it on first access."""
        if self._status_queue is None:
            self._status_queue = StatusQueue(
                status_panel_getter=self._get_status_panel
            )
        return self._status_queue

    @property
    def mcp_refresher(self) -> RefreshService:
        """Get RefreshService, creating it on first access."""
        if self._mcp_refresher is None:
            self._mcp_refresher = RefreshService(
                artifact_manager=self.artifact_manager,
                mcp_panel_getter=self._get_mcp_panel,
            )
        return self._mcp_refresher

    @property
    def prompt_service(self) -> PromptService:
        """Get PromptService, creating it on first access."""
        if self._prompt_service is None:
            self._prompt_service = PromptService(
                artifact_manager=self.artifact_manager,
                prompt_info_cache=self._prompt_info_cache,
                prompt_schema_cache=self._prompt_schema_cache,
            )
        return self._prompt_service

    @property
    def autocomplete_service(self) -> AutocompleteService:
        """Get AutocompleteService, creating it on first access."""
        if self._autocomplete_service is None:
            self._autocomplete_service = AutocompleteService(
                app=self.app,
                input_getter=self._get_input,
                prompt_service=self.prompt_service,  # Triggers lazy creation
                autocomplete_getter=self._get_autocomplete,
            )
        return self._autocomplete_service

    @property
    def query_handler(self) -> QueryHandler:
        """Get QueryHandler, creating it on first access."""
        if self._query_handler is None:
            self._query_handler = QueryHandler(
                agent_loop=self.agent_loop,
                chat_panel_getter=self._get_chat_panel,
                status_queue=self.status_queue,  # Triggers lazy creation
                mcp_initialized_getter=self._mcp_initialized_getter,
                focus_input=self._focus_input,
            )
        return self._query_handler

    @property
    def query_manager(self) -> QueryManager:
        """Get QueryManager, creating it on first access."""
        if self._query_manager is None:
            self._query_manager = QueryManager(
                processor=self.query_handler.process_query  # Triggers lazy creation
            )
        return self._query_manager

    # -------------------------------------------------------------------------
    # Lifecycle Management
    # -------------------------------------------------------------------------

    def subscribe_events(self) -> None:
        """
        Wire up all event subscriptions.
        
        Events are handled directly by services:
        - ConnectionStatusChanged → RefreshService
        - ReconnectProgress → RefreshService
        - ArtifactsFetched → RefreshService
        
        This is idempotent - can be called multiple times safely.
        """
        if self._events_subscribed:
            return
            
        self.event_bus.subscribe(
            ConnectionStatusChanged,
            self.mcp_refresher.handle_connection_status_changed,
        )
        self.event_bus.subscribe(
            ReconnectProgress,
            self.mcp_refresher.handle_reconnect_progress,
        )
        self.event_bus.subscribe(
            ArtifactsFetched,
            self.mcp_refresher.handle_artifacts_fetched,
        )
        
        self._events_subscribed = True
        logger.debug("Event subscriptions configured")

    async def start(self) -> None:
        """
        Start all services that need background tasks.
        
        This starts:
        - QueryManager (query processing worker)
        - StatusQueue (status update worker)
        """
        await self.query_manager.start()
        await self.status_queue.start()
        logger.info("Services started")

    async def stop(self) -> None:
        """Stop all services gracefully."""
        if self._mcp_refresher:
            await self._mcp_refresher.stop_periodic_refresh()
        if self._query_manager:
            await self._query_manager.stop()
        if self._status_queue:
            await self._status_queue.stop()
        logger.info("Services stopped")

    # -------------------------------------------------------------------------
    # MCP Initialization (Eager - must run before autocomplete is used)
    # -------------------------------------------------------------------------

    @property
    def is_mcp_initialized(self) -> bool:
        """Check if MCP connections are initialized."""
        return self._mcp_initialized

    async def initialize_mcp(self, use_auth: bool = False) -> tuple[list[str], list[str]]:
        """
        Initialize MCP connections and load resources/commands.
        
        This MUST be called eagerly (not lazy) to ensure resources and
        prompts are available when users press @ or / for autocomplete.
        
        This method:
        1. Initializes MCP connections via ArtifactManager
        2. Loads resources and commands
        3. Notifies callbacks (for autocomplete updates)
        4. Preloads prompt information (for argument completion)
        5. Refreshes MCP panel (shows connection status)
        6. Starts background periodic refresh task
        
        Args:
            use_auth: Whether to use OAuth authentication for remote servers
        
        Returns:
            Tuple of (resources, commands) lists
        """
        logger.info("Starting MCP connection initialization")

        try:
            # Initialize MCP connections
            await self.status_queue.add_info_message("Connecting to MCP servers...")
            await self.artifact_manager.initialize(use_auth=use_auth)

            server_count = len(self.artifact_manager.clients)
            if server_count > 0:
                await self.status_queue.add_success_message(
                    f"Connected to {server_count} MCP server(s)"
                )
            else:
                await self.status_queue.add_info_message("No MCP servers configured")

            # Load resources and commands
            await self.status_queue.add_info_message("Loading resources and commands...")

            try:
                resources = await self.artifact_manager.get_resource_list()
                commands = await self.artifact_manager.get_command_names()
                logger.info(f"Loaded {len(resources)} resources and {len(commands)} commands")

                # Notify callbacks (updates autocomplete)
                self._on_resources_loaded(resources)
                self._on_commands_loaded(commands)

                if resources or commands:
                    await self.status_queue.add_success_message(
                        f"Loaded {len(resources)} resource(s) and {len(commands)} command(s)"
                    )
                else:
                    await self.status_queue.add_info_message("No resources or commands found")

                # Preload prompt information for argument completion
                if commands:
                    try:
                        await self.prompt_service.preload_all(commands)
                        logger.info(f"Preloaded prompt information for {len(commands)} command(s)")
                    except Exception as e:
                        logger.error(f"Error preloading prompt information: {e}")

                # Update MCP panel with server information
                try:
                    await self.mcp_refresher.refresh()
                    logger.info("MCP panel refreshed successfully")
                except Exception as e:
                    logger.error(f"Error refreshing MCP panel: {e}")

                # Start background periodic refresh task
                try:
                    self.mcp_refresher.start_periodic_refresh(self._mcp_initialized_getter)
                    logger.info("Background periodic refresh started")
                except Exception as e:
                    logger.error(f"Error starting background periodic refresh: {e}")

                # Mark as initialized
                self._mcp_initialized = True
                logger.info("MCP connection initialization completed")

                return resources, commands

            except Exception as e:
                logger.error(f"Failed to load resources and commands: {e}")
                await self.status_queue.add_error_message(
                    f"Failed to load resources/commands: {str(e)}"
                )
                return [], []

        except Exception as e:
            logger.error(f"Error during MCP connection initialization: {e}", exc_info=True)
            await self.status_queue.add_error_message(f"MCP initialization error: {str(e)}")
            
            # Try to load resources/commands even if initialization had errors
            try:
                resources = await self.artifact_manager.get_resource_list()
                commands = await self.artifact_manager.get_command_names()
                self._on_resources_loaded(resources)
                self._on_commands_loaded(commands)
                return resources, commands
            except Exception as load_error:
                logger.error(f"Failed to load resources after initialization error: {load_error}")
                return [], []
