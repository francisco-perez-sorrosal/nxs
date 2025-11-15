# Session State Architecture - Implementation Plan

## I. ARCHITECTURAL REVIEW & REFACTORING RECOMMENDATIONS

### 1.1 Current Architecture Analysis

The Nexus application demonstrates several **strong architectural patterns** that should guide the Session State implementation:

#### **Existing Architectural Strengths:**

1. **Protocol-Based Extensibility**
   - `ToolProvider` protocol enables pluggable tool sources (MCPToolProvider, LocalToolProvider)
   - `Cache` protocol abstracts storage backends (MemoryCache, etc.)
   - `MCPClient` protocol defines client contracts
   - **Recommendation**: Session State should follow this pattern with `SessionStateProvider` protocol

2. **State Management Patterns**
   - **Conversation** (`conversation.py`): Manages message history with `to_dict()`/`from_dict()` serialization
   - **ToolRegistry** (`tool_registry.py`): Manages tool state with lazy loading and caching
   - **Proven pattern**: These classes demonstrate successful state management with persistence support
   - **Recommendation**: Session State should extend these patterns, not reinvent them

3. **Service Container Pattern** (`container.py`)
   - Lazy initialization of services via properties
   - Dependency injection through constructor lambdas
   - Clear lifecycle management (`start()`, `stop()`, `initialize_mcp()`)
   - **Recommendation**: SessionState should integrate as a service managed by ServiceContainer

4. **Queue-Based Async Processing** (`queue_processor.py`)
   - `AsyncQueueProcessor<T>` provides reusable FIFO processing pattern
   - Used successfully by StatusQueue and QueryQueue
   - **Recommendation**: State updates could use this pattern for async persistence

5. **Event-Driven Communication** (`events.py`, `EventBus`)
   - Decoupled communication via events (ConnectionStatusChanged, ArtifactsFetched, etc.)
   - **Recommendation**: Session State updates should publish StateChanged events

#### **Current Architecture Limitations:**

1. **No Holistic Session State**
   - **Issue**: Conversation manages messages, but no unified session state container
   - **Impact**: Cost tracking, reasoning history, user context scattered across components
   - **Evidence**: SessionManager has session metadata, but it's not integrated with conversation state

2. **Implicit Dependencies**
   - **Issue**: ServiceContainer uses lambdas for app state access (`self._session_getter = lambda: getattr(app, "session", None)`)
   - **Impact**: Tight coupling between services and TUI app
   - **Example**: `query_handler.py` line 226 creates session_getter callback
   - **Recommendation**: Make session state explicit, not accessed via app introspection

3. **No Persistence Strategy**
   - **Issue**: While Conversation has serialization, there's no unified persistence layer
   - **Impact**: Session resumption is incomplete (conversation exists, but cost/metadata lost)
   - **Evidence**: Conversation has `to_dict()`/`from_dict()`, but no file I/O or storage backend

4. **State Update Lifecycle Not Defined**
   - **Issue**: When should state be updated? After each message? After tool calls? On demand?
   - **Impact**: Inconsistent state updates, potential race conditions
   - **Recommendation**: Define clear state update triggers and lifecycle hooks

### 1.2 Architectural Refactoring Recommendations

#### **BEFORE Implementing Session State**

Before building Session State, consider these **strategic refactorings** to create a cleaner foundation:

#### **Refactoring 1: Introduce StateProvider Protocol**

**Current**: Direct instantiation of state objects (Conversation, ToolRegistry)

**Proposed**: Protocol-based state management

```python
# Location: src/nxs/domain/protocols/state.py

from typing import Protocol, Any, Optional

class StateProvider(Protocol):
    """Protocol for state providers (in-memory, file, database, etc.)."""

    async def save(self, key: str, data: dict[str, Any]) -> None:
        """Save state data under a key."""
        ...

    async def load(self, key: str) -> Optional[dict[str, Any]]:
        """Load state data by key. Returns None if not found."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if state exists for a key."""
        ...

    async def delete(self, key: str) -> None:
        """Delete state by key."""
        ...

    async def list_keys(self) -> list[str]:
        """List all available state keys."""
        ...
```

**Benefits**:
- Multiple backends: InMemoryStateProvider, FileStateProvider, DatabaseStateProvider
- Testable with MockStateProvider
- Matches existing protocol patterns (ToolProvider, Cache)

**Integration**:
```python
# Conversation becomes state-provider aware
conversation = Conversation(...)
await state_provider.save(f"session:{session_id}:conversation", conversation.to_dict())

# Session State uses the same provider
session_state = SessionState(session_id=session_id, state_provider=state_provider)
await session_state.save()  # Delegates to provider
```

#### **Refactoring 2: Extract State Update Service**

**Current**: State updates happen implicitly in AgentLoop callbacks

**Proposed**: Dedicated `StateUpdateService` for coordinated state updates

```python
# Location: src/nxs/application/state_update_service.py

class StateUpdateService:
    """Coordinates state updates from agent loop events.

    Listens to:
    - Message additions (conversation updates)
    - Tool executions (metadata updates)
    - Reasoning completions (research history updates)

    Updates:
    - SessionState
    - Publishes StateChanged events
    """

    def __init__(
        self,
        session_state: SessionState,
        event_bus: EventBus,
        state_provider: StateProvider,
    ):
        self.session_state = session_state
        self.event_bus = event_bus
        self.state_provider = state_provider

    async def on_message_added(self, role: str, content: str) -> None:
        """Called when a message is added to the conversation."""
        # Update interaction context
        await self.session_state.interaction_context.add_exchange(...)

        # Publish event
        self.event_bus.publish(StateChanged(session_id=..., component="conversation"))

        # Async persistence (fire and forget)
        asyncio.create_task(self.session_state.save())

    async def on_tool_executed(self, tool_name: str, result: str, metadata: dict) -> None:
        """Called when a tool is executed."""
        # Update metadata
        self.session_state.metadata.record_tool_call(...)

        # Potentially extract facts from tool results
        if should_extract_facts(tool_name, result):
            await self._extract_facts_from_tool_result(result)

    async def on_reasoning_complete(self, tracker: ResearchProgressTracker) -> None:
        """Called when adaptive reasoning completes."""
        # Move tracker to history
        self.session_state.research_history.append(tracker)

        # Extract confirmed facts to knowledge base
        for fact in tracker.insights.confirmed_facts:
            self.session_state.knowledge_base.add_fact(fact, source="research")
```

**Benefits**:
- Single responsibility: State updates isolated from orchestration
- Testable: Mock the service to verify state update logic
- Event-driven: Integrates naturally with existing EventBus
- Async persistence: Updates don't block agent loop

**Integration**:
```python
# In ServiceContainer
@property
def state_update_service(self) -> StateUpdateService:
    if self._state_update_service is None:
        self._state_update_service = StateUpdateService(
            session_state=self.session_state,  # From SessionManager
            event_bus=self.event_bus,
            state_provider=self.state_provider,
        )
    return self._state_update_service

# In QueryHandler
# Add state update hooks to callbacks
callbacks = {
    "on_tool_result": lambda name, result, success:
        await self.state_update_service.on_tool_executed(name, result, metadata),
}
```

#### **Refactoring 3: Unify SessionManager and SessionState**

**Current**: SessionManager and SessionState are conceptually separate

**Proposed**: SessionManager orchestrates SessionState lifecycle

