"""
NexusAutoComplete - AutoComplete overlay for NexusInput with command and resource completion.
"""

from textual_autocomplete import AutoComplete, DropdownItem, TargetState
from nxs.logger import get_logger
from nxs.tui.widgets.command_parser import (
    parse_command_arguments,
    extract_value_part,
    is_inside_quotes,
)
from nxs.tui.widgets.argument_suggestions import ArgumentSuggestionGenerator
from nxs.tui.widgets.input_field import NexusInput

logger = get_logger("nexus_input")


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
        
        # Initialize argument suggestion generator
        self._arg_suggestion_generator = ArgumentSuggestionGenerator(self._prompt_schema_cache)

    def on_mount(self) -> None:
        """Called when the AutoComplete widget is mounted."""
        logger.info("NexusAutoComplete overlay mounted")
        logger.info(f"Target widget: {self.target}")
        logger.info(f"Target widget type: {type(self.target)}")
        logger.info(f"Target widget has {len(self.input_widget.resources)} resources and {len(self.input_widget.commands)} commands")
    
    def get_matches(self, target_state: TargetState, candidates: list[DropdownItem], search_string: str) -> list[DropdownItem]:
        """
        Override to handle argument suggestions specially.
        
        When showing argument suggestions and search is empty, show ALL arguments.
        Otherwise, use default fuzzy matching.
        """
        # Check if we're showing argument suggestions (they have [R] or [O] prefix)
        if candidates and hasattr(candidates[0], 'prefix'):
            first_prefix = str(candidates[0].prefix) if candidates[0].prefix else ""
            if first_prefix and ('[R]' in first_prefix or '[O]' in first_prefix):
                # These are argument suggestions
                if not search_string or not search_string.strip():
                    # Empty search - show ALL argument suggestions without filtering
                    logger.debug(f"Showing all {len(candidates)} argument suggestions (empty search)")
                    return candidates
                # Non-empty search - use default fuzzy matching for filtering
                logger.debug(f"Filtering {len(candidates)} argument suggestions with search '{search_string}'")
        
        # For all other cases (commands, resources), use default fuzzy matching
        # Call parent's get_matches method with correct signature
        return super().get_matches(target_state, candidates, search_string)

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
                remaining_text = parts[1] if len(parts) > 1 else ""
                
                logger.info(f"Command detected with space: '{typed_command}', remaining text: '{remaining_text}'")
                logger.info(f"Cache has {len(self._prompt_schema_cache)} prompt schemas cached")
                
                if typed_command in self.input_widget.commands:
                    current_command = typed_command
                    logger.info(f"Command '{current_command}' is valid, generating argument suggestions...")
                    
                    # Show argument suggestions for this command
                    # Get all arguments (filtering of already-provided args happens in _get_argument_suggestions)
                    arg_suggestions = self._get_argument_suggestions(current_command, remaining_text)
                    logger.info(f"Generated {len(arg_suggestions)} argument suggestions for command '{current_command}' (remaining_text: '{remaining_text}')")
                    
                    if arg_suggestions:
                        # Add ALL argument suggestions - let fuzzy matcher handle filtering based on search string
                        # This ensures they appear when search is empty (just space after command)
                        for arg_item in arg_suggestions:
                            completions.append(arg_item)
                        logger.debug(f"Added {len(arg_suggestions)} argument suggestions for command '{current_command}'")
                    else:
                        # No argument suggestions - check if cache is empty or command has no args
                        if current_command not in self._prompt_schema_cache:
                            logger.warning(f"Command '{current_command}' not in prompt schema cache - prompts may not be loaded yet")
                        else:
                            logger.info(f"Command '{current_command}' has no argument suggestions (no args or all args already provided)")
                    
                    # Don't show the command itself when showing argument suggestions
                    # User already selected it, just show the arguments
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
        - Input: "/summary " → Returns: "" (should show all argument suggestions)

        Args:
            target_state: Current state of the input widget

        Returns:
            The substring to use for fuzzy matching
        """
        # Get text up to cursor position
        text = target_state.text[:target_state.cursor_position]

        logger.debug(f"get_search_string: full text='{text}', cursor_pos={target_state.cursor_position}")

        # Check for @ trigger (resources)
        if '@' in text:
            last_at = text.rfind('@')
            search_str = text[last_at + 1:]
            logger.info(f"get_search_string: @ trigger, returning '{search_str}'")
            return search_str

        # Check for / trigger (commands)
        if text.startswith('/'):
            search_str = text[1:]
            # If there's a space, user is typing arguments
            if ' ' in search_str:
                # Extract text after the command (everything after first space)
                parts = search_str.split(' ', 1)
                arg_text = parts[1] if len(parts) > 1 else ""
                
                if not arg_text.strip():
                    # Just space after command - show all arguments
                    logger.info(f"get_search_string: / trigger with space, empty arg_text -> returning empty string")
                    return ""
                
                # Parse arguments using quote-aware parser
                arg_parts = parse_command_arguments(arg_text)
                
                if not arg_parts:
                    # No parts - just whitespace, show all arguments
                    logger.info(f"get_search_string: / trigger, no arg parts -> returning empty")
                    return ""
                
                # Get the last argument being typed
                last_part = arg_parts[-1]
                
                # Extract value part if last part has =
                parsed = extract_value_part(last_part)
                if parsed:
                    arg_name, value_part = parsed
                    
                    # Check if we're typing inside a quoted value
                    if value_part.startswith('"'):
                        if is_inside_quotes(value_part):
                            # We're typing inside an incomplete quoted value - hide dropdown
                            logger.info(f"get_search_string: / trigger, typing inside incomplete quoted value (value_part='{value_part}') -> returning empty to hide dropdown")
                            return ""
                        elif value_part.count('"') >= 2 and value_part.endswith('"'):
                            # Complete quoted value - check if there's a space after it
                            if arg_text.rstrip().endswith(' '):
                                logger.info(f"get_search_string: / trigger, complete quoted value with trailing space -> returning empty to show remaining args")
                                return ""
                            # Otherwise, return empty to show remaining arguments
                            logger.info(f"get_search_string: / trigger, complete quoted value -> returning empty")
                            return ""
                        else:
                            # Just opened quote or edge case - hide dropdown
                            logger.info(f"get_search_string: / trigger, just opened quote or edge case (value_part='{value_part}') -> returning empty to hide dropdown")
                            return ""
                    else:
                        # Unquoted value - check if it's complete
                        if arg_text.rstrip().endswith(' '):
                            logger.info(f"get_search_string: / trigger, complete unquoted value with trailing space -> returning empty")
                            return ""
                        # If value part is non-empty, it's probably complete
                        if value_part and not value_part.isspace():
                            logger.info(f"get_search_string: / trigger, complete unquoted value -> returning empty")
                            return ""
                        else:
                            # Incomplete value - return it
                            logger.info(f"get_search_string: / trigger, incomplete unquoted value -> returning '{value_part}'")
                            return value_part
                else:
                    # Last part doesn't have = - user is typing an argument name
                    # Return this for fuzzy matching against argument names
                    logger.info(f"get_search_string: / trigger, typing argument name '{last_part}' -> returning for fuzzy match")
                    return last_part
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
                    
                    # Find the last incomplete argument name being typed (doesn't have =)
                    # This is what we need to replace with the selected argument
                    # Use quote-aware parsing to correctly handle arguments with spaces in values
                    arg_parts = parse_command_arguments(existing_text)
                    incomplete_arg_part = None
                    complete_args_before = []
                    
                    # Find the last incomplete argument (no = sign)
                    for i in range(len(arg_parts) - 1, -1, -1):
                        part = arg_parts[i]
                        parsed = extract_value_part(part)
                        
                        if not parsed:
                            # This is an incomplete argument name - user is typing it
                            incomplete_arg_part = part
                            complete_args_before = arg_parts[:i]
                            break
                        else:
                            # Check if this is a complete argument (has = and complete value)
                            arg_name, value_part = parsed
                            
                            # If it's a quoted value, check if quote is closed
                            if value_part.startswith('"'):
                                # Count quotes - even number means closed
                                quote_count = value_part.count('"')
                                if quote_count >= 2 and quote_count % 2 == 0:
                                    # Complete quoted argument - keep it
                                    continue
                                else:
                                    # Incomplete quoted value - this is the current argument
                                    # Don't replace it, just append new argument
                                    incomplete_arg_part = None
                                    break
                            else:
                                # Unquoted value - if it's not empty, it's complete
                                if value_part.strip():
                                    # Complete unquoted argument - keep it
                                    continue
                    
                    # Prepare the selected argument text
                    selected_arg_text = arg_text
                    if '=' in arg_text:
                        parts = arg_text.split('=', 1)
                        if not parts[1].startswith('"'):
                            # Add opening quote after =
                            selected_arg_text = parts[0] + '="' + parts[1]
                    
                    if incomplete_arg_part is not None:
                        # Replace the incomplete argument name with the selected argument
                        # Keep all complete arguments before it
                        complete_args_str = ' '.join(complete_args_before) if complete_args_before else ""
                        if complete_args_str:
                            new_args = complete_args_str + ' ' + selected_arg_text
                        else:
                            new_args = selected_arg_text
                        new_value = '/' + command + ' ' + new_args + text_after_cursor
                        new_cursor = len('/' + command + ' ' + new_args)
                        logger.info(f"apply_completion: Replacing incomplete arg '{incomplete_arg_part}' with '{selected_arg_text}'")
                    else:
                        # No incomplete argument name found - append new argument after existing ones
                        # Close any unclosed quotes first
                        existing_text_to_use = existing_text.rstrip()
                        
                        # Check if last part has unclosed quote
                        if existing_text_to_use:
                            last_eq_pos = existing_text_to_use.rfind('=')
                            if last_eq_pos >= 0:
                                value_part = existing_text_to_use[last_eq_pos + 1:].strip()
                                if value_part.startswith('"') and not (value_part.endswith('"') and value_part.count('"') >= 2):
                                    # Unclosed quote - close it
                                    existing_text_to_use = existing_text_to_use + '"'
                        
                        if existing_text_to_use:
                            new_args = existing_text_to_use + ' ' + selected_arg_text
                        else:
                            new_args = selected_arg_text
                        new_value = '/' + command + ' ' + new_args + text_after_cursor
                        new_cursor = len('/' + command + ' ' + new_args)
                        logger.info(f"apply_completion: Appending new arg '{selected_arg_text}' after existing args")
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
        
        Hide dropdown when user is typing INSIDE argument values (after = or inside quotes),
        to avoid showing empty dropdown when editing values.

        Note: search_string here is the ORIGINAL full text, not the processed one
        from get_search_string(). We check the target widget directly.
        """
        # Get the actual input text up to cursor
        text = self.target.value[:self.target.cursor_position]

        # For @ trigger: check if last @ has no space after it
        if '@' in text:
            last_at = text.rfind('@')
            text_after_at = text[last_at:]
            # Show if no space after @, hide if there's a space (completion done)
            if ' ' not in text_after_at:
                logger.info(f"should_show_dropdown: '@' active, text_after_at='{text_after_at}' -> True")
                return True

        # For / trigger: must be at start
        if text.startswith('/'):
            search_str = text[1:]
            
            # If there's a space, user is typing arguments
            if ' ' in search_str:
                parts = search_str.split(' ', 1)
                arg_text = parts[1] if len(parts) > 1 else ""
                
                if not arg_text.strip():
                    # Just space after command - show dropdown for argument suggestions
                    logger.info(f"should_show_dropdown: '/' with space, empty args -> True")
                    return True
                
                # Parse arguments using quote-aware parser
                arg_parts = parse_command_arguments(arg_text)
                
                if not arg_parts:
                    # No parts - just whitespace
                    logger.info(f"should_show_dropdown: '/' with space, no arg parts -> True")
                    return True
                
                last_part = arg_parts[-1]
                
                # Extract value part if last part has =
                parsed = extract_value_part(last_part)
                if parsed:
                    arg_name, value_part = parsed
                    
                    # Check if we're typing inside a quoted value
                    if value_part.startswith('"'):
                        if is_inside_quotes(value_part):
                            # We're typing inside an incomplete quoted value - hide dropdown
                            logger.info(f"should_show_dropdown: '/' typing inside incomplete quoted value (value_part='{value_part}') -> False")
                            return False
                        elif value_part.count('"') >= 2 and value_part.endswith('"'):
                            # Complete quoted value - check if there's trailing space
                            if arg_text.rstrip().endswith(' '):
                                # Space after complete argument - show dropdown for next arg
                                logger.info(f"should_show_dropdown: '/' with complete quoted value and space -> True")
                                return True
                            else:
                                # No space - user might be editing inside quotes, hide dropdown
                                logger.info(f"should_show_dropdown: '/' typing inside complete quoted value -> False")
                                return False
                        else:
                            # Just opened quote or edge case - hide dropdown
                            logger.info(f"should_show_dropdown: '/' just opened quote or edge case (value_part='{value_part}') -> False")
                            return False
                    else:
                        # Unquoted value - check if it's complete
                        if arg_text.rstrip().endswith(' '):
                            # Space after value - show dropdown for next arg
                            logger.info(f"should_show_dropdown: '/' with complete unquoted value and space -> True")
                            return True
                        elif value_part and not value_part.isspace():
                            # Has value but no space - user is typing a value, hide dropdown
                            logger.info(f"should_show_dropdown: '/' typing unquoted value -> False")
                            return False
                        else:
                            # Empty value - show dropdown
                            logger.info(f"should_show_dropdown: '/' with empty value -> True")
                            return True
                else:
                    # Last part doesn't have = - user is typing an argument name, show dropdown
                    logger.info(f"should_show_dropdown: '/' typing argument name -> True")
                    return True
            else:
                # No space - user is typing command name, show dropdown
                logger.info(f"should_show_dropdown: '/' typing command name -> True")
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
        # Update the generator's schema cache reference (in case it was updated)
        self._arg_suggestion_generator.schema_cache = self._prompt_schema_cache
        
        # Use the generator to create suggestions
        return self._arg_suggestion_generator.generate_suggestions(command_name, current_text)
    
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

