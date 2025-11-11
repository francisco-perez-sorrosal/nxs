# Phase 2/3: Cognitive Multi-Agent Architecture

## Overview

This document describes the future evolution of the Nexus reasoning system from Level 2 (Strategic Problem-Solver with adaptive reasoning) to Level 3/4 (Collaborative Multi-Agent System with self-evolution).

**Status**: Future work - to be implemented AFTER Phase 1 is complete and stable.

**Prerequisites**: 
- Phase 1 AdaptiveReasoningLoop fully implemented and validated
- Phase 1 in production with proven quality self-correction
- See: `REASONING_SYSTEM_PLAN.md` for Phase 1 details

**Timeline**: 4-6+ weeks across 2 major phases

---

## Phase 2: Sub-Agent Decomposition (Level 2/3 Transition)

**Objective:** Decompose reasoning into specialized sub-agents with brain-inspired nomenclature.

**Duration:** 2-3 weeks

### 2.1 Brain-Inspired Architecture

**New Module:** `src/nxs/application/cognitive/`

Introduce cognitive architecture inspired by brain structures:

```
src/nxs/application/cognitive/
├── __init__.py
├── cortex.py              # Central coordinator (prefrontal cortex)
├── perception.py          # Perception agent (sensory cortex)
├── memory.py              # Memory agent (hippocampus)
├── executive.py           # Executive agent (executive function)
├── motor.py               # Action execution (motor cortex)
├── messaging.py           # Inter-agent communication
└── types.py               # Shared cognitive types
```

**Architecture Mapping:**

| Brain Structure | Agent Component | Responsibility |
|-----------------|-----------------|----------------|
| **Prefrontal Cortex** | `CortexCoordinator` | Central planning, decision-making, coordination |
| **Sensory Cortex** | `PerceptionAgent` | Process input, extract context, gather resources |
| **Hippocampus** | `MemoryAgent` | Long-term memory, episodic recall, context retrieval |
| **Executive Function** | `ExecutiveAgent` | Task prioritization, goal management, evaluation |
| **Motor Cortex** | `MotorAgent` | Tool execution, action dispatch, result collection |

### 2.2 Agent Communication Protocol

**New Module:** `src/nxs/application/cognitive/messaging.py`

Define inter-agent communication:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from enum import Enum

class MessageType(Enum):
    """Types of inter-agent messages."""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"

@dataclass
class CognitiveMessage:
    """Message between cognitive agents."""
    sender: str              # Agent name (e.g., "perception", "memory")
    recipient: str           # Target agent name (e.g., "executive", "motor")
    message_type: MessageType
    payload: dict[str, Any]  # Message data
    correlation_id: str      # For tracking request-response pairs
    timestamp: datetime = field(default_factory=datetime.now)
    priority: int = 0        # Higher = more urgent
    
    def create_response(
        self,
        response_payload: dict[str, Any]
    ) -> "CognitiveMessage":
        """Create a response message to this message."""
        return CognitiveMessage(
            sender=self.recipient,
            recipient=self.sender,
            message_type=MessageType.RESPONSE,
            payload=response_payload,
            correlation_id=self.correlation_id,
            priority=self.priority
        )

@dataclass  
class CognitiveContext:
    """Shared context across cognitive agents.
    
    This is the 'workspace' that all agents read from and write to.
    It represents the current state of cognitive processing.
    """
    # Input
    user_query: str
    original_query: str  # Before preprocessing
    
    # State
    conversation_history: list[dict]
    accumulated_results: list[dict] = field(default_factory=list)
    current_plan: Optional[Any] = None  # ResearchPlan or other plan types
    
    # Memory
    memory_cache: dict[str, Any] = field(default_factory=dict)
    episodic_memories: list[dict] = field(default_factory=list)
    
    # Resources
    tool_registry: Optional[Any] = None
    artifact_manager: Optional[Any] = None
    
    # Metadata
    processing_stage: str = "initialized"
    iteration_count: int = 0
    confidence: float = 0.0
    
    def update_stage(self, stage: str) -> None:
        """Update processing stage with logging."""
        logger.info(f"Cognitive stage transition: {self.processing_stage} -> {stage}")
        self.processing_stage = stage
