from nxs.core.claude import Claude
from nxs.mcp_client.client import MCPAuthClient
from nxs.core.tools import ToolManager
from nxs.logger import get_logger
from anthropic.types import MessageParam

logger = get_logger("agent_loop")


class AgentLoop:
    def __init__(self, llm: Claude, clients: dict[str, MCPAuthClient], callbacks=None):
        self.llm: Claude = llm
        self.tool_clients: dict[str, MCPAuthClient] = clients
        self.messages: list[MessageParam] = []
        self.callbacks = callbacks or {}

    async def _process_query(self, query: str):
        logger.info(f"Processing query: {query[:100]}{'...' if len(query) > 100 else ''}")
        self.messages.append({"role": "user", "content": query})

    async def run(self, query: str, callbacks=None) -> str:
        logger.info(f"Starting agent loop session ({id(self)})")
        
        # Use provided callbacks or instance callbacks
        callbacks = callbacks or self.callbacks
        
        # Notify start
        if 'on_start' in callbacks:
            await callbacks['on_start']()
 
        final_text_response = ""

        await self._process_query(query)

        while True:
            logger.debug("Sending request to LLM")
            response = self.llm.chat(
                messages=self.messages,
                tools=await ToolManager.get_all_tools(self.tool_clients),
            )

            self.llm.add_assistant_message(self.messages, response)

            # Stream response text if callback available
            text = self.llm.text_from_message(response)
            if 'on_stream_chunk' in callbacks:
                # Simulate streaming by chunking with delays
                import asyncio
                for i in range(0, len(text), 20):  # Smaller chunks for more realistic streaming
                    chunk = text[i:i+20]
                    await callbacks['on_stream_chunk'](chunk)
                    # Add small delay to simulate real streaming
                    await asyncio.sleep(0.05)  # 50ms delay between chunks

            if response.stop_reason == "tool_use":
                logger.info("LLM requested tool use")
                
                # Notify tool call
                for block in response.content:
                    if block.type == "tool_use":
                        if 'on_tool_call' in callbacks:
                            await callbacks['on_tool_call'](
                                block.name,
                                block.input
                            )

                tool_result_parts = await ToolManager.execute_tool_requests(self.tool_clients, response)
                logger.debug(f"Tool execution completed, {len(tool_result_parts)} result parts")
                
                # Notify tool results
                if 'on_tool_result' in callbacks:
                    await callbacks['on_tool_result'](
                        tool_name='multiple',
                        result=str(tool_result_parts),
                        success=True
                    )

                self.llm.add_user_message(self.messages, tool_result_parts)
            else:
                final_text_response = text
                logger.info("Chat session completed successfully")
                
                if 'on_stream_complete' in callbacks:
                    await callbacks['on_stream_complete']()
                
                break

        return final_text_response
