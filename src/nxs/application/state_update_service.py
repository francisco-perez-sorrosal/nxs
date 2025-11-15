"""State update service for coordinating session state updates.

This module provides StateUpdateService which listens to agent loop events
and updates SessionState accordingly. It acts as a bridge between the
agent loop and the session state, ensuring state stays in sync with
conversation progress.

Phase 2: Core state update coordination
Phase 3: LLM-powered state extraction (future)
"""

import asyncio
from typing import Optional, Any, TYPE_CHECKING

from nxs.application.session_state import SessionState
from nxs.domain.events import EventBus, StateChanged
from nxs.domain.protocols import StateProvider
from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.application.state_extractor import StateExtractor

logger = get_logger(__name__)


class StateUpdateService:
    """Coordinates state updates from agent loop events.

    This service acts as a bridge between the agent loop and SessionState,
    listening to agent events and updating state components accordingly.

    Responsibilities:
    - Update interaction context from conversation exchanges
    - Record tool execution metadata
    - Track reasoning task completions
    - Publish StateChanged events for UI updates
    - Trigger async state persistence

    Phase 2: Basic state update coordination
    Phase 3: LLM-powered extraction for user profile and facts (future)

    Example:
        >>> state_update_service = StateUpdateService(
        ...     session_state=session.state,
        ...     event_bus=event_bus,
        ...     state_provider=provider,
        ... )
        >>>
        >>> # Called from agent loop callbacks
        >>> await state_update_service.on_message_added("user", "Hello!")
        >>> await state_update_service.on_tool_executed("search", result, metadata)
    """

    def __init__(
        self,
        session_state: SessionState,
        event_bus: EventBus,
        state_provider: StateProvider,
        enable_auto_save: bool = True,
        state_extractor: Optional["StateExtractor"] = None,
    ):
        """Initialize state update service.

        Args:
            session_state: SessionState instance to update
            event_bus: EventBus for publishing state change events
            state_provider: StateProvider for async persistence
            enable_auto_save: Whether to auto-save state after updates (default True)
            state_extractor: Optional StateExtractor for LLM-powered extraction (Phase 3+)
        """
        self.session_state = session_state
        self.event_bus = event_bus
        self.state_provider = state_provider
        self.enable_auto_save = enable_auto_save
        self.state_extractor = state_extractor

        logger.debug(
            f"StateUpdateService initialized for session: {session_state.session_id}, "
            f"extractor={'enabled' if state_extractor else 'disabled'}"
        )

    async def on_message_added(
        self,
        role: str,
        content: str,
        *,
        is_tool_result: bool = False,
    ) -> None:
        """Called when a message is added to the conversation.

        Updates interaction context with the exchange.

        Args:
            role: Message role ("user" or "assistant")
            content: Message content
            is_tool_result: Whether this is a tool result message (skip if True)
        """
        # Skip tool result messages (internal chatter)
        if is_tool_result:
            return

        # Update interaction context
        # For now, we track exchanges at a basic level
        # Phase 3 will add LLM-powered topic/intent extraction

        # Track last user message for potential fact extraction
        if role == "user":
            self._last_user_message = content

            # Phase 3: Extract user info from message if extractor available
            if self.state_extractor:
                try:
                    user_info = await self.state_extractor.extract_user_info(content)

                    # Update user profile if name detected
                    if user_info.get("name"):
                        self.session_state.user_profile.update_name(user_info["name"])
                        logger.debug(f"Extracted user name: {user_info['name']}")

                    # Add detected preferences
                    for key, value in user_info.get("preferences", {}).items():
                        self.session_state.user_profile.add_preference(key, value)

                    # Add detected facts about user
                    for fact in user_info.get("facts", []):
                        self.session_state.user_profile.add_fact(fact)

                except Exception as e:
                    logger.error(f"Error extracting user info: {e}", exc_info=True)

        elif role == "assistant" and hasattr(self, "_last_user_message"):
            # Complete exchange
            self.session_state.interaction_context.add_exchange(
                user_message=self._last_user_message,
                assistant_response=content,
            )
            logger.debug(
                f"Added exchange to interaction context: {len(self._last_user_message)} chars user, "
                f"{len(content)} chars assistant"
            )

            # Phase 3: Extract topic and intent if extractor available
            if self.state_extractor:
                try:
                    topic, intent = await self.state_extractor.extract_topic_and_intent(
                        self._last_user_message
                    )
                    if topic:
                        self.session_state.interaction_context.update_topic(topic)
                    if intent:
                        self.session_state.interaction_context.update_intent(intent)
                except Exception as e:
                    logger.error(f"Error extracting topic/intent: {e}", exc_info=True)

            # Phase 3: Extract preferences from exchange if extractor available
            if self.state_extractor:
                try:
                    preferences = await self.state_extractor.extract_preferences_from_exchange(
                        self._last_user_message, content
                    )
                    for key, value in preferences.items():
                        self.session_state.user_profile.add_preference(key, value)
                        logger.debug(f"Extracted preference: {key} = {value}")
                except Exception as e:
                    logger.error(f"Error extracting preferences: {e}", exc_info=True)

            # Publish state change event
            self.event_bus.publish(
                StateChanged(
                    session_id=self.session_state.session_id,
                    component="interaction_context",
                    change_type="exchange_added",
                )
            )

            # Auto-save if enabled
            if self.enable_auto_save:
                asyncio.create_task(self._save_state())

    async def on_tool_executed(
        self,
        tool_name: str,
        result: str,
        success: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Called when a tool is executed.

        Updates session metadata with tool call information.

        Args:
            tool_name: Name of the tool executed
            result: Tool execution result
            success: Whether execution was successful
            metadata: Optional metadata (tokens, cost, etc.)
        """
        # Update metadata
        tokens = metadata.get("tokens", 0) if metadata else 0
        cost = metadata.get("cost", 0.0) if metadata else 0.0

        self.session_state.metadata.record_tool_call(tokens=tokens, cost=cost)

        logger.debug(
            f"Recorded tool call: {tool_name}, success={success}, "
            f"tokens={tokens}, cost=${cost:.6f}"
        )

        # Phase 3: Extract facts from tool results if extractor available
        if self.state_extractor and success:
            try:
                facts = await self.state_extractor.extract_facts_from_tool_result(
                    tool_name=tool_name,
                    result=result,
                )
                for fact in facts:
                    self.session_state.knowledge_base.add_fact(
                        content=fact["content"],
                        source=fact.get("source", f"tool:{tool_name}"),
                        tags=fact.get("tags", []),
                        confidence=fact.get("confidence", 0.8),
                    )
                    logger.debug(f"Extracted fact from tool '{tool_name}': {fact['content'][:50]}...")
            except Exception as e:
                logger.error(f"Error extracting facts from tool result: {e}", exc_info=True)

        # Publish state change event
        self.event_bus.publish(
            StateChanged(
                session_id=self.session_state.session_id,
                component="metadata",
                change_type="tool_call_recorded",
            )
        )

        # Auto-save if enabled
        if self.enable_auto_save:
            asyncio.create_task(self._save_state())

    async def on_reasoning_complete(
        self,
        query: str,
        result: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Called when adaptive reasoning completes.

        Updates session metadata with reasoning task information.

        Args:
            query: Original query
            result: Reasoning result
            metadata: Optional metadata (tokens, cost, tracker, etc.)
        """
        # Update metadata
        tokens = metadata.get("tokens", 0) if metadata else 0
        cost = metadata.get("cost", 0.0) if metadata else 0.0

        self.session_state.metadata.record_reasoning_task(tokens=tokens, cost=cost)

        logger.debug(
            f"Recorded reasoning task: query_len={len(query)}, "
            f"tokens={tokens}, cost=${cost:.6f}"
        )

        # Phase 3: Extract confirmed facts from reasoning tracker (future)
        # if "tracker" in metadata:
        #     tracker = metadata["tracker"]
        #     for fact in tracker.insights.confirmed_facts:
        #         self.session_state.knowledge_base.add_fact(
        #             fact, source="research", confidence=0.9
        #         )

        # Publish state change event
        self.event_bus.publish(
            StateChanged(
                session_id=self.session_state.session_id,
                component="metadata",
                change_type="reasoning_task_recorded",
            )
        )

        # Auto-save if enabled
        if self.enable_auto_save:
            asyncio.create_task(self._save_state())

    async def update_user_profile(
        self,
        name: Optional[str] = None,
        preference_updates: Optional[dict[str, Any]] = None,
        facts: Optional[list[str]] = None,
    ) -> None:
        """Manually update user profile.

        This method allows manual updates to the user profile.
        Phase 3 will add automatic extraction from conversations.

        Args:
            name: User's name (if detected)
            preference_updates: Preferences to add/update
            facts: Facts about the user to add
        """
        if name:
            self.session_state.user_profile.update_name(name)
            logger.debug(f"Updated user name: {name}")

        if preference_updates:
            for key, value in preference_updates.items():
                self.session_state.user_profile.add_preference(key, value)
            logger.debug(f"Updated {len(preference_updates)} user preferences")

        if facts:
            for fact in facts:
                self.session_state.user_profile.add_fact(fact)
            logger.debug(f"Added {len(facts)} user facts")

        # Publish state change event
        self.event_bus.publish(
            StateChanged(
                session_id=self.session_state.session_id,
                component="user_profile",
                change_type="profile_updated",
            )
        )

        # Auto-save if enabled
        if self.enable_auto_save:
            asyncio.create_task(self._save_state())

    async def add_knowledge(
        self,
        content: str,
        source: str = "manual",
        tags: Optional[list[str]] = None,
        confidence: float = 1.0,
    ) -> None:
        """Manually add knowledge to the knowledge base.

        This method allows manual fact addition.
        Phase 3 will add automatic extraction from conversations.

        Args:
            content: Fact content
            source: Source of the fact
            tags: Optional tags for categorization
            confidence: Confidence score (0.0-1.0)
        """
        self.session_state.knowledge_base.add_fact(
            content=content,
            source=source,
            tags=tags,
            confidence=confidence,
        )

        logger.debug(f"Added fact to knowledge base: {content[:50]}...")

        # Publish state change event
        self.event_bus.publish(
            StateChanged(
                session_id=self.session_state.session_id,
                component="knowledge_base",
                change_type="fact_added",
            )
        )

        # Auto-save if enabled
        if self.enable_auto_save:
            asyncio.create_task(self._save_state())

    async def update_context(
        self,
        topic: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> None:
        """Manually update interaction context.

        This method allows manual context updates.
        Phase 3 will add automatic topic/intent detection from conversations.

        Args:
            topic: Current conversation topic
            intent: User's current intent
        """
        if topic:
            self.session_state.interaction_context.update_topic(topic)
            logger.debug(f"Updated conversation topic: {topic}")

        if intent:
            self.session_state.interaction_context.update_intent(intent)
            logger.debug(f"Updated user intent: {intent}")

        # Publish state change event
        self.event_bus.publish(
            StateChanged(
                session_id=self.session_state.session_id,
                component="interaction_context",
                change_type="context_updated",
            )
        )

        # Auto-save if enabled
        if self.enable_auto_save:
            asyncio.create_task(self._save_state())

    async def _save_state(self) -> None:
        """Save session state asynchronously.

        This is called automatically after state updates if enable_auto_save is True.
        """
        try:
            await self.session_state.save()
            logger.debug(f"Auto-saved session state: {self.session_state.session_id}")
        except Exception as e:
            logger.error(
                f"Failed to auto-save session state {self.session_state.session_id}: {e}",
                exc_info=True,
            )

    # Phase 3: LLM-powered extraction methods (future implementation)

    # async def _extract_facts_from_tool_result(self, tool_name: str, result: str) -> None:
    #     """Extract facts from tool results using LLM (Phase 3)."""
    #     pass

    # async def _extract_user_info_from_message(self, message: str) -> None:
    #     """Extract user information from messages using LLM (Phase 3)."""
    #     pass

    # async def _detect_topic_and_intent(self, user_message: str) -> tuple[str, str]:
    #     """Detect conversation topic and user intent using LLM (Phase 3)."""
    #     pass
