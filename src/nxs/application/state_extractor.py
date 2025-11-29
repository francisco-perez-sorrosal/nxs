"""State Extractor for LLM-powered extraction of structured information.

This module provides the StateExtractor class that uses Claude Haiku to extract
structured information from conversation exchanges, including:
- User profile information (name, occupation, expertise, preferences)
- Factual statements (configuration values, technical facts, decisions)
- Intent classification (question, command, research, chat)

The extractor uses lightweight Claude Haiku for fast, cost-efficient extraction
with structured JSON output.
"""

import json
from typing import Any, Optional

from anthropic import AsyncAnthropic
from anthropic.types import Message

from nxs.logger import get_logger

logger = get_logger(__name__)


class StateExtractor:
    """Extract structured information from conversations using LLM.

    Uses Claude Haiku for fast, inexpensive extraction of:
    - User profile data (identity, expertise, preferences)
    - Factual statements for knowledge base
    - User intent classification

    The extractor is designed to be called after each conversation exchange
    to incrementally build up session state.

    Attributes:
        client: AsyncAnthropic client for API calls
        model: Model to use for extraction (default: claude-3-haiku-20240307)
        max_tokens: Maximum tokens for extraction responses
        enable_user_extraction: Whether to extract user profile info
        enable_fact_extraction: Whether to extract facts
        enable_intent_extraction: Whether to classify intent

    Example:
        ```python
        extractor = StateExtractor(anthropic_client)

        # Extract user info
        user_info = await extractor.extract_user_info(
            "My name is Alice and I'm a senior Python developer",
            "Nice to meet you, Alice! How can I help you today?"
        )
        # Returns: {"name": "Alice", "occupation": "senior Python developer", ...}

        # Extract facts
        facts = await extractor.extract_facts(
            "What's the API rate limit?",
            "The API rate limit is 1000 requests per hour with a burst limit of 100."
        )
        # Returns: ["API rate limit is 1000 requests per hour", "Burst limit is 100 requests"]
        ```
    """

    def __init__(
        self,
        client: AsyncAnthropic,
        *,
        model: str = "claude-3-haiku-20240307",
        max_tokens: int = 500,
        enable_user_extraction: bool = True,
        enable_fact_extraction: bool = True,
        enable_intent_extraction: bool = True,
    ):
        """Initialize the StateExtractor.

        Args:
            client: AsyncAnthropic client for API calls
            model: Model to use for extraction (default: Haiku for speed/cost)
            max_tokens: Maximum tokens for extraction responses
            enable_user_extraction: Enable user profile extraction
            enable_fact_extraction: Enable fact extraction
            enable_intent_extraction: Enable intent classification
        """
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.enable_user_extraction = enable_user_extraction
        self.enable_fact_extraction = enable_fact_extraction
        self.enable_intent_extraction = enable_intent_extraction

        logger.debug(
            f"StateExtractor initialized: model={model}, "
            f"user_extraction={enable_user_extraction}, "
            f"fact_extraction={enable_fact_extraction}, "
            f"intent_extraction={enable_intent_extraction}"
        )

    async def extract_user_info(
        self,
        user_msg: str,
        assistant_msg: str,
    ) -> dict[str, Any]:
        """Extract user profile information from conversation exchange.

        Analyzes the conversation to extract structured information about the user,
        including identity, expertise, preferences, and project context.

        Args:
            user_msg: User's message
            assistant_msg: Assistant's response

        Returns:
            Dictionary with extracted user information fields.
            Only includes fields that were explicitly mentioned.
            Returns empty dict if extraction disabled or no info found.

        Example:
            >>> info = await extractor.extract_user_info(
            ...     "I'm Bob, a beginner Python developer working on a web app",
            ...     "Hi Bob! I'd be happy to help with your web app."
            ... )
            >>> info
            {
                "name": "Bob",
                "expertise_level": "beginner",
                "programming_languages": ["Python"],
                "current_project": "web app"
            }
        """
        if not self.enable_user_extraction:
            return {}

        # Skip extraction if messages are too short to contain useful info
        if len(user_msg) < 10 and len(assistant_msg) < 10:
            return {}

        prompt = f"""Extract user information from this conversation exchange.

User: {user_msg}
Assistant: {assistant_msg}

Extract ONLY information that is explicitly stated. Return JSON with these fields
(omit fields that are not mentioned):

{{
  "name": "string",
  "age": number,
  "location": "string",
  "occupation": "string",
  "expertise_level": "beginner|intermediate|expert",
  "programming_languages": ["string"],
  "frameworks": ["string"],
  "interests": ["string"],
  "current_project": "string",
  "project_tech_stack": ["string"],
  "communication_style": "concise|detailed|technical"
}}

Rules:
1. Only extract explicitly stated information
2. Infer expertise_level from context if mentioned (e.g., "senior developer" → "expert")
3. Extract programming languages and frameworks from project descriptions
4. Omit fields with no information
5. Return {{}} if nothing to extract

Return ONLY valid JSON, no additional text."""

        try:
            response: Message = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text content
            if not response.content or len(response.content) == 0:
                logger.warning("Empty response from user info extraction")
                return {}

            content_text = response.content[0].text if hasattr(response.content[0], "text") else str(response.content[0])

            # Parse JSON response
            extracted = json.loads(content_text)

            if extracted:
                logger.debug(f"Extracted user info: {list(extracted.keys())}")
            else:
                logger.debug("No user info extracted from exchange")

            return extracted

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse user info extraction response: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error during user info extraction: {e}", exc_info=True)
            return {}

    async def extract_facts(
        self,
        user_msg: str,
        assistant_msg: str,
    ) -> list[str]:
        """Extract factual statements from assistant's response.

        Identifies factual information that should be stored in the knowledge base
        for future reference, such as configuration values, file paths, technical
        facts, and decisions made.

        Args:
            user_msg: User's message (provides context)
            assistant_msg: Assistant's response (source of facts)

        Returns:
            List of factual statements as strings.
            Returns empty list if extraction disabled or no facts found.

        Example:
            >>> facts = await extractor.extract_facts(
            ...     "What's the database configuration?",
            ...     "The database runs on port 5432 with max_connections set to 100."
            ... )
            >>> facts
            ["Database port: 5432", "Database max_connections: 100"]
        """
        if not self.enable_fact_extraction:
            return []

        # Skip extraction if assistant response is too short
        if len(assistant_msg) < 20:
            return []

        prompt = f"""Extract factual statements from the assistant's response that might be
useful for future reference in this session.

User: {user_msg}
Assistant: {assistant_msg}

Return a JSON array of factual statements. Include:
- Configuration values (ports, limits, settings)
- File paths and locations
- Technical facts and specifications
- Decisions made or recommendations given
- Key findings or results

Rules:
1. Extract clear, self-contained facts (don't require context to understand)
2. Be concise but specific (e.g., "API rate limit: 1000 req/hr")
3. Omit conversational filler ("As I mentioned earlier...")
4. Maximum 10 facts per response
5. Return [] if no meaningful facts

Examples of good facts:
- "API rate limit is 1000 requests per hour"
- "Database config file: /etc/postgresql/postgresql.conf"
- "Recommended using React Hooks over class components"

Return ONLY a valid JSON array, no additional text."""

        try:
            response: Message = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text content
            if not response.content or len(response.content) == 0:
                logger.warning("Empty response from fact extraction")
                return []

            content_text = response.content[0].text if hasattr(response.content[0], "text") else str(response.content[0])

            # Parse JSON response
            facts = json.loads(content_text)

            if not isinstance(facts, list):
                logger.warning(f"Expected list from fact extraction, got {type(facts)}")
                return []

            # Filter out empty strings and limit to 10 facts
            facts = [f.strip() for f in facts if isinstance(f, str) and f.strip()][:10]

            if facts:
                logger.debug(f"Extracted {len(facts)} fact(s) from exchange")
            else:
                logger.debug("No facts extracted from exchange")

            return facts

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse fact extraction response: {e}")
            return []
        except Exception as e:
            logger.error(f"Error during fact extraction: {e}", exc_info=True)
            return []

    async def classify_intent(
        self,
        user_msg: str,
    ) -> dict[str, Any]:
        """Classify the user's intent from their message.

        Determines the type of request the user is making to help tailor
        the response and update interaction context.

        Args:
            user_msg: User's message to classify

        Returns:
            Dictionary with 'type' and 'confidence' keys.
            Type is one of: question, command, research, chat, clarification.
            Returns {"type": "chat", "confidence": 0.5} if classification fails.

        Example:
            >>> intent = await extractor.classify_intent(
            ...     "Can you explain how async/await works in Python?"
            ... )
            >>> intent
            {"type": "question", "confidence": 0.9, "details": {"topic": "async/await"}}
        """
        if not self.enable_intent_extraction:
            return {"type": "chat", "confidence": 0.5}

        # Quick heuristic checks before calling LLM
        if len(user_msg) < 5:
            return {"type": "chat", "confidence": 0.7}

        prompt = f"""Classify the user's intent from their message.

User message: {user_msg}

Classify the intent into one of these categories:
- "question": Asking for information or explanation
- "command": Requesting an action or task to be performed
- "research": Complex query requiring investigation or analysis
- "chat": Casual conversation or acknowledgment
- "clarification": Asking for clarification or providing clarification

Return JSON with this structure:
{{
  "type": "question|command|research|chat|clarification",
  "confidence": 0.0 to 1.0,
  "details": {{
    "topic": "optional topic/subject",
    "complexity": "simple|medium|complex"
  }}
}}

Rules:
1. Be conservative with "research" - only for complex analytical queries
2. Confidence should reflect certainty of classification
3. Include topic if identifiable
4. Return confidence < 0.7 if ambiguous

Return ONLY valid JSON, no additional text."""

        try:
            response: Message = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text content
            if not response.content or len(response.content) == 0:
                logger.warning("Empty response from intent classification")
                return {"type": "chat", "confidence": 0.5}

            content_text = response.content[0].text if hasattr(response.content[0], "text") else str(response.content[0])

            # Parse JSON response
            intent = json.loads(content_text)

            # Validate structure
            if not isinstance(intent, dict) or "type" not in intent:
                logger.warning("Invalid intent classification structure")
                return {"type": "chat", "confidence": 0.5}

            # Ensure confidence is present and valid
            if "confidence" not in intent or not isinstance(intent["confidence"], (int, float)):
                intent["confidence"] = 0.7

            # Ensure details dict exists
            if "details" not in intent:
                intent["details"] = {}

            logger.debug(
                f"Classified intent: {intent['type']} "
                f"(confidence={intent['confidence']:.2f})"
            )

            return intent

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse intent classification response: {e}")
            return {"type": "chat", "confidence": 0.5}
        except Exception as e:
            logger.error(f"Error during intent classification: {e}", exc_info=True)
            return {"type": "chat", "confidence": 0.5}
