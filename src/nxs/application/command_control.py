from typing import List, Tuple
from mcp.types import Prompt, PromptMessage
from anthropic.types import MessageParam

from nxs.application.chat import AgentLoop
from nxs.application.claude import Claude
from nxs.application.artifact_manager import ArtifactManager
from nxs.application.parsers import CompositeArgumentParser
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
        self.argument_parser = CompositeArgumentParser()

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
        # Extract the prompt's argument schema
        # Prompts have an 'arguments' field which is a JSON schema
        if not hasattr(prompt, 'arguments') or not prompt.arguments:
            logger.debug(f"Prompt '{command_name}' has no arguments schema, returning empty dict")
            return {}
        
        # Normalize schema using SchemaAdapter
        schema_info = self.argument_parser.normalize_schema(prompt.arguments, command_name)
        if not schema_info:
            return {}
        
        # Remove the command name and split the rest
        # Query format: "/command arg1 arg2 ..." or "/command @resource_id"
        remaining = query[len(f"/{command_name}"):].strip()
        
        # Parse arguments using the composite parser
        args = self.argument_parser.parse(
            query_remaining=remaining,
            arg_names=schema_info.arg_names,
            schema_dict=schema_info.schema_dict,
        )
        
        # Apply defaults for optional arguments that weren't provided
        args = self.argument_parser.apply_defaults(
            args=args,
            schema_dict=schema_info.schema_dict,
            command_name=command_name,
        )
        
        # Validate arguments against schema
        self.argument_parser.validate_arguments(
            args=args,
            required_args=schema_info.required_args,
            schema_dict=schema_info.schema_dict,
            command_name=command_name,
        )
        
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
