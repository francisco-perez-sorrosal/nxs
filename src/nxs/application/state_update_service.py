"""State Update Service for coordinated session state updates.

This module provides the StateUpdateService class that coordinates updates
to SessionState from various sources (message additions, tool executions,
reasoning completions) and publishes StateChanged events.

The service decouples state update logic from the agent loop, making state
management testable, maintainable, and event-driven.

Phase 3 Integration: Supports optional StateExtractor for LLM-powered extraction
of user profile information and facts from conversation exchanges.
"""

import asyncio
from typing import Any, Optional, TYPE_CHECKING

from nxs.application.session_state import SessionState, Intent
from nxs.domain.events import EventBus, StateChanged
from nxs.domain.protocols.state import StateProvider
from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.application.state_extractor import StateExtractor

logger = get_logger(__name__)


class StateUpdateService:
    """Coordinates state updates from agent loop events.

    This service listens to various events in the agent loop lifecycle
    (message additions, tool executions, reasoning completions) and updates
    the SessionState accordingly. It also publishes StateChanged events to
    notify subscribers of state changes and handles async persistence.

    Phase 3: Optionally uses StateExtractor to automatically extract user
    profile information and facts from conversation exchanges using LLM.

    The service provides a clean separation between:
    - Agent loop orchestration (CommandControlAgent)
    - State management (SessionState)
    - Event notification (EventBus)
    - Persistence (StateProvider)
    - Extraction (StateExtractor - Phase 3)

    Attributes:
        session_state: The SessionState instance to update
        event_bus: EventBus for publishing StateChanged events
        state_provider: StateProvider for async persistence
        session_id: Session ID for state storage key
        state_extractor: Optional StateExtractor for LLM-powered extraction

    Example:
        ```python
        # Without extraction
        service = StateUpdateService(
            session_state=session.state,
            event_bus=event_bus,
            state_provider=file_provider,
            session_id="session_123",
        )

        # With extraction
        extractor = StateExtractor(anthropic_client)
        service = StateUpdateService(
            session_state=session.state,
            event_bus=event_bus,
            state_provider=file_provider,
            session_id="session_123",
            state_extractor=extractor,
        )

        # Called when exchange completes
        await service.on_exchange_complete(
            user_msg="I'm a Python developer",
            assistant_msg="Great! How can I help you?"
        )
        # → Automatically extracts user info and facts
        ```
    """

    def __init__(
        self,
        session_state: SessionState,
        event_bus: EventBus,
        state_provider: StateProvider,
        session_id: str,
        state_extractor: Optional["StateExtractor"] = None,
    ):
        """Initialize the StateUpdateService.

        Args:
            session_state: The SessionState instance to update
            event_bus: EventBus for publishing StateChanged events
            state_provider: StateProvider for async persistence
            session_id: Session ID for state storage key
            state_extractor: Optional StateExtractor for automatic extraction
        """
        self.session_state = session_state
        self.event_bus = event_bus
        self.state_provider = state_provider
        self.session_id = session_id
        self.state_extractor = state_extractor

        if state_extractor:
            logger.debug(
                f"StateUpdateService initialized with extraction enabled "
                f"(user={state_extractor.enable_user_extraction}, "
                f"facts={state_extractor.enable_fact_extraction}, "
                f"intent={state_extractor.enable_intent_extraction})"
            )
        else:
            logger.debug("StateUpdateService initialized without extraction")

    async def on_exchange_complete(
        self,
        user_msg: str,
        assistant_msg: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Called when a complete user-assistant exchange is finished.

        Updates the interaction context with the exchange and records
        interaction statistics in the state metadata.

        If StateExtractor is configured, automatically extracts:
        - User profile information (name, expertise, preferences)
        - Factual statements for knowledge base
        - User intent classification

        Args:
            user_msg: User's message
            assistant_msg: Assistant's response
            metadata: Optional interaction metadata (tokens, cost, etc.)
        """
        try:
            # Add exchange to interaction context
            self.session_state.interaction_context.add_exchange(
                user_msg=user_msg,
                assistant_msg=assistant_msg,
            )

            # Update state metadata - count as 2 messages
            self.session_state.state_metadata.message_count += 2

            # Record interaction metadata if provided
            if metadata:
                self.session_state.state_metadata.record_interaction(metadata)

            # Extract information using LLM if extractor is configured
            if self.state_extractor:
                await self._extract_from_exchange(user_msg, assistant_msg)

            # Update last_updated timestamp
            from datetime import datetime

            self.session_state.last_updated = datetime.now()

            # Publish event
            self.event_bus.publish(
                StateChanged(
                    session_id=self.session_id,
                    component="interaction_context",
                    change_type="add",
                    details={"exchange": "complete"},
                )
            )

            # Async persistence (fire and forget)
            asyncio.create_task(self._persist_state())

            logger.debug("Recorded complete exchange in interaction context")

        except Exception as e:
            logger.error(
                f"Error updating state on exchange complete: {e}", exc_info=True
            )

    async def on_tool_executed(
        self,
        tool_name: str,
        success: bool,
        metadata: Optional[dict[str, Any]] = None,
        _result: Optional[str] = None,
    ) -> None:
        """Called when a tool is executed.

        Updates the state metadata with tool execution statistics.
        In the future, this could extract facts from tool results.

        Args:
            tool_name: Name of the executed tool
            success: Whether the tool execution succeeded
            metadata: Optional tool execution metadata (execution_time, etc.)
            _result: Optional tool execution result (reserved for future fact extraction)
        """
        try:
            # Extract execution time from metadata if available
            execution_time = 0.0
            if metadata and "execution_time" in metadata:
                execution_time = metadata["execution_time"]

            # Update state metadata
            self.session_state.state_metadata.record_tool_call(
                tool_name=tool_name,
                success=success,
                execution_time=execution_time,
            )

            # TODO: Extract facts from tool results in future enhancement
            # if _result and success and self._should_extract_facts(tool_name):
            #     await self._extract_facts_from_tool_result(tool_name, _result)

            # Update last_updated timestamp
            from datetime import datetime

            self.session_state.last_updated = datetime.now()

            # Publish event
            self.event_bus.publish(
                StateChanged(
                    session_id=self.session_id,
                    component="metadata",
                    change_type="update",
                    details={"tool_name": tool_name, "success": str(success)},
                )
            )

            # Async persistence (fire and forget)
            asyncio.create_task(self._persist_state())

        except Exception as e:
            logger.error(f"Error updating state on tool executed: {e}", exc_info=True)

    async def on_reasoning_complete(
        self,
        tracker: Any,  # ResearchProgressTracker
    ) -> None:
        """Called when adaptive reasoning completes.

        Extracts confirmed facts from the research tracker and adds them to
        the knowledge base.

        Args:
            tracker: ResearchProgressTracker instance with research results
        """
        try:
            # Check if tracker has confirmed facts
            if not hasattr(tracker, "insights"):
                logger.debug("Research tracker has no insights attribute")
                return

            insights = tracker.insights
            if not hasattr(insights, "confirmed_facts"):
                logger.debug("Research insights have no confirmed_facts attribute")
                return

            # Extract confirmed facts to knowledge base
            confirmed_facts = insights.confirmed_facts
            if confirmed_facts:
                for fact_content in confirmed_facts:
                    self.session_state.knowledge_base.add_fact(
                        content=fact_content,
                        source="research",
                        confidence=0.9,  # High confidence for confirmed facts
                        research_id=getattr(tracker, "research_id", None),
                    )

                logger.info(
                    f"Added {len(confirmed_facts)} confirmed fact(s) to knowledge base"
                )

                # Update last_updated timestamp
                from datetime import datetime

                self.session_state.last_updated = datetime.now()

                # Publish event
                self.event_bus.publish(
                    StateChanged(
                        session_id=self.session_id,
                        component="knowledge_base",
                        change_type="add",
                        details={"fact_count": str(len(confirmed_facts))},
                    )
                )

                # Async persistence (fire and forget)
                asyncio.create_task(self._persist_state())

        except Exception as e:
            logger.error(
                f"Error updating state on reasoning complete: {e}", exc_info=True
            )

    async def update_user_profile(
        self,
        profile_data: dict[str, Any],
    ) -> None:
        """Update user profile with extracted information.

        This method is called by Phase 3 (StateExtractor) when user profile
        information is extracted from conversation.

        Args:
            profile_data: Dictionary of profile fields to update
        """
        try:
            self.session_state.user_profile.update_from_dict(profile_data)

            # Update last_updated timestamp
            from datetime import datetime

            self.session_state.last_updated = datetime.now()

            # Publish event
            self.event_bus.publish(
                StateChanged(
                    session_id=self.session_id,
                    component="user_profile",
                    change_type="update",
                    details={"fields": ", ".join(profile_data.keys())},
                )
            )

            # Async persistence (fire and forget)
            asyncio.create_task(self._persist_state())

            logger.info(f"Updated user profile with fields: {list(profile_data.keys())}")

        except Exception as e:
            logger.error(f"Error updating user profile: {e}", exc_info=True)

    async def add_knowledge_fact(
        self,
        content: str,
        source: str,
        confidence: float = 0.8,
        **kwargs: Any,
    ) -> None:
        """Add a fact to the knowledge base.

        This method provides a convenient way to add facts from various
        sources (conversation, research, tool results, file content).

        Args:
            content: Fact content (the knowledge to store)
            source: Fact source ("conversation", "research", "tool", "file")
            confidence: Confidence score (0.0 to 1.0)
            **kwargs: Additional fact metadata (tags, references, etc.)
        """
        try:
            self.session_state.knowledge_base.add_fact(
                content=content,
                source=source,
                confidence=confidence,
                **kwargs,
            )

            # Update last_updated timestamp
            from datetime import datetime

            self.session_state.last_updated = datetime.now()

            # Publish event
            self.event_bus.publish(
                StateChanged(
                    session_id=self.session_id,
                    component="knowledge_base",
                    change_type="add",
                    details={"source": source},
                )
            )

            # Async persistence (fire and forget)
            asyncio.create_task(self._persist_state())

            logger.debug(f"Added fact from source '{source}' to knowledge base")

        except Exception as e:
            logger.error(f"Error adding knowledge fact: {e}", exc_info=True)

    async def _extract_from_exchange(
        self,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Extract information from conversation exchange using LLM.

        Phase 3: Calls StateExtractor to extract user profile information,
        facts, and intent from the conversation exchange, then updates
        the SessionState accordingly.

        Args:
            user_msg: User's message
            assistant_msg: Assistant's response
        """
        if not self.state_extractor:
            return

        try:
            # Extract user profile information
            user_info = await self.state_extractor.extract_user_info(
                user_msg, assistant_msg
            )
            if user_info:
                self.session_state.user_profile.update_from_dict(user_info)
                logger.debug(f"Updated user profile with extracted fields: {list(user_info.keys())}")

                # Publish profile update event
                self.event_bus.publish(
                    StateChanged(
                        session_id=self.session_id,
                        component="user_profile",
                        change_type="update",
                        details={"fields": ", ".join(user_info.keys())},
                    )
                )

            # Extract facts from assistant response
            facts = await self.state_extractor.extract_facts(
                user_msg, assistant_msg
            )
            if facts:
                for fact_content in facts:
                    self.session_state.knowledge_base.add_fact(
                        content=fact_content,
                        source="conversation",
                        confidence=0.8,
                    )
                logger.debug(f"Added {len(facts)} extracted fact(s) to knowledge base")

                # Publish knowledge base update event
                self.event_bus.publish(
                    StateChanged(
                        session_id=self.session_id,
                        component="knowledge_base",
                        change_type="add",
                        details={"fact_count": str(len(facts))},
                    )
                )

            # Classify user intent
            intent_data = await self.state_extractor.classify_intent(user_msg)
            if intent_data:
                intent = Intent(
                    type=intent_data["type"],
                    confidence=intent_data["confidence"],
                    details=intent_data.get("details", {}),
                )
                self.session_state.interaction_context.update_intent(intent)
                logger.debug(
                    f"Classified intent: {intent.type} "
                    f"(confidence={intent.confidence:.2f})"
                )

        except Exception as e:
            logger.error(
                f"Error during extraction from exchange: {e}",
                exc_info=True
            )
            # Don't propagate - extraction failures shouldn't break state updates

    async def _persist_state(self) -> None:
        """Persist the session state asynchronously.

        This is a fire-and-forget operation that saves the current state
        without blocking the agent loop. Errors are logged but don't
        propagate to the caller.
        """
        try:
            # Serialize state to dictionary
            state_dict = self.session_state.to_dict()

            # Save to provider using session_id as key
            state_key = f"session_state_{self.session_id}"
            await self.state_provider.save(state_key, state_dict)

            logger.debug(f"Persisted session state for session {self.session_id}")

        except Exception as e:
            logger.error(f"Error persisting session state: {e}", exc_info=True)

    async def load_state(self) -> bool:
        """Load the session state from the provider.

        This method is called when restoring a session to populate the
        SessionState with persisted data.

        Returns:
            True if state was loaded successfully, False otherwise
        """
        try:
            # Load from provider using session_id as key
            state_key = f"session_state_{self.session_id}"
            state_dict = await self.state_provider.load(state_key)

            if state_dict is None:
                logger.debug(f"No persisted state found for session {self.session_id}")
                return False

            # Restore state from dictionary
            from nxs.application.session_state import SessionState

            restored_state = SessionState.from_dict(state_dict)

            # Copy restored state to current state
            self.session_state.user_profile = restored_state.user_profile
            self.session_state.knowledge_base = restored_state.knowledge_base
            self.session_state.interaction_context = restored_state.interaction_context
            self.session_state.state_metadata = restored_state.state_metadata
            self.session_state.created_at = restored_state.created_at
            self.session_state.last_updated = restored_state.last_updated

            logger.info(
                f"Loaded session state for session {self.session_id} "
                f"({len(self.session_state.knowledge_base.facts)} facts)"
            )

            return True

        except Exception as e:
            logger.error(f"Error loading session state: {e}", exc_info=True)
            return False
