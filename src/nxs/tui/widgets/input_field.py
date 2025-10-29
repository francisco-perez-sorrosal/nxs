"""
NexusInput - Input field with AutoComplete overlay for commands and resources.
"""

from textual.widgets import Input
from textual_autocomplete import AutoComplete, DropdownItem, TargetState
from nxs.logger import get_logger

logger = get_logger("nexus_input")


class NexusInput(Input):
    """
    Simple input field that will be referenced by AutoComplete.
    
    This is a regular Input widget that stores resources and commands
    for use by the NexusAutoComplete overlay.
    """

    BORDER_TITLE = "Message"

    def __init__(
        self,
        resources: list[str] | None = None,
        commands: list[str] | None = None,
        **kwargs
    ):
        """
        Initialize the input field.

        Args:
            resources: List of available document/resource IDs (for @ completion)
            commands: List of available command names (for / completion)
        """
        self.resources = resources or []
        self.commands = commands or []

        logger.debug(f"Initializing NexusInput with {len(self.resources)} resources and {len(self.commands)} commands")

        super().__init__(
            placeholder="Type @ for docs, / for commands, then press Enter to send",
            **kwargs
        )

        logger.debug("NexusInput initialized successfully")

    def update_resources(self, resources: list[str]):
        """
        Update the list of available resources.

        Args:
            resources: New list of resource IDs
        """
        self.resources = resources

    def update_commands(self, commands: list[str]):
        """
        Update the list of available commands.

        Args:
            commands: New list of command names
        """
        self.commands = commands


