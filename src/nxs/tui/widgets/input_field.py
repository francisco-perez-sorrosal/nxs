"""
NexusInput - Input field with AutoComplete overlay for commands and resources.
"""

from textual.widgets import Input
from textual_autocomplete import AutoComplete, DropdownItem, TargetState
from nxs.core.artifact_manager import ArtifactManager
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
        
        # Cache for prompt information to avoid repeated lookups
        self._prompt_cache: dict[str, str | None] = {}  # Formatted argument strings for display
        self._prompt_schema_cache: dict[str, tuple] = {}  # Full prompt objects for argument expansion

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
            # Get text after the / symbol - might be command name or empty
            search_text = current_value[1:].strip()
            
            # If there's a space, extract just the command part (before first space)
            if ' ' in search_text:
                command_part = search_text.split(' ', 1)[0]
                # If user is typing a command, show matching commands
                prefix = command_part.lower()
            else:
                prefix = search_text.lower()

            logger.debug(f"Command completion triggered: prefix='{prefix}', search_text='{search_text}'")

            # Return ALL commands - fuzzy matching will filter them
            # But we can do a quick contains filter for performance
            if prefix:
                matching_commands = [
                    c for c in self.input_widget.commands
                    if prefix in c.lower() or c.lower().startswith(prefix)
                ]
            else:
                matching_commands = self.input_widget.commands

            logger.debug(f"Found {len(matching_commands)} matching commands")

            # Check if a command is already selected (has a space after command name)
            current_command = None
            if ' ' in search_text:
                # Extract the command that's already typed
                parts = search_text.split(' ', 1)
                typed_command = parts[0]
                
                logger.info(f"Command detected with space: '{typed_command}', remaining text: '{parts[1] if len(parts) > 1 else ''}'")
                logger.info(f"Cache has {len(self._prompt_schema_cache)} prompt schemas cached")
                
                if typed_command in self.input_widget.commands:
                    current_command = typed_command
                    logger.info(f"Command '{current_command}' is valid, generating argument suggestions...")
                    
                    # Show argument suggestions for this command (these appear first as nested items)
                    arg_suggestions = self._get_argument_suggestions(current_command, parts[1] if len(parts) > 1 else "")
                    logger.info(f"Generated {len(arg_suggestions)} argument suggestions for command '{current_command}'")
                    
                    if arg_suggestions:
                        # Add argument suggestions as dropdown items (appear first)
                        for arg_item in arg_suggestions:
                            completions.append(arg_item)
                        logger.debug(f"Added {len(arg_suggestions)} argument suggestions for command '{current_command}'")
                    else:
                        logger.warning(f"No argument suggestions generated for command '{current_command}' - check cache")
                    
                    # Still show the command itself for reference (appears after arguments)
                    arg_info_with_defaults = self._get_command_arguments_with_defaults(current_command)
                    if arg_info_with_defaults:
                        main_text = f"{current_command} ({arg_info_with_defaults})"
                    else:
                        main_text = current_command
                    completions.append(
                        DropdownItem(
                            main=main_text,
                            prefix="⚡"
                        )
                    )
                else:
                    # Not a valid command, but still show all matching commands
                    # User might want to switch commands
                    for command in matching_commands:
                        arg_info_with_defaults = self._get_command_arguments_with_defaults(command)
                        if arg_info_with_defaults:
                            main_text = f"{command} ({arg_info_with_defaults})"
                        else:
                            main_text = command
                        completions.append(
                            DropdownItem(
                                main=main_text,
                                prefix="⚡"
                            )
                        )
            else:
                # No command selected yet, show all matching commands
                for command in matching_commands:
                    # Get argument info with default values
                    arg_info_with_defaults = self._get_command_arguments_with_defaults(command)
                    
                    if arg_info_with_defaults:
                        main_text = f"{command} ({arg_info_with_defaults})"
                        logger.debug(f"Adding command '{command}' with args: {arg_info_with_defaults}")
                    else:
                        main_text = command
                        logger.debug(f"Adding command '{command}' without args")
                    
                    completions.append(
                        DropdownItem(
                            main=main_text,
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
            # If there's a space, user is typing arguments - return empty for argument suggestions
            # (argument suggestions don't need fuzzy matching, they're shown based on command)
            if ' ' in search_str:
                # Return empty string so argument suggestions are shown without filtering
                logger.info(f"get_search_string: / trigger with space, showing argument suggestions")
                return ""
            logger.info(f"get_search_string: / trigger, returning '{search_str}' for command matching")
            return search_str

        # No trigger - return empty to hide dropdown
        logger.debug(f"get_search_string: no trigger, returning empty string")
        return ""

    def apply_completion(self, value: str, state: TargetState) -> None:
        """
        Apply the selected completion to the input field.

        For commands (/), this expands the command with its arguments, pre-filling defaults
        and marking required arguments.
        
        For argument suggestions (starting with space and prefix), this inserts the argument
        into the command line.
        """
        text = state.text
        cursor_pos = state.cursor_position

        logger.info(f"apply_completion: value='{value}', text='{text}', cursor={cursor_pos}")

        # Check if this is an argument suggestion
        # Argument suggestions have format like:
        # - "arg_name=default" or "arg_name=default  (description)"
        # - "arg_name=<required>" or "arg_name=<required>  (description)"
        # - "arg_name?" or "arg_name?  (description)" (optional)
        # We detect them by checking if they look like argument assignments or end with ?
        is_argument_suggestion = False
        arg_text = None
        
        stripped_value = value.strip()
        
        # Check if it ends with ? (optional argument) or contains = (argument with default/required)
        if stripped_value.endswith('?'):
            # Optional argument format: "arg_name?" or "arg_name?  (description)"
            is_argument_suggestion = True
            arg_text = stripped_value.split('  (', 1)[0].rstrip('?').strip()  # Remove ? and description
            logger.info(f"Detected optional argument suggestion: '{arg_text}'")
        elif '=' in stripped_value and (
            '<required>' in stripped_value or 
            any(char.isalnum() or char in '"./@' for char in stripped_value.split('=', 1)[1] if len(stripped_value.split('=', 1)) > 1)
        ):
            # This looks like an argument suggestion with = (default or required)
            is_argument_suggestion = True
            arg_text = stripped_value.split('  (', 1)[0].strip()  # Remove description if present
            logger.info(f"Detected argument suggestion: '{arg_text}'")
        
        if is_argument_suggestion and arg_text:
            text_before_cursor = text[:cursor_pos]
            text_after_cursor = text[cursor_pos:]
            
            if text_before_cursor.startswith('/'):
                # Extract command and existing text after command
                remaining_after_command = text_before_cursor[1:].strip()
                
                if ' ' in remaining_after_command:
                    # Command already has some text - split into command and existing args
                    parts = remaining_after_command.split(' ', 1)
                    command = parts[0]
                    existing_text = parts[1] if len(parts) > 1 else ""
                    
                    # Close any unclosed quotes in existing_text before adding new argument
                    # Only close quotes on the LAST argument value (currently being typed)
                    # Don't touch quotes in earlier complete arguments
                    existing_text_closed = existing_text
                    if existing_text:
                        # Find the last = sign - that's where the current argument being typed is
                        last_eq_pos = existing_text.rfind('=')
                        if last_eq_pos >= 0:
                            # Get everything before the last = (complete arguments)
                            before_last_eq = existing_text[:last_eq_pos]
                            # Get the value part after the last = (current argument value being typed)
                            value_part = existing_text[last_eq_pos + 1:].strip()
                            
                            # Check if the current value starts with quote but doesn't end with quote
                            if value_part.startswith('"') and not (value_part.endswith('"') and value_part.count('"') >= 2):
                                # Unclosed quote in current argument - close it
                                # Only close if we're selecting a new argument (cursor at end)
                                if text_before_cursor.endswith(existing_text) or text_after_cursor == "":
                                    # Close the quote and reconstruct the text
                                    closed_value = value_part + '"'
                                    existing_text_closed = before_last_eq + '=' + closed_value
                            # If value is already properly closed or doesn't use quotes, keep it as is
                    
                    # Check if the existing text is actually an argument (not just random typing)
                    # If it looks like partial typing (e.g., "d"), replace it with the selected argument
                    # Otherwise, append the new argument
                    if existing_text_closed and not '=' in existing_text_closed and len(existing_text_closed.split()) == 1:
                        # Looks like user was typing - replace with selected argument
                        new_args = arg_text
                        if arg_text.endswith('=') or '=' in arg_text:
                            # Already has =, add opening quote if not present
                            if '=' in arg_text:
                                parts = arg_text.split('=', 1)
                                if not parts[1].startswith('"'):
                                    # Add opening quote after =
                                    new_args = parts[0] + '="' + parts[1]
                            new_value = '/' + command + ' ' + new_args + text_after_cursor
                            new_cursor = len('/' + command + ' ' + new_args)
                        else:
                            # Add = and opening quote for the user to fill in value
                            new_value = '/' + command + ' ' + new_args + '="' + text_after_cursor
                            new_cursor = len('/' + command + ' ' + new_args + '="')
                    else:
                        # Close existing argument and append new argument after existing ones
                        if existing_text_closed:
                            # Add space before new argument
                            new_args = existing_text_closed.rstrip() + ' ' + arg_text
                        else:
                            new_args = arg_text
                        if arg_text.endswith('=') or '=' in arg_text:
                            # Check if quote already present, if not add it
                            if '=' in arg_text:
                                parts = arg_text.split('=', 1)
                                if not parts[1].startswith('"'):
                                    arg_text = parts[0] + '="' + parts[1]
                                    new_args = existing_text_closed.rstrip() + ' ' + arg_text if existing_text_closed else arg_text
                            new_value = '/' + command + ' ' + new_args + text_after_cursor
                            new_cursor = len('/' + command + ' ' + new_args)
                        else:
                            # Add = and opening quote
                            new_value = '/' + command + ' ' + new_args + '="' + text_after_cursor
                            new_cursor = len('/' + command + ' ' + new_args + '="')
                else:
                    # No arguments yet, just add this one after the command
                    command = remaining_after_command
                    if arg_text.endswith('=') or '=' in arg_text:
                        # Already has =, add opening quote if not present
                        if '=' in arg_text:
                            parts = arg_text.split('=', 1)
                            if not parts[1].startswith('"'):
                                arg_text = parts[0] + '="' + parts[1]
                        new_value = '/' + command + ' ' + arg_text + text_after_cursor
                        new_cursor = len('/' + command + ' ' + arg_text)
                    else:
                        # Add = and opening quote for the user to fill in value
                        new_value = '/' + command + ' ' + arg_text + '="' + text_after_cursor
                        new_cursor = len('/' + command + ' ' + arg_text + '="')
                
                # Extract command for logging (it might be in different scopes)
                log_command = remaining_after_command.split(' ', 1)[0] if ' ' in remaining_after_command else remaining_after_command
                logger.info(f"apply_completion: argument suggestion '{arg_text}', command='{log_command}', new_value='{new_value}'")
            else:
                # Not in a command context, just insert
                new_value = text[:cursor_pos] + arg_text + ' ' + text[cursor_pos:]
                new_cursor = cursor_pos + len(arg_text) + 1
        else:
            # Extract command name if value contains argument info in parentheses
            # Format: "command (arg1, arg2 | Required: arg1)"
            if ' (' in value and value.endswith(')'):
                # Extract just the command name before the parentheses
                command_name = value.split(' (', 1)[0]
            else:
                command_name = value

            # Find the trigger character and position
            text_before_cursor = text[:cursor_pos]

            # Check for @ trigger (can be anywhere)
            if '@' in text_before_cursor:
                last_at = text_before_cursor.rfind('@')
                # Keep everything before @, add @value with a space, then text after cursor
                new_value = text[:last_at] + '@' + command_name + ' ' + text[cursor_pos:]
                new_cursor = last_at + len(command_name) + 2  # After @value and space
                logger.info(f"apply_completion: @ trigger at pos {last_at}, new_value='{new_value}'")

            # Check for / trigger (must be at start) - expand with arguments
            elif text_before_cursor.startswith('/'):
                # Check if this is selecting a command when already typing arguments
                remaining_after_command = text_before_cursor[1:].strip()
                if ' ' in remaining_after_command:
                    # User already has a command and some text - replace command part
                    parts = remaining_after_command.split(' ', 1)
                    new_value = '/' + command_name + ' ' + parts[1] + text[cursor_pos:]
                    new_cursor = len('/' + command_name + ' ' + parts[1])
                else:
                    # First time selecting command - expand with arguments
                    expanded_command = self._expand_command_with_arguments(command_name)
                    new_value = '/' + expanded_command + ' ' + text[cursor_pos:]
                    new_cursor = len(expanded_command) + 2  # After /command args and space
                logger.info(f"apply_completion: / trigger at start, expanded to '{expanded_command if 'expanded_command' in locals() else command_name}', new_value='{new_value}'")

            else:
                # Fallback: just insert the value
                new_value = text[:cursor_pos] + command_name + text[cursor_pos:]
                new_cursor = cursor_pos + len(command_name)
                logger.info(f"apply_completion: no trigger, new_value='{new_value}'")

        # Update the input field
        self.target.value = new_value
        self.target.cursor_position = new_cursor
        logger.info(f"apply_completion: set cursor to {new_cursor}")
    
    def _expand_command_with_arguments(self, command_name: str) -> str:
        """
        Expand a command with its arguments, pre-filling defaults and marking required.
        
        Args:
            command_name: Name of the command
            
        Returns:
            Expanded command string like "command arg1=value arg2=<required>"
        """
        if command_name not in self._prompt_schema_cache:
            logger.debug(f"No schema cache for '{command_name}', returning plain command")
            return command_name
        
        prompt, _ = self._prompt_schema_cache[command_name]
        
        if not hasattr(prompt, 'arguments') or not prompt.arguments:
            logger.debug(f"Prompt '{command_name}' has no arguments")
            return command_name
        
        schema = prompt.arguments
        arg_parts: list[str] = []
        
        # Extract arguments with defaults and required status
        if isinstance(schema, dict):
            properties = schema.get('properties', {})
            required_args = schema.get('required', [])
            
            for arg_name, arg_spec in properties.items():
                default = None
                is_required = arg_name in required_args
                
                if isinstance(arg_spec, dict):
                    default = arg_spec.get('default')
                    # Also check for default in description or other fields
                
                if default is not None:
                    # Pre-fill with default value
                    arg_parts.append(f"{arg_name}={default}")
                elif is_required:
                    # Mark as required - user must provide
                    arg_parts.append(f"{arg_name}=<required>")
                # Note: Optional arguments without defaults are skipped for cleaner UI
        
        elif isinstance(schema, list):
            # List of PromptArgument objects
            required_set = set()
            args_with_specs = {}
            
            for arg in schema:
                if isinstance(arg, dict):
                    arg_name = arg.get('name', '')
                    if arg_name:
                        args_with_specs[arg_name] = arg
                        if arg.get('required', False):
                            required_set.add(arg_name)
                elif hasattr(arg, 'name'):
                    arg_name = arg.name
                    args_with_specs[arg_name] = arg
                    if hasattr(arg, 'required') and arg.required:
                        required_set.add(arg_name)
            
            for arg_name, arg_spec in args_with_specs.items():
                default = None
                if isinstance(arg_spec, dict):
                    default = arg_spec.get('default')
                elif hasattr(arg_spec, 'default'):
                    default = getattr(arg_spec, 'default', None)
                
                is_required = arg_name in required_set
                
                if default is not None:
                    arg_parts.append(f"{arg_name}={default}")
                elif is_required:
                    arg_parts.append(f"{arg_name}=<required>")
                # Note: Optional arguments without defaults are skipped for cleaner UI
        
        if arg_parts:
            return f"{command_name} {' '.join(arg_parts)}"
        
        return command_name

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

        # For / trigger: must be at start
        # Keep dropdown visible while typing commands or their arguments
        if text.startswith('/'):
            # Always show dropdown when typing / commands (for command selection or argument suggestions)
            logger.info(f"should_show_dropdown: '/' active at start -> True")
            return True

        logger.info(f"should_show_dropdown: text='{text}' -> False")
        return False

    def _get_command_arguments(self, command_name: str) -> str | None:
        """
        Get argument information for a command to display in the dropdown.
        
        Args:
            command_name: Name of the command/prompt
            
        Returns:
            Formatted string showing required arguments, or None if unavailable
        """
        # Check cache first
        if command_name in self._prompt_cache:
            cached = self._prompt_cache[command_name]
            logger.debug(f"Found cached arg info for '{command_name}': {cached}")
            return cached
        
        logger.debug(f"No cached arg info for '{command_name}' (cache has {len(self._prompt_cache)} items)")
        return None
    
    def _get_command_arguments_with_defaults(self, command_name: str) -> str | None:
        """
        Get argument information including default values for display in dropdown.
        
        Args:
            command_name: Name of the command/prompt
            
        Returns:
            Formatted string showing arguments with defaults, or None if unavailable
        """
        if command_name not in self._prompt_schema_cache:
            return None
        
        prompt, _ = self._prompt_schema_cache[command_name]
        
        if not hasattr(prompt, 'arguments') or not prompt.arguments:
            return None
        
        schema = prompt.arguments
        arg_descriptions = []
        
        # Extract arguments with defaults
        if isinstance(schema, dict):
            properties = schema.get('properties', {})
            required_args = schema.get('required', [])
            
            for arg_name, arg_spec in properties.items():
                default = None
                is_required = arg_name in required_args
                
                if isinstance(arg_spec, dict):
                    default = arg_spec.get('default')
                    description = arg_spec.get('description', '')
                else:
                    if hasattr(arg_spec, 'default'):
                        default = getattr(arg_spec, 'default', None)
                    description = getattr(arg_spec, 'description', '') if hasattr(arg_spec, 'description') else ''
                
                if default is not None:
                    arg_descriptions.append(f"{arg_name}={default}")
                elif is_required:
                    arg_descriptions.append(f"{arg_name}*")
                else:
                    arg_descriptions.append(f"{arg_name}?")
        
        elif isinstance(schema, list):
            required_set = set()
            for arg in schema:
                if isinstance(arg, dict):
                    arg_name = arg.get('name', '')
                    if arg_name and arg.get('required', False):
                        required_set.add(arg_name)
                elif hasattr(arg, 'name') and hasattr(arg, 'required') and arg.required:
                    required_set.add(arg.name)
            
            for arg in schema:
                arg_name = None
                default = None
                
                if isinstance(arg, dict):
                    arg_name = arg.get('name', '')
                    default = arg.get('default')
                elif hasattr(arg, 'name'):
                    arg_name = arg.name
                    default = getattr(arg, 'default', None) if hasattr(arg, 'default') else None
                
                if arg_name:
                    is_required = arg_name in required_set
                    if default is not None:
                        arg_descriptions.append(f"{arg_name}={default}")
                    elif is_required:
                        arg_descriptions.append(f"{arg_name}*")
                    else:
                        arg_descriptions.append(f"{arg_name}?")
        
        if arg_descriptions:
            return ", ".join(arg_descriptions)
        
        return None
    
    def _get_argument_suggestions(self, command_name: str, current_text: str) -> list[DropdownItem]:
        """
        Get argument suggestions when typing a command's arguments.
        Shows all arguments: required [R] or optional [O] (arguments with defaults are optionals).
        """
        if command_name not in self._prompt_schema_cache:
            return []
        
        prompt, _ = self._prompt_schema_cache[command_name]
        if not hasattr(prompt, 'arguments') or not prompt.arguments:
            return []
        
        schema = prompt.arguments
        suggestions = []
        current_text = current_text.strip()
        
        # Extract already provided arguments to filter them out
        provided_args = set()
        if current_text:
            for part in current_text.split():
                if '=' in part:
                    arg_name = part.split('=', 1)[0].strip()
                    provided_args.add(arg_name)
        
        # Process schema based on type
        if isinstance(schema, dict):
            properties = schema.get('properties', {})
            required_args = schema.get('required', [])
            
            for arg_name, arg_spec in properties.items():
                if arg_name in provided_args:
                    continue
                
                default = None
                description = ""
                is_required = arg_name in required_args
                
                if isinstance(arg_spec, dict):
                    default = arg_spec.get('default')
                    description = arg_spec.get('description', '')
                
                # Validate default value - filter out PydanticUndefined and class references
                if default is not None:
                    default_str = str(default)
                    if 'Undefined' in default_str or 'PydanticUndefined' in default_str:
                        default = None
                    elif 'class' in default_str.lower() and '<' in default_str:
                        default = None
                
                # Show all arguments: required [R] or optional [O] (defaults are the same as optionals)
                if is_required:
                    # Required argument
                    suggestion_text = f"{arg_name}=<required>"
                    if description:
                        suggestion_text = f"{suggestion_text}  ({description})"
                    suggestions.append(
                        DropdownItem(
                            main=suggestion_text,
                            prefix="  [R]"
                        )
                    )
                else:
                    # Optional argument (with or without default)
                    # Auto-quote default values that contain spaces for better UX
                    if default is not None:
                        # Check if default value contains spaces - if so, quote it in the suggestion
                        if ' ' in str(default):
                            suggestion_text = f'{arg_name}="{default}"'
                        else:
                            suggestion_text = f"{arg_name}={default}"
                    else:
                        suggestion_text = f"{arg_name}=?"
                    if description:
                        suggestion_text = f"{suggestion_text}  ({description})"
                    suggestions.append(
                        DropdownItem(
                            main=suggestion_text,
                            prefix="  [O]"
                        )
                    )
        
        elif isinstance(schema, list):
            # List of PromptArgument objects
            required_set = set()
            for arg in schema:
                if isinstance(arg, dict):
                    if arg.get('name') and arg.get('required', False):
                        required_set.add(arg['name'])
                elif hasattr(arg, 'name') and hasattr(arg, 'required') and arg.required:
                    required_set.add(arg.name)
            
            for arg in schema:
                arg_name = None
                default = None
                description = ""
                
                if isinstance(arg, dict):
                    arg_name = arg.get('name', '')
                    default = arg.get('default')
                    description = arg.get('description', '')
                elif hasattr(arg, 'name'):
                    arg_name = arg.name
                    description = getattr(arg, 'description', '') if hasattr(arg, 'description') else ''
                    
                    # Try to extract default from PromptArgument (Pydantic model)
                    try:
                        if hasattr(arg, 'model_dump'):
                            arg_dict = arg.model_dump(exclude_unset=False, exclude_none=False)
                            default = arg_dict.get('default')
                        elif hasattr(arg, 'dict'):
                            arg_dict = arg.dict(exclude_unset=False, exclude_none=False)
                            default = arg_dict.get('default')
                        elif hasattr(arg, '__dict__'):
                            default = arg.__dict__.get('default')
                        else:
                            default = getattr(arg, 'default', None)
                    except Exception:
                        default = None
                
                if arg_name and arg_name not in provided_args:
                    is_required = arg_name in required_set
                    
                    # Validate default value - filter out PydanticUndefined and class references
                    if default is not None:
                        default_str = str(default)
                        if 'Undefined' in default_str or 'PydanticUndefined' in default_str:
                            default = None
                        elif 'class' in default_str.lower() and '<' in default_str:
                            default = None
                    
                    # Show all arguments: required [R] or optional [O] (defaults are the same as optionals)
                    if is_required:
                        # Required argument
                        suggestion_text = f"{arg_name}=<required>"
                        if description:
                            suggestion_text = f"{suggestion_text}  ({description})"
                        suggestions.append(
                            DropdownItem(
                                main=suggestion_text,
                                prefix="  [R]"
                            )
                        )
                    else:
                        # Optional argument (with or without default)
                        # Auto-quote default values that contain spaces for better UX
                        if default is not None:
                            # Check if default value contains spaces - if so, quote it in the suggestion
                            if ' ' in str(default):
                                suggestion_text = f'{arg_name}="{default}"'
                            else:
                                suggestion_text = f"{arg_name}={default}"
                        else:
                            suggestion_text = f"{arg_name}=?"
                        if description:
                            suggestion_text = f"{suggestion_text}  ({description})"
                        suggestions.append(
                            DropdownItem(
                                main=suggestion_text,
                                prefix="  [O]"
                            )
                        )
        
        return suggestions
    
    async def _load_prompt_info(self, command_name: str) -> None:
        """
        Load prompt argument information asynchronously and cache it.
        
        Args:
            command_name: Name of the command/prompt
        """
        if not self.input_widget.artifact_manager:
            return
        
        if command_name in self._prompt_cache:
            return
        
        try:
            prompt_info = await self.input_widget.artifact_manager.find_prompt(command_name)
            if prompt_info:
                prompt, _ = prompt_info
                arg_info = self._format_prompt_arguments(prompt)
                self._prompt_cache[command_name] = arg_info
        except Exception as e:
            logger.debug(f"Failed to load prompt info for '{command_name}': {e}")
    
    def _format_prompt_arguments(self, prompt) -> str | None:
        """
        Format prompt arguments into a readable string.
        
        Args:
            prompt: The Prompt object
            
        Returns:
            Formatted string showing arguments, or None if no arguments
        """
        if not hasattr(prompt, 'arguments') or not prompt.arguments:
            return None
        
        schema = prompt.arguments
        arg_names: list[str] = []
        required_args: list[str] = []
        
        # Handle different schema formats
        if isinstance(schema, list):
            # List of PromptArgument objects
            for arg in schema:
                if hasattr(arg, 'name'):
                    arg_names.append(arg.name)
                    if hasattr(arg, 'required') and arg.required:
                        required_args.append(arg.name)
                elif isinstance(arg, dict):
                    arg_name = arg.get('name', '')
                    if arg_name:
                        arg_names.append(arg_name)
                        if arg.get('required', False):
                            required_args.append(arg_name)
        elif isinstance(schema, dict):
            # JSON schema format
            properties = schema.get('properties', {})
            arg_names = list(properties.keys())
            required_args = schema.get('required', [])
        else:
            # Try attributes
            if hasattr(schema, 'properties'):
                properties = getattr(schema, 'properties', {})
                if isinstance(properties, dict):
                    arg_names = list(properties.keys())
            if hasattr(schema, 'required'):
                required_args = getattr(schema, 'required', [])
        
        if not arg_names:
            return None
        
        # Format: "arg1, arg2 (required: arg1)"
        arg_str = ", ".join(arg_names)
        if required_args:
            req_str = ", ".join(required_args)
            return f"{arg_str} | Required: {req_str}"
        
        return arg_str
