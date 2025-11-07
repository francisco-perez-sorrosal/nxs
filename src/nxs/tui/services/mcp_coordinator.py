"""
MCPCoordinator service for managing MCP initialization and lifecycle.

This service handles:
- MCP connection initialization
- Loading resources and commands
- Coordinating with other services (PromptService, AutocompleteService)
"""

from typing import TYPE_CHECKING, Callable

from nxs.core.artifact_manager import ArtifactManager
from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.tui.status_queue import StatusQueue

logger = get_logger("mcp_coordinator")


class MCPCoordinator:
    """
    Handles MCP initialization and lifecycle coordination.
    
    This service orchestrates the initialization of MCP connections,
    loading of resources and commands, and coordinates with other
    services like PromptService and AutocompleteService.
    """

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        status_queue: "StatusQueue",
        on_resources_loaded: Callable[[list[str]], None] | None = None,
        on_commands_loaded: Callable[[list[str]], None] | None = None,
    ):
        """
        Initialize the MCPCoordinator.

        Args:
            artifact_manager: The ArtifactManager instance
            status_queue: StatusQueue for status updates
            on_resources_loaded: Optional callback when resources are loaded
            on_commands_loaded: Optional callback when commands are loaded
        """
        self.artifact_manager = artifact_manager
        self.status_queue = status_queue
        self.on_resources_loaded = on_resources_loaded
        self.on_commands_loaded = on_commands_loaded
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if MCP connections are initialized."""
        return self._initialized

    async def initialize(self, use_auth: bool = False) -> tuple[list[str], list[str]]:
        """
        Initialize all MCP connections and load resources/commands.

        This method:
        1. Initializes MCP connections via ArtifactManager
        2. Loads resources and commands
        3. Calls callbacks to notify other components

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

            # Load resources and commands from ArtifactManager
            await self.status_queue.add_info_message("Loading resources and commands...")

            try:
                resources = await self.artifact_manager.get_resource_list()
                commands = await self.artifact_manager.get_command_names()
                logger.info(
                    f"Loaded {len(resources)} resources and {len(commands)} commands"
                )

                # Notify callbacks
                if self.on_resources_loaded:
                    self.on_resources_loaded(resources)
                if self.on_commands_loaded:
                    self.on_commands_loaded(commands)

                if resources or commands:
                    await self.status_queue.add_success_message(
                        f"Loaded {len(resources)} resource(s) and {len(commands)} command(s)"
                    )
                else:
                    await self.status_queue.add_info_message(
                        "No resources or commands found"
                    )

                # Mark as initialized
                self._initialized = True
                logger.info("MCP connection initialization completed")

                return resources, commands

            except Exception as e:
                logger.error(f"Failed to load resources and commands: {e}")
                await self.status_queue.add_error_message(
                    f"Failed to load resources/commands: {str(e)}"
                )
                # Return empty lists on error
                return [], []

        except Exception as e:
            logger.error(f"Error during MCP connection initialization: {e}", exc_info=True)
            await self.status_queue.add_error_message(
                f"MCP initialization error: {str(e)}"
            )
            # Try to load resources/commands even if initialization had errors
            try:
                resources = await self.artifact_manager.get_resource_list()
                commands = await self.artifact_manager.get_command_names()
                if self.on_resources_loaded:
                    self.on_resources_loaded(resources)
                if self.on_commands_loaded:
                    self.on_commands_loaded(commands)
                return resources, commands
            except Exception as load_error:
                logger.error(
                    f"Failed to load resources after initialization error: {load_error}"
                )
                return [], []