```python
# Location: src/nxs/application/session_manager.py

class SessionManager:
    """Manages session lifecycle and state persistence.

    Responsibilities:
    - Create new sessions with SessionState
    - Load existing sessions from StateProvider
    - Manage session switching (future: multi-session support)
    - Coordinate state persistence
    - Track session metadata (cost, duration, etc.)
    """

    def __init__(
        self,
        state_provider: StateProvider,
        event_bus: EventBus,
        *,
        conversation_factory: Callable[[], Conversation],
    ):
        self.state_provider = state_provider
        self.event_bus = event_bus
        self._conversation_factory = conversation_factory

        self._current_session: Optional[Session] = None
        self._session_state: Optional[SessionState] = None

    async def create_session(self, session_id: str | None = None) -> Session:
        """Create a new session with fresh state."""
        session_id = session_id or self._generate_session_id()

        # Create conversation
        conversation = self._conversation_factory()

        # Create session state
        session_state = SessionState(
            session_id=session_id,
            conversation=conversation,
            state_provider=self.state_provider,
        )

        # Create session wrapper
        session = Session(
            id=session_id,
            conversation=conversation,
            state=session_state,
        )

        self._current_session = session
        self._session_state = session_state

        # Publish event
        self.event_bus.publish(SessionCreated(session_id=session_id))

        return session

    async def load_session(self, session_id: str) -> Session:
        """Load an existing session from storage."""
        # Load state
        state_data = await self.state_provider.load(f"session:{session_id}")
        if not state_data:
            raise ValueError(f"Session {session_id} not found")

        # Deserialize
        session_state = SessionState.from_dict(state_data, state_provider=self.state_provider)

        # Create session wrapper
        session = Session(
            id=session_id,
            conversation=session_state.conversation,
            state=session_state,
        )

        self._current_session = session
        self._session_state = session_state

        # Publish event
        self.event_bus.publish(SessionLoaded(session_id=session_id))

        return session

    @property
    def current_session(self) -> Session:
        """Get current active session."""
        if not self._current_session:
            raise RuntimeError("No active session. Call create_session() first.")
        return self._current_session

    @property
    def session_state(self) -> SessionState:
        """Get current session state."""
        if not self._session_state:
            raise RuntimeError("No active session state.")
        return self._session_state
```

**Benefits**:
- Clear separation: SessionManager = lifecycle, SessionState = data
- Explicit session creation: No more implicit state creation
- Future-ready: Easy to add multi-session support
- Testable: Mock StateProvider for unit tests

#### **Refactoring 4: ServiceContainer Integration**

**Current**: ServiceContainer doesn't know about SessionState

**Proposed**: Add SessionState as a managed service

```python
# In ServiceContainer.__init__()
def __init__(
    self,
    app: "App",
    session_manager: SessionManager,  # NEW: Explicitly passed
    agent_loop,
    artifact_manager: ArtifactManager,
    event_bus: EventBus,
    ...
):
    self.session_manager = session_manager  # Store reference
    # ... rest of init

# Add property
@property
def session_state(self) -> SessionState:
    """Get current session state from SessionManager."""
    return self.session_manager.session_state

# Add state update service
@property
def state_update_service(self) -> StateUpdateService:
    """Get StateUpdateService, creating it on first access."""
    if self._state_update_service is None:
        self._state_update_service = StateUpdateService(
            session_state=self.session_state,
            event_bus=self.event_bus,
            state_provider=self.session_manager.state_provider,
        )
    return self._state_update_service
```

**Benefits**:
- Explicit dependencies: No more lambdas reaching into app state
- Lazy initialization maintained: Services created on first access
- Clear lifecycle: SessionManager creates state before ServiceContainer
- Type-safe: mypy can verify session_state exists

### 1.3 Recommended Implementation Order

To minimize disruption and maintain working code, implement Session State in **phases**:

#### **Phase 0: Foundation Refactorings** (Do First!)
1. ✅ Create `StateProvider` protocol (`src/nxs/domain/protocols/state.py`)
2. ✅ Implement `InMemoryStateProvider` (`src/nxs/infrastructure/state/memory.py`)
3. ✅ Implement `FileStateProvider` (`src/nxs/infrastructure/state/file.py`)
4. ✅ Add `StateProvider` to SessionManager constructor
5. ✅ Update ServiceContainer to explicitly pass SessionManager

**Testing**: Unit tests for StateProvider implementations

#### **Phase 1: Core SessionState** (Build State Container)
1. ✅ Create SessionState class with `to_dict()`/`from_dict()` (follows Conversation pattern)
2. ✅ Create component classes: UserProfile, KnowledgeBase, InteractionContext, SessionMetadata
3. ✅ Integrate SessionState into SessionManager
4. ✅ Add SessionState property to ServiceContainer

**Testing**: Unit tests for SessionState serialization, ServiceContainer integration test

#### **Phase 2: State Update Service** (Connect State to Agent Loop)
1. ✅ Create StateUpdateService with event handlers
2. ✅ Wire StateUpdateService to agent loop callbacks
3. ✅ Add StateChanged event to EventBus
4. ✅ Implement async persistence in StateUpdateService

**Testing**: Integration tests for state updates during conversations

#### **Phase 3: State Extraction** (LLM-Powered State Population)
1. ✅ Create StateExtractor for user profile extraction
2. ✅ Create StateExtractor for fact extraction
3. ✅ Wire extractors to StateUpdateService
4. ✅ Add extraction configuration (enable/disable)

**Testing**: Integration tests with real conversations, verify extraction accuracy

#### **Phase 4: Context Injection** (Use State in Prompts)
1. ✅ Implement `SessionState.get_context_for_prompt()`
2. ✅ Integrate context injection into CommandControlAgent
3. ✅ Add context verbosity controls
4. ✅ Optimize token usage with relevance filtering

**Testing**: Integration tests verifying context improves responses

#### **Phase 5: Persistence & Resumption** (Save/Load Sessions)
1. ✅ Implement session save on app exit
2. ✅ Implement session load on app start
3. ✅ Add session list UI
4. ✅ Add session switching support

**Testing**: End-to-end tests for session save/load/resume

---

## II. SESSION STATE SUB-ARCHITECTURE

### 2.1 Executive Summary

This section outlines the design and implementation of the **SessionState** sub-system that serves as the comprehensive state management layer for the Nexus agent. Building on the architectural refactorings above, SessionState maintains a rich, structured representation of the entire session, including:

1. **Conversation history** (message sequences) - Reuses existing Conversation class
2. **User profile** (extracted information about the user) - NEW
3. **Research progress** (complex reasoning task tracking via ResearchProgressTracker) - NEW
4. **Knowledge base** (facts and insights learned during the session) - NEW
5. **Interaction context** (current conversation context and intent) - NEW
6. **Session metadata** (costs, performance, statistics) - NEW

The State system transforms the session from a flat message sequence into a **semantic, queryable knowledge structure** that enables:
- Context-aware responses
- Personalized interactions
- Efficient information retrieval
- Cross-query learning
- Session persistence and resumption

---

## 1. Conceptual Model

### 1.1 The State vs. Messages Paradigm

**Traditional Approach (Message-only)**:
```
Session = List[Message]
- User: "My name is Alice"
- Assistant: "Nice to meet you, Alice!"
- User: "I'm 30 years old"
- Assistant: "Got it!"
- User: "What's my name?"
- Assistant: [Must scan all messages to find "Alice"]
```

**State-Driven Approach**:
```
Session = SessionState {
    messages: List[Message]  # Raw conversation
    user_profile: {
        name: "Alice"         # Extracted fact
        age: 30               # Extracted fact
    }
    knowledge_base: {
        facts: ["User is named Alice", "User is 30 years old"]
    }
}

Query: "What's my name?"
→ State lookup: user_profile.name = "Alice" (instant)
```

**Benefits**:
- **Semantic understanding**: State captures meaning, not just text
- **Efficient retrieval**: Direct access vs. message scanning
- **Persistent memory**: Facts survive across queries
- **Contextual awareness**: Rich context for every response

