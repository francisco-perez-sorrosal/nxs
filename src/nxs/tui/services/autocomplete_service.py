"""
AutocompleteService for managing autocomplete widget setup and lifecycle.

This service handles:
- Mounting the autocomplete overlay
- Updating autocomplete with resources and commands
- Copying prompt caches to autocomplete widget
"""

from typing import TYPE_CHECKING, Callable

from nxs.logger import get_logger

if TYPE_CHECKING:
    from textual.app import App
    from nxs.tui.widgets.autocomplete import NexusAutoComplete
    from nxs.tui.widgets.input_field import NexusInput

logger = get_logger("autocomplete_service")


class AutocompleteService:
    """
    Handles autocomplete setup and management.
    
    This service manages the lifecycle of the autocomplete overlay widget,
    including mounting, updating resources/commands, and syncing prompt caches.
    """

    def __init__(
        self,
        app: "App",
        input_getter: Callable[[], "NexusInput"],
        autocomplete_getter: Callable[[], "NexusAutoComplete | None"] | None = None,
    ):
        """
        Initialize the AutocompleteService.

        Args:
            app: The Textual App instance
            input_getter: Function to get the NexusInput widget
            autocomplete_getter: Optional function to get the NexusAutoComplete widget
        """
        self.app = app
        self.input_getter = input_getter
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

            autocomplete = NexusAutoComplete(input_widget)
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

    def copy_prompt_caches(
        self,
        prompt_info_dict: dict[str, str | None],
        prompt_schema_dict: dict[str, tuple],
    ) -> None:
        """
        Copy prompt caches to autocomplete widget.

        Args:
            prompt_info_dict: Dictionary mapping command names to argument info strings
            prompt_schema_dict: Dictionary mapping command names to (Prompt, server_name) tuples
        """
        try:
            if self.autocomplete_getter:
                autocomplete = self.autocomplete_getter()
                if autocomplete:
                    if prompt_info_dict:
                        autocomplete._prompt_cache = prompt_info_dict
                        logger.info(
                            f"Updated autocomplete prompt cache with {len(prompt_info_dict)} items"
                        )

                    if prompt_schema_dict:
                        autocomplete._prompt_schema_cache = prompt_schema_dict
                        logger.info(
                            f"Updated autocomplete prompt schema cache with {len(prompt_schema_dict)} items"
                        )
            else:
                # Try to find autocomplete widget using query
                from nxs.tui.widgets.autocomplete import NexusAutoComplete

                autocomplete_list = self.app.query(NexusAutoComplete)
                if autocomplete_list:
                    autocomplete = autocomplete_list[0]
                    if prompt_info_dict:
                        autocomplete._prompt_cache = prompt_info_dict
                        logger.info(
                            f"Updated autocomplete prompt cache with {len(prompt_info_dict)} items"
                        )

                    if prompt_schema_dict:
                        autocomplete._prompt_schema_cache = prompt_schema_dict
                        logger.info(
                            f"Updated autocomplete prompt schema cache with {len(prompt_schema_dict)} items"
                        )
        except Exception as e:
            logger.debug(f"Autocomplete widget not found yet, will copy cache when mounted: {e}")

    @property
    def is_mounted(self) -> bool:
        """Check if autocomplete is mounted."""
        return self._autocomplete_mounted