```

### 2.3 CortexCoordinator (Central Nervous System)

**New Class:** `src/nxs/application/cognitive/cortex.py`

```python
from nxs.application.cognitive.perception import PerceptionAgent
from nxs.application.cognitive.memory import MemoryAgent
from nxs.application.cognitive.executive import ExecutiveAgent
from nxs.application.cognitive.motor import MotorAgent
from nxs.application.cognitive.messaging import CognitiveContext, CognitiveMessage
from nxs.logger import get_logger

logger = get_logger(__name__)

class CortexCoordinator:
    """Central coordinator - orchestrates cognitive agents.
    
    Loosely inspired by prefrontal cortex:
    - High-level planning and decision-making
    - Coordinates specialized sub-agents
    - Maintains global state and context
    - Routes information between agents
    
    This is the "central nervous system" that manages the cognitive loop.
    """
    
    def __init__(
        self,
        llm: Claude,
        perception: PerceptionAgent,
        memory: MemoryAgent,
        executive: ExecutiveAgent,
        motor: MotorAgent,
        callbacks: Optional[dict] = None
    ):
        self.llm = llm
        self.perception = perception
        self.memory = memory
        self.executive = executive
        self.motor = motor
        self.callbacks = callbacks or {}
        self.context: Optional[CognitiveContext] = None
        
        logger.info("CortexCoordinator initialized with 4 cognitive agents")
    
    async def process(
        self,
        query: str,
        use_streaming: bool = True
    ) -> str:
        """Main cognitive processing loop.
        
        Process Flow:
        1. Perception: Understand and parse the query
        2. Memory: Retrieve relevant context and history
        3. Executive: Create and manage execution plan
        4. Motor: Execute actions via tools
        5. Iterate: Evaluate and refine (Executive + Motor loop)
        6. Synthesize: Generate final answer (Executive)
        7. Store: Save to long-term memory (Memory)
        
        Args:
            query: User's query
            use_streaming: Whether to use streaming responses
            
        Returns:
            Final comprehensive answer
        """
        logger.info(f"Cortex processing query: {query[:100]}...")
        
        # Initialize shared cognitive context
        self.context = CognitiveContext(
            user_query=query,
            original_query=query,
            conversation_history=[],
            tool_registry=None,  # Will be set by agents
        )
        
        try:
            # Phase 1: PERCEPTION - Understand the query
            logger.info("Phase 1: Perception - Understanding query")
            self.context.update_stage("perception")
            
            if "on_perception" in self.callbacks:
                await self.callbacks["on_perception"]()
            
            perception_result = await self.perception.process(
                query, self.context
            )
            
            logger.info(
                f"Perception complete: intent={perception_result.get('intent')}, "
                f"complexity={perception_result.get('complexity')}"
            )
            
            # Phase 2: MEMORY - Retrieve relevant context
            logger.info("Phase 2: Memory - Retrieving context")
            self.context.update_stage("memory_retrieval")
            
            if "on_memory_retrieval" in self.callbacks:
                await self.callbacks["on_memory_retrieval"]()
            
            memory_result = await self.memory.retrieve(
                query, self.context
            )
            
            self.context.memory_cache = memory_result
            logger.info(
                f"Memory retrieval complete: "
                f"{len(memory_result.get('episodic', []))} episodic memories, "
                f"{len(memory_result.get('semantic', []))} semantic memories"
            )
            
            # Phase 3: EXECUTIVE PLANNING - Create execution plan
            logger.info("Phase 3: Executive - Creating execution plan")
            self.context.update_stage("planning")
            
            if "on_planning" in self.callbacks:
                await self.callbacks["on_planning"]()
            
            plan = await self.executive.plan(
                query=query,
                perception=perception_result,
                memory=memory_result,
                context=self.context
            )
            
            self.context.current_plan = plan
            logger.info(
                f"Plan created: {plan.get('subtask_count', 0)} subtasks, "
                f"estimated_iterations={plan.get('max_iterations', 0)}"
            )
            
            # Phase 4: EXECUTION LOOP - Motor + Executive coordination
            logger.info("Phase 4: Execution Loop - Iterative execution")
            self.context.update_stage("execution")
            
            max_iterations = plan.get("max_iterations", 3)
            
            for iteration in range(max_iterations):
                logger.info(f"Iteration {iteration + 1}/{max_iterations}")
                self.context.iteration_count = iteration
                
                if "on_iteration" in self.callbacks:
                    await self.callbacks["on_iteration"](iteration, max_iterations)
                
                # 4a: MOTOR - Execute current action(s)
                current_action = await self.executive.get_next_action(
                    plan, self.context
                )
                
                if current_action is None:
                    logger.info("No more actions in plan, moving to evaluation")
                    break
                
                logger.debug(f"Executing action: {current_action.get('description')}")
                
                execution_result = await self.motor.execute(
                    action=current_action,
                    context=self.context,
                    use_streaming=use_streaming,
                    callbacks=self.callbacks
                )
                
                self.context.accumulated_results.append(execution_result)
                
                # 4b: EXECUTIVE - Evaluate progress
                logger.debug("Evaluating progress")
                evaluation = await self.executive.evaluate(
                    results=self.context.accumulated_results,
                    plan=plan,
                    context=self.context
                )
                
                self.context.confidence = evaluation.get("confidence", 0.0)
                
                logger.info(
                    f"Evaluation: complete={evaluation.get('is_complete')}, "
                    f"confidence={self.context.confidence:.2f}"
                )
                
                # Check if we're done
                if evaluation.get("is_complete"):
                    logger.info("Task complete, proceeding to synthesis")
                    break
                
                # 4c: EXECUTIVE - Adjust plan if needed
                if evaluation.get("adjustments_needed"):
                    logger.debug("Adjusting plan based on evaluation")
                    plan = await self.executive.adjust_plan(
                        evaluation, plan, self.context
                    )
                    self.context.current_plan = plan
            
            # Phase 5: SYNTHESIS - Generate final answer
            logger.info("Phase 5: Executive - Synthesizing final answer")
            self.context.update_stage("synthesis")
            
            if "on_synthesis" in self.callbacks:
                await self.callbacks["on_synthesis"]()
            
            final_answer = await self.executive.synthesize(
                results=self.context.accumulated_results,
                query=query,
                context=self.context
            )
            
            logger.info(
                f"Synthesis complete: {len(final_answer)} chars, "
                f"confidence={self.context.confidence:.2f}"
            )
            
            # Phase 6: MEMORY STORAGE - Save to long-term memory
            logger.info("Phase 6: Memory - Storing results")
            self.context.update_stage("memory_storage")
            
            await self.memory.store(
                query=query,
                answer=final_answer,
                context=self.context
            )
            
            logger.info("Cortex processing complete")
            self.context.update_stage("complete")
            
            return final_answer
            
        except Exception as e:
            logger.error(f"Cortex processing failed: {e}", exc_info=True)
            self.context.update_stage("error")
            raise