### 1.2 State Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                         SessionState                            │
│  The top-level container for all session information            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │   Conversation   │  │   UserProfile    │                   │
│  │  (messages)      │  │  (who they are)  │                   │
│  └──────────────────┘  └──────────────────┘                   │
│                                                                 │
│  ┌────────────────────────────────────────┐                   │
│  │      ResearchProgressTracker           │                   │
│  │  (complex reasoning state)             │                   │
│  │  - Only active during reasoning tasks  │                   │
│  └────────────────────────────────────────┘                   │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │  KnowledgeBase   │  │ InteractionCtx   │                   │
│  │  (learned facts) │  │ (current intent) │                   │
│  └──────────────────┘  └──────────────────┘                   │
│                                                                 │
│  ┌──────────────────┐                                          │
│  │ SessionMetadata  │                                          │
│  │ (costs, stats)   │                                          │
│  └──────────────────┘                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Data Structures

### 2.1 SessionState (Top-Level)

**Location**: `src/nxs/application/session_state.py`

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum


class SessionState:
    """
    Top-level state container for an entire agent session.

    The SessionState maintains a rich, structured representation of the
    conversation that goes beyond message history. It extracts and stores
    semantic information, enabling context-aware, personalized interactions.

    Lifecycle:
    1. Created at session start
    2. Updated incrementally after each interaction
    3. Persisted periodically and at session end
    4. Can be loaded to resume previous sessions
    """

    def __init__(self, session_id: str):
        # Identity
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_updated = datetime.now()

        # Core components
        self.conversation = Conversation()  # Message history (existing)
        self.user_profile = UserProfile()   # Information about the user
        self.knowledge_base = KnowledgeBase()  # Facts learned
        self.interaction_context = InteractionContext()  # Current context
        self.metadata = SessionMetadata()   # Session stats

        # Research tracking (optional - only for complex queries)
        self.active_research: Optional[ResearchProgressTracker] = None
        self.research_history: list[ResearchProgressTracker] = []

        # State update tracking
        self._pending_updates: list[StateUpdate] = []
        self._update_log: list[StateUpdate] = []

    # === State Updates ===

    def mark_updated(self):
        """Mark state as updated."""
        self.last_updated = datetime.now()

    async def update_from_interaction(
        self,
        user_message: str,
        assistant_response: str,
        tool_calls: list[dict] = None,
        metadata: dict = None
    ):
        """
        Update state based on a completed interaction.

        This is the main entry point for state updates. After each
        user-assistant exchange, this method:
        1. Adds messages to conversation history
        2. Extracts information for user profile
        3. Updates knowledge base with new facts
        4. Updates interaction context
        5. Records metadata (costs, tokens, etc.)
        """
        # Update conversation (existing)
        self.conversation.add_user_message(user_message)
        self.conversation.add_assistant_message(assistant_response)

        # Extract and update state components
        await self._extract_user_info(user_message, assistant_response)
        await self._extract_facts(user_message, assistant_response)
        await self._update_context(user_message, assistant_response)

        # Update metadata
        if metadata:
            self.metadata.record_interaction(metadata)

        # Record tool usage
        if tool_calls:
            for tool_call in tool_calls:
                self.metadata.record_tool_call(
                    tool_name=tool_call["name"],
                    success=tool_call.get("success", True),
                    execution_time=tool_call.get("execution_time", 0)
                )

        self.mark_updated()

    async def _extract_user_info(self, user_msg: str, assistant_msg: str):
        """Extract user information from the interaction."""
        # Use LLM to extract structured user info
        # Patterns to detect:
        # - "My name is X" → user_profile.name = X
        # - "I'm Y years old" → user_profile.age = Y
        # - "I like Z" → user_profile.interests.append(Z)

        extractor_prompt = f"""
Extract user information from this conversation turn.

User: {user_msg}
Assistant: {assistant_msg}

Extract any mentions of:
- Name
- Age
- Location
- Occupation
- Interests/preferences
- Technical expertise level
- Project context

Return as JSON with only fields that are mentioned.
"""

        # Call lightweight LLM (haiku) for extraction
        extracted = await self._call_extractor_llm(extractor_prompt)

        # Update user profile with extracted info
        if extracted:
            self.user_profile.update_from_dict(extracted)

    async def _extract_facts(self, user_msg: str, assistant_msg: str):
        """Extract factual statements to knowledge base."""
        # Extract confirmed facts from assistant responses
        # Example: "The API rate limit is 1000 requests/hour"
        #       → knowledge_base.add_fact("API rate limit: 1000 req/hr")

        extractor_prompt = f"""
Extract factual statements from the assistant's response that might be
useful for future reference in this session.

User: {user_msg}
Assistant: {assistant_msg}

Return a list of factual statements (e.g., configuration values, file paths,
technical facts, decisions made, etc.). Only include facts that are likely
to be referenced later.
"""

        facts = await self._call_extractor_llm(extractor_prompt)

        if facts:
            for fact in facts:
                self.knowledge_base.add_fact(
                    content=fact,
                    source="conversation",
                    confidence=0.8
                )

    async def _update_context(self, user_msg: str, assistant_msg: str):
        """Update interaction context."""
        # Track conversation flow, current topic, intent
        self.interaction_context.add_exchange(user_msg, assistant_msg)

        # Classify intent
        intent = await self._classify_intent(user_msg)
        self.interaction_context.update_intent(intent)

    # === Research Tracking Integration ===

    def start_research(self, query: str, complexity: ComplexityAnalysis) -> ResearchProgressTracker:
        """
        Start a new research task with progress tracking.

        Called by AdaptiveReasoningLoop when beginning a complex query.
        """
        tracker = ResearchProgressTracker(query, complexity)
        self.active_research = tracker
        self.mark_updated()
        return tracker

    def end_research(self, final_response: str):
        """
        Complete the active research task.

        Moves active research to history and extracts key findings
        into the knowledge base.
        """
        if self.active_research:
            # Extract findings to knowledge base
            if self.active_research.insights.confirmed_facts:
                for fact in self.active_research.insights.confirmed_facts:
                    self.knowledge_base.add_fact(
                        content=fact,
                        source="research",
                        confidence=0.9,
                        research_id=self.active_research.query
                    )

            # Move to history
            self.research_history.append(self.active_research)
            self.active_research = None
            self.mark_updated()

    # === Context Extraction for LLM ===

    def get_context_for_prompt(
        self,
        query: str,
        mode: str = "auto"
    ) -> str:
        """
        Extract relevant context from state for LLM prompt.

        This is the key method that transforms State into natural language
        context that gets injected into LLM prompts.

        Args:
            query: The current user query
            mode: Context verbosity ("minimal", "standard", "comprehensive")

        Returns:
            Natural language context string
        """
        sections = []

        # 1. User Profile Context (if relevant)
        if self.user_profile.has_information():
            profile_text = self.user_profile.to_context_text()
            if profile_text:
                sections.append(f"# User Profile\n{profile_text}\n")

        # 2. Relevant Facts from Knowledge Base
        relevant_facts = self.knowledge_base.get_relevant_facts(query, limit=10)
        if relevant_facts:
            sections.append("# Relevant Facts from Session\n")
            for fact in relevant_facts:
                sections.append(f"- {fact.content}")
            sections.append("")

        # 3. Interaction Context
        context_summary = self.interaction_context.get_summary()
        if context_summary:
            sections.append(f"# Current Context\n{context_summary}\n")

        # 4. Active Research (if any)
        if self.active_research:
            research_context = self.active_research.to_context_text(
                self.active_research.current_strategy
            )
            sections.append(research_context)

        # 5. Recent Research (if relevant)
        if mode == "comprehensive" and self.research_history:
            recent = self.research_history[-2:]  # Last 2 research tasks
            for i, tracker in enumerate(recent, 1):
                sections.append(f"\n# Previous Research Task {i}\n")
                sections.append(f"Query: {tracker.query}")
                if tracker.insights.confirmed_facts:
                    sections.append("Key findings:")
                    for fact in tracker.insights.confirmed_facts[:3]:
                        sections.append(f"- {fact}")
                sections.append("")

        return "\n".join(sections)

    def get_compact_context(self) -> str:
        """Get minimal context summary (for token efficiency)."""
        parts = []

        if self.user_profile.name:
            parts.append(f"User: {self.user_profile.name}")

        fact_count = len(self.knowledge_base.facts)
        if fact_count > 0:
            parts.append(f"{fact_count} facts learned")

        if self.active_research:
            parts.append(f"Active research: {self.active_research.query[:50]}...")

        return " | ".join(parts) if parts else "New session"

    # === Querying State ===

    async def query(self, question: str) -> Optional[str]:
        """
        Query the state to retrieve information.

        Example:
            state.query("What is the user's name?")
            → "Alice"

            state.query("What did we learn about the API?")
            → "API rate limit is 1000 requests/hour..."
        """
        # Try user profile first
        if "name" in question.lower() and self.user_profile.name:
            return self.user_profile.name

        if "age" in question.lower() and self.user_profile.age:
            return str(self.user_profile.age)

        # Query knowledge base
        facts = self.knowledge_base.search(question, limit=3)
        if facts:
            return "\n".join(f"- {f.content}" for f in facts)

        # Fallback: Query conversation history with LLM
        return await self._query_conversation_history(question)

    async def _query_conversation_history(self, question: str) -> Optional[str]:
        """Query conversation history using LLM."""
        recent_messages = self.conversation.get_recent_messages(limit=20)

        prompt = f"""
Based on the conversation history below, answer this question:

{question}

Conversation:
{recent_messages}

If the answer is not in the conversation, respond with "Not found".
"""

        response = await self._call_extractor_llm(prompt)
        return response if response != "Not found" else None

    # === Persistence ===

    def to_dict(self) -> dict:
        """Serialize state to dictionary for persistence."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "conversation": self.conversation.to_dict(),
            "user_profile": self.user_profile.to_dict(),
            "knowledge_base": self.knowledge_base.to_dict(),
            "interaction_context": self.interaction_context.to_dict(),
            "metadata": self.metadata.to_dict(),
            "active_research": self.active_research.to_dict() if self.active_research else None,
            "research_history": [r.to_dict() for r in self.research_history],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        """Deserialize state from dictionary."""
        state = cls(session_id=data["session_id"])
        state.created_at = datetime.fromisoformat(data["created_at"])
        state.last_updated = datetime.fromisoformat(data["last_updated"])

        state.conversation = Conversation.from_dict(data["conversation"])
        state.user_profile = UserProfile.from_dict(data["user_profile"])
        state.knowledge_base = KnowledgeBase.from_dict(data["knowledge_base"])
        state.interaction_context = InteractionContext.from_dict(data["interaction_context"])
        state.metadata = SessionMetadata.from_dict(data["metadata"])

        if data.get("active_research"):
            state.active_research = ResearchProgressTracker.from_dict(data["active_research"])

        state.research_history = [
            ResearchProgressTracker.from_dict(r) for r in data.get("research_history", [])
        ]

        return state

    async def save(self, filepath: str):
        """Save state to file."""
        import json
        data = self.to_dict()
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    async def load(cls, filepath: str) -> "SessionState":
        """Load state from file."""
        import json
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)

    # === Utility ===

    async def _call_extractor_llm(self, prompt: str) -> Any:
        """Call lightweight LLM for extraction tasks."""
        # Use Haiku for fast, cheap extraction
        # Implementation: Call Claude Haiku with structured output
        pass
```

---

### 2.2 UserProfile

```python
@dataclass
class UserProfile:
    """
    Profile information about the user extracted from conversations.

    This captures WHO the user is, not WHAT they're asking about.
    """

    # Identity
    name: Optional[str] = None
    age: Optional[int] = None
    location: Optional[str] = None
    occupation: Optional[str] = None

    # Technical context
    expertise_level: Optional[str] = None  # "beginner", "intermediate", "expert"
    programming_languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)

    # Preferences
    interests: list[str] = field(default_factory=list)
    communication_style: Optional[str] = None  # "concise", "detailed", "technical"

    # Project context
    current_project: Optional[str] = None
    project_tech_stack: list[str] = field(default_factory=list)

    # Meta
    confidence_scores: dict[str, float] = field(default_factory=dict)
    last_updated: Optional[datetime] = None

    def has_information(self) -> bool:
        """Check if profile has any meaningful information."""
        return any([
            self.name, self.age, self.occupation,
            self.interests, self.programming_languages,
            self.current_project
        ])

    def update_from_dict(self, data: dict):
        """Update profile from extracted data."""
        for key, value in data.items():
            if hasattr(self, key) and value:
                # Update field
                current = getattr(self, key)

                if isinstance(current, list):
                    # Append to list (deduplicate)
                    if isinstance(value, list):
                        for item in value:
                            if item not in current:
                                current.append(item)
                    elif value not in current:
                        current.append(value)
                else:
                    # Overwrite scalar
                    setattr(self, key, value)

                # Track confidence
                self.confidence_scores[key] = 0.8  # Default confidence

        self.last_updated = datetime.now()

    def to_context_text(self) -> str:
        """Convert profile to natural language context."""
        parts = []

        if self.name:
            parts.append(f"User's name: {self.name}")

        if self.occupation:
            parts.append(f"Occupation: {self.occupation}")

        if self.expertise_level:
            parts.append(f"Technical expertise: {self.expertise_level}")

        if self.programming_languages:
            parts.append(f"Familiar with: {', '.join(self.programming_languages)}")

        if self.interests:
            parts.append(f"Interests: {', '.join(self.interests)}")

        if self.current_project:
            parts.append(f"Current project: {self.current_project}")
            if self.project_tech_stack:
                parts.append(f"Project stack: {', '.join(self.project_tech_stack)}")

        if self.communication_style:
            parts.append(f"Prefers {self.communication_style} communication")

        return "\n".join(parts)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "UserProfile":
        """Deserialize from dictionary."""
        return cls(**data)
```

---

### 2.3 KnowledgeBase

```python
@dataclass
class Fact:
    """A single factual statement learned during the session."""

    content: str
    source: str  # "conversation", "research", "tool", "file"
    confidence: float  # 0.0 to 1.0
    timestamp: datetime

    # Context
    research_id: Optional[str] = None  # Link to research task
    message_index: Optional[int] = None  # Link to conversation message

    # Metadata
    tags: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)  # File paths, URLs, etc.

    def __hash__(self):
        return hash(self.content)


class KnowledgeBase:
    """
    Repository of facts and insights learned during the session.

    The knowledge base stores structured factual information extracted
    from conversations, research tasks, and tool executions. It enables:
    - Efficient fact retrieval
    - Semantic search
    - Fact deduplication
    - Confidence tracking
    """

    def __init__(self):
        self.facts: list[Fact] = []
        self._fact_index: dict[str, Fact] = {}  # Hash → Fact

    def add_fact(
        self,
        content: str,
        source: str,
        confidence: float = 0.8,
        **kwargs
    ):
        """Add a new fact to the knowledge base."""
        fact = Fact(
            content=content,
            source=source,
            confidence=confidence,
            timestamp=datetime.now(),
            **kwargs
        )

        # Deduplicate based on content similarity
        existing = self._find_similar_fact(content)
        if existing:
            # Update existing fact with higher confidence
            if confidence > existing.confidence:
                existing.confidence = confidence
                existing.timestamp = datetime.now()
        else:
            # Add new fact
            self.facts.append(fact)
            self._fact_index[hash(content)] = fact

    def _find_similar_fact(self, content: str) -> Optional[Fact]:
        """Find similar existing fact (simple string matching for now)."""
        content_lower = content.lower()
        for fact in self.facts:
            if fact.content.lower() == content_lower:
                return fact
        return None

    def get_relevant_facts(
        self,
        query: str,
        limit: int = 10,
        min_confidence: float = 0.5
    ) -> list[Fact]:
        """
        Retrieve facts relevant to a query.

        Uses simple keyword matching for now; could be enhanced with
        semantic embeddings later.
        """
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        scored_facts = []
        for fact in self.facts:
            if fact.confidence < min_confidence:
                continue

            fact_terms = set(fact.content.lower().split())
            overlap = len(query_terms & fact_terms)

            if overlap > 0:
                score = overlap / len(query_terms)
                scored_facts.append((score, fact))

        # Sort by score descending
        scored_facts.sort(key=lambda x: x[0], reverse=True)

        return [fact for _, fact in scored_facts[:limit]]

    def search(self, query: str, limit: int = 5) -> list[Fact]:
        """Search facts (alias for get_relevant_facts)."""
        return self.get_relevant_facts(query, limit=limit)

    def get_facts_by_source(self, source: str) -> list[Fact]:
        """Get all facts from a specific source."""
        return [f for f in self.facts if f.source == source]

    def get_recent_facts(self, limit: int = 10) -> list[Fact]:
        """Get most recent facts."""
        sorted_facts = sorted(self.facts, key=lambda f: f.timestamp, reverse=True)
        return sorted_facts[:limit]

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "facts": [
                {
                    "content": f.content,
                    "source": f.source,
                    "confidence": f.confidence,
                    "timestamp": f.timestamp.isoformat(),
                    "research_id": f.research_id,
                    "message_index": f.message_index,
                    "tags": f.tags,
                    "references": f.references,
                }
                for f in self.facts
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeBase":
        """Deserialize from dictionary."""
        kb = cls()
        for fact_data in data.get("facts", []):
            fact = Fact(
                content=fact_data["content"],
                source=fact_data["source"],
                confidence=fact_data["confidence"],
                timestamp=datetime.fromisoformat(fact_data["timestamp"]),
                research_id=fact_data.get("research_id"),
                message_index=fact_data.get("message_index"),
                tags=fact_data.get("tags", []),
                references=fact_data.get("references", []),
            )
            kb.facts.append(fact)
            kb._fact_index[hash(fact.content)] = fact
        return kb
```

---

### 2.4 InteractionContext

```python
@dataclass
class Intent:
    """User's intent in current interaction."""
    type: str  # "question", "command", "research", "chat", "clarification"
    confidence: float
    details: dict[str, Any] = field(default_factory=dict)