class NexusAutoComplete(AutoComplete):
    """
    AutoComplete overlay for NexusInput.
    
    This widget floats above the screen as an overlay and shows
    completion suggestions when the user types @ or /.
    """

    def __init__(self, input_widget: NexusInput):
        """
        Initialize the AutoComplete overlay.

        Args:
            input_widget: The NexusInput widget to provide completions for
        """
        logger.info("Initializing NexusAutoComplete overlay")
        logger.info(f"Target input widget has {len(input_widget.resources)} resources and {len(input_widget.commands)} commands")
        
        # Store the input widget reference first
        self.input_widget = input_widget
        
        super().__init__(
            target=input_widget,
            candidates=self._get_candidates,  # Pass the method directly
            prevent_default_enter=True,  # Prevent Enter from submitting when selecting from dropdown
        )
        logger.info(f"AutoComplete initialized with candidates function: {self.candidates}")
        
        logger.info("NexusAutoComplete overlay initialized successfully")

    def on_mount(self) -> None:
        """Called when the AutoComplete widget is mounted."""
        logger.info("NexusAutoComplete overlay mounted")
        logger.info(f"Target widget: {self.target}")
        logger.info(f"Target widget type: {type(self.target)}")
        logger.info(f"Target widget has {len(self.input_widget.resources)} resources and {len(self.input_widget.commands)} commands")

    def _get_candidates(self, state: TargetState) -> list[DropdownItem]:
        """
        Generate completion items based on current input state.

        This is called by textual-autocomplete to populate the dropdown.

        Args:
            state: Current state of the target input widget

        Returns:
            List of DropdownItem objects for the dropdown
        """
        current_value = state.text
        completions = []

        logger.debug(f"_get_candidates called with: '{current_value}' (length: {len(current_value)})")

        # Check if we should show resource completions (@ prefix)
        if '@' in current_value:
            # Get text after the last @ symbol
            last_at_pos = current_value.rfind('@')
            prefix = current_value[last_at_pos + 1:].lower()

            logger.debug(f"Resource completion triggered: prefix='{prefix}'")

            # Return ALL resources - fuzzy matching will filter them
            # But we can do a quick startswith filter for performance
            if prefix:
                matching_resources = [
                    r for r in self.input_widget.resources
                    if prefix in r.lower()  # Use 'in' instead of 'startswith' for more flexibility
                ]
            else:
                matching_resources = self.input_widget.resources

            logger.debug(f"Found {len(matching_resources)} matching resources")

            # Create dropdown items for matching resources
            for resource in matching_resources:
                completions.append(
                    DropdownItem(
                        main=resource,
                        prefix="📄"  # Document icon
                    )
                )

        # Check if we should show command completions (/ prefix)
        if current_value.startswith('/'):
            # Get text after the / symbol
            prefix = current_value[1:].lower()

            logger.debug(f"Command completion triggered: prefix='{prefix}'")

            # Return ALL commands - fuzzy matching will filter them
            # But we can do a quick contains filter for performance
            if prefix:
                matching_commands = [
                    c for c in self.input_widget.commands
                    if prefix in c.lower()
                ]
            else:
                matching_commands = self.input_widget.commands

            logger.debug(f"Found {len(matching_commands)} matching commands")

            # Create dropdown items for matching commands
            for command in matching_commands:
                completions.append(
                    DropdownItem(
                        main=command,
                        prefix="⚡"  # Command icon
                    )
                )

        logger.debug(f"_get_candidates returning {len(completions)} total candidates")
        return completions

    def get_search_string(self, target_state: TargetState) -> str:
        """
        Extract the search string for fuzzy matching based on trigger characters.

        This is critical for making the dropdown work! The library's fuzzy matcher
        needs to compare ONLY the text after @ or /, not the entire input.

        For example:
        - Input: "hello @dep" → Returns: "dep" (matches "deposition.md")
        - Input: "test /summ" → Returns: "summ" (matches "summarize")
        - Input: "@" → Returns: "" (shows all resources)

        Args:
            target_state: Current state of the input widget

        Returns:
            The substring to use for fuzzy matching
        """
        # Get text up to cursor position
        text = target_state.text[:target_state.cursor_position]

        logger.debug(f"get_search_string: full text='{text}'")

        # Check for @ trigger (resources)
        if '@' in text:
            last_at = text.rfind('@')
            search_str = text[last_at + 1:]
            logger.info(f"get_search_string: @ trigger, returning '{search_str}'")
            return search_str

        # Check for / trigger (commands)
        if text.startswith('/'):
            search_str = text[1:]
            logger.info(f"get_search_string: / trigger, returning '{search_str}'")
            return search_str

        # No trigger - return empty to hide dropdown
        logger.debug(f"get_search_string: no trigger, returning empty string")
        return ""

    def apply_completion(self, value: str, state: TargetState) -> None:
        """
        Apply the selected completion to the input field.

        This preserves the trigger character (@ or /) and the text before it,
        replacing only the part after the trigger with the selected value.
        """
        text = state.text
        cursor_pos = state.cursor_position

        logger.info(f"apply_completion: value='{value}', text='{text}', cursor={cursor_pos}")

        # Find the trigger character and position
        text_before_cursor = text[:cursor_pos]

        # Check for @ trigger (can be anywhere)
        if '@' in text_before_cursor:
            last_at = text_before_cursor.rfind('@')
            # Keep everything before @, add @value with a space, then text after cursor
            new_value = text[:last_at] + '@' + value + ' ' + text[cursor_pos:]
            new_cursor = last_at + len(value) + 2  # After @value and space
            logger.info(f"apply_completion: @ trigger at pos {last_at}, new_value='{new_value}'")

        # Check for / trigger (must be at start)
        elif text_before_cursor.startswith('/'):
            # Keep /value with a space, then text after cursor
            new_value = '/' + value + ' ' + text[cursor_pos:]
            new_cursor = len(value) + 2  # After /value and space
            logger.info(f"apply_completion: / trigger at start, new_value='{new_value}'")

        else:
            # Fallback: just insert the value
            new_value = text[:cursor_pos] + value + text[cursor_pos:]
            new_cursor = cursor_pos + len(value)
            logger.info(f"apply_completion: no trigger, new_value='{new_value}'")

        # Update the input field
        self.target.value = new_value
        self.target.cursor_position = new_cursor
        logger.info(f"apply_completion: set cursor to {new_cursor}")

    def should_show_dropdown(self, search_string: str) -> bool:
        """
        Override to show dropdown only for @ and / triggers.

        Note: search_string here is the ORIGINAL full text, not the processed one
        from get_search_string(). We check the target widget directly.
        """
        # Get the actual input text up to cursor
        text = self.target.value[:self.target.cursor_position]

        # BUGFIX: Only show dropdown if actively typing after @ or /
        # Don't show if there's a space after the trigger (completion done)

        # For @ trigger: check if last @ has no space after it
        if '@' in text:
            last_at = text.rfind('@')
            text_after_at = text[last_at:]
            # Show if no space after @, hide if there's a space (completion done)
            if ' ' not in text_after_at:
                logger.info(f"should_show_dropdown: '@' active, text_after_at='{text_after_at}' -> True")
                return True

        # For / trigger: must be at start and no space after it
        if text.startswith('/'):
            if ' ' not in text:
                logger.info(f"should_show_dropdown: '/' active at start, no space -> True")
                return True

        logger.info(f"should_show_dropdown: text='{text}' -> False")
        return False