```

### 2.4 Specialized Sub-Agents

#### PerceptionAgent (`perception.py`)

```python
class PerceptionAgent:
    """Processes and interprets input queries.
    
    Inspired by sensory cortex - the entry point for external stimuli.
    
    Responsibilities:
    - Parse user intent
    - Extract @resource mentions
    - Identify /command requests
    - Classify query type (simple/complex/research)
    - Extract entities and context
    """
    
    def __init__(
        self,
        llm: Claude,
        artifact_manager: Optional[Any] = None
    ):
        self.llm = llm
        self.artifact_manager = artifact_manager
        self.parser = CompositeArgumentParser()
        
    async def process(
        self,
        query: str,
        context: CognitiveContext
    ) -> dict[str, Any]:
        """Process and interpret the query.
        
        Returns:
            dict with:
            - intent: What the user wants to do
            - complexity: simple/medium/complex
            - query_type: question/command/research/creative
            - entities: Extracted entities
            - resources: Mentioned resources (@mentions)
            - commands: Identified commands (/commands)
        """
```

#### MemoryAgent (`memory.py`)

```python
class MemoryAgent:
    """Manages different memory types.
    
    Inspired by hippocampus - memory formation and retrieval.
    
    Memory Types:
    - Short-term: Current conversation (from Conversation object)
    - Episodic: Past conversations and solutions
    - Semantic: Factual knowledge (from MCP resources)
    - Procedural: Learned strategies and patterns
    """
    
    def __init__(
        self,
        llm: Claude,
        storage_path: Path,
        artifact_manager: Optional[Any] = None
    ):
        self.llm = llm
        self.storage_path = storage_path
        self.artifact_manager = artifact_manager
        
        # Memory stores
        self.episodic_store = EpisodicMemoryStore(storage_path / "episodic")
        self.semantic_store = SemanticMemoryStore(storage_path / "semantic")
        self.procedural_store = ProceduralMemoryStore(storage_path / "procedural")
    
    async def retrieve(
        self,
        query: str,
        context: CognitiveContext
    ) -> dict[str, Any]:
        """Retrieve relevant memories.
        
        Returns:
            dict with:
            - episodic: List of past similar conversations
            - semantic: Relevant facts and knowledge
            - procedural: Applicable strategies
        """
    
    async def store(
        self,
        query: str,
        answer: str,
        context: CognitiveContext
    ) -> None:
        """Store new memories."""