class InteractionContext:
    """
    Current context and flow of the interaction.

    Tracks the immediate conversational context including:
    - Recent exchange history (sliding window)
    - Current topic/intent
    - Conversation flow patterns
    """

    def __init__(self):
        self.recent_exchanges: list[dict] = []  # Last N exchanges
        self.current_topic: Optional[str] = None
        self.current_intent: Optional[Intent] = None

        # Flow tracking
        self.question_count: int = 0
        self.command_count: int = 0
        self.research_count: int = 0

        # Context window
        self.max_exchanges: int = 5  # Keep last 5 exchanges in context

    def add_exchange(self, user_msg: str, assistant_msg: str):
        """Add an exchange to recent history."""
        exchange = {
            "user": user_msg,
            "assistant": assistant_msg,
            "timestamp": datetime.now().isoformat()
        }

        self.recent_exchanges.append(exchange)

        # Keep only last N exchanges
        if len(self.recent_exchanges) > self.max_exchanges:
            self.recent_exchanges.pop(0)

    def update_intent(self, intent: Intent):
        """Update current intent."""
        self.current_intent = intent

        # Update counts
        if intent.type == "question":
            self.question_count += 1
        elif intent.type == "command":
            self.command_count += 1
        elif intent.type == "research":
            self.research_count += 1

    def get_summary(self) -> str:
        """Get context summary."""
        parts = []

        if self.current_topic:
            parts.append(f"Current topic: {self.current_topic}")

        if self.current_intent:
            parts.append(f"User intent: {self.current_intent.type}")

        if self.recent_exchanges:
            parts.append(f"Recent exchanges: {len(self.recent_exchanges)}")

        return "\n".join(parts)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "recent_exchanges": self.recent_exchanges,
            "current_topic": self.current_topic,
            "current_intent": {
                "type": self.current_intent.type,
                "confidence": self.current_intent.confidence,
                "details": self.current_intent.details
            } if self.current_intent else None,
            "question_count": self.question_count,
            "command_count": self.command_count,
            "research_count": self.research_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionContext":
        """Deserialize from dictionary."""
        ctx = cls()
        ctx.recent_exchanges = data.get("recent_exchanges", [])
        ctx.current_topic = data.get("current_topic")

        if data.get("current_intent"):
            intent_data = data["current_intent"]
            ctx.current_intent = Intent(
                type=intent_data["type"],
                confidence=intent_data["confidence"],
                details=intent_data.get("details", {})
            )

        ctx.question_count = data.get("question_count", 0)
        ctx.command_count = data.get("command_count", 0)
        ctx.research_count = data.get("research_count", 0)

        return ctx
