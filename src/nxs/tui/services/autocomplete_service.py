"""
AutocompleteService for managing autocomplete widget setup and lifecycle.

This service handles:
- Mounting the autocomplete overlay
- Updating autocomplete with resources and commands
"""

from typing import TYPE_CHECKING, Callable

from nxs.logger import get_logger

if TYPE_CHECKING:
    from textual.app import App
    from nxs.tui.widgets.autocomplete import NexusAutoComplete
    from nxs.tui.widgets.input_field import NexusInput
    from nxs.tui.services.prompt_service import PromptService

logger = get_logger("autocomplete_service")


class AutocompleteService:
    """
    Handles autocomplete setup and management.

    This service manages the lifecycle of the autocomplete overlay widget,
    including mounting and updating resources/commands.
    """

    def __init__(
        self,
        app: "App",
        input_getter: Callable[[], "NexusInput"],
        prompt_service: "PromptService",
        autocomplete_getter: Callable[[], "NexusAutoComplete | None"] | None = None,
    ):
        """
        Initialize the AutocompleteService.

        Args:
            app: The Textual App instance
            input_getter: Function to get the NexusInput widget
            prompt_service: PromptService for prompt caching
            autocomplete_getter: Optional function to get the NexusAutoComplete widget
        """
        self.app = app
        self.input_getter = input_getter
        self.prompt_service = prompt_service
        self.autocomplete_getter = autocomplete_getter
        self._autocomplete_mounted = False

    def mount_autocomplete(self) -> None:
        """
        Mount the AutoComplete overlay after the app is mounted.

        This should be called after the app is fully mounted, typically
        via call_after_refresh() to ensure the input widget is ready.
        """
        try:
            input_widget = self.input_getter()
            logger.info(
                f"Creating AutoComplete for input widget with "
                f"{len(input_widget.resources)} resources and "
                f"{len(input_widget.commands)} commands"
            )
            from nxs.tui.widgets.autocomplete import NexusAutoComplete

            autocomplete = NexusAutoComplete(input_widget, self.prompt_service)
            self.app.mount(autocomplete)
            self._autocomplete_mounted = True
            logger.info("AutoComplete overlay mounted successfully")
        except Exception as e:
            logger.error(f"Failed to mount AutoComplete overlay: {e}")

    def update_resources(self, resources: list[str]) -> None:
        """
        Update resources in the input widget.

        Args:
            resources: List of resource URIs
        """
        try:
            input_widget = self.input_getter()
            input_widget.update_resources(resources)
        except Exception as e:
            logger.error(f"Failed to update resources in input widget: {e}")

    def update_commands(self, commands: list[str]) -> None:
        """
        Update commands in the input widget.

        Args:
            commands: List of command names
        """
        try:
            input_widget = self.input_getter()
            input_widget.update_commands(commands)
        except Exception as e:
            logger.error(f"Failed to update commands in input widget: {e}")

    @property
    def is_mounted(self) -> bool:
        """Check if autocomplete is mounted."""
        return self._autocomplete_mounted

