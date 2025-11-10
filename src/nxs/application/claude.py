"""Claude API wrapper with streaming and cache control support.

This module provides an enhanced wrapper around the Anthropic Python SDK with:
- Real streaming support using async context managers
- Prompt caching support for cost optimization
- Extended thinking support
- Type-safe API with proper annotations
- Backward compatibility with legacy chat() method
"""

from collections.abc import AsyncIterator
from typing import Any, Optional

from anthropic import Anthropic, AsyncAnthropic
from anthropic.lib.streaming._types import MessageStreamEvent
from anthropic.types import (
    Message,
    MessageParam,
    TextBlockParam,
    ToolParam,
)

from nxs.logger import get_logger

logger = get_logger(__name__)


class Claude:
    """Enhanced Claude API wrapper.

    Provides both synchronous (chat) and asynchronous streaming (stream_message)
    interfaces to the Anthropic API with support for:
    - Prompt caching for 90% cost reduction
    - Real streaming with async/await
    - Extended thinking mode
    - Type-safe parameters

    Example (synchronous):
        >>> claude = Claude(model="claude-sonnet-4.5")
        >>> response = claude.chat(
        ...     messages=[{"role": "user", "content": "Hello"}],
        ...     system="You are helpful"
        ... )

    Example (streaming):
        >>> async for event in claude.stream_message(
        ...     messages=[{"role": "user", "content": "Hello"}],
        ...     system="You are helpful"
        ... ):
        ...     if event.type == "content_block_delta":
        ...         print(event.delta.text, end="")
    """

    def __init__(self, model: str):
        """Initialize Claude API wrapper.

        Args:
            model: Claude model ID (e.g., "claude-sonnet-4.5")
        """
        self.client = Anthropic()
        self.async_client = AsyncAnthropic()
        self.model = model

        logger.debug(f"Claude wrapper initialized with model: {model}")

    def add_user_message(self, messages: list, message: Any) -> None:
        """Add a user message to a message list.

        Helper method for backward compatibility.

        Args:
            messages: List to append to.
            message: Message content (Message object or string).
        """
        user_message = {
            "role": "user",
            "content": message.content if isinstance(message, Message) else message,
        }
        messages.append(user_message)

    def add_assistant_message(self, messages: list, message: Any) -> None:
        """Add an assistant message to a message list.

        Helper method for backward compatibility.

        Args:
            messages: List to append to.
            message: Message content (Message object or string).
        """
        assistant_message = {
            "role": "assistant",
            "content": message.content if isinstance(message, Message) else message,
        }
        messages.append(assistant_message)

    def text_from_message(self, message: Message) -> str:
        """Extract text content from a Message.

        Args:
            message: Anthropic Message object.

        Returns:
            Concatenated text from all text blocks.
        """
        return "\n".join(
            [block.text for block in message.content if block.type == "text"]
        )

    def chat(
        self,
        messages: list[MessageParam],
        system: Optional[str | list[TextBlockParam]] = None,
        temperature: float = 1.0,
        stop_sequences: Optional[list[str]] = None,
        tools: Optional[list[ToolParam]] = None,
        thinking: bool = False,
        thinking_budget: int = 1024,
        max_tokens: int = 8000,
    ) -> Message:
        """Send a chat request to Claude (synchronous, non-streaming).

        This is the legacy method maintained for backward compatibility.
        For new code, consider using stream_message() for real streaming.

        Args:
            messages: List of message dictionaries with cache_control support.
            system: System message (string or list with cache_control).
            temperature: Sampling temperature (0.0 to 1.0).
            stop_sequences: Sequences that stop generation.
            tools: Tool definitions with cache_control support.
            thinking: Enable extended thinking mode.
            thinking_budget: Token budget for thinking (if enabled).
            max_tokens: Maximum tokens in response.

        Returns:
            Message object from Anthropic API.

        Example:
            >>> response = claude.chat(
            ...     messages=[{"role": "user", "content": "Hello"}],
            ...     system=[{
            ...         "type": "text",
            ...         "text": "You are helpful",
            ...         "cache_control": {"type": "ephemeral"}
            ...     }]
            ... )
        """
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if stop_sequences:
            params["stop_sequences"] = stop_sequences

        if thinking:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }

        if tools:
            params["tools"] = tools

        if system:
            params["system"] = system

        logger.debug(
            f"Creating message: {len(messages)} messages, "
            f"{len(tools) if tools else 0} tools, "
            f"system={'yes' if system else 'no'}"
        )

        message = self.client.messages.create(**params)

        logger.debug(
            f"Message created: {message.stop_reason}, "
            f"{len(message.content)} content blocks"
        )

        return message

    async def stream_message(
        self,
        messages: list[MessageParam],
        system: Optional[str | list[TextBlockParam]] = None,
        temperature: float = 1.0,
        stop_sequences: Optional[list[str]] = None,
        tools: Optional[list[ToolParam]] = None,
        thinking: bool = False,
        thinking_budget: int = 1024,
        max_tokens: int = 8000,
    ) -> AsyncIterator[MessageStreamEvent]:
        """Stream a chat request to Claude (asynchronous, real streaming).

        This method provides real streaming using the Anthropic SDK's async
        stream context manager. Events are yielded as they arrive from the API.

        Args:
            messages: List of message dictionaries with cache_control support.
            system: System message (string or list with cache_control).
            temperature: Sampling temperature (0.0 to 1.0).
            stop_sequences: Sequences that stop generation.
            tools: Tool definitions with cache_control support.
            thinking: Enable extended thinking mode.
            thinking_budget: Token budget for thinking (if enabled).
            max_tokens: Maximum tokens in response.

        Yields:
            MessageStreamEvent objects from Anthropic API:
            - message_start: Beginning of message
            - content_block_start: Beginning of content block
            - content_block_delta: Incremental content (text.delta)
            - content_block_stop: End of content block
            - message_delta: Message metadata updates
            - message_stop: End of message

        Example:
            >>> async for event in claude.stream_message(
            ...     messages=[{"role": "user", "content": "Write a story"}]
            ... ):
            ...     if event.type == "content_block_delta":
            ...         if event.delta.type == "text_delta":
            ...             print(event.delta.text, end="", flush=True)
            ...     elif event.type == "message_stop":
            ...         print()  # Newline at end
        """
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if stop_sequences:
            params["stop_sequences"] = stop_sequences

        if thinking:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }

        if tools:
            params["tools"] = tools

        if system:
            params["system"] = system

        logger.debug(
            f"Starting message stream: {len(messages)} messages, "
            f"{len(tools) if tools else 0} tools, "
            f"system={'yes' if system else 'no'}"
        )

        # Use the async streaming context manager
        async with self.async_client.messages.stream(**params) as stream:
            async for event in stream:
                yield event

        logger.debug("Message stream completed")

    async def create_message(
        self,
        messages: list[MessageParam],
        system: Optional[str | list[TextBlockParam]] = None,
        temperature: float = 1.0,
        stop_sequences: Optional[list[str]] = None,
        tools: Optional[list[ToolParam]] = None,
        thinking: bool = False,
        thinking_budget: int = 1024,
        max_tokens: int = 8000,
    ) -> Message:
        """Create a message asynchronously (non-streaming).

        This is the async equivalent of chat() for use in async contexts.

        Args:
            messages: List of message dictionaries with cache_control support.
            system: System message (string or list with cache_control).
            temperature: Sampling temperature (0.0 to 1.0).
            stop_sequences: Sequences that stop generation.
            tools: Tool definitions with cache_control support.
            thinking: Enable extended thinking mode.
            thinking_budget: Token budget for thinking (if enabled).
            max_tokens: Maximum tokens in response.

        Returns:
            Message object from Anthropic API.
        """
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if stop_sequences:
            params["stop_sequences"] = stop_sequences

        if thinking:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }

        if tools:
            params["tools"] = tools

        if system:
            params["system"] = system

        logger.debug(
            f"Creating async message: {len(messages)} messages, "
            f"{len(tools) if tools else 0} tools"
        )

        message = await self.async_client.messages.create(**params)

        logger.debug(
            f"Async message created: {message.stop_reason}, "
            f"{len(message.content)} content blocks"
        )

        return message