```

---

### 2.5 SessionMetadata

```python
@dataclass
class TokenUsage:
    """Token usage for a single API call."""
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


class SessionMetadata:
    """
    Session statistics and metadata.

    Tracks performance, costs, and usage patterns.
    """

    def __init__(self):
        # Interaction counts
        self.message_count: int = 0
        self.tool_call_count: int = 0
        self.research_task_count: int = 0

        # Token usage
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cache_creation_tokens: int = 0
        self.total_cache_read_tokens: int = 0

        # Costs (USD)
        self.total_cost: float = 0.0
        self.cost_breakdown: dict[str, float] = {
            "input": 0.0,
            "output": 0.0,
            "cache_creation": 0.0,
            "cache_read": 0.0,
        }

        # Tool usage
        self.tool_usage: dict[str, int] = {}  # tool_name → count
        self.tool_success_rate: dict[str, float] = {}  # tool_name → success rate

        # Timing
        self.session_duration: float = 0.0  # seconds
        self.average_response_time: float = 0.0  # seconds
        self._response_times: list[float] = []

    def record_interaction(self, metadata: dict):
        """Record metadata from an interaction."""
        self.message_count += 1

        # Token usage
        if "usage" in metadata:
            usage = metadata["usage"]
            self.total_input_tokens += usage.get("input_tokens", 0)
            self.total_output_tokens += usage.get("output_tokens", 0)
            self.total_cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
            self.total_cache_read_tokens += usage.get("cache_read_input_tokens", 0)

        # Cost
        if "cost" in metadata:
            self.total_cost += metadata["cost"]
            if "cost_breakdown" in metadata:
                for key, value in metadata["cost_breakdown"].items():
                    self.cost_breakdown[key] += value

        # Response time
        if "response_time" in metadata:
            self._response_times.append(metadata["response_time"])
            self.average_response_time = sum(self._response_times) / len(self._response_times)

    def record_tool_call(self, tool_name: str, success: bool, execution_time: float = 0):
        """Record a tool call."""
        self.tool_call_count += 1
        self.tool_usage[tool_name] = self.tool_usage.get(tool_name, 0) + 1

        # Update success rate
        if tool_name not in self.tool_success_rate:
            self.tool_success_rate[tool_name] = 1.0 if success else 0.0
        else:
            # Running average
            count = self.tool_usage[tool_name]
            current_rate = self.tool_success_rate[tool_name]
            new_rate = (current_rate * (count - 1) + (1.0 if success else 0.0)) / count
            self.tool_success_rate[tool_name] = new_rate

    def get_summary(self) -> dict:
        """Get summary statistics."""
        return {
            "message_count": self.message_count,
            "tool_calls": self.tool_call_count,
            "research_tasks": self.research_task_count,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost_usd": round(self.total_cost, 4),
            "avg_response_time_sec": round(self.average_response_time, 2),
            "cache_efficiency": self._calculate_cache_efficiency(),
        }

    def _calculate_cache_efficiency(self) -> float:
        """Calculate cache hit rate."""
        total_input = self.total_input_tokens + self.total_cache_read_tokens
        if total_input == 0:
            return 0.0
        return self.total_cache_read_tokens / total_input

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "message_count": self.message_count,
            "tool_call_count": self.tool_call_count,
            "research_task_count": self.research_task_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_creation_tokens": self.total_cache_creation_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cost": self.total_cost,
            "cost_breakdown": self.cost_breakdown,
            "tool_usage": self.tool_usage,
            "tool_success_rate": self.tool_success_rate,
            "session_duration": self.session_duration,
            "average_response_time": self.average_response_time,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionMetadata":
        """Deserialize from dictionary."""
        metadata = cls()
        for key, value in data.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)
        return metadata