```

#### ExecutiveAgent (`executive.py`)

```python
class ExecutiveAgent:
    """High-level planning and evaluation.
    
    Inspired by executive function - the "manager" of cognitive processes.
    
    Responsibilities:
    - Task decomposition
    - Progress evaluation
    - Plan adjustment
    - Result synthesis
    - Goal management
    """
    
    def __init__(
        self,
        llm: Claude,
        planner: Optional[Planner] = None,
        evaluator: Optional[Evaluator] = None,
        synthesizer: Optional[Synthesizer] = None
    ):
        self.llm = llm
        self.planner = planner or Planner(llm, ReasoningConfig())
        self.evaluator = evaluator or Evaluator(llm, ReasoningConfig())
        self.synthesizer = synthesizer or Synthesizer(llm, ReasoningConfig())
    
    async def plan(
        self,
        query: str,
        perception: dict,
        memory: dict,
        context: CognitiveContext
    ) -> dict[str, Any]:
        """Create execution plan."""
    
    async def get_next_action(
        self,
        plan: dict,
        context: CognitiveContext
    ) -> Optional[dict[str, Any]]:
        """Get next action from plan."""
    
    async def evaluate(
        self,
        results: list[dict],
        plan: dict,
        context: CognitiveContext
    ) -> dict[str, Any]:
        """Evaluate progress."""
    
    async def adjust_plan(
        self,
        evaluation: dict,
        plan: dict,
        context: CognitiveContext
    ) -> dict[str, Any]:
        """Adjust plan based on evaluation."""
    
    async def synthesize(
        self,
        results: list[dict],
        query: str,
        context: CognitiveContext
    ) -> str:
        """Synthesize final answer."""
