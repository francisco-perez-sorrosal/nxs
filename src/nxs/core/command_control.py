from typing import List, Tuple
from mcp.types import Prompt, PromptMessage
from anthropic.types import MessageParam

from nxs.core.chat import AgentLoop
from nxs.core.claude import Claude
from nxs.core.artifact_manager import ArtifactManager
from nxs.logger import get_logger

logger = get_logger("main")


class CommandControlAgent(AgentLoop):
    def __init__(
        self,
        artifact_manager: ArtifactManager,
        claude_service: Claude,
        callbacks=None,
    ):
        # Get clients from ArtifactManager for the base AgentLoop
        clients = artifact_manager.clients
        super().__init__(clients=clients, llm=claude_service, callbacks=callbacks)
        self.artifact_manager = artifact_manager

    async def _extract_resources(self, query: str) -> str:
        mentions = [word[1:] for word in query.split() if word.startswith("@")]

        resource_ids = await self.artifact_manager.get_resources()
        mentioned_docs: list[Tuple[str, str, str]] = []

        for mcp_name, resource_uris in resource_ids.items():
            for resource_id in resource_uris:
                # Check if the resource_id or URI is in mentions
                if resource_id in mentions or any(mention in resource_id for mention in mentions):
                    content = await self.tool_clients[mcp_name].read_resource(resource_id)
                    mentioned_docs.append((mcp_name, resource_id, content))

        resource_context = "".join(f'\n<resource id="{mcp_name}:{resource_id}">\n{content}\n</resource>\n' for mcp_name, resource_id, content in mentioned_docs)
        logger.info(f"Extracted resource context: {resource_context}")
        return resource_context

    def _parse_key_value_pairs(self, text: str) -> list[tuple[str, str]]:
        """
        Parse key=value pairs from text, handling quoted strings correctly.
        
        Examples:
            'style="very format"' -> [('style', 'very format')]
            'style=very key2="value with spaces"' -> [('style', 'very'), ('key2', 'value with spaces')]
            "style='single quotes'" -> [('style', 'single quotes')]
        
        Args:
            text: String containing key=value pairs
            
        Returns:
            List of (key, value) tuples
        """
        pairs = []
        i = 0
        while i < len(text):
            # Skip whitespace
            while i < len(text) and text[i].isspace():
                i += 1
            if i >= len(text):
                break
            
            # Find the key (everything up to =)
            key_start = i
            while i < len(text) and text[i] != '=' and not text[i].isspace():
                i += 1
            
            if i >= len(text) or text[i] != '=':
                # No = found, skip this token
                while i < len(text) and not text[i].isspace():
                    i += 1
                continue
            
            key = text[key_start:i].strip()
            i += 1  # Skip the =
            
            # Skip whitespace after =
            while i < len(text) and text[i].isspace():
                i += 1
            
            if i >= len(text):
                # No value after =
                pairs.append((key, ''))
                break
            
            # Parse the value (handling quoted strings)
            value_start = i
            if text[i] in ['"', "'"]:
                # Quoted string
                quote_char = text[i]
                i += 1  # Skip opening quote
                value_start = i
                # Find closing quote
                while i < len(text) and text[i] != quote_char:
                    # Handle escaped quotes
                    if text[i] == '\\' and i + 1 < len(text) and text[i + 1] == quote_char:
                        i += 2
                    else:
                        i += 1
                value = text[value_start:i]
                i += 1  # Skip closing quote
            else:
                # Unquoted value - take until next space or end
                while i < len(text) and not text[i].isspace():
                    i += 1
                value = text[value_start:i].strip()
            
            pairs.append((key, value))
        
        return pairs

    def _parse_command_arguments(
        self, 
        query: str, 
        command_name: str, 
        prompt: Prompt
    ) -> dict[str, str]:
        """
        Parse command arguments from user query based on prompt's argument schema.

        Args:
            query: Full user query string (e.g., "/format @docs://document1.pdf")
            command_name: The command name (e.g., "format")
            prompt: The Prompt object with its argument schema

        Returns:
            Dictionary of parsed arguments matching the prompt's schema
        """
        args: dict[str, str] = {}
        
        # Extract the prompt's argument schema
        # Prompts have an 'arguments' field which is a JSON schema
        if not hasattr(prompt, 'arguments') or not prompt.arguments:
            logger.debug(f"Prompt '{command_name}' has no arguments schema, returning empty dict")
            return args
        
        # Get the properties from the arguments schema
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
            # JSON schema format with 'properties'
            properties = schema.get('properties', {})
            arg_names = list(properties.keys())
            required_args = schema.get('required', [])
        else:
            # Try to get properties as an attribute
            if hasattr(schema, 'properties'):
                properties = getattr(schema, 'properties', {})
                if isinstance(properties, dict):
                    arg_names = list(properties.keys())
            if hasattr(schema, 'required'):
                required_args = getattr(schema, 'required', [])
        
        if not arg_names:
            logger.debug(f"Prompt '{command_name}' has no argument properties")
            return args
        
        # Remove the command name and split the rest
        # Query format: "/command arg1 arg2 ..." or "/command @resource_id"
        remaining = query[len(f"/{command_name}"):].strip()
        
        # If there's only one argument and remaining text starts with @,
        # treat it as a resource reference
        if len(arg_names) == 1 and remaining.startswith('@'):
            arg_name = arg_names[0]
            # Extract resource ID (may include mcp:// prefix)
            resource_ref = remaining[1:].strip()
            
            # If it contains a colon, it might be "mcp_name:resource_id"
            if ':' in resource_ref and not resource_ref.startswith('mcp://'):
                parts = resource_ref.split(':', 1)
                resource_ref = parts[1] if len(parts) > 1 else resource_ref
            
            # Extract just the resource identifier (remove mcp:// prefix if present)
            if resource_ref.startswith('mcp://'):
                # Extract resource ID from URI like "mcp://server/resource_id"
                resource_id = resource_ref.split('/', 3)[-1] if '/' in resource_ref[6:] else resource_ref
            else:
                resource_id = resource_ref
            
            args[arg_name] = resource_id
            logger.debug(f"Parsed single argument '{arg_name}' = '{resource_id}' from resource reference")
        else:
            # Parse multiple arguments
            # Try to parse as space-separated values
            # Format: "/command value1 value2 ..." or "/command key=value key2=value2"
            
            # Check if arguments are in key=value format
            if '=' in remaining:
                # Parse key=value pairs with proper quoted string handling
                pairs = self._parse_key_value_pairs(remaining)
                for key, value in pairs:
                    if key in arg_names:
                        args[key] = value
                        logger.debug(f"Parsed argument '{key}' = '{value}' from key=value format")
            else:
                # Parse as positional arguments
                values = remaining.split()
                for i, arg_name in enumerate(arg_names):
                    if i < len(values):
                        value = values[i].strip().strip('"').strip("'")
                        # Remove @ prefix if present
                        if value.startswith('@'):
                            value = value[1:]
                            # Handle mcp:// prefix
                            if value.startswith('mcp://'):
                                value = value.split('/', 3)[-1] if '/' in value[6:] else value
                            # Handle server:resource format
                            elif ':' in value and not value.startswith('mcp://'):
                                parts = value.split(':', 1)
                                value = parts[1] if len(parts) > 1 else value
                        args[arg_name] = value
                        logger.debug(f"Parsed positional argument '{arg_name}' = '{value}'")
        
        # Build a complete schema dictionary for validation and default extraction
        schema_dict: dict[str, dict] = {}
        if isinstance(schema, list):
            # Convert list of PromptArgument to schema dict format
            for arg in schema:
                if isinstance(arg, dict):
                    arg_name = arg.get('name', '')
                    if arg_name:
                        schema_dict[arg_name] = {
                            'required': arg.get('required', False),
                            'default': arg.get('default'),
                            'description': arg.get('description', ''),
                            'type': arg.get('type', 'string')
                        }
                elif hasattr(arg, 'name'):
                    arg_name = arg.name
                    # Try to get defaults from model_dump
                    default = None
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
                        pass
                    
                    # Filter out invalid defaults (PydanticUndefined, etc.)
                    if default is not None:
                        default_str = str(default)
                        if 'Undefined' in default_str or 'PydanticUndefined' in default_str:
                            default = None
                        elif 'class' in default_str.lower() and '<' in default_str:
                            default = None
                    
                    schema_dict[arg_name] = {
                        'required': getattr(arg, 'required', False) if hasattr(arg, 'required') else False,
                        'default': default,
                        'description': getattr(arg, 'description', '') if hasattr(arg, 'description') else '',
                        'type': 'string'
                    }
        elif isinstance(schema, dict):
            # Already in dict format
            properties = schema.get('properties', {})
            if not isinstance(properties, dict):
                logger.warning(f"Prompt '{command_name}' has non-dict properties: {type(properties)}")
                properties = {}
            required_list = schema.get('required', [])
            required_set = set(required_list) if isinstance(required_list, list) else set()
            for arg_name, arg_spec in properties.items():
                if isinstance(arg_spec, dict):
                    schema_dict[arg_name] = {
                        'required': arg_name in required_set,
                        'default': arg_spec.get('default'),
                        'description': arg_spec.get('description', ''),
                        'type': arg_spec.get('type', 'string')
                    }
                else:
                    schema_dict[arg_name] = {
                        'required': arg_name in required_set,
                        'default': None,
                        'description': getattr(arg_spec, 'description', '') if hasattr(arg_spec, 'description') else '',
                        'type': 'string'
                    }
        
        # Apply defaults for optional arguments that weren't provided
        for arg_name, arg_info in schema_dict.items():
            if arg_name not in args:
                if 'default' in arg_info and arg_info['default'] is not None:
                    # Apply default value
                    args[arg_name] = arg_info['default']
                    logger.debug(f"Applied default value for '{arg_name}': {arg_info['default']}")
        
        # Validate required arguments
        missing = [arg for arg in required_args if arg not in args]
        if missing:
            logger.warning(f"Missing required arguments for prompt '{command_name}': {missing}")
            # For now, we'll still proceed but log the warning
        
        # Validate provided arguments against schema
        invalid_args = []
        for arg_name, arg_value in args.items():
            if arg_name not in schema_dict:
                invalid_args.append(arg_name)
                logger.warning(f"Unknown argument '{arg_name}' for prompt '{command_name}'")
            # TODO: Add type validation if needed
        
        if invalid_args:
            logger.warning(f"Invalid arguments provided for prompt '{command_name}': {invalid_args}")
        
        logger.info(f"Final arguments for '{command_name}' (after applying defaults): {args}")
        return args

    async def _process_command(self, query: str) -> bool:
        """
        Process a command query (starting with /).

        Args:
            query: The user query (e.g., "/format @docs://document1.pdf")

        Returns:
            True if the query was processed as a command, False otherwise
        """
        if not query.startswith("/"):
            return False

        # Extract command name
        words = query.split()
        if not words:
            return False
            
        command_name = words[0].replace("/", "")
        
        # Find the prompt definition from MCP servers
        prompt_info = await self.artifact_manager.find_prompt(command_name)
        if not prompt_info:
            logger.warning(f"Command '{command_name}' not found in any MCP server")
            return False
        
        prompt, mcp_server_name = prompt_info
        
        # Parse arguments from the query based on the prompt's schema
        try:
            args = self._parse_command_arguments(query, command_name, prompt)
            
            # Get the MCP client for this server
            mcp_client = self.tool_clients.get(mcp_server_name)
            if not mcp_client:
                logger.error(f"MCP client not found for server '{mcp_server_name}'")
                return False
            
            # Call get_prompt with the parsed arguments
            logger.info(f"Executing prompt '{command_name}' on server '{mcp_server_name}' with arguments: {args}")
            logger.info(f"Arguments dict structure: {type(args)}, keys: {list(args.keys())}, values: {list(args.values())}")
            
            try:
                messages = await mcp_client.get_prompt(command_name, args)
                
                if messages:
                    prompt_messages = convert_prompt_messages_to_message_params(messages)
                    logger.info(f"Successfully processed command '{command_name}'")
                    logger.info(f"Returned prompt messages: {len(prompt_messages)} message(s)")
                    logger.debug(f"First message structure: {prompt_messages[0] if prompt_messages else 'None'}")
                    self.messages += prompt_messages
                    return True
                else:
                    logger.warning(f"No messages returned from prompt '{command_name}'")
                    return False
            except Exception as e:
                logger.error(f"Error calling get_prompt for '{command_name}': {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise
                
        except Exception as e:
            logger.error(f"Error processing command '{command_name}': {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _process_query(self, query: str):
        logger.info(f"CommandControlAgent processing query: '{query[:50]}{'...' if len(query) > 50 else ''}'")

        # Check if this is a command
        is_command = await self._process_command(query)
        if is_command:
            logger.info("Query was processed as a command")
            return

        logger.debug("Extracting resources from query")
        added_resources = await self._extract_resources(query)

        if added_resources:
            logger.info(f"Found {len(added_resources)} characters of resource content")
        else:
            logger.debug("No resources found in query")

        prompt = f"""
        The user has a question:
        <query>
        {query}
        </query>

        The following context may be useful in answering their question:
        <context>
        {added_resources}
        </context>

        Note the user's query might contain references to documents like "@report.docx". The "@" is only
        included as a way of mentioning the doc. The actual name of the document would be "report.docx".
        If the document content is included in this prompt, you don't need to use an additional tool to read the document.
        Answer the user's question directly and concisely. Start with the exact information they need.
        Don't refer to or mention the provided context in any way - just use it to inform your answer.
        """

        logger.debug("Adding user message to conversation")
        self.messages.append({"role": "user", "content": prompt})


def convert_prompt_message_to_message_param(
    prompt_message: "PromptMessage",
) -> MessageParam:
    role = "user" if prompt_message.role == "user" else "assistant"

    content = prompt_message.content

    # Check if content is a dict-like object with a "type" field
    if isinstance(content, dict) or hasattr(content, "__dict__"):
        content_type = content.get("type", None) if isinstance(content, dict) else getattr(content, "type", None)
        if content_type == "text":
            content_text = content.get("text", "") if isinstance(content, dict) else getattr(content, "text", "")
            return {"role": role, "content": content_text}

    if isinstance(content, list):
        text_blocks = []
        for item in content:
            # Check if item is a dict-like object with a "type" field
            if isinstance(item, dict) or hasattr(item, "__dict__"):
                item_type = item.get("type", None) if isinstance(item, dict) else getattr(item, "type", None)
                if item_type == "text":
                    item_text = item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
                    text_blocks.append({"type": "text", "text": item_text})

        if text_blocks:
            return {"role": role, "content": text_blocks}

    return {"role": role, "content": ""}


def convert_prompt_messages_to_message_params(
    prompt_messages: List[PromptMessage],
) -> List[MessageParam]:
    return [convert_prompt_message_to_message_param(msg) for msg in prompt_messages]