```

---

## 3. Integration with Current Architecture

### 3.1 Integration Points

```
┌────────────────────────────────────────────────────────────┐
│                        NexusApp (TUI)                      │
│                                                            │
│  On app start:                                             │
│    session_state = SessionState(session_id=uuid())        │
│                                                            │
│  On user query:                                            │
│    context = session_state.get_context_for_prompt(query)  │
│    response = agent_loop.run(query, context=context)      │
│    session_state.update_from_interaction(...)             │
│                                                            │
│  On app close:                                             │
│    session_state.save("sessions/{session_id}.json")       │
│                                                            │
└────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌────────────────────────────────────────────────────────────┐
│                   AdaptiveReasoningLoop                    │
│                                                            │
│  async def run(query, context=None):                       │
│    # Use state context if provided                         │
│    if context:                                             │
│      enhanced_query = f"{query}\n\nContext:\n{context}"   │
│                                                            │
│    # Start research tracking                               │
│    tracker = session_state.start_research(query, ...)     │
│                                                            │
│    # Execute strategy...                                   │
│    response = await self._execute_strategy(...)           │
│                                                            │
│    # End research tracking                                 │
│    session_state.end_research(response)                   │
│                                                            │
│    return response                                         │
│                                                            │
└────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌────────────────────────────────────────────────────────────┐
│                    CommandControlAgent                     │
│                                                            │
│  Has access to session_state via constructor               │
│                                                            │
│  Can query state:                                          │
│    facts = session_state.knowledge_base.search(query)     │
│                                                            │
│  Can update state:                                         │
│    session_state.knowledge_base.add_fact(...)             │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 3.2 Modified Architecture Files

**File**: `src/nxs/tui/app.py` (NexusApp)

```python
class NexusApp(App):

    def __init__(self, ...):
        super().__init__()

        # Create session state
        self.session_state = SessionState(session_id=str(uuid.uuid4()))

        # Pass state to components
        self.agent = CommandControlAgent(
            session_state=self.session_state,
            ...
        )

    async def on_query_submit(self, query: str):
        """Handle user query submission."""

        # Get context from state
        context = self.session_state.get_context_for_prompt(query)

        # Execute query
        response = await self.agent.run(query, context=context)

        # Update state
        await self.session_state.update_from_interaction(
            user_message=query,
            assistant_response=response,
            tool_calls=self.agent.get_tool_calls(),
            metadata=self.agent.get_metadata()
        )

        # Display response
        self.chat_panel.display_response(response)

    async def on_mount(self):
        """App mounted - load previous session if exists."""
        # Check for saved session
        last_session = self._find_last_session()
        if last_session:
            resume = await self._ask_resume_session()
            if resume:
                self.session_state = await SessionState.load(last_session)
                # Display session info
                self._display_session_summary()

    async def on_exit(self):
        """Save session state before exit."""
        session_path = f"sessions/{self.session_state.session_id}.json"
        await self.session_state.save(session_path)
```

**File**: `src/nxs/application/reasoning_loop.py`

```python
class AdaptiveReasoningLoop(AgentLoop):

    def __init__(
        self,
        session_state: SessionState,  # NEW parameter
        ...
    ):
        super().__init__(...)
        self.session_state = session_state

    async def run(
        self,
        query: str,
        *,
        context: str = None,  # NEW parameter
        stream: bool = True,
        ...
    ) -> str:
        """Execute query with state-aware context."""

        # Analyze complexity
        complexity = await self.analyzer.analyze(query, ...)

        # Start research tracking in state
        tracker = self.session_state.start_research(query, complexity)

        # Inject state context into query
        if context:
            enhanced_query = f"{query}\n\n# Session Context\n{context}"
        else:
            enhanced_query = query

        # Execute strategy with tracker
        response = await self._execute_strategy(enhanced_query, tracker, ...)

        # End research tracking
        self.session_state.end_research(response)

        return response
```

**File**: `src/nxs/core/command_control.py`

```python
class CommandControlAgent(AgentLoop):

    def __init__(
        self,
        session_state: SessionState,  # NEW parameter
        ...
    ):
        super().__init__(...)
        self.session_state = session_state

    async def process_query(self, query: str) -> str:
        """Process query with state awareness."""

        # Check if query is about state
        if self._is_state_query(query):
            # Query state directly
            answer = await self.session_state.query(query)
            if answer:
                return answer

        # Regular processing
        return await super().run(query)

    def _is_state_query(self, query: str) -> bool:
        """Check if query is asking about session state."""
        state_keywords = ["my name", "what did", "earlier", "before", "we discussed"]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in state_keywords)
```

---

## 4. Usage Patterns

### 4.1 Basic Conversation with State

```python
# Session start
state = SessionState(session_id="abc123")

# User: "My name is Alice and I'm working on a Python project"
query1 = "My name is Alice and I'm working on a Python project"
response1 = await agent.run(query1)
await state.update_from_interaction(query1, response1)

# State now has:
# - user_profile.name = "Alice"
# - user_profile.current_project = "Python project"

# Later in session...
# User: "What's my name?"
query2 = "What's my name?"

# Get context (includes user profile)
context = state.get_context_for_prompt(query2)
# Context: "User's name: Alice"

response2 = await agent.run(query2, context=context)
# Response: "Your name is Alice."
```

### 4.2 Complex Research with State

```python
# User asks complex query
query = "Analyze the performance issues in our API"

# Get state context
context = state.get_context_for_prompt(query)
# Context might include:
# - Previous facts about the API
# - User's project tech stack
# - Related tool results from earlier queries

# Execute with reasoning
response = await reasoning_loop.run(query, context=context)

# During execution:
# 1. state.start_research() creates tracker
# 2. Tools are called, results logged in tracker
# 3. Facts extracted to knowledge base
# 4. state.end_research() archives tracker

# Later query can reference this research
query2 = "What did we learn about the API?"
answer = await state.query(query2)
# Returns facts from knowledge base
```

### 4.3 Session Resumption

```python
# On app start
app = NexusApp()

# Check for previous session
if os.path.exists("sessions/last_session.json"):
    state = await SessionState.load("sessions/last_session.json")

    # Display session summary
    print(f"Resuming session from {state.created_at}")
    print(f"Messages: {state.metadata.message_count}")
    print(f"Facts learned: {len(state.knowledge_base.facts)}")

    # User can reference previous session
    # User: "Where were we?"
    summary = state.interaction_context.get_summary()
    # Shows recent context
else:
    state = SessionState(session_id=uuid4())
```

---

## 5. Context Injection Strategy

### 5.1 When to Inject Context

