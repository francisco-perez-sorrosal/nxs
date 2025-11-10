"""Conversation state management with cache control support.

This module provides the Conversation class that manages message history,
applies prompt caching optimizations, and supports persistence for sessions.

Key features:
- Message history management (user, assistant, tool results)
- Anthropic prompt caching with cache_control markers
- Conversation persistence (to_dict/from_dict)
- Token estimation and history management
- Separation of state from orchestration (AgentLoop)

Prompt Caching Strategy:
- System messages: Always cached (long-lived prompts)
- Tools: Always cached (stable across conversation)
- Messages: Cache last user message + assistant response pair
- Minimum 1,024 tokens per cache checkpoint (Anthropic requirement)

Cache Processing Order (Anthropic API):
1. Tools
2. System message
3. Conversation messages (chronological)
"""

from datetime import datetime
from typing import Any, Optional, cast

from anthropic.types import (
    ContentBlock,
    Message,
    MessageParam,
    TextBlockParam,
    ToolResultBlockParam,
    ToolUseBlock,
)

from nxs.logger import get_logger

logger = get_logger(__name__)


class Conversation:
    """Manages conversation message history with prompt caching support.

    The Conversation class separates message state management from orchestration
    logic (AgentLoop). It handles:
    - Adding user, assistant, and tool result messages
    - Applying cache_control markers for cost optimization
    - Converting to/from dict for session persistence
    - Estimating token usage
    - Managing history truncation

    Example:
        >>> conversation = Conversation(
        ...     system_message="You are a helpful assistant.",
        ...     enable_caching=True
        ... )
        >>> conversation.add_user_message("Hello!")
        >>> messages = conversation.get_messages_for_api()
        >>> # Use messages with Claude API
        >>> conversation.add_assistant_message(response)
    """

    def __init__(
        self,
        system_message: Optional[str] = None,
        max_history_messages: Optional[int] = None,
        enable_caching: bool = True,
    ):
        """Initialize a new conversation.

        Args:
            system_message: Optional system prompt for the conversation.
            max_history_messages: Maximum number of messages to retain.
                If None, no limit is applied. If set, older messages are
                truncated while preserving the most recent exchanges.
            enable_caching: Whether to apply cache_control markers for
                Anthropic prompt caching. Defaults to True for 90% cost
                reduction on cached content.
        """
        self._messages: list[MessageParam] = []
        self._system_message = system_message
        self._max_history_messages = max_history_messages
        self._enable_caching = enable_caching
        self._created_at = datetime.now()
        self._last_modified_at = datetime.now()

        logger.debug(
            f"Conversation initialized: caching={enable_caching}, "
            f"max_messages={max_history_messages}"
        )

    def add_user_message(self, content: str | list[dict[str, Any]]) -> None:
        """Add a user message to the conversation.

        Args:
            content: User message content. Can be:
                - str: Plain text message
                - list[dict]: Rich content blocks (text, images, documents)

        Example:
            >>> conversation.add_user_message("What is the weather?")
            >>> conversation.add_user_message([
            ...     {"type": "text", "text": "Analyze this image"},
            ...     {"type": "image", "source": {...}}
            ... ])
        """
        # Type checkers need help with the flexible content parameter
        # We cast to the proper MessageParam structure
        message: MessageParam = {"role": "user", "content": cast(Any, content)}
        self._messages.append(message)
        self._last_modified_at = datetime.now()
        self._apply_history_limit()

        logger.debug(f"Added user message: {len(self._messages)} total messages")

    def add_assistant_message(self, message: Message) -> None:
        """Add an assistant message to the conversation.

        Args:
            message: Anthropic Message object from API response containing
                assistant's reply, which may include text content and/or
                tool use blocks.

        Example:
            >>> response = await claude.create_message(...)
            >>> conversation.add_assistant_message(response)
        """
        # Extract content from the Message object
        content: list[ContentBlock] = message.content

        assistant_message: MessageParam = {
            "role": "assistant",
            "content": content,
        }
        self._messages.append(assistant_message)
        self._last_modified_at = datetime.now()
        self._apply_history_limit()

        logger.debug(
            f"Added assistant message with {len(content)} content blocks: "
            f"{len(self._messages)} total messages"
        )

    def add_tool_results(self, tool_use_blocks: list[ToolUseBlock], results: list[str]) -> None:
        """Add tool execution results to the conversation.

        After Claude requests tool calls (via ToolUseBlock), this method adds
        the execution results back into the conversation so Claude can continue
        with the results.

        Args:
            tool_use_blocks: List of ToolUseBlock from Claude's response
                containing tool_use_id and tool parameters.
            results: List of tool execution result strings corresponding
                to each tool_use_block (same order and length).

        Example:
            >>> tool_blocks = [block for block in message.content
            ...                if block.type == "tool_use"]
            >>> results = await execute_tools(tool_blocks)
            >>> conversation.add_tool_results(tool_blocks, results)
        """
        if len(tool_use_blocks) != len(results):
            raise ValueError(
                f"Mismatch between tool_use_blocks ({len(tool_use_blocks)}) "
                f"and results ({len(results)})"
            )

        # Build tool result content blocks
        # Use ToolResultBlockParam for proper typing
        tool_result_content: list[ToolResultBlockParam] = [
            {
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": result,
            }
            for tool_block, result in zip(tool_use_blocks, results)
        ]

        tool_message: MessageParam = {
            "role": "user",
            "content": cast(Any, tool_result_content),
        }
        self._messages.append(tool_message)
        self._last_modified_at = datetime.now()
        self._apply_history_limit()

        logger.debug(
            f"Added {len(results)} tool results: {len(self._messages)} total messages"
        )

    def get_messages_for_api(self) -> list[MessageParam]:
        """Get messages formatted for Anthropic API with cache control.

        Applies cache_control markers to optimize costs:
        - Caches the last user message in the conversation
        - This enables 90% cost reduction on cached content

        Cache placement rationale:
        - Last user message is most likely to be stable and reused
        - Covers common patterns: streaming responses, tool calls, retries
        - Meets 1,024 token minimum for caching efficiency

        Returns:
            List of MessageParam dicts ready for Anthropic API, with
            cache_control markers applied if caching is enabled.

        Example:
            >>> messages = conversation.get_messages_for_api()
            >>> response = await claude.create_message(
            ...     messages=messages,
            ...     system=conversation.get_system_message_for_api()
            ... )
        """
        if not self._enable_caching or not self._messages:
            return self._messages

        # Clone messages to avoid mutating internal state
        messages = [msg.copy() for msg in self._messages]

        # Find the last user message and mark it for caching
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                # Apply cache control to the last content block
                content = messages[i]["content"]
                if isinstance(content, str):
                    # Convert string content to list format for cache_control
                    text_block: TextBlockParam = {
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"},
                    }
                    messages[i]["content"] = cast(Any, [text_block])
                elif isinstance(content, list) and content:
                    # Add cache_control to last block in list
                    # Create new list with all blocks except last, then add modified last block
                    new_content = list(content[:-1])
                    last_block = dict(content[-1])  # Convert to dict for modification
                    last_block["cache_control"] = {"type": "ephemeral"}
                    new_content.append(last_block)
                    messages[i]["content"] = cast(Any, new_content)

                logger.debug(f"Applied cache control to last user message at index {i}")
                break

        return messages

    def get_system_message_for_api(self) -> str | list[TextBlockParam] | None:
        """Get system message formatted for API with cache control.

        System messages are always cached (if caching is enabled) because:
        - They are stable across the entire conversation
        - They are typically long (instructions, context, examples)
        - They provide maximum cost savings (90% reduction)

        Returns:
            System message with cache_control marker, or None if no system
            message is set. Can be:
            - str: Simple text system message (converted to cached format)
            - list[TextBlockParam]: Rich content blocks with cache_control
            - None: No system message

        Example:
            >>> system = conversation.get_system_message_for_api()
            >>> response = await claude.create_message(
            ...     messages=messages,
            ...     system=system
            ... )
        """
        if not self._system_message:
            return None

        if not self._enable_caching:
            return self._system_message

        # Apply cache control to system message
        # System messages are always cached for maximum savings
        text_block: TextBlockParam = {
            "type": "text",
            "text": self._system_message,
            "cache_control": {"type": "ephemeral"},
        }
        return [text_block]

    def clear_history(self) -> None:
        """Clear all messages from the conversation.

        Preserves system message and configuration. Useful for starting
        a fresh conversation within the same session.

        Example:
            >>> conversation.clear_history()
            >>> assert conversation.get_message_count() == 0
        """
        self._messages.clear()
        self._last_modified_at = datetime.now()
        logger.info("Conversation history cleared")

    def get_message_count(self) -> int:
        """Get the total number of messages in the conversation.

        Returns:
            Integer count of messages (user, assistant, tool results).

        Example:
            >>> count = conversation.get_message_count()
            >>> print(f"Conversation has {count} messages")
        """
        return len(self._messages)

    def get_token_estimate(self) -> int:
        """Estimate token count for the conversation.

        Provides a rough estimate based on character count. For accurate
        token counting, use Anthropic's token counting API or library.

        Estimation: ~4 characters per token (English text average)

        Returns:
            Estimated token count for all messages.

        Example:
            >>> tokens = conversation.get_token_estimate()
            >>> print(f"~{tokens} tokens")
        """
        total_chars = 0

        # Count system message
        if self._system_message:
            total_chars += len(self._system_message)

        # Count conversation messages
        for message in self._messages:
            content = message["content"]
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total_chars += len(block["text"])
                    # Note: Image/document tokens not estimated here

        # Rough estimate: 4 chars per token
        return total_chars // 4

    def _serialize_content_block(self, block: Any) -> dict[str, Any]:
        """Convert Anthropic SDK content block to JSON-serializable dict.
        
        Args:
            block: Content block (can be dict, TextBlock, ToolUseBlock, etc.)
            
        Returns:
            Plain dict representation
        """
        if isinstance(block, dict):
            # Already a dict, but recursively clean nested objects
            return {k: self._serialize_value(v) for k, v in block.items()}
        elif hasattr(block, "model_dump"):
            # Pydantic model (Anthropic SDK objects)
            return block.model_dump()
        elif hasattr(block, "__dict__"):
            # Generic object with __dict__
            return {k: self._serialize_value(v) for k, v in block.__dict__.items() if not k.startswith("_")}
        else:
            # Primitive type
            return block

    def _serialize_value(self, value: Any) -> Any:
        """Recursively serialize a value to JSON-safe format.
        
        Args:
            value: Any value to serialize
            
        Returns:
            JSON-safe representation
        """
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        elif isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif hasattr(value, "model_dump"):
            # Pydantic model
            return value.model_dump()
        elif hasattr(value, "__dict__"):
            # Generic object
            return {k: self._serialize_value(v) for k, v in value.__dict__.items() if not k.startswith("_")}
        else:
            # Fallback: convert to string
            return str(value)

    def _serialize_messages(self) -> list[dict[str, Any]]:
        """Convert messages to JSON-serializable format.
        
        Handles Anthropic SDK objects (TextBlock, ToolUseBlock, etc.)
        and converts them to plain dicts.
        
        Returns:
            List of serialized message dicts
        """
        serialized = []
        for msg in self._messages:
            msg_dict = dict(msg)  # Copy the message dict
            
            # Serialize content if present
            if "content" in msg_dict:
                content = msg_dict["content"]
                if isinstance(content, str):
                    msg_dict["content"] = content
                elif isinstance(content, list):
                    msg_dict["content"] = [self._serialize_content_block(block) for block in content]
                else:
                    msg_dict["content"] = self._serialize_value(content)
            
            serialized.append(msg_dict)
        
        return serialized

    def to_dict(self) -> dict[str, Any]:
        """Serialize conversation to dictionary for persistence.

        Returns:
            Dictionary containing all conversation state:
            - messages: Message history (with SDK objects converted to dicts)
            - system_message: System prompt
            - max_history_messages: History limit
            - enable_caching: Caching configuration
            - created_at: ISO timestamp
            - last_modified_at: ISO timestamp

        Example:
            >>> data = conversation.to_dict()
            >>> json.dump(data, file)
        """
        return {
            "messages": self._serialize_messages(),
            "system_message": self._system_message,
            "max_history_messages": self._max_history_messages,
            "enable_caching": self._enable_caching,
            "created_at": self._created_at.isoformat(),
            "last_modified_at": self._last_modified_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Conversation":
        """Deserialize conversation from dictionary.

        Args:
            data: Dictionary from to_dict() containing conversation state.

        Returns:
            Restored Conversation instance with all state.

        Example:
            >>> data = json.load(file)
            >>> conversation = Conversation.from_dict(data)
        """
        conversation = cls(
            system_message=data.get("system_message"),
            max_history_messages=data.get("max_history_messages"),
            enable_caching=data.get("enable_caching", True),
        )

        conversation._messages = data.get("messages", [])

        # Restore timestamps
        if "created_at" in data:
            conversation._created_at = datetime.fromisoformat(data["created_at"])
        if "last_modified_at" in data:
            conversation._last_modified_at = datetime.fromisoformat(data["last_modified_at"])

        logger.info(
            f"Conversation restored: {len(conversation._messages)} messages, "
            f"created {conversation._created_at.isoformat()}"
        )

        return conversation

    def _apply_history_limit(self) -> None:
        """Apply max_history_messages limit by truncating oldest messages.

        Preserves the most recent messages when limit is exceeded.
        Called automatically after adding messages.
        """
        if self._max_history_messages is None:
            return

        if len(self._messages) > self._max_history_messages:
            removed_count = len(self._messages) - self._max_history_messages
            self._messages = self._messages[-self._max_history_messages :]
            logger.debug(f"Truncated {removed_count} old messages (limit: {self._max_history_messages})")

    @property
    def created_at(self) -> datetime:
        """Get conversation creation timestamp."""
        return self._created_at

    @property
    def last_modified_at(self) -> datetime:
        """Get last modification timestamp."""
        return self._last_modified_at

    @property
    def system_message(self) -> Optional[str]:
        """Get system message."""
        return self._system_message

    @system_message.setter
    def system_message(self, value: Optional[str]) -> None:
        """Set system message and update modification time."""
        self._system_message = value
        self._last_modified_at = datetime.now()
        logger.debug(f"System message updated: {len(value) if value else 0} chars")
