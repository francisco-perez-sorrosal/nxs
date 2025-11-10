"""
QueryHandler for handling query processing and agent loop callbacks.

This handler processes:
- Query submission and processing
- Agent loop callbacks (stream chunks, tool calls, etc.)
- Status updates during query processing
"""

from typing import TYPE_CHECKING, Callable, Optional

from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.application.chat import AgentLoop
    from nxs.presentation.widgets.chat_panel import ChatPanel
    from nxs.presentation.status_queue import StatusQueue

logger = get_logger("query_handler")


class QueryHandler:
    """
    Handles query processing and agent loop callbacks.

    This handler manages the processing of user queries through the agent loop,
    handles streaming chunks, tool calls, and status updates.
    """

    def __init__(
        self,
        agent_loop: "AgentLoop",
        chat_panel_getter: Callable[[], "ChatPanel"],
        status_queue: "StatusQueue",
        mcp_initialized_getter: Callable[[], bool],
        focus_input: Callable[[], None],
        on_query_complete: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize the QueryHandler.

        Args:
            agent_loop: The AgentLoop instance for processing queries
            chat_panel_getter: Function to get the ChatPanel widget
            status_queue: StatusQueue for status updates
            mcp_initialized_getter: Function to check if MCP is initialized
            focus_input: Function to focus the input field
            on_query_complete: Optional callback invoked after successful query processing
        """
        self.agent_loop = agent_loop
        self.chat_panel_getter = chat_panel_getter
        self.status_queue = status_queue
        self.mcp_initialized_getter = mcp_initialized_getter
        self.focus_input = focus_input
        self.on_query_complete = on_query_complete

    async def process_query(self, query: str, query_id: int) -> None:
        """
        Process a user query through the agent loop.

        Args:
            query: User's input text
            query_id: Sequential ID of the query for ordering
        """
        logger.info(
            f"Starting to process query (query_id={query_id}): " f"'{query[:50]}{'...' if len(query) > 50 else ''}'"
        )

        # Check if MCP connections are still initializing (non-blocking)
        # Tools will be dynamically discovered - they'll be empty at first, then populate as servers connect
        if not self.mcp_initialized_getter():
            logger.info("MCP connections still initializing, but proceeding with query")
            await self.status_queue.add_info_message(
                "Processing query (MCP tools will be available once servers connect)..."
            )

        try:
            # Add assistant message start marker when processing begins
            # This ensures the correct buffer is active when chunks arrive
            chat = self.chat_panel_getter()
            chat.add_assistant_message_start()
            logger.debug(f"Added assistant message start marker (query_id={query_id})")

            # Run the agent loop with UI callbacks
            # Note: User message was already added in on_input_submitted to ensure
            # it appears in submission order
            logger.info(f"Running agent loop with query (query_id={query_id}): {query[:100]}...")

            await self.agent_loop.run(
                query,
                callbacks={
                    "on_stream_chunk": self._on_stream_chunk,
                    "on_stream_complete": self._on_stream_complete,
                    "on_tool_call": self._on_tool_call,
                    "on_tool_result": self._on_tool_result,
                    "on_start": self._on_start,
                },
            )

            logger.info(f"Query processing completed successfully (query_id={query_id})")
            
            # Invoke post-query callback (e.g., session auto-save)
            if self.on_query_complete:
                try:
                    self.on_query_complete()
                    logger.debug("on_query_complete callback invoked successfully")
                except Exception as callback_error:
                    logger.error(f"Error in on_query_complete callback: {callback_error}", exc_info=True)

        except Exception as e:
            logger.error(f"Error processing query (query_id={query_id}): {e}", exc_info=True)
            chat = self.chat_panel_getter()
            chat.add_panel(
                f"[bold red]Error:[/] {str(e)}",
                title="Error",
                style="red",
            )
        finally:
            logger.debug(f"Cleaning up after query processing (query_id={query_id})")

            # Refocus the input field so user can continue typing
            self.focus_input()

    async def _on_start(self) -> None:
        """Called when agent loop starts processing."""
        logger.debug("Agent loop started processing")
        await self.status_queue.add_info_message("Processing query...")

    async def _on_stream_chunk(self, chunk: str) -> None:
        """
        Handle streaming chunks from the agent.

        Args:
            chunk: A piece of the assistant's response
        """
        logger.debug(f"Received stream chunk: '{chunk[:30]}{'...' if len(chunk) > 30 else ''}'")
        chat = self.chat_panel_getter()
        chat.add_assistant_chunk(chunk)

    async def _on_stream_complete(self) -> None:
        """Called when streaming is complete."""
        logger.debug("Stream completed")
        chat = self.chat_panel_getter()
        chat.finish_assistant_message()  # Properly finish the assistant message

    async def _on_tool_call(self, tool_name: str, params: dict) -> None:
        """
        Handle tool call notifications.

        Args:
            tool_name: Name of the tool being called
            params: Tool parameters
        """
        logger.info(f"Tool call: {tool_name} with params: {params}")
        await self.status_queue.add_tool_call(tool_name, params)

    async def _on_tool_result(self, tool_name: str, result: str, success: bool = True) -> None:
        """
        Handle tool execution results.

        Args:
            tool_name: Name of the tool that was executed
            result: Result text/data
            success: Whether the tool executed successfully
        """
        logger.info(f"Tool result: {tool_name} - success={success}, result length={len(str(result))}")
        await self.status_queue.add_tool_result(tool_name, result, success)
