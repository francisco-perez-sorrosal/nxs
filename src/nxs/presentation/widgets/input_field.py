"""
NexusInput - Input field for commands and resources.

This is a simple Input widget that stores resources and commands
for use by the NexusAutoComplete overlay (see autocomplete.py).
"""

from textual.widgets import Input
from nxs.application.artifact_manager import ArtifactManager
from nxs.logger import get_logger

logger = get_logger("nexus_input")


class NexusInput(Input):
    """
    Simple input field that will be referenced by AutoComplete.
    
    This is a regular Input widget that stores resources and commands
    for use by the NexusAutoComplete overlay.
    """

    BORDER_TITLE = "Message"

    def _close_unclosed_quotes(self, text: str) -> str:
        """
        Close any unclosed quotes in the text.
        CRITICAL: Only closes quotes on the LAST argument value (currently being typed).
        Preserves all earlier complete arguments unchanged, including multi-word values.
        
        Example:
            Input:  'depth_level="short" style="very format'
            Output: 'depth_level="short" style="very format"'
            
            Note: Only the last value (after last =) gets its quote closed.
            Earlier arguments like depth_level="short" remain untouched.
        
        Args:
            text: Text that may contain unclosed quotes
            
        Returns:
            Text with unclosed quotes closed on the last argument only
        """
        if not text:
            return text
        
        # Find the last = sign - that's where the current argument being typed is
        last_eq_pos = text.rfind('=')
        if last_eq_pos < 0:
            # No = signs, nothing to close
            return text
        
        # Get everything before the last = (preserve all earlier complete arguments)
        before_last_eq = text[:last_eq_pos]
        
        # Get the value part after the last = (current argument value being typed)
        value_part = text[last_eq_pos + 1:].strip()
        
        # Check if the current value starts with quote but doesn't end with quote
        if value_part.startswith('"'):
            # Check if it's properly closed (ends with " and has at least 2 quotes)
            if not (value_part.endswith('"') and value_part.count('"') >= 2):
                # Unclosed quote - add closing quote at the end
                # This preserves multi-word values because we only close at the very end
                return before_last_eq + '=' + value_part + '"'
        
        # Value is already properly closed or doesn't use quotes
        return text

    def __init__(
        self,
        resources: list[str] | None = None,
        commands: list[str] | None = None,
        artifact_manager: ArtifactManager | None = None,
        **kwargs
    ):
        """
        Initialize the input field.

        Args:
            resources: List of available document/resource IDs (for @ completion)
            commands: List of available command names (for / completion)
            artifact_manager: ArtifactManager instance for accessing prompt information
        """
        self.resources = resources or []
        self.commands = commands or []
        self.artifact_manager = artifact_manager
        self._quote_inserting = False  # Flag to prevent infinite loops

        logger.debug(f"Initializing NexusInput with {len(self.resources)} resources and {len(self.commands)} commands")

        super().__init__(
            placeholder="Type @ for docs, / for commands, then press Enter to send",
            **kwargs
        )

        logger.debug("NexusInput initialized successfully")

    def watch_value(self, value: str) -> None:
        """
        Watch for value changes to add auto-quotes after = in command arguments.
        Called whenever the input value changes.
        """
        if self._quote_inserting:
            return
        
        if not value.startswith('/'):
            return
        
        cursor_pos = self.cursor_position
        if cursor_pos > len(value):
            return
        
        text_before = value[:cursor_pos]
        text_after = value[cursor_pos:]
        
        # Check if user just typed = (text before cursor ends with = and text after doesn't start with quote)
        if text_before.endswith('=') and not text_after.startswith('"'):
            remaining = text_before[1:].strip()  # Remove leading /
            
            # Check if there's an argument name before the = (has space or is after command)
            if ' ' in remaining:
                # There's already some argument, check the context
                parts = remaining.split()
                last_part = parts[-1] if parts else ""
                
                # Check if last part ends with = (user just typed it)
                if last_part.endswith('=') and len(last_part) > 1:
                    # This is arg=, add opening quote immediately after =
                    self._quote_inserting = True
                    new_value = value[:cursor_pos] + '"' + value[cursor_pos:]
                    self.value = new_value
                    self.cursor_position = cursor_pos + 1
                    self._quote_inserting = False
            elif remaining and remaining.endswith('='):
                # First argument after command, like "/command arg="
                # Check if there's an argument name before =
                if len(remaining) > 1:
                    # This is arg=, add opening quote immediately after =
                    self._quote_inserting = True
                    new_value = value[:cursor_pos] + '"' + value[cursor_pos:]
                    self.value = new_value
                    self.cursor_position = cursor_pos + 1
                    self._quote_inserting = False

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
