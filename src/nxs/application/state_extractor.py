"""State extraction service for LLM-powered information extraction.

This module provides StateExtractor which uses LLMs to extract structured
information from unstructured conversation and tool results.

Phase 3: Placeholder implementation with manual extraction
Phase 4+: LLM-powered extraction using Claude API

Extraction targets:
- User profile information (name, preferences, context)
- Facts from conversations and tool results
- Topic and intent detection from user messages
"""

from typing import Optional, Any

from nxs.application.claude import Claude
from nxs.logger import get_logger

logger = get_logger(__name__)


class StateExtractor:
    """Service for extracting structured information from unstructured content.

    This service uses LLM prompts to extract:
    - User profile information (name, preferences, facts about user)
    - Knowledge facts from conversations and tool results
    - Conversation topics and user intents

    Phase 3: Placeholder with basic keyword-based extraction
    Phase 4+: Full LLM-powered extraction with structured prompts

    Example:
        >>> extractor = StateExtractor(llm=claude, enable_extraction=True)
        >>>
        >>> # Extract user info from message
        >>> user_info = await extractor.extract_user_info("My name is Alice")
        >>> # {'name': 'Alice', 'preferences': {}, 'facts': []}
        >>>
        >>> # Extract facts from tool result
        >>> facts = await extractor.extract_facts_from_tool_result(
        ...     tool_name="search",
        ...     result="Python was created by Guido van Rossum in 1991"
        ... )
        >>> # [{'content': 'Python was created by Guido van Rossum in 1991',
        >>> #   'source': 'tool:search', 'confidence': 0.8}]
    """

    def __init__(
        self,
        llm: Optional[Claude] = None,
        enable_extraction: bool = False,
    ):
        """Initialize state extractor.

        Args:
            llm: Claude API wrapper for LLM-powered extraction (optional)
            enable_extraction: Whether to enable extraction (default False for Phase 3)
        """
        self.llm = llm
        self.enable_extraction = enable_extraction

        if not enable_extraction:
            logger.info(
                "StateExtractor initialized with extraction disabled "
                "(Phase 3 placeholder mode)"
            )
        else:
            logger.info("StateExtractor initialized with extraction enabled")

    async def extract_user_info(
        self,
        message: str,
    ) -> dict[str, Any]:
        """Extract user information from a message.

        Phase 3: Placeholder with basic keyword detection
        Phase 4+: LLM-powered extraction with structured prompt

        Args:
            message: User message to analyze

        Returns:
            Dictionary with:
            - name: str | None - Detected user name
            - preferences: dict[str, Any] - Detected preferences
            - facts: list[str] - Facts about the user
        """
        if not self.enable_extraction:
            return {"name": None, "preferences": {}, "facts": []}

        # Phase 3: Basic keyword-based extraction
        # Phase 4+: Replace with LLM prompt
        result = {"name": None, "preferences": {}, "facts": []}

        # Simple name detection (Phase 3 placeholder)
        if "my name is" in message.lower():
            # Extract name after "my name is"
            parts = message.lower().split("my name is")
            if len(parts) > 1:
                name_part = parts[1].strip().split()[0] if parts[1].strip() else None
                if name_part:
                    result["name"] = name_part.capitalize()

        logger.debug(f"Extracted user info from message: {result}")
        return result

    async def extract_facts_from_tool_result(
        self,
        tool_name: str,
        result: str,
    ) -> list[dict[str, Any]]:
        """Extract facts from tool execution results.

        Phase 3: Disabled (returns empty list)
        Phase 4+: LLM-powered fact extraction

        Args:
            tool_name: Name of the tool that was executed
            result: Tool execution result text

        Returns:
            List of fact dictionaries with:
            - content: str - Fact content
            - source: str - Source identifier (e.g., "tool:search")
            - confidence: float - Confidence score (0.0-1.0)
            - tags: list[str] - Optional tags
        """
        if not self.enable_extraction:
            return []

        # Phase 3: Placeholder - no automatic fact extraction
        # Phase 4+: Use LLM to extract facts from tool results
        #
        # Example prompt for Phase 4:
        # """
        # Extract factual information from this tool result.
        # Tool: {tool_name}
        # Result: {result}
        #
        # Return facts as JSON array:
        # [
        #   {
        #     "content": "fact statement",
        #     "confidence": 0.9,
        #     "tags": ["tag1", "tag2"]
        #   }
        # ]
        # """

        logger.debug(f"Fact extraction from tool '{tool_name}' not yet implemented")
        return []

    async def extract_topic_and_intent(
        self,
        user_message: str,
    ) -> tuple[str, str]:
        """Detect conversation topic and user intent.

        Phase 3: Disabled (returns empty strings)
        Phase 4+: LLM-powered topic and intent detection

        Args:
            user_message: User's message to analyze

        Returns:
            Tuple of (topic, intent)
            - topic: Detected conversation topic
            - intent: Detected user intent (e.g., "question", "command", "request")
        """
        if not self.enable_extraction:
            return "", ""

        # Phase 3: Placeholder - no automatic topic/intent detection
        # Phase 4+: Use LLM to detect topic and intent
        #
        # Example prompt for Phase 4:
        # """
        # Analyze this user message and identify:
        # 1. Topic: What is the message about?
        # 2. Intent: What does the user want to do?
        #
        # Message: {user_message}
        #
        # Return as JSON:
        # {
        #   "topic": "...",
        #   "intent": "..."
        # }
        # """

        logger.debug("Topic/intent detection not yet implemented")
        return "", ""

    async def extract_preferences_from_exchange(
        self,
        user_message: str,
        assistant_response: str,
    ) -> dict[str, Any]:
        """Extract user preferences from conversation exchange.

        Phase 3: Disabled (returns empty dict)
        Phase 4+: LLM-powered preference extraction

        Args:
            user_message: User's message
            assistant_response: Assistant's response

        Returns:
            Dictionary of detected preferences
        """
        if not self.enable_extraction:
            return {}

        # Phase 3: Placeholder - no automatic preference extraction
        # Phase 4+: Use LLM to extract preferences from exchanges
        #
        # Example: User says "I prefer Python over JavaScript"
        # -> Extract: {"programming_language_preference": "Python"}

        logger.debug("Preference extraction not yet implemented")
        return {}

    # Phase 4+ methods (future implementation)
    #
    # async def _call_llm_for_extraction(
    #     self,
    #     prompt: str,
    #     max_tokens: int = 500,
    # ) -> str:
    #     """Call LLM for extraction task (Phase 4+)."""
    #     if not self.llm:
    #         raise ValueError("LLM required for extraction")
    #
    #     response = await self.llm.send_message(
    #         messages=[{"role": "user", "content": prompt}],
    #         max_tokens=max_tokens,
    #     )
    #     return response.content[0].text
    #
    # async def _parse_json_response(
    #     self,
    #     response: str,
    # ) -> Any:
    #     """Parse JSON response from LLM (Phase 4+)."""
    #     import json
    #     try:
    #         return json.loads(response)
    #     except json.JSONDecodeError as e:
    #         logger.error(f"Failed to parse LLM response as JSON: {e}")
    #         return None
