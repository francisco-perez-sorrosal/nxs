from collections.abc import Mapping
from nxs.application.claude import Claude
from nxs.domain.protocols import MCPClient
from nxs.application.tools import ToolManager
from nxs.logger import get_logger
from anthropic.types import MessageParam

logger = get_logger("agent_loop")


class AgentLoop:
    """
    Agent loop managing conversation with Claude AI.

    Design Note: self.messages maintains conversation state across multiple run() calls.
    This is INTENTIONAL - the LLM is stateless and requires full message history on each call.

    Future Enhancement: Multi-Session Support
    -----------------------------------------
    Planned feature: Multiple concurrent conversation sessions (like browser tabs).
    Each session will have its own AgentLoop instance maintaining separate state.

    Implementation pattern (not yet implemented):
        SessionManager {
            sessions: Dict[session_id, AgentLoop]
            create_session(session_id) -> AgentLoop
            switch_session(session_id) -> AgentLoop
            delete_session(session_id)
        }

    See: application/session_manager.py (placeholder for future implementation)
    """

    def __init__(self, llm: Claude, clients: Mapping[str, MCPClient], callbacks=None):
        self.llm: Claude = llm
        self.tool_clients: Mapping[str, MCPClient] = clients
        self.messages: list[MessageParam] = []  # Conversation state - persists across run() calls
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
                    # Convert to JSON string for consistent formatting
                    import json
                    await callbacks['on_tool_result'](
                        tool_name='multiple',
                        result=json.dumps(tool_result_parts, default=str),
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