```python
def should_inject_context(query: str, state: SessionState) -> bool:
    """Decide if state context should be injected."""

    # Always inject if:
    # 1. Query references previous conversation
    if any(word in query.lower() for word in ["earlier", "before", "previous", "we discussed"]):
        return True

    # 2. Query asks about user info
    if any(word in query.lower() for word in ["my", "me", "i"]):
        return True

    # 3. Knowledge base has relevant facts
    relevant_facts = state.knowledge_base.get_relevant_facts(query)
    if relevant_facts:
        return True

    # 4. Active research in progress
    if state.active_research:
        return True

    return False
```

### 5.2 Context Verbosity Levels

```python
def get_context(query: str, state: SessionState, mode: str = "auto") -> str:
    """Get appropriate context level."""

    if mode == "auto":
        # Determine automatically
        if state.active_research:
            mode = "comprehensive"  # Full context for research
        elif len(state.knowledge_base.facts) > 20:
            mode = "standard"  # Medium context
        else:
            mode = "minimal"  # Light context

    if mode == "minimal":
        return state.get_compact_context()
    elif mode == "standard":
        return state.get_context_for_prompt(query, mode="standard")
    else:
        return state.get_context_for_prompt(query, mode="comprehensive")
```

---

## 6. Fact Extraction Implementation

### 6.1 Extraction Strategy

```python
class StateExtractor:
    """Extract structured information from conversations."""

    def __init__(self, anthropic_client):
        self.client = anthropic_client

    async def extract_user_info(
        self,
        user_msg: str,
        assistant_msg: str
    ) -> dict:
        """Extract user profile information."""

        prompt = f"""
Extract user information from this conversation exchange.

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
  "interests": ["string"],
  "current_project": "string",
  "communication_style": "concise|detailed|technical"
}}

If no information is mentioned, return {{}}.
"""

        response = await self.client.messages.create(
            model="claude-3-haiku-20240307",  # Fast, cheap
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return {}

    async def extract_facts(
        self,
        user_msg: str,
        assistant_msg: str
    ) -> list[str]:
        """Extract factual statements."""

        prompt = f"""
Extract factual statements from the assistant's response that might be
useful for future reference.

User: {user_msg}
Assistant: {assistant_msg}

Return a JSON array of factual statements. Include:
- Configuration values
- File paths
- Technical facts
- Decisions made
- Key findings

Example: ["API rate limit is 1000 requests/hour", "Server runs on port 8080"]

If no facts, return [].
"""

        response = await self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return []
```

---

## 7. Benefits and Use Cases

### 7.1 Personalized Interactions

**Before (Message-only)**:
```
User: "My name is Alice"
Assistant: "Hi Alice!"

[50 messages later]

User: "What's my name?"
Assistant: [Scans 50 messages] "Your name is Alice"
```

**After (State-driven)**:
```
User: "My name is Alice"
Assistant: "Hi Alice!"
→ State: user_profile.name = "Alice"

[50 messages later]

User: "What's my name?"
→ State lookup: O(1)
Assistant: "Your name is Alice"
```

### 7.2 Cross-Query Learning

**Scenario**: User asks about API in multiple queries

```python
# Query 1: "What's the API rate limit?"
→ Response: "1000 requests/hour"
→ State: knowledge_base.add_fact("API rate limit: 1000 req/hr")

# Query 2: "Write code to call the API"
→ Context includes: "API rate limit: 1000 req/hr"
→ Generated code includes rate limiting logic
```

### 7.3 Session Resumption

```python
# Session 1 (Monday)
User: "I'm building a chat app with React and Node"
→ State: user_profile.current_project = "chat app"
→ State: user_profile.project_tech_stack = ["React", "Node"]
→ Save state

# Session 2 (Tuesday)
→ Load state
User: "Help me add authentication"
→ Context: "User is building a chat app with React and Node"
→ Assistant provides React/Node-specific auth guidance
```

### 7.4 Research Continuity

```python
# Complex query triggers research
User: "Analyze our database performance"
→ State: start_research()
→ Research executes, calls tools, gathers data
→ State: end_research() → facts added to knowledge base

# Later query
User: "What did we learn about the database?"
→ State.query() returns facts from research
→ No need to re-execute expensive operations
```

---

## 8. Implementation Phases

### Phase 1: Core State Infrastructure (Week 1)

**Goals**: Implement basic SessionState and component classes

**Tasks**:
1. Create `session_state.py` with:
   - SessionState class
   - UserProfile class
   - Basic serialization (to_dict/from_dict)

2. Create `knowledge_base.py` with:
   - Fact class
   - KnowledgeBase class
   - Basic fact storage and retrieval

3. Create `interaction_context.py` with:
   - InteractionContext class
   - Intent tracking

4. Create `session_metadata.py` with:
   - SessionMetadata class
   - Usage tracking

**Testing**:
- Unit tests for each component
- Serialization round-trip tests
- Basic state operations

### Phase 2: Extraction System (Week 2)

**Goals**: Implement fact and profile extraction

**Tasks**:
1. Create `state_extractor.py` with:
   - StateExtractor class
   - extract_user_info() method
   - extract_facts() method
   - Intent classification

2. Integrate with SessionState:
   - update_from_interaction() calls extractor
   - Extracted data updates components

3. Add extraction prompts:
   - User info extraction prompt
   - Fact extraction prompt
   - Intent classification prompt

**Testing**:
- Test extraction with sample conversations
- Verify profile updates
- Check fact deduplication

### Phase 3: NexusApp Integration (Week 3)

**Goals**: Integrate SessionState into TUI

**Tasks**:
1. Modify `tui/app.py`:
   - Create SessionState on app start
   - Pass state to agent components
   - Update state after each interaction

2. Add session management:
   - Save state on app exit
   - Load state on app start
   - Session resumption UI

3. Display state information:
   - Show session summary in header
   - Display user profile in side panel
   - Show fact count in status bar

**Testing**:
- End-to-end TUI tests
- Session save/load tests
- State persistence verification

### Phase 4: Agent Integration (Week 4)

**Goals**: Connect state to reasoning loop

**Tasks**:
1. Modify `AdaptiveReasoningLoop`:
   - Accept SessionState parameter
   - Call state.start_research()
   - Call state.end_research()

2. Modify `CommandControlAgent`:
   - Accept SessionState parameter
   - Query state for contextual info
   - Update state with findings

3. Implement context injection:
   - get_context_for_prompt() integration
   - Context verbosity control
   - Token budget management

**Testing**:
- Integration tests with state
- Context injection tests
- Research tracking verification

### Phase 5: Context Optimization (Week 5)

**Goals**: Optimize context extraction and token usage

**Tasks**:
1. Implement smart context selection:
   - Relevance scoring for facts
   - Context pruning strategies
   - Token counting

2. Add semantic search:
   - Fact similarity matching
   - Query-fact relevance scoring
   - Top-K fact retrieval

3. Optimize extraction:
   - Batch extraction calls
   - Cache extraction results
   - Reduce extraction frequency

**Testing**:
- Token usage benchmarks
- Context relevance tests
- Performance profiling

### Phase 6: Advanced Features (Week 6)

**Goals**: Add advanced state capabilities

**Tasks**:
1. Cross-query learning:
   - Share facts across queries
   - Build session-level knowledge
   - Fact importance ranking

2. State querying:
   - Natural language queries
   - Fact search and retrieval
   - State summarization

3. State visualization:
   - TUI panel for knowledge base
   - Profile display
   - Research history viewer

**Testing**:
- Cross-query tests
- Query accuracy tests
- UI/UX verification

---

## 9. Edge Cases and Considerations

### 9.1 Extraction Accuracy

**Challenge**: LLM may extract incorrect information

**Solution**:
```python
# Confidence scoring
fact = Fact(
    content="User is 30 years old",
    confidence=0.8  # Not 100% certain
)

# User correction
if user_says_no():
    state.knowledge_base.remove_fact(fact)
    state.user_profile.age = None
```