```

#### MotorAgent (`motor.py`)

```python
class MotorAgent:
    """Executes actions via tools.
    
    Inspired by motor cortex - the "executor" that takes action.
    
    Responsibilities:
    - Tool selection and invocation
    - Result collection
    - Error handling and retry
    - Action dispatch to appropriate handlers
    """
    
    def __init__(
        self,
        llm: Claude,
        tool_registry: ToolRegistry,
        mcp_clients: Optional[dict] = None
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.mcp_clients = mcp_clients or {}
    
    async def execute(
        self,
        action: dict[str, Any],
        context: CognitiveContext,
        use_streaming: bool = True,
        callbacks: Optional[dict] = None
    ) -> dict[str, Any]:
        """Execute an action.
        
        Args:
            action: Action specification with:
                - type: "tool_call" | "query" | "resource_fetch"
                - details: Action-specific details
            context: Shared cognitive context
            use_streaming: Whether to use streaming
            callbacks: Optional callbacks
            
        Returns:
            Execution result with:
            - success: bool
            - result: Result data
            - metadata: Execution metadata
        """
```

### 2.5 Integration with Existing System

**Update:** `src/nxs/application/command_control.py`

```python
class CommandControlAgent:
    """Command control with cognitive architecture.
    
    Supports three execution modes:
    1. Simple mode: Direct AgentLoop (fast, single-pass)
    2. Reasoning mode: ReasoningLoop with planning (thorough, multi-step)
    3. Cognitive mode: Full CortexCoordinator (advanced, multi-agent)
    """
    
    def __init__(
        self,
        artifact_manager: ArtifactManager,
        claude_service: Claude,
        mode: str = "simple",  # "simple" | "reasoning" | "cognitive"
        callbacks=None,
        reasoning_config: Optional[ReasoningConfig] = None,
    ):
        self.artifact_manager = artifact_manager
        self.claude = claude_service
        self.mode = mode
        self.callbacks = callbacks or {}
        
        # Build based on mode
        if mode == "cognitive":
            self.cortex = self._build_cognitive_system()
        elif mode == "reasoning":
            self.reasoning_loop = self._build_reasoning_loop(reasoning_config)
        else:  # simple
            self.agent_loop = self._build_simple_loop()
    
    def _build_cognitive_system(self) -> CortexCoordinator:
        """Initialize full cognitive architecture."""
        from nxs.application.cognitive.cortex import CortexCoordinator
        from nxs.application.cognitive.perception import PerceptionAgent
        from nxs.application.cognitive.memory import MemoryAgent
        from nxs.application.cognitive.executive import ExecutiveAgent
        from nxs.application.cognitive.motor import MotorAgent
        
        # Create tool registry
        tool_registry = ToolRegistry(enable_caching=True)
        mcp_provider = MCPToolProvider(self.artifact_manager.clients)
        tool_registry.register_provider(mcp_provider)
        
        # Create cognitive agents
        perception = PerceptionAgent(self.claude, self.artifact_manager)
        memory = MemoryAgent(
            self.claude,
            storage_path=Path.home() / ".nxs" / "memory",
            artifact_manager=self.artifact_manager
        )
        executive = ExecutiveAgent(self.claude)
        motor = MotorAgent(
            self.claude,
            tool_registry=tool_registry,
            mcp_clients=self.artifact_manager.clients
        )
        
        return CortexCoordinator(
            llm=self.claude,
            perception=perception,
            memory=memory,
            executive=executive,
            motor=motor,
            callbacks=self.callbacks
        )
    
    async def run(self, query: str, use_streaming: bool = True) -> str:
        """Run with selected architecture."""
        if self.mode == "cognitive":
            return await self.cortex.process(query, use_streaming)
        elif self.mode == "reasoning":
            return await self.reasoning_loop.run(query, use_streaming)
        else:
            return await self.agent_loop.run(query, use_streaming)
```

### Phase 2 Benefits

**Advanced Capabilities:**
- True multi-agent coordination with specialized roles
- Long-term memory beyond conversation history
- Explicit perception and action separation
- Modular cognitive functions (test/swap agents independently)
- Foundation for meta-learning and self-improvement
- Brain-inspired architecture (easier to reason about and explain)

**Monitoring and Observability:**
- Agent communication logs via messaging protocol
- Cognitive state inspection via CognitiveContext
- Performance metrics per agent
- Debugging tools for agent interactions
- Stage-by-stage progress tracking

---

## Phase 3: Advanced Multi-Agent Orchestration (Level 3/4)

**Objective:** Implement agent-to-agent coordination and self-evolution capabilities.

**Duration:** Future work (after Phase 1 & 2 stabilize)

### 3.1 Agent Delegation and Coordination

**New Module:** `src/nxs/application/cognitive/coordination.py`

```python
class AgentCoordinator:
    """Enables agents to delegate to specialized sub-agents."""
    
    async def delegate(
        self,
        task: Task,
        target_agent: str,
        context: CognitiveContext
    ) -> TaskResult:
        """Delegate task to specialized agent."""
```

### 3.2 Dynamic Agent Creation

**New Module:** `src/nxs/application/cognitive/factory.py`

```python
class AgentFactory:
    """Creates specialized agents on-demand."""
    
    async def create_specialist(
        self,
        domain: str,
        requirements: dict
    ) -> SpecialistAgent:
        """Create a specialist agent for specific domain."""
```

### 3.3 Meta-Learning and Adaptation

**New Module:** `src/nxs/application/cognitive/meta.py`

```python
class MetaLearner:
    """Learns patterns and improves agent strategies."""
    
    async def analyze_performance(
        self,
        task_history: list[Task]
    ) -> PerformanceReport:
        """Analyze past performance and identify improvements."""
```

---

## Implementation Roadmap

### Stage 3: Cognitive Architecture (Phase 2 - Week 3-5)

**Week 3:**
- Create `cognitive/` module structure
- Implement `messaging.py` with CognitiveMessage and CognitiveContext
- Implement `types.py` for cognitive types
- Implement PerceptionAgent
- Write tests for PerceptionAgent

**Week 4:**
- Implement MemoryAgent with storage backends
- Implement ExecutiveAgent (wrapping Phase 1 components)
- Implement MotorAgent
- Write tests for Memory, Executive, and Motor agents

**Week 5:**
- Implement CortexCoordinator
- Integration testing for cognitive system
- Update CommandControlAgent with cognitive mode
- Performance optimization
- Documentation for cognitive architecture

### Stage 4: Advanced Features (Phase 3 - Week 5+)

**Future Work:**
- Agent delegation system
- Dynamic agent creation
- Meta-learning capabilities
- Performance optimization
- Production hardening

---

## Configuration

**Environment Variables:**
```bash
# Cognitive mode (Phase 2)
ENABLE_COGNITIVE=false           # Phase 2 feature flag
MEMORY_STORAGE_PATH=~/.nxs/memory

# Meta-learning (Phase 3)
ENABLE_META_LEARNING=false       # Phase 3 feature flag
```

### Rollout Strategy

**Phase 2 Rollout:**
1. Deploy with `AGENT_MODE=simple` (default)
2. Beta test `AGENT_MODE=reasoning`
3. Beta test `AGENT_MODE=cognitive`
4. Gradual rollout based on query complexity

**Phase 3 Rollout:**
1. Advanced features opt-in only
2. Long-term evaluation
3. Production hardening

---

## Success Metrics

### Level 3 Metrics (Multi-Agent)

**Coordination Metrics:**
- Agent coordination efficiency: >90% successful handoffs
- Memory recall accuracy: >85% relevant memories
- Task delegation success rate: >95%

**Learning Metrics:**
- Meta-learning improvement: >10% performance gain over time
- Strategy adaptation: >80% successful adjustments
- Pattern recognition: >75% accuracy

---

## Risks and Mitigations

### Phase 2/3 Specific Risks

**Risk: Debugging Complexity**
- **Impact:** Medium (development velocity)
- **Mitigation:**
  - Comprehensive logging at each stage
  - Visualization tools for agent communication
  - CognitiveContext state inspection
  - Replay capabilities for debugging
  - Clear error messages and traces

**Risk: Memory Storage Issues**
- **Impact:** Low (storage costs)
- **Mitigation:**
  - TTL and cleanup policies
  - Compressed storage formats
  - Selective memory retention
  - Storage monitoring
  - User controls for privacy

---

## Next Steps

### After Phase 1 Completion

1. Validate Phase 1 performance and quality metrics
2. Gather user feedback on adaptive reasoning
3. Stabilize Phase 1 in production (1-2 months)
4. Begin Phase 2 design refinement based on learnings
5. Prototype PerceptionAgent and MemoryAgent

### Long-term Vision (6+ months)

1. Self-evolving agent capabilities
2. Multi-agent collaboration patterns
3. Autonomous agent creation
4. Cross-session learning
5. Advanced reasoning techniques (symbolic AI, neuro-symbolic)

---

## Conclusion

Phase 2/3 represents the evolution from strategic problem-solving to true cognitive multi-agent systems. The brain-inspired architecture provides:

- Modularity and specialized responsibilities
- Long-term memory and learning
- Agent coordination and delegation
- Foundation for self-evolution

This is an ambitious vision that builds upon the solid foundation of Phase 1's self-correcting adaptive reasoning system.

