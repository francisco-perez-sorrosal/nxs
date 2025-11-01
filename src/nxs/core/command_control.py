from typing import List, Tuple
from mcp.types import Prompt, PromptMessage
from anthropic.types import MessageParam

from nxs.core.chat import AgentLoop
from nxs.core.claude import Claude
from nxs.mcp_client.client import AuthClient
from nxs.logger import get_logger

logger = get_logger("main")


class CommandControlAgent(AgentLoop):
    def __init__(
        self,
        clients: dict[str, AuthClient],
        claude_service: Claude,
        callbacks=None,
    ):
        super().__init__(clients=clients, llm=claude_service, callbacks=callbacks)

    async def list_prompts(self) -> list[Prompt]:
        all_prompts = []
        for mcp_name, mcp_client in self.tool_clients.items():
            logger.info(f"Listing prompts for {mcp_name}")
            prompts = await mcp_client.list_prompts()
            all_prompts.extend(prompts)
        return all_prompts

    async def list_resource_ids(self) -> dict[str, list[str]]:
        all_resource_ids = {}
        for mcp_name, mcp_client in self.tool_clients.items():
            logger.info(f"Listing resource IDs for {mcp_name}")
            resource_ids = await mcp_client.list_resources()
            if isinstance(resource_ids, list) and len(resource_ids) > 0:
                logger.info(f"Resource IDs{type(resource_ids[0])}: {resource_ids[0]}")
            all_resource_ids[mcp_name] = [r.uri for r in resource_ids]
        return all_resource_ids

    async def _extract_resources(self, query: str) -> str:
        mentions = [word[1:] for word in query.split() if word.startswith("@")]

        resource_ids = await self.list_resource_ids()
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
            messages = await self.tool_clients[mcp_name].get_prompt(command, resource_id)
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
