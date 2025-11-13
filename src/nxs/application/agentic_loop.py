"""Refactored AgentLoop with Conversation and ToolRegistry.

This module provides the new AgentLoop implementation that:
- Uses Conversation for message state management
- Uses ToolRegistry for pluggable tool sources
- Provides real streaming via Claude.stream_message()
- Maintains backward compatibility with callbacks
- Enables session persistence through Conversation

The refactored design separates concerns:
- AgentLoop: Orchestration and control flow
- Conversation: Message history and state
- ToolRegistry: Tool discovery and execution
- Claude: API communication (sync and streaming)
"""

import asyncio
import time
from collections.abc import Mapping
from typing import Any, Callable, Optional

from anthropic.types import ContentBlockDeltaEvent, Message, MessageStopEvent, ToolUseBlock

from nxs.application.approval import ApprovalManager, ApprovalType, create_approval_request
from nxs.application.claude import Claude
from nxs.application.conversation import Conversation
from nxs.application.tool_registry import ToolRegistry
from nxs.application.cost_calculator import CostCalculator
from nxs.logger import get_logger

logger = get_logger("agent_loop")


class AgentLoop:
    """Orchestrates conversation loop with Claude using tools.

    The AgentLoop manages the interaction cycle:
    1. User query → Conversation
    2. Get messages + tools → Claude API
    3. If tool use → Execute tools → Loop back to step 2
    4. If text response → Return to user

    Key improvements over legacy AgentLoop:
    - Conversation handles message state (not self.messages)
    - ToolRegistry provides pluggable tool sources (not just MCP)
    - Real streaming via async generators (not fake chunking)
    - Session persistence ready (via Conversation.to_dict/from_dict)

    Example:
        >>> conversation = Conversation(system_message="You are helpful")
        >>> tool_registry = ToolRegistry()
        >>> tool_registry.register_provider(mcp_provider)
        >>>
        >>> agent = AgentLoop(
        ...     llm=claude,
        ...     conversation=conversation,
        ...     tool_registry=tool_registry
        ... )
        >>>
        >>> result = await agent.run("What's the weather?")
    """

    def __init__(
        self,
        llm: Claude,
        conversation: Optional[Conversation] = None,
        tool_registry: Optional[ToolRegistry] = None,
        callbacks: Optional[dict[str, Callable]] = None,
        approval_manager: Optional[ApprovalManager] = None,
        # Legacy parameter for backward compatibility
        clients: Optional[Mapping[str, Any]] = None,
    ):
        """Initialize the agent loop with backward compatibility.

        Supports two initialization modes:
        1. New mode (recommended): conversation + tool_registry
        2. Legacy mode: clients (creates Conversation and ToolRegistry internally)

        Args:
            llm: Claude API wrapper with streaming support.
            conversation: Conversation instance (optional for legacy mode).
            tool_registry: ToolRegistry instance (optional for legacy mode).
            callbacks: Optional callbacks for streaming, tool execution, etc.
            approval_manager: Optional ApprovalManager for tool execution approval.
            clients: Legacy parameter - Mapping[str, MCPClient] (deprecated).

        Example (new mode):
            >>> conversation = Conversation(system_message="You are helpful")
            >>> tool_registry = ToolRegistry()
            >>> agent = AgentLoop(llm, conversation, tool_registry)

        Example (legacy mode - deprecated):
            >>> agent = AgentLoop(llm, clients=mcp_clients)
        """
        self.llm = llm
        self.callbacks = callbacks or {}
        self.approval_manager = approval_manager

        # Backward compatibility: If clients provided, create Conversation and ToolRegistry
        if clients is not None and (conversation is None or tool_registry is None):
            from nxs.application.mcp_tool_provider import MCPToolProvider

            logger.warning(
                "AgentLoop initialized with legacy 'clients' parameter. "
                "Consider migrating to conversation + tool_registry pattern."
            )

            # Create default Conversation if not provided
            if conversation is None:
                conversation = Conversation(enable_caching=True)
                logger.debug("Created default Conversation for legacy mode")

            # Create ToolRegistry with MCPToolProvider if not provided
            if tool_registry is None:
                tool_registry = ToolRegistry(enable_caching=True)
                mcp_provider = MCPToolProvider(clients)
                tool_registry.register_provider(mcp_provider)
                logger.debug("Created ToolRegistry with MCPToolProvider for legacy mode")

            # Store clients for CommandControlAgent compatibility
            self.tool_clients = clients

        # Validate required parameters
        if conversation is None or tool_registry is None:
            raise ValueError(
                "AgentLoop requires either (conversation + tool_registry) "
                "or (clients) parameters"
            )

        self.conversation = conversation
        self.tool_registry = tool_registry
        self.cost_calculator = CostCalculator()

        # Progress tracker integration (Phase 2)
        self._current_tracker: Optional[Any] = None  # ResearchProgressTracker

        logger.debug(
            f"AgentLoop initialized: {conversation.get_message_count()} "
            f"messages, {tool_registry.get_tool_count()} tools"
        )

    @property
    def messages(self):
        """Legacy property for CommandControlAgent compatibility.

        Provides direct access to conversation messages for backward compatibility.
        """
        return self.conversation._messages

    async def run(
        self,
        query: str,
        callbacks: Optional[dict[str, Callable]] = None,
        use_streaming: bool = True,
    ) -> str:
        """Run the agent loop for a user query.

        Args:
            query: User's query/message.
            callbacks: Optional callbacks override (uses instance callbacks if None).
            use_streaming: Whether to use real streaming (default True).
                Set to False for backward compatibility with fake chunking.

        Returns:
            Final text response from Claude.

        Callback interface:
            - on_start(): Called at start of run
            - on_stream_chunk(chunk: str): Called for each streamed text chunk
            - on_tool_call(name: str, input: dict): Called when tool requested
            - on_tool_result(name: str, result: str, success: bool): Called with tool result
            - on_usage(usage: dict, cost: float): Called after each API response with token usage
            - on_stream_complete(): Called when streaming completes

        Example:
            >>> result = await agent.run(
            ...     "Search for Python tutorials",
            ...     callbacks={
            ...         "on_stream_chunk": lambda c: print(c, end=""),
            ...         "on_tool_call": lambda n, i: print(f"\\nCalling {n}..."),
            ...     }
            ... )
        """
        callbacks = callbacks or self.callbacks

        logger.info(f"Starting agent loop: query='{query[:100]}...'")

        # Notify start
        if "on_start" in callbacks:
            await callbacks["on_start"]()

        # Add user query to conversation (skip if empty - used for pre-added messages like commands)
        if query:
            self.conversation.add_user_message(query)

        final_text_response = ""
        # Track cumulative usage for this conversation round (may include multiple API calls)
        round_input_tokens = 0
        round_output_tokens = 0

        # Main conversation loop: continue until Claude stops requesting tools
        while True:
            # Get conversation state with cache control
            messages = self.conversation.get_messages_for_api()
            system = self.conversation.get_system_message_for_api()
            tools = await self.tool_registry.get_tool_definitions_for_api()

            logger.debug(
                f"Claude API call: {len(messages)} messages, "
                f"{len(tools)} tools, system={'yes' if system else 'no'}"
            )

            # Choose streaming or non-streaming based on flag
            if use_streaming and "on_stream_chunk" in callbacks:
                # Real streaming path
                response = await self._run_with_streaming(
                    messages, system, tools, callbacks
                )
            else:
                # Non-streaming path (legacy compatibility)
                response = await self._run_without_streaming(
                    messages, system, tools, callbacks
                )

            # Add assistant response to conversation
            self.conversation.add_assistant_message(response)

            # Extract usage from response and notify callback
            if hasattr(response, "usage") and response.usage:
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                round_input_tokens += input_tokens
                round_output_tokens += output_tokens

                # Calculate cost for this API call
                cost = self.cost_calculator.calculate_cost(
                    self.llm.model, input_tokens, output_tokens
                )

                # Notify callback with usage
                if "on_usage" in callbacks:
                    usage = {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    }
                    await callbacks["on_usage"](usage, cost)
            else:
                logger.warning("API response missing usage field - cannot track tokens/cost")

            # Check stop reason
            if response.stop_reason == "tool_use":
                logger.info("Claude requested tool execution")

                # Extract tool use blocks
                tool_blocks = [
                    block for block in response.content if block.type == "tool_use"
                ]

                # Execute tools and add results to conversation
                await self._execute_tools(tool_blocks, callbacks)

                # Loop continues - send tool results back to Claude

            else:
                # Claude returned final text response
                final_text_response = self._extract_text(response)

                logger.info(
                    f"Agent loop completed: {len(final_text_response)} chars returned"
                )

                if "on_stream_complete" in callbacks:
                    await callbacks["on_stream_complete"]()

                # Log round totals if we had multiple API calls
                if round_input_tokens > 0 or round_output_tokens > 0:
                    round_cost = self.cost_calculator.calculate_cost(
                        self.llm.model, round_input_tokens, round_output_tokens
                    )
                    logger.debug(
                        f"Round totals: {round_input_tokens} input, "
                        f"{round_output_tokens} output tokens, ${round_cost:.6f}"
                    )

                break

        return final_text_response

    async def _execute_with_tool_tracking(
        self,
        query: str,
        tracker: Any,  # ResearchProgressTracker
        use_streaming: bool = False,
        callbacks: Optional[dict[str, Callable]] = None,
    ) -> str:
        """
        Execute query with tool call tracking.

        Wrapper around base run() that intercepts tool executions
        and logs them to the tracker.

        IMPORTANT: Calls parent AgentLoop.run() directly to avoid recursive
        calls to AdaptiveReasoningLoop.run() which would trigger reasoning again.

        Args:
            query: User query to execute
            tracker: ResearchProgressTracker instance
            use_streaming: Whether to use streaming (default False for buffered execution)
            callbacks: Optional callbacks override

        Returns:
            Final text response from Claude
        """
        # Set current tracker for tool execution interception
        self._current_tracker = tracker

        # Set recursion prevention flag (for AdaptiveReasoningLoop)
        # If self is AdaptiveReasoningLoop, this tells run() to skip reasoning logic
        # and delegate directly to AgentLoop for simple query execution with tool tracking
        previous_skip_reasoning = False
        if hasattr(self, '_skip_reasoning'):
            previous_skip_reasoning = self._skip_reasoning
            self._skip_reasoning = True

        try:
            # Call self.run():
            # - If self is AdaptiveReasoningLoop: _skip_reasoning flag causes it to
            #   bypass reasoning and call parent AgentLoop.run() directly
            # - If self is just AgentLoop: flag is ignored, executes normally
            response = await self.run(query, callbacks=callbacks, use_streaming=use_streaming)
            return response
        finally:
            # Clean up: restore original state
            self._current_tracker = None
            if hasattr(self, '_skip_reasoning'):
                self._skip_reasoning = previous_skip_reasoning

    async def _run_with_streaming(
        self,
        messages: list,
        system: Any,
        tools: list,
        callbacks: dict[str, Callable],
    ) -> Message:
        """Run Claude with real streaming.

        Args:
            messages: Message history with cache control.
            system: System message with cache control.
            tools: Tool definitions with cache control.
            callbacks: Callbacks dictionary.

        Returns:
            Complete Message object after stream finishes.
        """
        logger.debug("Using real streaming via Claude.stream_message()")

        # Build parameters for streaming request
        params = {
            "model": self.llm.model,
            "max_tokens": 8000,
            "messages": messages,
            "temperature": 1.0,
        }

        # Only add tools if we have any (empty list is falsy, so this works)
        if tools:
            params["tools"] = tools
            tool_names = [t.get("name", "unknown") for t in tools]
            logger.info(f"Adding {len(tools)} tools to streaming request: {tool_names}")  # DEBUG: Check tools
        else:
            logger.warning("No tools being sent to Claude API in streaming request")  # DEBUG: Warn if no tools

        # Only add system if we have one
        if system:
            params["system"] = system

        # Stream with context manager
        async with self.llm.async_client.messages.stream(**params) as stream:
            # Process stream events
            async for event in stream:
                try:
                    # Log event type for debugging
                    event_type = getattr(event, "type", None)
                    logger.debug(f"Received stream event: {event_type}")
                    
                    # Handle content block deltas (text streaming)
                    # Events are typed objects from Anthropic SDK
                    if isinstance(event, ContentBlockDeltaEvent):
                        # Access delta directly from typed event
                        delta = event.delta
                        if hasattr(delta, "text") and delta.text:
                            if "on_stream_chunk" in callbacks:
                                await callbacks["on_stream_chunk"](delta.text)
                    
                    # Also check by type string for compatibility
                    elif event_type == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta:
                            text = getattr(delta, "text", None)
                            if text and "on_stream_chunk" in callbacks:
                                await callbacks["on_stream_chunk"](text)
                                
                except Exception as e:
                    logger.error(f"Error processing stream event: {e}", exc_info=True)
                    raise

            # Get final message from stream context
            response = await stream.get_final_message()

        return response

    async def _run_without_streaming(
        self,
        messages: list,
        system: Any,
        tools: list,
        callbacks: dict[str, Callable],
    ) -> Message:
        """Run Claude without streaming (legacy compatibility).

        Args:
            messages: Message history with cache control.
            system: System message with cache control.
            tools: Tool definitions with cache control.
            callbacks: Callbacks dictionary.

        Returns:
            Message object from Claude.
        """
        logger.debug("Using non-streaming via Claude.create_message()")

        # Build parameters
        params = {
            "messages": messages,
        }
        
        # Only add tools if we have any
        if tools:
            params["tools"] = tools
            
        # Only add system if we have one
        if system:
            params["system"] = system

        # Call Claude API without streaming
        response = await self.llm.create_message(**params)

        # Extract text and simulate streaming with fake chunks if callback present
        text = self._extract_text(response)

        if "on_stream_chunk" in callbacks:
            # Fake streaming for backward compatibility
            for i in range(0, len(text), 20):
                chunk = text[i : i + 20]
                await callbacks["on_stream_chunk"](chunk)
                await asyncio.sleep(0.05)  # Artificial delay

        return response

    async def _execute_tools(
        self, tool_blocks: list[ToolUseBlock], callbacks: dict[str, Callable]
    ) -> None:
        """Execute tool requests and add results to conversation.

        Modified to integrate with ResearchProgressTracker (Phase 2):
        - Checks tracker cache before executing tools
        - Logs tool executions to tracker with timing
        - Tracks success/failure metadata

        Args:
            tool_blocks: List of ToolUseBlock from Claude's response.
            callbacks: Callbacks dictionary.
        """
        results: list[str] = []
        approve_all = False
        deny_all = False

        for tool_block in tool_blocks:
            tool_name = tool_block.name
            tool_input = tool_block.input

            logger.debug(f"Executing tool: {tool_name}")

            # NEW: Check tracker for cached result (Phase 2)
            cached_result = None
            should_execute = True

            # Convert tool_input to dict[str, Any] for tracker and execution
            # ToolUseBlock.input is typed as object but is actually a dict
            tool_args: dict[str, Any] = {}
            if isinstance(tool_input, dict):
                tool_args = {str(k): v for k, v in tool_input.items()}
            elif hasattr(tool_input, "__dict__"):
                tool_args = {str(k): v for k, v in tool_input.__dict__.items()}

            if self._current_tracker:
                should_execute, cached_result = self._current_tracker.should_execute_tool(
                    tool_name, tool_args
                )

                if not should_execute and cached_result:
                    logger.info(f"Using cached result for {tool_name}")
                    results.append(cached_result)

                    # Notify tool result (cached)
                    if "on_tool_result" in callbacks:
                        await callbacks["on_tool_result"](tool_name, cached_result, True)

                    # Log cached execution to tracker
                    self._current_tracker.log_tool_execution(
                        tool_name=tool_name,
                        arguments=tool_args,
                        success=True,
                        result=cached_result,
                        execution_time_ms=0.0,  # Cached, no execution time
                    )

                    continue

            # Notify tool call
            if "on_tool_call" in callbacks:
                await callbacks["on_tool_call"](tool_name, tool_input)

            # Human-in-the-Loop: Request approval if enabled
            if (
                self.approval_manager
                and self.approval_manager.config.require_tool_approval
                and tool_name not in self.approval_manager.config.tool_whitelist
                and not approve_all
            ):
                logger.info(f"Requesting approval for tool: {tool_name}")

                # Get tool schema for description
                tool_schema = await self.tool_registry.get_tool_schema(tool_name)
                description = ""
                if tool_schema:
                    description = tool_schema.get("description", "")

                # Build approval request details
                approval_details = {
                    "tool_name": tool_name,
                    "description": description,
                    "input": tool_input,
                }

                request = create_approval_request(
                    approval_type=ApprovalType.TOOL_EXECUTION,
                    title=f"Execute Tool: {tool_name}",
                    details=approval_details,
                )

                response = await self.approval_manager.request_approval(request)

                # Handle approval response
                if response.metadata.get("approve_all"):
                    approve_all = True
                    logger.info("Approve All selected - auto-approving remaining tools")
                elif response.metadata.get("deny_all"):
                    deny_all = True
                    logger.info("Deny All selected - denying remaining tools")

                if not response.approved or deny_all:
                    logger.info(f"Tool execution denied: {tool_name}")
                    error_msg = f"Tool '{tool_name}' execution denied by user"
                    results.append(error_msg)

                    # Notify tool result
                    if "on_tool_result" in callbacks:
                        await callbacks["on_tool_result"](tool_name, error_msg, False)

                    # NEW: Log denied execution to tracker (Phase 2)
                    if self._current_tracker:
                        self._current_tracker.log_tool_execution(
                            tool_name=tool_name,
                            arguments=tool_args,
                            success=False,
                            error=error_msg,
                            execution_time_ms=0.0,
                        )

                    continue

                logger.info(f"Tool execution approved: {tool_name}")

            # NEW: Track execution time (Phase 2)
            start_time = time.time()
            execution_time_ms = 0.0

            try:
                # Execute via ToolRegistry (tool_args already converted above)
                result = await self.tool_registry.execute_tool(tool_name, tool_args)
                execution_time_ms = (time.time() - start_time) * 1000
                results.append(result)

                # Notify tool result
                if "on_tool_result" in callbacks:
                    await callbacks["on_tool_result"](tool_name, result, True)

                logger.debug(f"Tool '{tool_name}' succeeded: {len(result)} chars")

                # NEW: Log successful execution to tracker (Phase 2)
                if self._current_tracker:
                    self._current_tracker.log_tool_execution(
                        tool_name=tool_name,
                        arguments=tool_args,
                        success=True,
                        result=result,
                        execution_time_ms=execution_time_ms,
                    )

            except Exception as e:
                execution_time_ms = (time.time() - start_time) * 1000
                error_msg = f"Error executing tool '{tool_name}': {e}"
                logger.error(error_msg, exc_info=True)

                results.append(error_msg)

                # Notify tool error
                if "on_tool_result" in callbacks:
                    await callbacks["on_tool_result"](tool_name, error_msg, False)

                # NEW: Log failed execution to tracker (Phase 2)
                if self._current_tracker:
                    self._current_tracker.log_tool_execution(
                        tool_name=tool_name,
                        arguments=tool_args,
                        success=False,
                        error=error_msg,
                        execution_time_ms=execution_time_ms,
                    )

        # Add all tool results to conversation
        self.conversation.add_tool_results(tool_blocks, results)

        logger.debug(f"Added {len(results)} tool results to conversation")

    def _extract_text(self, message: Message) -> str:
        """Extract text content from a Message.

        Args:
            message: Anthropic Message object.

        Returns:
            Concatenated text from all text blocks.
        """
        return "\n".join(
            [block.text for block in message.content if block.type == "text"]
        )

    def get_message_count(self) -> int:
        """Get conversation message count.

        Returns:
            Number of messages in the conversation.
        """
        return self.conversation.get_message_count()

    def clear_history(self) -> None:
        """Clear conversation history.

        Useful for starting fresh while keeping the same agent instance.
        """
        self.conversation.clear_history()
        logger.info("Conversation history cleared")
