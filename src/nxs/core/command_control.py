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

        for mcp_name, resource_ids in resource_ids.items():
            for resource_id in resource_ids:
                if resource_id in mentions:
                    content = await self.tool_clients[mcp_name].read_resource(resource_id)
                    mentioned_docs.append((mcp_name, resource_id, content))

        resource_context = "".join(f'\n<resource id="{mcp_name}:{resource_id}">\n{content}\n</resource>\n' for mcp_name, resource_id, content in mentioned_docs)
        logger.info(f"Extracted esource context: {resource_context}")
        return resource_context

    async def _process_command(self, query: str) -> bool:
        if not query.startswith("/"):
            return False

        words = query.split()
        command = words[0].replace("/", "")

        # Strip @ prefix from resource name if present (e.g., @report.pdf -> report.pdf)
        if words[1].startswith('@'):
            mcp_name, resource_id = words[1].split(":")
            mcp_name = mcp_name[1:]
            resource_id = resource_id[1:]
            # get_prompt expects a dict of args, not a single string
            messages = await self.tool_clients[mcp_name].get_prompt(command, {"resource_id": resource_id})
            self.messages += convert_prompt_messages_to_message_params(messages)
            return True
        else:
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