### 9.2 State Size Growth

**Challenge**: State grows unbounded over long sessions

**Solution**:
```python
# Prune old facts
def prune_state(state: SessionState, max_facts: int = 100):
    """Keep only most recent/relevant facts."""
    if len(state.knowledge_base.facts) > max_facts:
        # Sort by relevance and recency
        scored = [
            (fact.timestamp.timestamp() * fact.confidence, fact)
            for fact in state.knowledge_base.facts
        ]
        scored.sort(reverse=True)
        state.knowledge_base.facts = [f for _, f in scored[:max_facts]]
```

### 9.3 Context Relevance

**Challenge**: Injecting irrelevant context wastes tokens

**Solution**:
```python
# Relevance filtering
def get_relevant_context(query: str, state: SessionState) -> str:
    """Only include relevant parts of state."""

    context_parts = []

    # Only include user profile if query references user
    if has_user_reference(query):
        context_parts.append(state.user_profile.to_context_text())

    # Only include facts relevant to query
    relevant_facts = state.knowledge_base.get_relevant_facts(query, limit=5)
    if relevant_facts:
        context_parts.append(format_facts(relevant_facts))

    return "\n\n".join(context_parts)
```

### 9.4 Privacy and Persistence

**Challenge**: State contains sensitive user information

**Solution**:
```python
# Opt-in persistence
def save_state(state: SessionState, persist_profile: bool = False):
    """Save state with privacy controls."""
    data = state.to_dict()

    if not persist_profile:
        # Exclude user profile from saved state
        data["user_profile"] = UserProfile().to_dict()

    # Encrypt sensitive fields
    if data["user_profile"]["name"]:
        data["user_profile"]["name"] = encrypt(data["user_profile"]["name"])

    save_json(data, path)
```

---

## 10. Success Metrics

### 10.1 Context Retrieval Efficiency

**Metric**: Time to retrieve relevant information
- Baseline: Scan N messages (O(N))
- Target: Direct state lookup (O(1))
- Measure: Query response time for factual questions

### 10.2 Fact Extraction Accuracy

**Metric**: % of correctly extracted facts
- Target: >90% accuracy
- Measure: Manual review of extracted facts
- Track: False positives (incorrect facts) and false negatives (missed facts)

### 10.3 Context Relevance

**Metric**: % of injected context that is relevant
- Target: >80% relevance
- Measure: LLM assessment of context usefulness
- Track: Wasted tokens from irrelevant context

### 10.4 Session Continuity

**Metric**: Successful session resumptions
- Target: 100% successful loads
- Measure: State serialization round-trips
- Track: Data loss or corruption

### 10.5 Token Efficiency

**Metric**: Token savings from state-based context vs. full history
- Target: 30-50% reduction
- Measure: Compare tokens with/without state
- Track: Cost savings

---

## 11. Future Enhancements

### 11.1 Semantic Embeddings

**Idea**: Use vector embeddings for fact similarity

```python
class KnowledgeBase:
    def __init__(self):
        self.facts: list[Fact] = []
        self.embeddings: np.ndarray = None  # Fact embeddings
        self.embedding_model = SentenceTransformer(...)

    def add_fact(self, content: str, **kwargs):
        fact = Fact(content=content, **kwargs)
        self.facts.append(fact)

        # Generate embedding
        embedding = self.embedding_model.encode(content)
        self.embeddings = np.vstack([self.embeddings, embedding])

    def search_semantic(self, query: str, limit: int = 5) -> list[Fact]:
        """Semantic similarity search."""
        query_embedding = self.embedding_model.encode(query)

        # Cosine similarity
        similarities = cosine_similarity([query_embedding], self.embeddings)[0]

        # Top-K
        top_indices = np.argsort(similarities)[-limit:][::-1]
        return [self.facts[i] for i in top_indices]
```

### 11.2 Multi-Session Memory

**Idea**: Share knowledge across sessions

```python
class GlobalKnowledgeBase:
    """Cross-session knowledge repository."""

    def __init__(self):
        self.sessions: dict[str, SessionState] = {}
        self.global_facts: KnowledgeBase = KnowledgeBase()

    def add_session(self, session: SessionState):
        """Add session and merge facts."""
        self.sessions[session.session_id] = session

        # Merge facts to global knowledge
        for fact in session.knowledge_base.facts:
            if fact.confidence > 0.8:  # Only high-confidence facts
                self.global_facts.add_fact(fact.content, source="session")

    def get_global_context(self, query: str) -> str:
        """Get context from all sessions."""
        return self.global_facts.search(query, limit=5)
```

### 11.3 Automatic Fact Verification

**Idea**: Verify extracted facts against sources

```python
async def verify_fact(fact: Fact, sources: list[str]) -> float:
    """Verify fact against source documents."""

    prompt = f"""
Verify if this fact is supported by the sources:

Fact: {fact.content}

Sources:
{chr(10).join(sources)}

Return confidence score (0.0 to 1.0) and explanation.
"""

    response = await call_llm(prompt)
    confidence = parse_confidence(response)

    # Update fact confidence
    fact.confidence = confidence
    return confidence
```

---

## 12. Relationship with ResearchProgressTracker

The ResearchProgressTracker is now a **component of SessionState** rather than a standalone entity:

```python
# Old architecture (from RESEARCH_PROGRESS_TRACKING_PLAN.md)
tracker = ResearchProgressTracker(query, complexity)
# Tracker is orphaned after query completes

# New architecture (integrated with State)
SessionState
├── active_research: ResearchProgressTracker  # Current research
├── research_history: list[ResearchProgressTracker]  # Past research
└── knowledge_base: KnowledgeBase  # Facts extracted from research

# Benefits:
# 1. Research results persisted in knowledge base
# 2. Future queries can reference past research
# 3. Research history available for context
# 4. Unified state management
```

**Integration Flow**:
```python
# User asks complex query
query = "Analyze API performance"

# Start research (creates tracker in state)
tracker = session_state.start_research(query, complexity)

# Execute research (tracker updated throughout)
response = await reasoning_loop.run(query, tracker=tracker)

# End research (extract facts, archive tracker)
session_state.end_research(response)
# → tracker.insights.confirmed_facts added to knowledge_base
# → tracker moved to research_history
# → active_research set to None

# Future query can reference this research
query2 = "What did we learn about the API?"
facts = session_state.knowledge_base.search("API")
# Returns facts extracted from research tracker
```

---

## 13. Conclusion

The **SessionState** architecture elevates Nexus from a stateless message-passing system to a **stateful, context-aware agent** with persistent memory and semantic understanding.

**Key Principles**:
1. **Semantic over Sequential**: Store meaning, not just messages
2. **Structured over Flat**: Organized components instead of message lists
3. **Queryable over Searchable**: Direct lookups instead of scans
4. **Persistent over Ephemeral**: State survives sessions
5. **Integrated over Isolated**: Research tracking is part of state

**Architecture Summary**:
```
SessionState (Top-level)
├── Conversation (messages) - existing
├── UserProfile (who they are) - NEW
├── KnowledgeBase (what we learned) - NEW
├── InteractionContext (current flow) - NEW
├── SessionMetadata (costs, stats) - NEW
├── active_research (current research) - NEW
└── research_history (past research) - NEW
```

**Value Proposition**:
- **For Users**: Personalized, context-aware interactions
- **For LLM**: Rich context without message scanning
- **For System**: Efficient fact retrieval and cross-query learning
- **For Development**: Clean separation of concerns

The State system, combined with the ResearchProgressTracker, creates a **comprehensive cognitive architecture** that maintains both immediate execution state (research) and long-term session memory (knowledge base), enabling truly intelligent, adaptive conversations.

---

**Next Steps**: Review this design, provide feedback, then proceed with Phase 1 implementation of core state infrastructure.
