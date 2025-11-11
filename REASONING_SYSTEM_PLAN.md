# Reasoning Multi-Agent System Evolution Plan

## Document Updates Summary

**Last Updated:** Based on comprehensive review and feedback

**Major Improvements Added:**

1. **TUI Integration & Reasoning Visibility (Section 1.4 - NEW/ENHANCED)**
   - **Collapsible Reasoning Trace Panel** - Progressive disclosure design to prevent information overload
   - Complete callback interface with dual routing (StatusPanel vs TracePanel)
   - `ReasoningTracePanel` widget - Hierarchical trace display with collapsible behavior
   - StatusPanel simplified - High-level events only
   - Keyboard shortcuts (`Ctrl+R`, `Ctrl+Shift+R`)
   - Visual activity indicators (🔔 when reasoning active)
   - NexusApp integration with dynamic header updates

2. **Supporting Utilities (Section 1.5 - NEW)**
   - `load_prompt()` utility for template loading
   - `format_prompt()` for safe variable substitution
   - `get_claude_for_component()` for model-specific instances
   - Claude.with_model() enhancement

3. **Error Handling & Graceful Degradation (Section 1.6 - NEW)**
   - Comprehensive error handling strategy
   - Fallback matrix for component failures
   - User notification patterns
   - Never-fail principle

4. **Streaming Strategy Decision (Section 1.2 - ENHANCED)**
   - Buffered evaluation approach (quality-first)
   - Message management clarification
   - Response lifecycle specification

5. **Complete main.py Integration (Section 1.7 - EXPANDED)**
   - Full SessionManager integration
   - ReasoningConfig loading from environment
   - Factory pattern with reasoning config
   - TUI callback setup strategy

6. **Quality Thresholds (Config - ADDED)**
   - `min_quality_direct`, `min_quality_light`, `min_quality_deep`
   - Self-correction trigger levels

7. **Comprehensive Testing Strategy (EXPANDED)**
   - Test organization structure
   - MockClaude implementation
   - Concrete test examples with assertions
   - Integration test scenarios
   - TUI callback testing

**Issues Resolved:**

- ✅ TUI status reporting for reasoning modes
- ✅ **Information overload prevention** - Collapsible trace panel for detailed reasoning steps
- ✅ Streaming vs. quality evaluation conflict
- ✅ Conversation message management during escalation
- ✅ SessionManager integration with reasoning config
- ✅ Prompt loading utility specification
- ✅ Model selection per component
- ✅ Error handling and fallback behaviors
- ✅ Testing specifications with concrete examples
- ✅ Configuration completeness
- ✅ Type definitions enhanced
- ✅ **Callback routing strategy** - StatusPanel vs ReasoningTracePanel separation

---

## Executive Summary

This document outlines the phased evolution of the Nexus agent system from a Level 1 "Connected Problem-Solver" to a Level 2/3 "Strategic Multi-Agent Reasoning System." The transformation will introduce structured planning, iterative refinement, and multi-agent coordination inspired by cognitive neuroscience.

**Timeline:** 5+ weeks across 3 major phases
**Approach:** Incremental evolution with backward compatibility
**Architecture:** Brain-inspired modular design with central coordination

---

## Current State Analysis

### Existing Architecture (Level 1)

**Core Components:**
- `AgentLoop`: Core orchestration with Claude integration, tool execution, streaming
- `CommandControlAgent`: Extends AgentLoop, adds resource extraction (`@resource`) and command processing (`/command`)
- `Conversation`: Message state management with prompt caching
- `ToolRegistry`: Pluggable tool providers (MCP servers via protocol)
- `Claude`: API wrapper with real streaming support
- `SessionManager`: Conversation persistence and lifecycle management

**Current Capabilities:**
- ✅ Connected problem-solver with MCP tool integration
- ✅ Resource mentions via `@resource` syntax
- ✅ Command prompts via `/command` syntax  
- ✅ Real streaming responses with proper event handling
- ✅ Session persistence to JSON
- ✅ Prompt caching optimization (90% cost reduction)

**Current Limitations:**
- ❌ No explicit planning phase - relies on Claude's implicit reasoning
- ❌ No iterative refinement or research loops
- ❌ No task decomposition or multi-step strategies
- ❌ Single-pass execution model
- ❌ No memory beyond conversation history
- ❌ No specialized sub-agents for different cognitive functions

---

## Phase 1: Modular Planning & Reasoning (Level 2 Foundation)

**Objective:** Introduce structured planning and iterative reasoning while maintaining clean modularity and backward compatibility.

**Duration:** 2-3 weeks

### 1.1 Create Core Reasoning Components

**New Module Structure:**
```
src/nxs/application/reasoning/
├── __init__.py
├── analyzer.py         # Query complexity analysis (NEW)
├── planner.py          # Query planning and decomposition
├── evaluator.py        # Completeness evaluation
├── synthesizer.py      # Result synthesis
├── config.py           # Configuration dataclasses
└── types.py            # Shared types (ResearchPlan, EvaluationResult, etc.)
```

#### Key Classes

**0. QueryComplexityAnalyzer (`analyzer.py`)** - NEW COMPONENT

Automatically analyzes query complexity to determine execution strategy.

```python
class QueryComplexityAnalyzer:
    """Analyzes query complexity to determine execution strategy.
    
    This is the "triage" component that decides whether a query needs:
    - Simple execution (common knowledge + tools suffice)
    - Light reasoning (1-2 iterations, minimal planning)
    - Deep reasoning (full planning, multiple iterations)
    
    Responsibilities:
    - Analyze query structure and content
    - Detect multi-part questions
    - Assess information requirements
    - Determine if research/iteration needed
    - Recommend execution strategy
    
    Pattern: Lightweight classifier/analyzer, not a full agent yet
    """
    
    def __init__(self, llm: Claude, config: ReasoningConfig):
        self.llm = llm
        self.config = config
        self.prompt_template = load_prompt("reasoning/complexity_analysis.txt")
    
    async def analyze(
        self,
        query: str,
        available_tools: Optional[list[str]] = None,
        conversation_context: Optional[dict] = None
    ) -> ComplexityAnalysis:
        """Analyze query complexity and recommend strategy.
        
        Args:
            query: User's query
            available_tools: List of available tool names
            conversation_context: Recent conversation context
            
        Returns:
            ComplexityAnalysis with:
            - complexity_level: "simple" | "medium" | "complex"
            - reasoning_required: bool
            - recommended_strategy: "direct" | "light_planning" | "deep_reasoning"
            - rationale: Explanation of the assessment
            - estimated_iterations: Suggested iteration count (0-N)
        """
```

**Complexity Levels:**

| Level | Characteristics | Example Queries | Strategy |
|-------|----------------|-----------------|----------|
| **Simple** | - Single, direct question<br>- Answerable with common knowledge<br>- May need 1 tool call<br>- No research needed | "What is Python?", "Calculate 2+2", "Get current time" | Direct AgentLoop (fast-path) |
| **Medium** | - Multi-part but related<br>- Needs 2-3 tool calls<br>- Light planning helps<br>- 1-2 iterations sufficient | "Compare Python and Java performance", "Summarize document and list key points" | Light planning (1-2 iterations) |
| **Complex** | - Multi-step research<br>- Requires synthesis<br>- Multiple information sources<br>- Iterative refinement | "Research competitive landscape for X, analyze trends, and recommend strategy" | Full reasoning (3+ iterations) |

**Input:** User query + context
**Output:** `ComplexityAnalysis` with strategy recommendation

**1. Planner (`planner.py`)**

Generates initial research/action queries from user goal and decomposes complex tasks into subtasks.

```python
class Planner:
    """Strategic query planning and task decomposition.
    
    Responsibilities:
    - Analyze user query for complexity
    - Generate initial research queries
    - Decompose complex tasks into subtasks
    - Prioritize execution order
    
    Pattern inspired by: DeepResearcher.generate_research_queries()
    """
    
    def __init__(self, llm: Claude, config: ReasoningConfig):
        self.llm = llm
        self.config = config
        self.prompt_template = load_prompt("reasoning/planning.txt")
    
    async def generate_plan(
        self, 
        query: str,
        context: Optional[dict] = None
    ) -> ResearchPlan:
        """Generate execution plan for query.
        
        Args:
            query: User's question or goal
            context: Optional context (resources, history, etc.)
            
        Returns:
            ResearchPlan with ordered subtasks/queries
        """
```

**Input:** User query + optional context
**Output:** `ResearchPlan` (list of prioritized queries/actions)

**2. Evaluator (`evaluator.py`)**

Evaluates BOTH research completeness AND response quality (NEW!).

```python
class Evaluator:
    """Dual-purpose evaluation: research completeness + response quality.
    
    Responsibilities:
    1. Research Evaluation (existing):
       - Assess if results answer the query
       - Identify information gaps
       - Generate additional queries for missing info
       
    2. Response Quality Evaluation (NEW - for self-correction):
       - Assess response quality and completeness
       - Determine if escalation needed
       - Identify what's missing or inadequate
    
    Pattern inspired by: DeepResearcher.evaluate_research_completeness()
    """
    
    def __init__(self, llm: Claude, config: ReasoningConfig):
        self.llm = llm
        self.config = config
        self.research_evaluation_prompt = load_prompt("reasoning/evaluation.txt")
        self.quality_evaluation_prompt = load_prompt("reasoning/quality_check.txt")  # NEW
    
    async def evaluate(
        self,
        query: str,
        results: list[dict],
        current_plan: ResearchPlan
    ) -> EvaluationResult:
        """Evaluate if research results are sufficient.
        
        Args:
            query: Original user query
            results: Accumulated results so far
            current_plan: Current execution plan
            
        Returns:
            EvaluationResult with completeness and next actions
        """
    
    async def evaluate_response_quality(
        self,
        query: str,
        response: str,
        strategy_used: str,
        expected_complexity: ComplexityAnalysis
    ) -> EvaluationResult:
        """Evaluate response quality for self-correction (NEW).
        
        This is the key method for self-correction!
        
        Args:
            query: Original user query
            response: Generated response to evaluate
            strategy_used: Which strategy produced this response
            expected_complexity: Initial complexity analysis
            
        Returns:
            EvaluationResult with:
            - is_complete: True if quality sufficient, False if escalation needed
            - confidence: Quality score (0.0 to 1.0)
            - reasoning: Explanation of quality assessment
            - missing_aspects: What's lacking (triggers escalation)
        
        Quality Criteria:
        - Completeness: Does it answer all parts of the query?
        - Accuracy: Is information correct and reliable?
        - Depth: Appropriate detail level for query complexity?
        - Coherence: Well-structured and clear?
        - Relevance: Stays on topic, no tangents?
        """
```

**Input (Research):** Original query + accumulated results + current plan
**Output:** `EvaluationResult` (is_complete: bool, confidence: float, additional_queries: list)

**Input (Quality - NEW):** Query + response + strategy + complexity
**Output:** `EvaluationResult` (is_complete: bool, confidence: float, missing_aspects: list)

**3. Synthesizer (`synthesizer.py`)**

Combines multiple tool results into coherent response with filtering and ranking.

```python
class Synthesizer:
    """Result synthesis and answer generation.
    
    Responsibilities:
    - Filter results by relevance
    - Rank information by importance
    - Combine multiple sources coherently
    - Generate final comprehensive answer
    
    Pattern inspired by: DeepResearcher.filter_results() + generate_research_answer()
    """
    
    def __init__(self, llm: Claude, config: ReasoningConfig):
        self.llm = llm
        self.config = config
        self.filter_prompt = load_prompt("reasoning/filter.txt")
        self.synthesis_prompt = load_prompt("reasoning/synthesis.txt")
    
    async def filter_results(
        self,
        query: str,
        results: list[dict]
    ) -> list[dict]:
        """Filter results by relevance to query."""
    
    async def synthesize(
        self,
        query: str,
        filtered_results: list[dict]
    ) -> str:
        """Generate final answer from filtered results.
        
        Args:
            query: Original user query
            filtered_results: Filtered and ranked results
            
        Returns:
            Final synthesized answer as string
        """
```

**Input:** Query + accumulated results
**Output:** Final synthesized answer (string)

#### Type Definitions (`types.py`)

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class ComplexityLevel(Enum):
    """Query complexity levels."""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"

class ExecutionStrategy(Enum):
    """Recommended execution strategies."""
    DIRECT = "direct"              # Fast-path: direct AgentLoop
    LIGHT_PLANNING = "light_planning"  # 1-2 iterations with minimal planning
    DEEP_REASONING = "deep_reasoning"  # Full reasoning with multiple iterations

@dataclass
class ComplexityAnalysis:
    """Result of query complexity analysis."""
    complexity_level: ComplexityLevel
    reasoning_required: bool
    recommended_strategy: ExecutionStrategy
    rationale: str
    estimated_iterations: int = 1
    confidence: float = 0.0
    
    # Analysis details
    requires_research: bool = False
    requires_synthesis: bool = False
    multi_part_query: bool = False
    tool_count_estimate: int = 0

@dataclass
class SubTask:
    """Individual subtask in a research plan."""
    query: str
    priority: int
    tool_hints: Optional[list[str]] = None
    dependencies: list[str] = field(default_factory=list)

@dataclass
class ResearchPlan:
    """Plan for executing a complex query."""
    original_query: str
    subtasks: list[SubTask]
    max_iterations: int = 3
    estimated_complexity: str = "medium"  # low/medium/high
    complexity_analysis: Optional[ComplexityAnalysis] = None  # NEW: Store original analysis
    
    @property
    def current_step(self) -> Optional[SubTask]:
        """Get next subtask to execute."""
        return self.subtasks[0] if self.subtasks else None

@dataclass
class EvaluationResult:
    """Result of completeness evaluation."""
    is_complete: bool
    confidence: float
    reasoning: str
    additional_queries: list[str] = field(default_factory=list)
    missing_aspects: list[str] = field(default_factory=list)
```

### 1.2 Introduce Self-Correcting Adaptive ReasoningLoop

**New Class:** `src/nxs/application/reasoning_loop.py`

Extends the existing `AgentLoop` to add **adaptive** reasoning with **self-correction**:

#### Critical Design Decision: Streaming vs. Quality Evaluation

**The Challenge**: Quality evaluation happens AFTER execution, but streaming sends responses to users in real-time. How do we reconcile this?

**Chosen Approach: Buffered Evaluation (Quality First)**

```
Flow: Execute → Buffer Response → Evaluate Quality → (Pass: Stream | Fail: Escalate & Retry)
```

**Rationale:**
- **Quality Guarantee**: User never sees low-quality responses
- **Clean UX**: Single, final response (not multiple attempts visible)
- **Trade-off**: Slightly higher latency (~1-2s for evaluation), but consistent quality

**Implementation Strategy:**
1. During execution attempts, disable streaming to user
2. Capture full response in buffer
3. Evaluate buffered response quality
4. If quality sufficient: Stream to user
5. If quality insufficient: Discard buffer, escalate, retry

**Alternative Considered (Transparent Iteration):**
- Stream first response immediately
- Show "Refining answer..." if escalation needed
- Stream revised response
- **Rejected**: More transparent but confusing UX, users see failed attempts

```python
class AdaptiveReasoningLoop(AgentLoop):
    """Self-correcting adaptive agent loop with quality feedback.
    
    Key Innovations:
    1. Automatically analyzes query complexity and adapts execution
    2. ALWAYS evaluates responses - even for "simple" queries
    3. Self-corrects: If simple execution produces poor result, automatically escalates
    4. Guarantees quality: No response sent without passing evaluation
    5. Buffers responses during evaluation (quality-first delivery)
    
    Execution Flow (ALL paths include buffering + evaluation):
    1. DIRECT → Execute & Buffer → Evaluate → (Pass: Stream | Fail: Escalate to LIGHT)
    2. LIGHT → Plan → Execute & Buffer → Evaluate → (Pass: Stream | Fail: Escalate to DEEP)
    3. DEEP → Full reasoning → Buffer → Evaluate → Stream (no further escalation)
    
    Message Management:
    - User query added to conversation once at start
    - Execution attempts buffered (NOT added to conversation)
    - Only final quality-approved response added to conversation
    - Failed attempts logged for debugging but not persisted in conversation
    
    Self-Correction Example:
    - Query: "What is quantum computing?"
    - Initial: Classified as SIMPLE
    - Execute: Quick response via AgentLoop (buffered, not streamed)
    - Evaluate: "Response is superficial, lacks key concepts" (confidence: 0.4)
    - Auto-escalate: Discard buffer, re-execute as LIGHT with research (buffered)
    - Re-evaluate: "Now comprehensive and accurate" (confidence: 0.85)
    - Stream: Final quality-checked response to user
    - Persist: Add approved response to conversation history
    
    This ensures fast execution when possible, but NEVER sacrifices quality.
    Maintains backward compatibility - intelligently adds overhead only when needed.
    """
    
    def __init__(
        self,
        llm: Claude,
        conversation: Conversation,
        tool_registry: ToolRegistry,
        analyzer: QueryComplexityAnalyzer,
        planner: Planner,
        evaluator: Evaluator,
        synthesizer: Synthesizer,
        max_iterations: int = 3,
        callbacks: Optional[dict] = None,
        force_strategy: Optional[ExecutionStrategy] = None  # Override for testing/debugging
    ):
        super().__init__(llm, conversation, tool_registry, callbacks)
        self.analyzer = analyzer
        self.planner = planner
        self.evaluator = evaluator
        self.synthesizer = synthesizer
        self.max_iterations = max_iterations
        self.force_strategy = force_strategy  # None = auto-detect
    
    async def run(
        self,
        query: str,
        use_streaming: bool = True,
        callbacks: Optional[dict[str, Callable]] = None
    ) -> str:
        """Run with adaptive execution strategy based on query complexity.
        
        Self-Correcting Adaptive Process:
        0. Analysis Phase: Determine initial query complexity
        1. Strategy Selection: Choose execution path
        2. Execute: Run chosen strategy
        3. Evaluate: ALWAYS evaluate response quality (NEW!)
        4. Self-Correct: If quality insufficient, escalate and retry (NEW!)
        5. Return: Only return quality-approved responses
        
        ALL execution paths include quality evaluation:
        - DIRECT: Fast execution → Evaluate → (Good: Return | Poor: → LIGHT)
        - LIGHT: Light planning → Evaluate → (Good: Return | Poor: → DEEP)
        - DEEP: Full reasoning → Evaluate → Return (final attempt)
        
        Args:
            query: User's query/message
            use_streaming: Whether to use streaming (default True)
            callbacks: Optional callback overrides
            
        Returns:
            Quality-approved final answer
        """
        callbacks = callbacks or self.callbacks
        
        # Phase 0: COMPLEXITY ANALYSIS (Intelligence Layer)
        logger.info("Phase 0: Analyzing query complexity")
        if "on_analysis" in callbacks:
            await callbacks["on_analysis"]()
        
        # Get available tools for analysis
        tool_names = self.tool_registry.get_tool_names()
        
        # Analyze complexity (can be overridden for testing)
        if self.force_strategy:
            logger.warning(f"Forcing strategy: {self.force_strategy}")
            initial_strategy = self.force_strategy
            complexity = ComplexityAnalysis(
                complexity_level=ComplexityLevel.COMPLEX,
                reasoning_required=True,
                recommended_strategy=self.force_strategy,
                rationale="Forced by configuration",
                estimated_iterations=self.max_iterations
            )
        else:
            complexity = await self.analyzer.analyze(
                query=query,
                available_tools=tool_names,
                conversation_context={}  # Could pass recent messages
            )
            initial_strategy = complexity.recommended_strategy
        
        logger.info(
            f"Initial Complexity Analysis: level={complexity.complexity_level.value}, "
            f"strategy={initial_strategy.value}, "
            f"iterations={complexity.estimated_iterations}"
        )
        
        # Phase 1: ADAPTIVE EXECUTION WITH SELF-CORRECTION
        # Try execution strategies in order: DIRECT → LIGHT → DEEP
        # Escalate automatically if evaluation fails
        
        current_strategy = initial_strategy
        execution_attempts = []
        
        while True:
            logger.info(f"Attempting strategy: {current_strategy.value}")
            
            # Execute with current strategy
            if current_strategy == ExecutionStrategy.DIRECT:
                result = await self._execute_direct(
                    query, complexity, use_streaming, callbacks
                )
                execution_attempts.append(("DIRECT", result))
                
            elif current_strategy == ExecutionStrategy.LIGHT_PLANNING:
                result = await self._execute_light_planning(
                    query, complexity, use_streaming, callbacks
                )
                execution_attempts.append(("LIGHT", result))
                
            else:  # DEEP_REASONING
                result = await self._execute_deep_reasoning(
                    query, complexity, use_streaming, callbacks
                )
                execution_attempts.append(("DEEP", result))
            
            # Phase 2: QUALITY EVALUATION (Always performed!)
            logger.info("Phase 2: Evaluating response quality")
            if "on_quality_check" in callbacks:
                await callbacks["on_quality_check"]()
            
            evaluation = await self._evaluate_response_quality(
                query=query,
                response=result,
                strategy_used=current_strategy,
                complexity=complexity
            )
            
            logger.info(
                f"Quality evaluation: sufficient={evaluation.is_complete}, "
                f"confidence={evaluation.confidence:.2f}"
            )
            
            # Phase 3: SELF-CORRECTION DECISION
            if evaluation.is_complete or current_strategy == ExecutionStrategy.DEEP_REASONING:
                # Either quality is good, or we've tried the deepest strategy
                logger.info(
                    f"Returning response: strategy={current_strategy.value}, "
                    f"attempts={len(execution_attempts)}, "
                    f"quality={evaluation.confidence:.2f}"
                )
                
                if "on_final_response" in callbacks:
                    await callbacks["on_final_response"](
                        result, current_strategy, execution_attempts
                    )
                
                return result
            
            # Quality insufficient - escalate!
            logger.warning(
                f"Response quality insufficient ({evaluation.confidence:.2f}), "
                f"escalating from {current_strategy.value}"
            )
            
            if "on_auto_escalation" in callbacks:
                await callbacks["on_auto_escalation"](
                    current_strategy, evaluation
                )
            
            # Escalate to next strategy level
            if current_strategy == ExecutionStrategy.DIRECT:
                current_strategy = ExecutionStrategy.LIGHT_PLANNING
                logger.info("Auto-escalating: DIRECT → LIGHT_PLANNING")
            elif current_strategy == ExecutionStrategy.LIGHT_PLANNING:
                current_strategy = ExecutionStrategy.DEEP_REASONING
                logger.info("Auto-escalating: LIGHT_PLANNING → DEEP_REASONING")
            else:
                # Already at DEEP, shouldn't reach here due to check above
                break
    
    async def _execute_direct(
        self,
        query: str,
        complexity: ComplexityAnalysis,
        use_streaming: bool,
        callbacks: dict
    ) -> str:
        """Execute with direct strategy (fast-path).
        
        Fast execution:
        - No planning overhead
        - Direct AgentLoop execution
        - Good for simple, straightforward queries
        """
        logger.info("Direct execution (fast-path)")
        if "on_direct_execution" in callbacks:
            await callbacks["on_direct_execution"]()
        
        # Just run the base AgentLoop - minimal overhead
        result = await super().run(
            query=query,
            use_streaming=use_streaming,
            callbacks=callbacks
        )
        
        logger.info(f"Direct execution complete: {len(result)} chars")
        return result
        
    
    async def _execute_light_planning(
        self,
        query: str,
        complexity: ComplexityAnalysis,
        use_streaming: bool,
        callbacks: dict
    ) -> str:
        """Execute with light planning (1-2 iterations, minimal overhead).
        
        Light planning:
        - Quick analysis of query parts
        - Execute 1-2 steps
        - No deep evaluation/synthesis
        - Good for medium-complexity queries
        """
        logger.info("Light planning execution")
        if "on_light_planning" in callbacks:
            await callbacks["on_light_planning"]()
        
        # Create a simplified plan (fewer subtasks, less detail)
        plan = await self.planner.generate_plan(
            query,
            context={"complexity": complexity, "mode": "light"}
        )
        
        # Limit iterations for light planning
        max_iters = min(2, complexity.estimated_iterations)
        
        accumulated_results = []
        
        for iteration in range(max_iters):
            if not plan.current_step:
                break
            
            logger.debug(f"Light iteration {iteration + 1}/{max_iters}")
            
            result = await super().run(
                query=plan.current_step.query,
                use_streaming=use_streaming,
                callbacks=callbacks
            )
            
            accumulated_results.append({
                "query": plan.current_step.query,
                "result": result,
                "iteration": iteration
            })
            
            plan.subtasks.pop(0)
        
        # Simple synthesis (no filtering, just combine)
        if len(accumulated_results) == 1:
            return accumulated_results[0]["result"]
        else:
            # Quick synthesis without filtering
            return await self.synthesizer.synthesize(
                query, accumulated_results
            )
    
    async def _execute_deep_reasoning(
        self,
        query: str,
        complexity: ComplexityAnalysis,
        use_streaming: bool,
        callbacks: dict
    ) -> str:
        """Execute with full reasoning cycle (original ReasoningLoop logic).
        
        Deep reasoning:
        - Full planning phase
        - Iterative execution with evaluation
        - Gap identification and additional queries
        - Result filtering and synthesis
        - Good for complex research queries
        """
        logger.info("Deep reasoning execution")
        
        # Phase 1: Planning (full detail)
        logger.info(f"Phase 1: Planning for query: {query[:100]}")
        if "on_planning" in callbacks:
            await callbacks["on_planning"]()
        
        plan = await self.planner.generate_plan(
            query,
            context={"complexity": complexity, "mode": "deep"}
        )
        plan.complexity_analysis = complexity
        logger.info(f"Generated plan with {len(plan.subtasks)} subtasks")
        
        # Phase 2: Iterative execution and evaluation
        accumulated_results = []
        executed_queries = []
        
        for iteration in range(self.max_iterations):
            logger.info(f"Phase 2: Iteration {iteration + 1}/{self.max_iterations}")
            
            if "on_iteration" in callbacks:
                await callbacks["on_iteration"](iteration, self.max_iterations)
            
            # Execute current subtask via parent AgentLoop
            if plan.current_step:
                logger.debug(f"Executing subtask: {plan.current_step.query}")
                
                # Use parent's run() to execute subtask with tools
                result = await super().run(
                    query=plan.current_step.query,
                    use_streaming=use_streaming,
                    callbacks=callbacks
                )
                
                accumulated_results.append({
                    "query": plan.current_step.query,
                    "result": result,
                    "iteration": iteration
                })
                executed_queries.append(plan.current_step.query)
                
                # Move to next subtask
                plan.subtasks.pop(0)
            
            # Phase 3: Evaluation
            logger.info("Phase 3: Evaluating completeness")
            if "on_evaluation" in callbacks:
                await callbacks["on_evaluation"]()
            
            evaluation = await self.evaluator.evaluate(
                query=query,
                results=accumulated_results,
                current_plan=plan
            )
            
            logger.info(
                f"Evaluation: complete={evaluation.is_complete}, "
                f"confidence={evaluation.confidence:.2f}"
            )
            
            # Check if we're done
            if evaluation.is_complete:
                logger.info("Query fully answered, proceeding to synthesis")
                break
            
            # Phase 4: Plan adjustment if needed
            if evaluation.additional_queries and iteration < self.max_iterations - 1:
                logger.info(
                    f"Adding {len(evaluation.additional_queries)} additional queries"
                )
                for additional_query in evaluation.additional_queries:
                    if additional_query not in executed_queries:
                        plan.subtasks.append(
                            SubTask(
                                query=additional_query,
                                priority=1
                            )
                        )
        
        # Phase 5: Synthesis
        logger.info("Phase 5: Synthesizing final answer")
        if "on_synthesis" in callbacks:
            await callbacks["on_synthesis"]()
        
        # Filter results first
        filtered_results = await self.synthesizer.filter_results(
            query, accumulated_results
        )
        
        # Generate final answer
        final_answer = await self.synthesizer.synthesize(
            query, filtered_results
        )
        
        logger.info(f"Deep reasoning complete: {len(final_answer)} chars generated")
        
        return final_answer
    
    async def _evaluate_response_quality(
        self,
        query: str,
        response: str,
        strategy_used: ExecutionStrategy,
        complexity: ComplexityAnalysis
    ) -> EvaluationResult:
        """Evaluate response quality to determine if escalation needed.
        
        Quality criteria:
        - Completeness: Does it fully answer the query?
        - Accuracy: Is the information correct?
        - Depth: Is it detailed enough for the question?
        - Coherence: Is it well-structured and clear?
        
        Returns EvaluationResult with:
        - is_complete: True if quality is sufficient
        - confidence: Quality score (0.0 to 1.0)
        - reasoning: Explanation of quality assessment
        - missing_aspects: What's lacking (if insufficient)
        """
        logger.debug(
            f"Evaluating response quality: strategy={strategy_used.value}, "
            f"response_length={len(response)}"
        )
        
        # Use evaluator to assess response quality
        # This is similar to completeness evaluation but focused on response quality
        evaluation = await self.evaluator.evaluate_response_quality(
            query=query,
            response=response,
            strategy_used=strategy_used.value,
            expected_complexity=complexity
        )
        
        # Apply minimum confidence threshold based on strategy
        # Higher strategies require higher confidence to avoid escalation
        min_confidence_thresholds = {
            ExecutionStrategy.DIRECT: 0.6,        # Lenient - allow escalation
            ExecutionStrategy.LIGHT_PLANNING: 0.7,  # Moderate
            ExecutionStrategy.DEEP_REASONING: 0.5,  # Accept lower - final attempt
        }
        
        min_confidence = min_confidence_thresholds.get(
            strategy_used, 
            self.config.min_confidence
        )
        
        # Override is_complete based on confidence threshold
        if evaluation.confidence < min_confidence:
            evaluation.is_complete = False
            logger.debug(
                f"Quality below threshold: {evaluation.confidence:.2f} < {min_confidence}"
            )
        
        return evaluation
```

**Key Design Decisions:**
- **Self-correcting**: ALWAYS evaluates responses, auto-escalates if quality insufficient
- **Quality guarantee**: No response sent without passing evaluation
- **Adaptive intelligence**: Automatically analyzes complexity and routes appropriately
- **Three execution paths**: Direct (fast), Light (balanced), Deep (thorough)
- **Fast but never sloppy**: Tries fast path first, but escalates automatically if needed
- **Graceful scaling**: Adds complexity only when needed
- **Override capability**: `force_strategy` for testing/debugging
- Extends `AgentLoop` rather than replacing it (backward compatibility)
- Composition over inheritance: Uses Analyzer/Planner/Evaluator/Synthesizer as dependencies
- Preserves streaming via callbacks (callback for each phase + escalation callbacks)
- Works with existing Conversation and ToolRegistry
- Delegates tool execution to parent `AgentLoop.run()`

**Performance Characteristics (with self-correction):**

| Strategy | Typical Latency | Escalation Rate | Final Quality |
|----------|-----------------|-----------------|---------------|
| DIRECT | ~1-3s | ~10-15% → LIGHT | Good when sufficient |
| LIGHT_PLANNING | ~5-10s | ~5-10% → DEEP | High quality |
| DEEP_REASONING | ~15-30s | N/A (final) | Highest quality |

**Self-Correction Examples:**

| Query | Initial | Evaluation | Escalation | Final |
|-------|---------|------------|------------|-------|
| "What is Python?" | DIRECT → Basic answer | "Too superficial" | → LIGHT | Comprehensive answer |
| "Compare X and Y" | LIGHT → Basic comparison | "Missing key aspects" | → DEEP | Deep analysis |
| "2+2?" | DIRECT → "4" | "Complete" | None | "4" (fast) |

**Key Insight:**
The system is optimistic (tries fast path) but never naive (always validates).
This ensures we're fast when we can be, thorough when we need to be.

### 1.3 Simplify CommandControlAgent Architecture

**Major Simplification:** `src/nxs/application/command_control.py`

**KEY CHANGE**: CommandControlAgent NO LONGER extends AgentLoop - uses AdaptiveReasoningLoop directly!

```python
class CommandControlAgent:  # NO LONGER extends AgentLoop!
    """Command control with adaptive reasoning capabilities.
    
    ARCHITECTURE CHANGE: No longer extends AgentLoop - composition over inheritance!
    
    Simplification:
    - AdaptiveReasoningLoop handles ALL execution (no dual paths)
    - CommandControlAgent focuses on preprocessing only:
      * Resource extraction via @mentions
      * Command prompt processing via /commands
    - Cleaner separation of concerns
    
    Intelligence (delegated to AdaptiveReasoningLoop):
    - Automatically analyzes query complexity
    - Routes to appropriate execution strategy
    - Self-corrects via quality evaluation
    - No manual configuration required
    
    Why this is better:
    - Simpler architecture (one execution path)
    - All queries benefit from self-correction
    - Easier to maintain and test
    - No "emergency fallback" needed - AdaptiveReasoningLoop IS the path
    """
    
    def __init__(
        self,
        artifact_manager: ArtifactManager,
        claude_service: Claude,
        callbacks=None,
        reasoning_config: Optional[ReasoningConfig] = None,
    ):
        # Store dependencies
        self.artifact_manager = artifact_manager
        self.claude = claude_service
        self.callbacks = callbacks or {}
        self.argument_parser = CompositeArgumentParser()
        
        # Create dependencies from artifact manager
        clients = artifact_manager.clients
        conversation = Conversation(enable_caching=True)
        tool_registry = ToolRegistry(enable_caching=True)
        
        from nxs.application.mcp_tool_provider import MCPToolProvider
        mcp_provider = MCPToolProvider(clients)
        tool_registry.register_provider(mcp_provider)
        
        # Initialize reasoning components
        from nxs.application.reasoning.analyzer import QueryComplexityAnalyzer
        from nxs.application.reasoning.planner import Planner
        from nxs.application.reasoning.evaluator import Evaluator
        from nxs.application.reasoning.synthesizer import Synthesizer
        from nxs.application.reasoning_loop import AdaptiveReasoningLoop
        
        config = reasoning_config or ReasoningConfig()
        
        # Initialize all reasoning components
        analyzer = QueryComplexityAnalyzer(claude_service, config)
        planner = Planner(claude_service, config)
        evaluator = Evaluator(claude_service, config)
        synthesizer = Synthesizer(claude_service, config)
        
        # Create adaptive reasoning loop (THE ONLY execution path)
        self.adaptive_loop = AdaptiveReasoningLoop(
            llm=claude_service,
            conversation=conversation,
            tool_registry=tool_registry,
            analyzer=analyzer,
            planner=planner,
            evaluator=evaluator,
            synthesizer=synthesizer,
            max_iterations=config.max_iterations,
            callbacks=callbacks,
            force_strategy=config.force_strategy  # From config
        )
        
        logger.info(
            "CommandControlAgent initialized with self-correcting "
            "adaptive reasoning (single execution path)"
        )
    
    async def run(
        self,
        query: str,
        use_streaming: bool = True,
        callbacks: Optional[dict] = None
    ) -> str:
        """Run with self-correcting adaptive execution.
        
        Simplified Process:
        1. Pre-process query (extract resources, handle commands)
        2. Delegate to AdaptiveReasoningLoop (handles everything):
           a. Analyzes complexity
           b. Selects initial strategy
           c. Executes
           d. Evaluates response quality
           e. Auto-escalates if quality insufficient
           f. Returns quality-approved response
        
        Architecture: Composition over inheritance!
        CommandControlAgent = Preprocessor + AdaptiveReasoningLoop
        """
        # Pre-processing (existing logic - resources, commands)
        processed_query = await self._preprocess_query(query)
        
        # Special case: command processing returned empty
        # (command was processed, messages already added to conversation)
        if not processed_query:
            logger.debug("Command processed, returning empty response")
            return ""
        
        # Delegate ALL execution to adaptive loop
        # It handles: analysis, execution, evaluation, escalation, quality control
        logger.debug("Delegating to self-correcting adaptive reasoning loop")
        return await self.adaptive_loop.run(
            processed_query,
            use_streaming=use_streaming,
            callbacks=callbacks or self.callbacks
        )
    
    async def _preprocess_query(self, query: str) -> str:
        """Pre-process query with resource extraction and command handling.
        
        Existing functionality:
        - Extract @resource mentions
        - Process /command prompts
        - Enrich query with context
        """
        # Check for commands first
        is_command = await self._process_command(query)
        if is_command:
            # Command was processed, return special marker
            # (The command already added messages to conversation)
            return ""
        
        # Extract resources
        resource_context = await self._extract_resources(query)
        
        if resource_context:
            # Enrich query with resource context
            enriched_query = f"""
The user has a question:
<query>
{query}
</query>

The following context may be useful in answering their question:
<context>
{resource_context}
</context>

Note the user's query might contain references to documents like "@report.docx". The "@" is only
included as a way of mentioning the doc. The actual name of the document would be "report.docx".
If the document content is included in this prompt, you don't need to use an additional tool to read the document.
Answer the user's question directly and concisely. Start with the exact information they need.
Don't refer to or mention the provided context in any way - just use it to inform your answer.
"""
            return enriched_query
        
        return query
    
    # Keep existing preprocessing methods: _extract_resources, _process_command
    # These are unchanged and handle resource/command extraction
    # (Implementation details omitted for brevity)
```

**Architecture Benefits:**

1. **Simpler**: One execution path (AdaptiveReasoningLoop), not two (AgentLoop + AdaptiveReasoningLoop)
2. **Clearer**: CommandControlAgent = Preprocessing only
3. **More robust**: ALL queries benefit from self-correction
4. **Easier to test**: No inheritance hierarchy, just composition
5. **Better separation**: Preprocessing vs execution logic cleanly separated

**Code Comparison:**

```python
# OLD (inheritance, dual paths):
class CommandControlAgent(AgentLoop):
    def run(query):
        if force_simple:
            return super().run(query)  # AgentLoop
        else:
            return self.adaptive_loop.run(query)  # AdaptiveReasoningLoop

# NEW (composition, single path):
class CommandControlAgent:
    def run(query):
        preprocessed = self._preprocess_query(query)
        return self.adaptive_loop.run(preprocessed)  # Always adaptive!
```

### 1.4 TUI Integration & Reasoning Visibility

**Objective**: Provide real-time feedback to users about reasoning mode, strategy, and progress without overwhelming the status panel.

#### Architecture Decision: Collapsible Reasoning Trace Panel

**Problem**: Deep reasoning can generate many events (analysis, planning, tool calls, evaluations, escalations). Showing all of these in the main StatusPanel would:
- Overwhelm users with too much detail
- Make the panel scroll excessively
- Mix reasoning details with general app events
- Create visual noise

**Solution**: Introduce a separate, collapsible `ReasoningTracePanel` for detailed reasoning traces.

**Design Principles:**
1. **Progressive Disclosure**: Collapsed by default, expandable on demand
2. **Visual Notification**: Indicator shows when reasoning is active
3. **Separation of Concerns**: 
   - StatusPanel = High-level app events (mode changes, completion)
   - ReasoningTracePanel = Detailed reasoning trace (steps, tool calls, evaluations)
4. **Persistent State**: Can stay open across queries for debugging/learning
5. **Non-intrusive**: Doesn't block chat or require modal interaction

**Updated Layout:**

```
┌─────────────────────────────┬──────────┐
│         Header              │          │
├─────────────────────────────┼──────────┤
│                             │          │
│      Chat Panel             │   MCP    │
│     (scrollable)            │  Panel   │
│                             │          │
├─────────────────────────────┤          │
│    Status Panel             │          │
│  (high-level events)        │          │
├─────────────────────────────┤          │
│ [▼ Reasoning Trace] 🔔      │          │  ← Collapsible header (NEW)
├─────────────────────────────┤          │
│  Reasoning Trace Panel      │          │  ← NEW: Detailed trace (expanded)
│  (phases, steps, tools)     │          │
├─────────────────────────────┤          │
│      Input Field            │          │
├─────────────────────────────┼──────────┤
│         Footer              │          │
└─────────────────────────────┴──────────┘
```

**States:**

| State | Header | Behavior |
|-------|--------|----------|
| **Collapsed (Idle)** | `[▶ Reasoning Trace]` | No space used, click to expand |
| **Collapsed (Active)** | `[▶ Reasoning Trace] 🔔 Active` | Indicator pulses, shows activity |
| **Expanded** | `[▼ Reasoning Trace] 🔔` | Shows full trace, scrollable |

**Keyboard Shortcuts:**
- `Ctrl+R`: Toggle reasoning trace panel
- `Ctrl+Shift+R`: Clear reasoning trace

**User Experience Flow:**

```
User: "Explain quantum computing"
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status Panel (visible):
  🎯 Reasoning mode: Direct
  
Reasoning Trace Header:
  [▶ Reasoning Trace] 🔔 Active  ← Indicator shows activity
  
[User can click to expand or press Ctrl+R]

━━━━━━━━━━━━━━━━━━━━━━━━━━━
If user expands, Reasoning Trace Panel shows:

  ━━━ Phase 0: Complexity Analysis ━━━
  ⚡ Analyzing query complexity...
  ✓ Complexity: SIMPLE → Strategy: DIRECT
  
  ━━━ Phase 1: Execution (DIRECT) ━━━
  ⚡ Executing query (fast path)...
  
  ━━━ Phase 2: Quality Evaluation ━━━
  🔍 Checking response quality...
  Quality: 0.45 - Insufficient (lacks depth)
  Missing: Technical principles, applications
  
  ━━━ Phase 3: Auto-Escalation ━━━
  ⚠️ Escalating: DIRECT → LIGHT
  Reason: Response too superficial for question
  
  ━━━ Phase 1: Execution (LIGHT) ━━━
  📋 Light Planning...
    • Subtask 1: Define quantum computing
    • Subtask 2: List key applications
  
  🔧 Iteration 1/2
  Query: "Define quantum computing fundamentals"
  
  ━━━ Phase 2: Quality Evaluation ━━━
  🔍 Checking response quality...
  ✓ Quality: 0.88 - Sufficient
  
  ━━━ Complete ━━━
  ✅ Final Strategy: LIGHT
  📊 Attempts: 2 (DIRECT → LIGHT)
  ⭐ Quality: 0.88
```

#### Callback Interface for Reasoning Events

**Callback Routing Strategy:**

All reasoning callbacks now route to **ReasoningTracePanel** for detailed logging, while **StatusPanel** only receives high-level summaries.

**New Callbacks for AdaptiveReasoningLoop:**

```python
# Comprehensive callback interface for TUI integration
reasoning_callbacks = {
    # Phase 0: Complexity Analysis
    "on_analysis_start": async () -> None,
        # → StatusPanel: "🎯 Analyzing query..."
        # → ReasoningTracePanel: "━━━ Phase 0: Complexity Analysis ━━━\n⚡ Analyzing query complexity..."
        # → Header subtitle: "Analyzing..."
        # → Trace indicator: Activate
    
    "on_analysis_complete": async (complexity: ComplexityAnalysis) -> None,
        # → StatusPanel: (none - keep clean)
        # → ReasoningTracePanel: "✓ Complexity: {level} → Strategy: {strategy}\n  Confidence: {confidence}, Est. iterations: {est}"
    
    # Phase 1: Strategy Execution
    "on_strategy_selected": async (strategy: ExecutionStrategy, rationale: str) -> None,
        # → StatusPanel: "🎯 Mode: {strategy.value.title()}"
        # → ReasoningTracePanel: "━━━ Phase 1: Execution ({strategy}) ━━━\n{rationale}"
        # → Header subtitle: "Mode: {strategy}"
    
    "on_direct_execution": async () -> None,
        # → StatusPanel: (none)
        # → ReasoningTracePanel: "⚡ Executing query (fast path)..."
    
    "on_light_planning": async () -> None,
        # → StatusPanel: (none)
        # → ReasoningTracePanel: "📋 Light planning (1-2 iterations)..."
    
    "on_deep_reasoning": async () -> None,
        # → StatusPanel: (none)
        # → ReasoningTracePanel: "🔬 Deep reasoning (full analysis)..."
    
    # Phase 2: Quality Evaluation
    "on_quality_check_start": async () -> None,
        # → StatusPanel: (none)
        # → ReasoningTracePanel: "━━━ Phase 2: Quality Evaluation ━━━\n🔍 Checking response quality..."
    
    "on_quality_check_complete": async (evaluation: EvaluationResult) -> None,
        # → StatusPanel: (none)
        # → ReasoningTracePanel: "Quality: {confidence:.2f} - {sufficient/insufficient}\n{reasoning}"
    
    # Phase 3: Auto-Escalation
    "on_auto_escalation": async (
        from_strategy: ExecutionStrategy,
        to_strategy: ExecutionStrategy,
        reason: str,
        confidence: float
    ) -> None,
        # → StatusPanel: "⚠️ Refining response..." (brief)
        # → ReasoningTracePanel: "━━━ Phase 3: Auto-Escalation ━━━\n⚠️ Escalating: {from} → {to}\nReason: {reason}\nQuality: {confidence:.2f}"
    
    # Progress Updates (Deep Reasoning only)
    "on_iteration": async (current: int, total: int, subtask: str) -> None,
        # → StatusPanel: (none)
        # → ReasoningTracePanel: "🔧 Iteration {current}/{total}\nQuery: {subtask}"
    
    "on_planning_complete": async (plan: ResearchPlan) -> None,
        # → StatusPanel: (none)
        # → ReasoningTracePanel: "📋 Plan generated:\n  • {subtask1}\n  • {subtask2}..."
    
    # Tool execution (routed to ReasoningTracePanel instead of StatusPanel)
    "on_tool_call": async (name: str, params: dict) -> None,
        # → StatusPanel: (none - keep clean)
        # → ReasoningTracePanel: "🔧 Tool: {name}\n  Params: {params_summary}"
    
    "on_tool_result": async (name: str, result: Any) -> None,
        # → StatusPanel: (none)
        # → ReasoningTracePanel: "  └─ Result: {result_summary}"
    
    # Final Result
    "on_final_response": async (
        final_strategy: ExecutionStrategy,
        attempt_count: int,
        final_quality: float,
        escalated: bool
    ) -> None,
        # → StatusPanel: "✅ Query complete"
        # → ReasoningTracePanel: "━━━ Complete ━━━\n✅ Strategy: {strategy}\n📊 Attempts: {count}\n⭐ Quality: {quality:.2f}"
        # → Header subtitle: "Ready"
        # → Trace indicator: Deactivate (but keep expanded if user opened it)
    
    # Streaming (to chat panel, not affected)
    "on_stream_chunk": async (chunk: str) -> None,
        # → ChatPanel: (unchanged)
}
```

#### TUI Implementation Changes

**1. New Widget: ReasoningTracePanel** (`src/nxs/presentation/widgets/reasoning_trace_panel.py`):

```python
from textual.widgets import RichLog, Static
from textual.containers import Container
from rich.panel import Panel
from rich.text import Text

class ReasoningTracePanel(RichLog):
    """Collapsible panel for detailed reasoning trace logging.
    
    Features:
    - Hierarchical display of reasoning phases
    - Auto-scrolling to latest event
    - Visual separation between phases
    - Tool call nesting display
    - Expandable/collapsible
    """
    
    BORDER_TITLE = "Reasoning Trace"
    
    def __init__(self, **kwargs):
        """Initialize with collapsed state."""
        super().__init__(
            markup=True,
            highlight=True,
            auto_scroll=True,
            wrap=True,
            **kwargs
        )
        self.is_active = False  # Tracks if reasoning is currently happening
    
    def start_phase(self, phase_name: str, phase_number: int):
        """Start a new reasoning phase with visual separator.
        
        Args:
            phase_name: Name of the phase (e.g., "Complexity Analysis")
            phase_number: Phase number (0, 1, 2, 3)
        """
        self.write("\n")
        separator = f"━━━ Phase {phase_number}: {phase_name} ━━━"
        self.write(f"[bold cyan]{separator}[/]\n")
        self.is_active = True
    
    def log_event(self, icon: str, message: str, indent: int = 0):
        """Log a reasoning event with optional indentation.
        
        Args:
            icon: Emoji or symbol for the event
            message: Event description
            indent: Indentation level (for nesting)
        """
        indent_str = "  " * indent
        self.write(f"{indent_str}{icon} {message}\n")
    
    def log_tool_call(self, tool_name: str, params_summary: str):
        """Log a tool call with nesting."""
        self.write(f"🔧 Tool: [bold]{tool_name}[/]\n")
        self.write(f"  Params: {params_summary}\n")
    
    def log_tool_result(self, result_summary: str):
        """Log tool result (nested under tool call)."""
        self.write(f"  └─ Result: {result_summary}\n")
    
    def log_plan(self, subtasks: list[str]):
        """Log a generated plan with subtasks."""
        self.write("📋 Plan generated:\n")
        for i, subtask in enumerate(subtasks, 1):
            self.write(f"  {i}. {subtask}\n")
    
    def log_quality_check(self, confidence: float, is_sufficient: bool, reasoning: str):
        """Log quality evaluation results."""
        status = "Sufficient" if is_sufficient else "Insufficient"
        color = "green" if is_sufficient else "yellow"
        
        self.write(f"Quality: [{color}]{confidence:.2f} - {status}[/]\n")
        if reasoning:
            self.write(f"[dim]{reasoning}[/]\n")
    
    def log_escalation(self, from_strategy: str, to_strategy: str, reason: str, confidence: float):
        """Log auto-escalation event."""
        self.write(f"[bold yellow]⚠️ Escalating:[/] {from_strategy} → {to_strategy}\n")
        self.write(f"[dim]Reason: {reason}[/]\n")
        self.write(f"[dim]Quality: {confidence:.2f}[/]\n")
    
    def complete_reasoning(self, strategy: str, attempts: int, quality: float):
        """Mark reasoning as complete with summary."""
        self.write("\n")
        self.write("[bold cyan]━━━ Complete ━━━[/]\n")
        self.write(f"✅ Final Strategy: [bold]{strategy}[/]\n")
        self.write(f"📊 Attempts: {attempts}\n")
        self.write(f"⭐ Quality: {quality:.2f}\n")
        self.is_active = False


class ReasoningTraceHeader(Static):
    """Collapsible header for reasoning trace panel.
    
    Shows:
    - Expand/collapse indicator (▶/▼)
    - Activity indicator (🔔 when active)
    - Click to toggle
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.collapsed = True
        self.active = False
    
    def render(self) -> Text:
        """Render header with current state."""
        indicator = "▶" if self.collapsed else "▼"
        activity = " 🔔 Active" if self.active else ""
        
        return Text.from_markup(
            f"[bold cyan]{indicator} Reasoning Trace[/]{activity}"
        )
    
    def toggle(self):
        """Toggle collapsed state."""
        self.collapsed = not self.collapsed
        self.refresh()
    
    def set_active(self, active: bool):
        """Set activity state."""
        self.active = active
        self.refresh()


class CollapsibleReasoningTrace(Container):
    """Container that combines header and panel for collapsible behavior."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.header = ReasoningTraceHeader()
        self.panel = ReasoningTracePanel()
        self.panel.display = False  # Start collapsed
    
    def compose(self):
        """Compose header and panel."""
        yield self.header
        yield self.panel
    
    def on_click(self, event):
        """Handle click to toggle."""
        if event.widget == self.header:
            self.toggle()
    
    def toggle(self):
        """Toggle panel visibility."""
        self.header.toggle()
        self.panel.display = not self.header.collapsed
        self.refresh(layout=True)
    
    def set_active(self, active: bool):
        """Set activity indicator."""
        self.header.set_active(active)
```

**2. Simplified StatusPanel** (`src/nxs/presentation/widgets/status_panel.py`):

Now only handles high-level application events, not detailed reasoning:

```python
class StatusPanel(RichLog):
    """Simplified status panel for high-level application events only.
    
    Reasoning details are now handled by ReasoningTracePanel.
    This keeps the status panel clean and focused.
    """
    
    BORDER_TITLE = "Status"
    
    def __init__(self, **kwargs):
        """Initialize the status panel."""
        super().__init__(markup=True, highlight=True, auto_scroll=True, wrap=True, **kwargs)
        self.write("[bold yellow]Application Status[/]\n")
        self.add_divider()
    
    def update_mode(self, mode: str):
        """Display current reasoning mode (high-level only).
        
        Args:
            mode: "Analyzing" | "Direct" | "Light Reasoning" | "Deep Reasoning" | "Refining" | "Complete"
        """
        mode_icons = {
            "Analyzing": "⚡",
            "Direct": "🎯",
            "Light Reasoning": "🧠",
            "Deep Reasoning": "🔬",
            "Refining": "⚠️",
            "Complete": "✅",
        }
        icon = mode_icons.get(mode, "•")
        self.write(f"{icon} Mode: [bold]{mode}[/]\n")
    
    def log_completion(self):
        """Log query completion."""
        self.write("✅ Query complete\n")
        self.add_divider()
    
    # Keep existing tool display methods for non-reasoning tool calls
    # (e.g., MCP server operations, file operations, etc.)
```

**3. Update NexusApp** (`src/nxs/presentation/tui/nexus_app.py`):

Integrate the new `CollapsibleReasoningTrace` widget:

```python
from nxs.presentation.widgets.reasoning_trace_panel import CollapsibleReasoningTrace

class NexusApp(App):
    """Main TUI application with reasoning trace panel."""
    
    # Bindings - add new shortcut for reasoning trace
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True, show=False),
        Binding("tab", "focus_next", "Next Field", show=False),
        Binding("shift+tab", "focus_previous", "Previous Field", show=False),
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
        Binding("ctrl+r", "toggle_reasoning_trace", "Toggle Reasoning Trace"),  # NEW
        Binding("ctrl+shift+r", "clear_reasoning_trace", "Clear Reasoning Trace"),  # NEW
    ]
    
    current_reasoning_mode: str = "Ready"
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        
        with Horizontal():
            # Left side: Main content
            with Vertical(id="main-content"):
                yield ChatPanel()
                yield StatusPanel()
                yield CollapsibleReasoningTrace()  # NEW: Collapsible reasoning trace
                yield NexusInput()
            
            # Right side: MCP panel
            yield MCPPanel()
        
        yield Footer()
    
    def action_toggle_reasoning_trace(self):
        """Toggle reasoning trace panel (Ctrl+R)."""
        trace = self.query_one(CollapsibleReasoningTrace)
        trace.toggle()
    
    def action_clear_reasoning_trace(self):
        """Clear reasoning trace panel (Ctrl+Shift+R)."""
        trace = self.query_one(CollapsibleReasoningTrace)
        trace.panel.clear()
    
    def update_reasoning_mode_display(self, mode: str):
        """Update header subtitle to show current reasoning mode."""
        self.current_reasoning_mode = mode
        self.sub_title = f"AI Chat | Mode: {mode}"
        self.refresh()
    
    def setup_reasoning_callbacks(self) -> dict:
        """Create callback dictionary for reasoning events.
        
        Routes callbacks to appropriate widgets:
        - StatusPanel: High-level summaries only
        - ReasoningTracePanel: Detailed trace logging
        """
        status_panel = self.query_one(StatusPanel)
        reasoning_trace = self.query_one(CollapsibleReasoningTrace)
        trace_panel = reasoning_trace.panel
        
        return {
            # Phase 0: Complexity Analysis
            "on_analysis_start": lambda: (
                status_panel.update_mode("Analyzing"),
                trace_panel.start_phase("Complexity Analysis", 0),
                trace_panel.log_event("⚡", "Analyzing query complexity..."),
                reasoning_trace.set_active(True),
                self.update_reasoning_mode_display("Analyzing")
            ),
            
            "on_analysis_complete": lambda complexity: (
                trace_panel.log_event(
                    "✓",
                    f"Complexity: {complexity.complexity_level.value.upper()} → "
                    f"Strategy: {complexity.recommended_strategy.value}"
                ),
                trace_panel.log_event(
                    "  ",
                    f"Confidence: {complexity.confidence:.2f}, "
                    f"Est. iterations: {complexity.estimated_iterations}",
                    indent=1
                )
            ),
            
            # Phase 1: Strategy Execution
            "on_strategy_selected": lambda strategy, rationale: (
                status_panel.update_mode(strategy.value.replace("_", " ").title()),
                trace_panel.start_phase(f"Execution ({strategy.value.upper()})", 1),
                trace_panel.log_event("📋", rationale if rationale else f"Strategy: {strategy.value}"),
                self.update_reasoning_mode_display(strategy.value.replace("_", " ").title())
            ),
            
            "on_direct_execution": lambda: trace_panel.log_event("⚡", "Executing query (fast path)..."),
            "on_light_planning": lambda: trace_panel.log_event("📋", "Light planning (1-2 iterations)..."),
            "on_deep_reasoning": lambda: trace_panel.log_event("🔬", "Deep reasoning (full analysis)..."),
            
            "on_planning_complete": lambda plan: trace_panel.log_plan(
                [f"{task.query}" for task in plan.subtasks]
            ),
            
            # Progress Updates
            "on_iteration": lambda current, total, subtask: (
                trace_panel.log_event("🔧", f"Iteration {current}/{total}"),
                trace_panel.log_event("", f"Query: {subtask}", indent=1)
            ),
            
            # Tool Calls (now routed to trace panel, not status panel)
            "on_tool_call": lambda name, params: trace_panel.log_tool_call(
                name,
                str(params)[:100] + "..." if len(str(params)) > 100 else str(params)
            ),
            
            "on_tool_result": lambda name, result: trace_panel.log_tool_result(
                str(result)[:100] + "..." if len(str(result)) > 100 else str(result)
            ),
            
            # Phase 2: Quality Evaluation
            "on_quality_check_start": lambda: (
                trace_panel.start_phase("Quality Evaluation", 2),
                trace_panel.log_event("🔍", "Checking response quality...")
            ),
            
            "on_quality_check_complete": lambda evaluation: trace_panel.log_quality_check(
                evaluation.confidence,
                evaluation.is_complete,
                evaluation.reasoning
            ),
            
            # Phase 3: Auto-Escalation
            "on_auto_escalation": lambda from_s, to_s, reason, conf: (
                status_panel.update_mode("Refining"),
                trace_panel.start_phase("Auto-Escalation", 3),
                trace_panel.log_escalation(
                    from_s.value,
                    to_s.value,
                    reason,
                    conf
                )
            ),
            
            # Final Result
            "on_final_response": lambda strategy, attempts, quality, escalated: (
                status_panel.log_completion(),
                trace_panel.complete_reasoning(strategy.value, attempts, quality),
                reasoning_trace.set_active(False),
                self.update_reasoning_mode_display("Ready")
            ),
            
            # Streaming (to chat panel, unchanged)
            "on_stream_chunk": self._handle_stream_chunk,
        }
```

**Integration in main.py:**

```python
# In main() function after creating NexusApp:
app = NexusApp(
    agent_loop=session.agent_loop,
    artifact_manager=artifact_manager,
)

# Set up reasoning callbacks after app is ready
# (Will be done via app.setup_reasoning_callbacks() in NexusApp.on_mount())
```

#### User Experience Flow

**Example 1: Simple Query (Direct Execution)**
```
User: "What is 2+2?"
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Header: "Nexus | Mode: Analyzing"
Status: ⚡ Analyzing query complexity...
Status: ✓ Complexity: SIMPLE, Strategy: DIRECT
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Header: "Nexus | Mode: Direct"
Status: 🎯 Executing (fast path)...
Status: 🔍 Evaluating response quality...
Status: ✅ Complete: DIRECT (1 attempt, quality: 0.95)
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Header: "Nexus | Mode: Ready"
Chat: "The answer is 4."
```

**Example 2: Escalation Scenario**
```
User: "Explain quantum computing"
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status: ⚡ Analyzing...
Status: 🎯 Strategy: DIRECT
Status: Executing (fast path)...
Status: 🔍 Evaluating response quality...
Status: Quality: 0.35 - Insufficient (Strategy: DIRECT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status: ⚠️ Escalating: DIRECT → LIGHT
Status: 🧠 Light reasoning (1-2 iterations)...
Status: 🔍 Evaluating response quality...
Status: ✅ Complete: LIGHT (2 attempts, quality: 0.88)
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Chat: [Comprehensive answer about quantum computing]
```

### 1.5 Supporting Utilities

**New Module**: `src/nxs/application/reasoning/utils.py`

Utility functions for reasoning components:

```python
"""Utility functions for reasoning system."""

from pathlib import Path
from typing import Any
from string import Template

from nxs.logger import get_logger

logger = get_logger("reasoning.utils")


def load_prompt(prompt_name: str) -> str:
    """Load a prompt template from the prompts directory.
    
    Args:
        prompt_name: Relative path from prompts/ directory
                    e.g., "reasoning/complexity_analysis.txt"
    
    Returns:
        Prompt template as string
    
    Raises:
        FileNotFoundError: If prompt file doesn't exist
    """
    # Resolve path relative to package
    prompts_dir = Path(__file__).parent.parent.parent / "prompts"
    prompt_path = prompts_dir / prompt_name
    
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt template not found: {prompt_path}\n"
            f"Expected at: {prompt_path.absolute()}"
        )
    
    logger.debug(f"Loading prompt template: {prompt_name}")
    return prompt_path.read_text(encoding="utf-8")


def format_prompt(template: str, **kwargs: Any) -> str:
    """Format a prompt template with variables.
    
    Uses Python's string.Template for safe substitution.
    
    Args:
        template: Prompt template string with ${variable} placeholders
        **kwargs: Variable values for substitution
    
    Returns:
        Formatted prompt string
    
    Raises:
        KeyError: If required variable is missing
    """
    try:
        return Template(template).substitute(**kwargs)
    except KeyError as e:
        missing_var = str(e).strip("'")
        available = list(kwargs.keys())
        raise KeyError(
            f"Missing required variable '{missing_var}' in prompt template. "
            f"Available variables: {available}"
        )


def get_claude_for_component(
    base_llm: "Claude",
    component_model: str
) -> "Claude":
    """Create a Claude instance for a specific component with different model.
    
    Args:
        base_llm: Base Claude instance (contains API key)
        component_model: Model to use for this component
    
    Returns:
        New Claude instance with specified model
    """
    from nxs.application.claude import Claude
    
    # Create new instance with same API key but different model
    return Claude(
        model=component_model,
        api_key=base_llm.api_key,  # Reuse API key from base instance
        max_tokens=base_llm.max_tokens,
    )
```

**Claude Enhancement**: Add `with_model()` method to Claude class:

```python
# In src/nxs/application/claude.py:

class Claude:
    """Anthropic API wrapper with streaming support."""
    
    def with_model(self, model: str) -> "Claude":
        """Create a new Claude instance with a different model.
        
        Useful for reasoning components that need different models
        (e.g., Haiku for analysis, Sonnet for planning).
        
        Args:
            model: Model identifier to use
        
        Returns:
            New Claude instance with same API key but different model
        """
        return Claude(
            model=model,
            api_key=self.api_key,
            max_tokens=self.max_tokens,
        )
```

### 1.6 Error Handling & Graceful Degradation

**Objective**: Ensure system remains functional even when reasoning components fail.

#### Error Handling Strategy

**Principle**: Never fail completely - always return *some* response to the user.

```python
# In AdaptiveReasoningLoop:

async def run(self, query: str, ...) -> str:
    """Run with comprehensive error handling."""
    
    try:
        # Phase 0: Complexity Analysis
        try:
            complexity = await self.analyzer.analyze(query, ...)
        except Exception as e:
            logger.error(f"Complexity analysis failed: {e}", exc_info=True)
            # Fallback: Default to MEDIUM complexity
            complexity = ComplexityAnalysis(
                complexity_level=ComplexityLevel.MEDIUM,
                reasoning_required=True,
                recommended_strategy=ExecutionStrategy.LIGHT_PLANNING,
                rationale="Complexity analysis failed, defaulting to medium",
                estimated_iterations=2,
                confidence=0.0,  # Zero confidence indicates fallback
            )
            if "on_error" in callbacks:
                await callbacks["on_error"]("complexity_analysis", str(e))
        
        # Continue with execution...
        
    except Exception as e:
        # Catastrophic failure - fall back to basic AgentLoop
        logger.error(f"AdaptiveReasoningLoop failed completely: {e}", exc_info=True)
        
        if "on_error" in callbacks:
            await callbacks["on_error"]("adaptive_loop", str(e))
        
        # Last resort: Direct execution without reasoning
        logger.warning("Falling back to direct AgentLoop execution")
        return await super().run(query, use_streaming, callbacks)
```

**Fallback Matrix:**

| Component Failure | Fallback Behavior | User Impact |
|------------------|-------------------|-------------|
| **Complexity Analyzer** | Default to MEDIUM (LIGHT strategy) | Slight over-processing, but functional |
| **Planner** | Skip planning, execute query directly | Works like DIRECT mode |
| **Evaluator** | Accept all responses (no escalation) | No quality check, faster but potentially lower quality |
| **Synthesizer** | Return last result without synthesis | May lack coherence but has content |
| **Entire Loop** | Fall back to base AgentLoop | Works like old system, no reasoning |

**User Notifications:**

```python
# In TUI callbacks:
"on_error": async (component: str, error: str) -> None:
    # → StatusPanel: "⚠️ Warning: {component} unavailable (degraded mode)"
    # → Continue execution with fallback
```

### 1.7 Configuration and Integration

**New Config:** `src/nxs/application/reasoning/config.py`

```python
from dataclasses import dataclass

@dataclass
class ReasoningConfig:
    """Configuration for reasoning components."""
    
    # Iteration control
    max_iterations: int = 3
    min_confidence: float = 0.7
    
    # Complexity thresholds (for automatic routing)
    simple_threshold: float = 0.3  # Below this = SIMPLE
    complex_threshold: float = 0.7  # Above this = COMPLEX, between = MEDIUM
    
    # Quality thresholds (for self-correction - NEW)
    min_quality_direct: float = 0.6    # Minimum quality for DIRECT responses
    min_quality_light: float = 0.7     # Minimum quality for LIGHT responses
    min_quality_deep: float = 0.5      # Accept lower for DEEP (final attempt)
    
    # Model selection (can use different models for different phases)
    analysis_model: str = "claude-haiku-3.5"  # Fast, cheap for complexity analysis
    planning_model: str = "claude-sonnet-4.5"
    evaluation_model: str = "claude-sonnet-4.5"
    synthesis_model: str = "claude-sonnet-4.5"
    
    # Caching
    enable_caching: bool = True
    
    # Prompt paths
    complexity_prompt_path: str = "prompts/reasoning/complexity_analysis.txt"  # NEW
    planning_prompt_path: str = "prompts/reasoning/planning.txt"
    evaluation_prompt_path: str = "prompts/reasoning/evaluation.txt"
    synthesis_prompt_path: str = "prompts/reasoning/synthesis.txt"
    filter_prompt_path: str = "prompts/reasoning/filter.txt"
    
    # Performance tuning
    max_subtasks: int = 5
    min_subtasks: int = 1
    parallel_execution: bool = False  # Future feature
    
    # Analysis caching (NEW - cache complexity analysis)
    cache_analysis: bool = True  # Cache similar queries
    analysis_cache_ttl: int = 3600  # 1 hour
    
    # Strategy overrides (for testing/debugging)
    force_strategy: Optional[str] = None  # "direct", "light", "deep", or None
    
    # Logging
    debug_mode: bool = False
```

**Complete `src/nxs/main.py` Integration:**

Shows full integration with SessionManager, ReasoningConfig, and TUI callbacks:

```python
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

import typer

from nxs.logger import get_logger, setup_logger
from nxs.application.claude import Claude
from nxs.application.command_control import CommandControlAgent
from nxs.application.artifact_manager import ArtifactManager
from nxs.application.session_manager import SessionManager
from nxs.application.reasoning.config import ReasoningConfig
from nxs.presentation.tui import NexusApp

load_dotenv()

# Anthropic Config
claude_model = os.getenv("CLAUDE_MODEL", "")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

assert claude_model, "Error: CLAUDE_MODEL cannot be empty. Update .env"
assert anthropic_api_key, "Error: ANTHROPIC_API_KEY cannot be empty. Update .env"

cli = typer.Typer(
    name="nxs",
    help="Nexus command control with Claude integration and MCP-based CLI",
    add_completion=False,
)


@cli.command()
async def main(
    debug: bool = typer.Option(os.getenv("DEBUG", "false").lower() == "true", "--debug", help="Enable debug mode"),
):
    """Main application entry point with SessionManager and Reasoning integration."""
    
    # Ensure logging is set up
    setup_logger(log_level="DEBUG" if debug else "INFO")
    logger = get_logger("main")

    logger.info("🚀 Starting Nexus with Adaptive Reasoning System")

    # Create core services
    claude_service = Claude(model=claude_model)
    artifact_manager = ArtifactManager()
    
    # NEW: Load reasoning configuration from environment
    reasoning_config = ReasoningConfig(
        max_iterations=int(os.getenv("MAX_REASONING_ITERATIONS", "3")),
        min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.7")),
        # Complexity thresholds for automatic routing
        simple_threshold=float(os.getenv("SIMPLE_THRESHOLD", "0.3")),
        complex_threshold=float(os.getenv("COMPLEX_THRESHOLD", "0.7")),
        # Quality thresholds for self-correction
        min_quality_direct=float(os.getenv("MIN_QUALITY_DIRECT", "0.6")),
        min_quality_light=float(os.getenv("MIN_QUALITY_LIGHT", "0.7")),
        min_quality_deep=float(os.getenv("MIN_QUALITY_DEEP", "0.5")),
        # Model selection (can use cheaper models for analysis)
        analysis_model=os.getenv("ANALYSIS_MODEL", "claude-haiku-3.5"),  # Fast, cheap
        planning_model=os.getenv("PLANNING_MODEL", claude_model),
        evaluation_model=os.getenv("EVALUATION_MODEL", claude_model),
        synthesis_model=os.getenv("SYNTHESIS_MODEL", claude_model),
        # Optional strategy override for debugging
        force_strategy=os.getenv("FORCE_REASONING_STRATEGY", None),  # "direct", "light", "deep", or None
        debug_mode=debug,
    )
    
    logger.info(
        f"Reasoning Config: max_iter={reasoning_config.max_iterations}, "
        f"analysis_model={reasoning_config.analysis_model}"
    )

    # Create agent factory that produces CommandControlAgent with reasoning
    # This preserves command parsing (/cmd) and resource extraction (@resource)
    def create_command_control_agent(conversation):
        """Factory to create CommandControlAgent with session-managed conversation.
        
        Args:
            conversation: The Conversation instance managed by SessionManager
            
        Returns:
            CommandControlAgent instance that uses the provided conversation
            and has adaptive reasoning enabled
        """
        # Create CommandControlAgent with reasoning config
        # NOTE: We pass reasoning_config here!
        agent = CommandControlAgent(
            artifact_manager=artifact_manager,
            claude_service=claude_service,
            reasoning_config=reasoning_config,  # NEW: Pass reasoning config
            # Callbacks will be set up by TUI after app initialization
        )
        
        # Replace the internally-created conversation with session-managed one
        # This ensures session persistence works while keeping reasoning features
        agent.conversation = conversation
        
        logger.debug("Created CommandControlAgent with reasoning and session-managed conversation")
        return agent

    # Create SessionManager with custom agent factory
    session_manager = SessionManager(
        llm=claude_service,
        storage_dir=Path.home() / ".nxs" / "sessions",
        system_message="You are a helpful AI assistant with advanced reasoning capabilities.",
        enable_caching=True,
        agent_factory=create_command_control_agent,  # Uses reasoning config
    )

    logger.info("SessionManager initialized with CommandControlAgent (Reasoning enabled)")

    # Get or restore the default session
    # This will either restore from ~/.nxs/sessions/session.json or create new
    session = await session_manager.get_or_create_default_session()
    
    logger.info(
        f"Session ready: {session.session_id} "
        f"({session.get_message_count()} messages in history)"
    )

    # Launch Textual TUI with session's agent_loop
    # The agent_loop is CommandControlAgent with adaptive reasoning
    app = NexusApp(
        agent_loop=session.agent_loop,
        artifact_manager=artifact_manager,
    )
    
    # NOTE: Reasoning callbacks will be set up in NexusApp.on_mount()
    # via app.setup_reasoning_callbacks(), which will inject callbacks
    # into session.agent_loop.adaptive_loop.callbacks
    
    try:
        await app.run_async()
    finally:
        # Save session before exit
        logger.info("Saving session before exit...")
        session_manager.save_active_session()
        logger.info("Session saved successfully")
        
        # Clean up ArtifactManager connections
        await artifact_manager.cleanup()


def run():
    """Entry point for the Nexus application."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
```

**Key Integration Points:**

1. **ReasoningConfig Creation**: Loaded from environment variables with sensible defaults
2. **Factory Pattern**: `create_command_control_agent()` captures `reasoning_config` in closure
3. **SessionManager**: Uses factory to create agents with reasoning config
4. **TUI Callback Setup**: Deferred to `NexusApp.on_mount()` to avoid circular dependencies
5. **Conversation Injection**: Session-managed conversation replaces internal one (preserves persistence)
6. **Error Handling**: Wrapped in try/finally for clean session save

**Key Changes:**
- **No inheritance** - CommandControlAgent uses composition
- **Single execution path** - AdaptiveReasoningLoop handles everything
- **Always adaptive** - no fallback needed, system self-corrects
- **Simpler configuration** - no enable/disable flags, no emergency modes
- **Quality guarantee** - all responses evaluated before returning

### 1.5 Prompt Engineering

**New Directory:** `src/nxs/prompts/reasoning/`

Create specialized prompts for reasoning components:

```
src/nxs/prompts/reasoning/
├── complexity_analysis.txt  # Query complexity analysis
├── quality_check.txt       # Response quality evaluation (NEW - for self-correction)
├── planning.txt            # Task decomposition prompt
├── evaluation.txt          # Research completeness evaluation prompt
├── synthesis.txt           # Result synthesis prompt
└── filter.txt              # Result filtering prompt
```

**Complexity Analysis Prompt** (`complexity_analysis.txt`) - NEW:
```
You are a query complexity analyzer. Your task is to assess whether a query requires simple execution, light planning, or deep reasoning.

# Your Task

Analyze the user's query and determine:
1. **Complexity Level**: Simple, Medium, or Complex
2. **Strategy Recommendation**: Direct, Light Planning, or Deep Reasoning
3. **Reasoning**: Explain your assessment
4. **Estimated Iterations**: How many iterations would be needed (0-5)

# Analysis Criteria

## SIMPLE Queries (Direct Execution)
- Single, well-defined question
- Answerable with general knowledge or 1 tool call
- No synthesis or research needed
- Examples:
  * "What is Python?"
  * "Get the current time"
  * "Calculate 2 + 2"
  * "What's the weather in NYC?"

## MEDIUM Queries (Light Planning)
- 2-3 related questions or parts
- Needs multiple tool calls but straightforward
- Light coordination helps
- Examples:
  * "Compare Python and Java, then recommend one"
  * "Summarize this document and list key points"
  * "Get weather and recommend activities"

## COMPLEX Queries (Deep Reasoning)
- Multi-step research or analysis
- Requires information from multiple sources
- Needs synthesis and iteration
- May have implicit sub-questions
- Examples:
  * "Research competitive landscape for X, analyze trends, recommend strategy"
  * "Find similar companies, compare their approaches, synthesize insights"
  * "Investigate this topic comprehensively and provide analysis"

# User Query

{query}

# Available Tools

{tools}

# Conversation Context

{context}

# Output Format

Provide your analysis:

**Complexity Level:** [SIMPLE | MEDIUM | COMPLEX]

**Recommended Strategy:** [DIRECT | LIGHT_PLANNING | DEEP_REASONING]

**Estimated Iterations:** [0-5]

**Confidence:** [0.0-1.0]

**Reasoning:**
[Explain why you chose this complexity level and strategy. Be specific about what aspects of the query led to your decision.]

**Analysis Flags:**
- Requires Research: [Yes/No]
- Requires Synthesis: [Yes/No]
- Multi-Part Query: [Yes/No]
- Tool Count Estimate: [number]
```

**Response Quality Check Prompt** (`quality_check.txt`) - NEW FOR SELF-CORRECTION:
```
You are a response quality evaluator. Your task is to assess if a response adequately answers the user's query and determine if escalation to deeper reasoning is needed.

# Your Task

Evaluate the response and determine:
1. **Quality Assessment**: Is the response sufficient?
2. **Confidence Score**: How confident are you in quality? (0.0 to 1.0)
3. **Missing Aspects**: What's missing or inadequate?
4. **Escalation Recommendation**: Should we retry with deeper reasoning?

# Evaluation Criteria

## SUFFICIENT Response (No Escalation)
- Directly answers the query
- Appropriate depth for the question
- Accurate and reliable information
- Well-structured and clear
- No significant gaps or errors

## INSUFFICIENT Response (Escalation Needed)
- **Superficial**: Lacks depth for the query complexity
- **Incomplete**: Missing key aspects or parts of query
- **Vague**: Too general, needs specifics
- **Inaccurate**: Contains errors or questionable info
- **Confusing**: Poorly structured or unclear

# Context

**Original Query:**
{query}

**Generated Response:**
{response}

**Strategy Used:** {strategy_used}
- DIRECT: Fast execution, might lack depth
- LIGHT_PLANNING: Moderate depth
- DEEP_REASONING: Maximum depth

**Expected Complexity:** {expected_complexity}

# Output Format

**Quality Assessment:** [SUFFICIENT | INSUFFICIENT]

**Confidence Score:** [0.0-1.0]

**Reasoning:**
[Explain your assessment. Be specific about what makes the response sufficient or insufficient.]

**Missing Aspects:** (if INSUFFICIENT)
- Aspect 1
- Aspect 2
...

**Escalation Recommendation:**
- If INSUFFICIENT and strategy was DIRECT: Recommend LIGHT_PLANNING
- If INSUFFICIENT and strategy was LIGHT_PLANNING: Recommend DEEP_REASONING
- If INSUFFICIENT and strategy was DEEP_REASONING: Accept as best effort

**Key Questions:**
1. Does it answer ALL parts of the query?
2. Is the depth appropriate for the question?
3. Is the information accurate and reliable?
4. Would a user be satisfied with this response?
```

**Planning Prompt** (`planning.txt`):
```
You are a strategic planning assistant. Given a user's query, your task is to decompose it into a structured research plan.

# Your Task

Analyze the query and create a plan that includes:
1. **Key Information Needs**: What specific information is required to answer this query?
2. **Subtasks**: Break down the query into specific, actionable subtasks
3. **Tool Hints**: Suggest which tools or approaches would be most effective
4. **Execution Order**: Prioritize subtasks logically

# Guidelines

- For simple queries, a single subtask may suffice
- For complex queries, create 2-5 subtasks
- Each subtask should be independently executable
- Prioritize by importance and logical dependency
- Be specific - avoid vague subtasks

# Query

{query}

# Available Tools

{tools}

# Context

{context}

# Output Format

Provide your plan as a structured list:

1. [HIGH PRIORITY] First subtask description
   Tools: tool1, tool2
   
2. [MEDIUM PRIORITY] Second subtask description
   Tools: tool3
   
3. [LOW PRIORITY] Third subtask description
   Tools: tool4

Then provide an overall strategy summary explaining your approach.
```

**Evaluation Prompt** (`evaluation.txt`):
```
You are an evaluation assistant. Your task is to determine if the accumulated results sufficiently answer the original query.

# Your Task

Analyze the original query and results to determine:
1. **Completeness**: Are all aspects of the query addressed?
2. **Confidence**: How confident are you in the completeness? (0.0 to 1.0)
3. **Missing Aspects**: What information is still needed?
4. **Additional Queries**: What specific queries would fill the gaps?

# Guidelines

- Be thorough - look for implicit requirements
- Consider completeness across multiple dimensions
- If confidence is below 0.8, identify specific gaps
- Additional queries should be concrete and actionable

# Original Query

{query}

# Accumulated Results

{results}

# Current Plan

{plan}

# Output Format

## Completeness Assessment
[Your analysis here]

## Confidence Score
[0.0 to 1.0]

## Missing Aspects
- Aspect 1
- Aspect 2
...

## Additional Queries Needed
1. Specific query 1
2. Specific query 2
...

If complete, write "COMPLETE" and explain why the results are sufficient.
```

**Synthesis Prompt** (`synthesis.txt`):
```
You are a synthesis assistant. Your task is to combine multiple research results into a comprehensive, coherent answer.

# Your Task

Create a final answer that:
1. **Directly addresses** the user's original query
2. **Integrates information** from multiple sources
3. **Maintains coherence** and logical flow
4. **Cites sources** when making specific claims
5. **Acknowledges limitations** if any gaps remain

# Guidelines

- Start with the most direct answer to the query
- Organize information logically
- Synthesize rather than concatenate
- Use clear, concise language
- Avoid unnecessary repetition
- Don't mention the research process itself

# Original Query

{query}

# Filtered Results

{results}

# Output

Provide your comprehensive answer below:
```

**Filter Prompt** (`filter.txt`):
```
You are a filtering assistant. Your task is to identify which results are most relevant to answering the query.

# Your Task

Review each result and:
1. Rate relevance (0-10)
2. Identify key information
3. Filter out redundant or irrelevant content
4. Rank by importance

# Guidelines

- Focus on direct relevance to the query
- Favor specific facts over general information
- Consider recency and authority
- Remove duplicate information
- Keep top 5-7 most valuable results

# Query

{query}

# Results to Filter

{results}

# Output Format

For each result you keep, provide:

Result ID: [number]
Relevance: [0-10]
Key Information: [brief summary]
Reasoning: [why this is relevant]

Then provide a ranked list of result IDs in order of importance.
```

### Phase 1 Benefits

**Immediate Value:**
- ✅ **Self-correcting quality guarantee** - always evaluates responses, auto-escalates when needed
- ✅ **Intelligent automatic adaptation** - no manual configuration needed
- ✅ **Fast but never sloppy** - tries fast path first, but escalates automatically if quality insufficient
- ✅ **Graceful scaling** - adds reasoning complexity only when beneficial
- ✅ Structured planning makes reasoning explicit and inspectable
- ✅ Iterative refinement improves answer quality for complex queries
- ✅ Modular design enables testing each component independently
- ✅ Clean architecture via composition over inheritance
- ✅ Foundation for future multi-agent decomposition
- ✅ Enhanced observability through phase callbacks and escalation tracking
- ✅ **Better UX** - users don't need to know about reasoning modes

**Performance Improvements:**
- Simple queries: **Fast** (1-3s typical, escalates if quality insufficient ~10-15% of time)
- Medium queries: **Balanced** (5-10s, quality-checked, escalates ~5-10% of time)
- Complex queries: **Thorough** (15-30s, highest quality guarantee)
- Average overhead: **Minimal for most queries** - escalation only when needed
- Quality improvement: **Measurable boost** from auto-escalation

**Testing Strategy:**
1. **Unit Tests**: Each component (Analyzer, Planner, Evaluator with both methods, Synthesizer) in isolation
2. **Complexity Analysis Tests**: Verify correct strategy selection for various queries
3. **Quality Evaluation Tests**: Test response quality assessment and escalation triggers
4. **Integration Tests**: Full AdaptiveReasoningLoop execution with real/mocked LLM
5. **Strategy Tests**: Test each execution path (direct, light, deep)
6. **Escalation Tests**: Verify auto-escalation triggers when quality insufficient
7. **Performance Tests**: Latency and token usage per strategy, escalation overhead
8. **End-to-end Tests**: Verify quality guarantee - no poor responses reach user

---

## Phase 1 Implementation Complete

Phase 1 focuses exclusively on building and validating the **self-correcting adaptive reasoning system**. Once Phase 1 is complete, stable, and validated in production, the system will be ready to evolve further.

### Next Evolution: Cognitive Multi-Agent Architecture

For the future vision of Phase 2/3 (brain-inspired cognitive agents, multi-agent coordination, meta-learning), see:

**→ [`PHASE_2_3_COGNITIVE_ARCHITECTURE.md`](PHASE_2_3_COGNITIVE_ARCHITECTURE.md)**

This separate document describes:
- Phase 2: Brain-inspired sub-agent decomposition (PerceptionAgent, MemoryAgent, ExecutiveAgent, MotorAgent)
- CortexCoordinator for multi-agent orchestration
- Phase 3: Advanced capabilities (agent delegation, dynamic agent creation, meta-learning)
- Implementation roadmap for cognitive features
- Success metrics for Level 3/4 agent systems

**Prerequisites for Phase 2/3:**
- Phase 1 must be complete, stable, and proven in production
- Self-correction mechanism validated with real-world data
- Quality metrics meeting targets
- User satisfaction with adaptive reasoning

---

## Implementation Roadmap

### Stage 1: Foundation (Phase 1 - Week 1-2)

**Week 1:**
- [ ] Create `reasoning/` module structure
- [ ] Implement `types.py` with ComplexityAnalysis, ResearchPlan, EvaluationResult, etc.
- [ ] Implement `config.py` with ReasoningConfig (complexity + quality thresholds)
- [ ] Create reasoning prompts directory
- [ ] **Implement QueryComplexityAnalyzer (Priority 1)**
- [ ] Create complexity analysis prompt
- [ ] **Implement Evaluator with dual methods: evaluate() + evaluate_response_quality() (Priority 1)**
- [ ] Create quality check prompt (for self-correction)
- [ ] Implement Planner with basic query decomposition
- [ ] Write unit tests for Analyzer, Evaluator (both methods), and Planner

**Week 2:**
- [ ] Implement Synthesizer with result aggregation
- [ ] **Create AdaptiveReasoningLoop with self-correction**
- [ ] Implement three execution methods: _execute_direct(), _execute_light_planning(), _execute_deep_reasoning()
- [ ] Implement _evaluate_response_quality() (uses Evaluator.evaluate_response_quality())
- [ ] Implement auto-escalation logic (DIRECT → LIGHT → DEEP)
- [ ] Write unit tests for Synthesizer
- [ ] Write comprehensive tests for AdaptiveReasoningLoop:
  * Test each execution path
  * Test quality evaluation
  * Test auto-escalation triggers
  * Test final quality guarantee
- [ ] Test strategy selection accuracy
- [ ] Test escalation scenarios (when quality insufficient)

### Stage 2: Integration & TUI Enhancement (Phase 1 - Week 2-3)

**Week 2-3: Core Integration**
- [ ] **Simplify CommandControlAgent architecture**
- [ ] Remove AgentLoop inheritance (composition over inheritance)
- [ ] Single execution path via AdaptiveReasoningLoop
- [ ] Remove all enable/disable flags and fallback modes
- [ ] Update main.py with simplified initialization (no flags)

**Week 2-3: TUI Integration**
- [ ] **Create ReasoningTracePanel widget (Priority 1)**
  * Implement `ReasoningTracePanel` (extends RichLog)
  * Implement `ReasoningTraceHeader` (collapsible header with indicator)
  * Implement `CollapsibleReasoningTrace` (container widget)
  * Add keyboard shortcut handlers (`Ctrl+R`, `Ctrl+Shift+R`)
- [ ] **Simplify StatusPanel**
  * Remove reasoning detail methods
  * Keep only high-level event logging
  * Maintain non-reasoning tool call display
- [ ] **Update NexusApp**
  * Add `CollapsibleReasoningTrace` to layout
  * Implement callback routing logic (StatusPanel vs TracePanel)
  * Add action handlers for toggle/clear
  * Update `setup_reasoning_callbacks()` with dual routing
- [ ] **Test TUI Integration**
  * Test collapsible behavior
  * Test activity indicator
  * Test callback routing
  * Test keyboard shortcuts
  * Visual testing of trace display hierarchy

**Week 3: Testing & Refinement**
- [ ] Refine prompts based on testing:
  * Complexity analysis accuracy
  * Quality evaluation sensitivity
- [ ] Integration testing with full system
- [ ] **Performance benchmarking:**
  * Latency per strategy
  * Escalation frequency
  * Quality improvement from escalation
- [ ] **Tune thresholds based on data:**
  * Complexity thresholds (initial routing)
  * Quality thresholds (escalation triggers)
- [ ] Monitor metrics:
  * Strategy distribution (initial vs final)
  * Escalation patterns
  * Quality scores
- [ ] Documentation and examples:
  * Self-correction in action
  * Threshold tuning guide
  * Reasoning trace usage guide

---

## Testing Strategy

### Test Organization

**Directory Structure:**
```
tests/
├── reasoning/
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures and mocks
│   ├── test_analyzer.py      # QueryComplexityAnalyzer tests
│   ├── test_planner.py       # Planner tests
│   ├── test_evaluator.py     # Evaluator tests (both methods)
│   ├── test_synthesizer.py   # Synthesizer tests
│   ├── test_reasoning_loop.py # AdaptiveReasoningLoop tests
│   └── fixtures/
│       ├── queries.json       # Test query datasets
│       ├── responses.json     # Mock LLM responses
│       └── complexity_analyses.json
├── integration/
│   ├── test_adaptive_reasoning.py
│   ├── test_command_control_with_reasoning.py
│   └── test_tui_integration.py
└── performance/
    ├── test_latency.py
    ├── test_escalation_overhead.py
    └── benchmarks/
```

### Unit Tests

**Mocking Strategy:**

Create a reusable `MockClaude` class for deterministic testing:

```python
# tests/reasoning/conftest.py
import pytest
from typing import List, Dict, Any
from nxs.application.claude import Claude

class MockClaude:
    """Mock Claude for deterministic testing."""
    
    def __init__(self, responses: List[str] = None, response_map: Dict[str, str] = None):
        """Initialize with canned responses.
        
        Args:
            responses: List of responses to return in order
            response_map: Dict mapping query patterns to responses
        """
        self.responses = responses or []
        self.response_map = response_map or {}
        self.call_count = 0
        self.calls = []  # Track all calls
    
    async def create_message(self, messages, **kwargs):
        """Mock create_message."""
        self.call_count += 1
        
        # Extract query from messages
        query = messages[-1].get("content", "") if messages else ""
        self.calls.append({"query": query, "kwargs": kwargs})
        
        # Return mapped response or next in sequence
        if query in self.response_map:
            response_text = self.response_map[query]
        elif self.responses:
            response_text = self.responses.pop(0)
        else:
            response_text = "Mock response"
        
        # Return in Claude message format
        return type('MockMessage', (), {
            'content': [type('MockContent', (), {
                'type': 'text',
                'text': response_text
            })()]
        })()

@pytest.fixture
def mock_claude():
    """Fixture providing MockClaude."""
    return MockClaude

@pytest.fixture
def sample_queries():
    """Load sample queries from fixtures."""
    import json
    from pathlib import Path
    fixture_path = Path(__file__).parent / "fixtures" / "queries.json"
    if fixture_path.exists():
        return json.loads(fixture_path.read_text())
    return {
        "simple": ["What is 2+2?", "What is Python?"],
        "medium": ["Compare Python and Java", "Summarize the document"],
        "complex": ["Research competitive landscape for X", "Comprehensive analysis of Y"]
    }
```

**Component Tests with Concrete Examples:**

```python
# tests/reasoning/test_analyzer.py
import pytest
from nxs.application.reasoning.analyzer import QueryComplexityAnalyzer
from nxs.application.reasoning.types import ComplexityLevel, ExecutionStrategy
from nxs.application.reasoning.config import ReasoningConfig

@pytest.mark.asyncio
async def test_analyzer_simple_query(mock_claude):
    """Test that simple queries are classified as SIMPLE."""
    llm = mock_claude(responses=[
        "**Complexity Level:** SIMPLE\n**Recommended Strategy:** DIRECT\n**Estimated Iterations:** 1\n**Confidence:** 0.95"
    ])
    analyzer = QueryComplexityAnalyzer(llm, ReasoningConfig())
    
    result = await analyzer.analyze("What is 2+2?")
    
    assert result.complexity_level == ComplexityLevel.SIMPLE
    assert result.recommended_strategy == ExecutionStrategy.DIRECT
    assert result.estimated_iterations == 1
    assert result.confidence >= 0.9

@pytest.mark.asyncio
async def test_analyzer_complex_query(mock_claude):
    """Test that complex multi-part queries are classified correctly."""
    llm = mock_claude(responses=[
        "**Complexity Level:** COMPLEX\n**Recommended Strategy:** DEEP_REASONING\n**Estimated Iterations:** 3"
    ])
    analyzer = QueryComplexityAnalyzer(llm, ReasoningConfig())
    
    result = await analyzer.analyze(
        "Research the competitive landscape for quantum computing startups, "
        "analyze market trends, and recommend investment strategies"
    )
    
    assert result.complexity_level == ComplexityLevel.COMPLEX
    assert result.recommended_strategy == ExecutionStrategy.DEEP_REASONING
    assert result.estimated_iterations >= 3
    assert result.requires_research is True
    assert result.multi_part_query is True

@pytest.mark.asyncio
async def test_analyzer_error_handling(mock_claude):
    """Test analyzer handles LLM errors gracefully."""
    llm = mock_claude()
    llm.create_message = lambda *args, **kwargs: (_ for _ in ()).throw(Exception("API Error"))
    
    analyzer = QueryComplexityAnalyzer(llm, ReasoningConfig())
    
    # Should not raise, but return default/fallback
    with pytest.raises(Exception):  # Or catch and verify fallback
        await analyzer.analyze("Any query")

# tests/reasoning/test_evaluator.py
@pytest.mark.asyncio
async def test_evaluator_response_quality_sufficient(mock_claude):
    """Test that high-quality responses pass evaluation."""
    llm = mock_claude(responses=[
        "**Quality Assessment:** SUFFICIENT\n**Confidence Score:** 0.85\n**Reasoning:** Complete and accurate"
    ])
    evaluator = Evaluator(llm, ReasoningConfig())
    
    result = await evaluator.evaluate_response_quality(
        query="What is quantum computing?",
        response="Quantum computing is a type of computation that harnesses quantum phenomena...",
        strategy_used="DIRECT",
        expected_complexity=None
    )
    
    assert result.is_complete is True
    assert result.confidence >= 0.8

@pytest.mark.asyncio
async def test_evaluator_response_quality_insufficient(mock_claude):
    """Test that low-quality responses trigger escalation."""
    llm = mock_claude(responses=[
        "**Quality Assessment:** INSUFFICIENT\n**Confidence Score:** 0.35\n"
        "**Missing Aspects:**\n- Lacks technical depth\n- Missing key concepts"
    ])
    evaluator = Evaluator(llm, ReasoningConfig())
    
    result = await evaluator.evaluate_response_quality(
        query="Explain quantum computing in detail",
        response="It's a type of computer.",
        strategy_used="DIRECT",
        expected_complexity=None
    )
    
    assert result.is_complete is False
    assert result.confidence < 0.5
    assert len(result.missing_aspects) > 0

# tests/reasoning/test_planner.py
async def test_planner_simple_query(mock_claude):
    """Test planner with simple single-step query."""
    llm = mock_claude(responses=[
        "1. [HIGH PRIORITY] Search for Python definition\nTools: search"
    ])
    planner = Planner(llm, ReasoningConfig())
    
    plan = await planner.generate_plan("What is Python?")
    
    assert len(plan.subtasks) == 1
    assert plan.estimated_complexity == "low"
    assert plan.subtasks[0].priority == 1

async def test_planner_complex_query(mock_claude):
    """Test planner with complex multi-step query."""
    llm = mock_claude(responses=[
        """1. [HIGH PRIORITY] Research quantum computing basics
Tools: search, wikipedia

2. [HIGH PRIORITY] Identify key players in quantum space
Tools: search

3. [MEDIUM PRIORITY] Analyze market trends
Tools: search, analysis

4. [LOW PRIORITY] Synthesize recommendations
Tools: none"""
    ])
    planner = Planner(llm, ReasoningConfig())
    
    plan = await planner.generate_plan(
        "Research quantum computing landscape and provide recommendations"
    )
    
    assert len(plan.subtasks) >= 3
    assert plan.estimated_complexity in ["medium", "high"]
    # Verify priorities are assigned
    assert all(task.priority for task in plan.subtasks)
```

### Integration Tests

**Full System Testing:**
- Full reasoning loop execution
- Adaptive strategy selection and escalation
- Resource extraction + reasoning
- Command processing + reasoning
- TUI integration with callbacks

**Comprehensive Integration Test Examples:**

```python
# tests/integration/test_adaptive_reasoning.py
import pytest
from nxs.application.claude import Claude
from nxs.application.conversation import Conversation
from nxs.application.tool_registry import ToolRegistry
from nxs.application.reasoning_loop import AdaptiveReasoningLoop
from nxs.application.reasoning.analyzer import QueryComplexityAnalyzer
from nxs.application.reasoning.planner import Planner
from nxs.application.reasoning.evaluator import Evaluator
from nxs.application.reasoning.synthesizer import Synthesizer
from nxs.application.reasoning.config import ReasoningConfig

@pytest.mark.integration
@pytest.mark.asyncio
async def test_adaptive_reasoning_direct_no_escalation():
    """Test simple query that completes with DIRECT strategy."""
    # Setup real components (can use real Claude or mocks)
    claude = Claude(model="claude-sonnet-4.5")  # or MockClaude for speed
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()
    
    # Create reasoning components
    analyzer = QueryComplexityAnalyzer(claude, config)
    planner = Planner(claude, config)
    evaluator = Evaluator(claude, config)
    synthesizer = Synthesizer(claude, config)
    
    # Track callbacks
    callback_log = []
    
    callbacks = {
        "on_analysis_start": lambda: callback_log.append("analysis_start"),
        "on_strategy_selected": lambda s, r: callback_log.append(f"strategy:{s.value}"),
        "on_quality_check_complete": lambda e: callback_log.append(f"quality:{e.confidence:.2f}"),
        "on_final_response": lambda s, a, q, e: callback_log.append(f"final:{s.value}"),
    }
    
    # Create adaptive loop
    adaptive_loop = AdaptiveReasoningLoop(
        llm=claude,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        callbacks=callbacks,
    )
    
    # Execute
    result = await adaptive_loop.run("What is 2+2?", use_streaming=False)
    
    # Verify
    assert result is not None
    assert len(result) > 0
    assert "4" in result or "four" in result.lower()
    
    # Verify callback sequence
    assert "analysis_start" in callback_log
    assert any("strategy:DIRECT" in log for log in callback_log)
    assert any("quality:" in log for log in callback_log)
    assert any("final:DIRECT" in log for log in callback_log)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_adaptive_reasoning_with_escalation():
    """Test complex query that triggers escalation."""
    # Setup
    claude = Claude(model="claude-sonnet-4.5")
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig(
        min_quality_direct=0.8,  # High threshold to force escalation
    )
    
    analyzer = QueryComplexityAnalyzer(claude, config)
    planner = Planner(claude, config)
    evaluator = Evaluator(claude, config)
    synthesizer = Synthesizer(claude, config)
    
    # Track escalation
    escalations = []
    
    callbacks = {
        "on_auto_escalation": lambda from_s, to_s, r, c: escalations.append({
            "from": from_s.value,
            "to": to_s.value,
            "reason": r,
            "confidence": c
        }),
    }
    
    adaptive_loop = AdaptiveReasoningLoop(
        llm=claude,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        callbacks=callbacks,
    )
    
    # Execute with query likely to trigger escalation
    result = await adaptive_loop.run(
        "Provide a comprehensive explanation of quantum computing including "
        "key principles, applications, and current limitations",
        use_streaming=False
    )
    
    # Verify result quality
    assert result is not None
    assert len(result) > 200  # Should be comprehensive
    
    # Verify escalation happened (likely DIRECT → LIGHT or LIGHT → DEEP)
    # Note: May not always escalate if quality is good enough
    print(f"Escalations: {escalations}")  # For debugging


@pytest.mark.integration
@pytest.mark.asyncio
async def test_command_control_with_reasoning():
    """Test CommandControlAgent with adaptive reasoning."""
    from nxs.application.command_control import CommandControlAgent
    from nxs.application.artifact_manager import ArtifactManager
    
    # Setup
    claude = Claude(model="claude-sonnet-4.5")
    artifact_manager = ArtifactManager()  # or mock
    config = ReasoningConfig()
    
    # Create agent
    agent = CommandControlAgent(
        artifact_manager=artifact_manager,
        claude_service=claude,
        reasoning_config=config,
    )
    
    # Test simple query
    result = await agent.run("What is Python?", use_streaming=False)
    assert result is not None
    assert "python" in result.lower()
    
    # Test with resource mention
    result_with_resource = await agent.run(
        "Summarize @document.txt",
        use_streaming=False
    )
    # Will either process resource or indicate it's not found
    assert result_with_resource is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tui_callback_integration():
    """Test that TUI callbacks work correctly with reasoning loop."""
    from unittest.mock import AsyncMock, MagicMock
    
    # Setup
    claude = Claude(model="claude-sonnet-4.5")
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()
    
    # Create components
    analyzer = QueryComplexityAnalyzer(claude, config)
    planner = Planner(claude, config)
    evaluator = Evaluator(claude, config)
    synthesizer = Synthesizer(claude, config)
    
    # Mock TUI callbacks
    on_analysis = AsyncMock()
    on_strategy_selected = AsyncMock()
    on_quality_check = AsyncMock()
    on_escalation = AsyncMock()
    on_final = AsyncMock()
    
    callbacks = {
        "on_analysis_start": on_analysis,
        "on_strategy_selected": on_strategy_selected,
        "on_quality_check_start": on_quality_check,
        "on_auto_escalation": on_escalation,
        "on_final_response": on_final,
    }
    
    adaptive_loop = AdaptiveReasoningLoop(
        llm=claude,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        callbacks=callbacks,
    )
    
    # Execute
    await adaptive_loop.run("Test query", use_streaming=False)
    
    # Verify callbacks were invoked
    on_analysis.assert_called()
    on_strategy_selected.assert_called()
    on_quality_check.assert_called()
    on_final.assert_called()
    # on_escalation may or may not be called depending on quality
```

### Performance Tests

**Metrics to Track:**
- Latency per phase and strategy
- Escalation frequency and overhead
- Total end-to-end latency by strategy
- Token usage per component
- Caching effectiveness
- Quality improvement from escalation

**Performance Test Example:**
```python
@pytest.mark.performance
async def test_adaptive_reasoning_latency():
    """Benchmark adaptive reasoning latency by query type."""
    queries = load_test_queries()  # Mix of simple/medium/complex
    
    results = []
    for query in queries:
        start = time.time()
        result = await adaptive_loop.run(query)
        elapsed = time.time() - start
        results.append({
            "query": query,
            "latency": elapsed,
            "final_strategy": result.strategy_used,
            "escalated": result.was_escalated
        })
    
    # Verify simple queries stay fast
    simple_queries = [r for r in results if r["final_strategy"] == "DIRECT"]
    avg_simple = sum(r["latency"] for r in simple_queries) / len(simple_queries)
    assert avg_simple < 3.0  # Max 3 seconds for simple queries
```

### User Acceptance Tests

**Complex Scenarios:**
- Multi-step research questions
- Iterative refinement scenarios
- Self-correction and escalation
- Quality guarantee validation
- Tool coordination

---

## Rollout Strategy

### Configuration Variables

**Environment Variables:**
```bash
# .env

# Reasoning configuration (Phase 1)
# No enable/disable flags - adaptive reasoning is THE path
MAX_REASONING_ITERATIONS=3
MIN_CONFIDENCE=0.7

# Complexity thresholds (automatic routing)
SIMPLE_THRESHOLD=0.3             # Below this = direct execution
COMPLEX_THRESHOLD=0.7            # Above this = deep reasoning

# Quality thresholds (self-correction)
MIN_QUALITY_DIRECT=0.6           # Minimum quality for DIRECT responses
MIN_QUALITY_LIGHT=0.7            # Minimum quality for LIGHT responses
MIN_QUALITY_DEEP=0.5             # Accept lower for DEEP (final attempt)

# Model selection (can use cheaper models for analysis)
ANALYSIS_MODEL=claude-haiku-3.5  # Fast, cheap for complexity analysis
PLANNING_MODEL=claude-sonnet-4.5
EVALUATION_MODEL=claude-sonnet-4.5
SYNTHESIS_MODEL=claude-sonnet-4.5
```

**Key Configuration:**
- **No enable/disable flags** - adaptive reasoning is the only path
- **No emergency fallback** - system is reliable enough, self-corrects
- **Quality thresholds** - control when escalation happens
- **Thresholds for tuning** - both complexity analysis and quality evaluation
- **Cheaper model for analysis** - optimization for frequent operations

### Gradual Migration

**Phase 1 Rollout:**
1. Deploy with adaptive reasoning as the only execution path
2. Monitor metrics:
   - Initial strategy distribution (simple/medium/complex)
   - Escalation rate (how often quality triggers retry)
   - Final strategy distribution (after escalations)
   - Quality scores by strategy
3. Tune thresholds based on data:
   - Complexity thresholds (affects initial routing)
   - Quality thresholds (affects escalation frequency)
4. A/B test threshold combinations
5. Optimize prompts:
   - Complexity analysis accuracy
   - Quality evaluation sensitivity
6. Watch for patterns:
   - Which query types escalate most?
   - Is escalation improving quality?
   - Are we over/under-escalating?

---

## Success Metrics

### Level 2 Metrics (Adaptive Reasoning + Planning)

**Quality Metrics:**
- Query decomposition accuracy: >85% correct subtasks
- Answer completeness: >90% user satisfaction
- Self-correction effectiveness: >70% quality improvement after escalation
- Escalation precision: <20% unnecessary escalations

**Performance Metrics:**
- Average iteration count: 2-3 iterations for complex queries
- Time-to-answer: <30s for complex queries
- Simple query speed: <3s average (no regression)
- Token efficiency: <20% average increase (across all queries)

**User Metrics:**
- User satisfaction: >4.0/5.0
- Task success rate: >95%
- Preference for adaptive system: >70% for complex queries

---

## Risks and Mitigations

### Risk 1: Increased Latency

**Risk:** Multi-step processing and quality checks add latency
**Impact:** High (user experience)
**Mitigation:**
- Fast-path for simple queries (direct execution)
- Aggressive prompt caching (90% reduction)
- Streaming updates at each phase
- Performance monitoring and alerting
- Auto-escalation only when necessary

### Risk 2: Higher Token Costs

**Risk:** Multiple LLM calls increase costs (analysis, evaluation, potential escalation)
**Impact:** Medium (operational costs)
**Mitigation:**
- Use cheaper models for analysis (Haiku for complexity)
- Extensive caching of plans and evaluations
- Monitor escalation rates
- Cost-benefit analysis of quality improvements
- Adjustable quality thresholds

### Risk 3: Over-Escalation

**Risk:** System escalates too aggressively, wasting resources
**Impact:** Medium (performance and cost)
**Mitigation:**
- Tune quality thresholds based on real data
- Monitor escalation patterns
- A/B testing of thresholds
- Escalation rate dashboards
- Circuit breakers for runaway escalation

### Risk 4: Under-Escalation

**Risk:** System doesn't escalate when it should, quality suffers
**Impact:** High (user satisfaction)
**Mitigation:**
- Conservative initial thresholds
- User feedback integration
- Quality metric monitoring
- Manual review of low-quality responses
- Continuous threshold tuning

---

## Next Steps After Phase 1 Implementation

### Short-term (1-2 months)
1. Gather user feedback on reasoning quality and self-correction
2. Optimize prompts based on real usage patterns
3. Tune complexity and quality thresholds
4. Add telemetry and observability for escalation
5. Create user documentation and examples

### Medium-term (3-6 months)
1. Analyze escalation patterns and effectiveness
2. Optimize for cost and latency based on data
3. Expand test coverage with real-world scenarios
4. Consider Phase 2 implementation (if Phase 1 proves successful)
5. Explore additional quality metrics

### Long-term (6+ months)
1. Evaluate Phase 2/3: Cognitive multi-agent architecture (see PHASE_2_3_COGNITIVE_ARCHITECTURE.md)
2. Advanced reasoning techniques
3. Cross-session learning
4. Specialized domain agents

---

## Conclusion

This Phase 1 plan provides a comprehensive approach to building a **self-correcting adaptive reasoning system** that:

- **Automatically analyzes** query complexity
- **Intelligently routes** to appropriate execution strategy (direct/light/deep)
- **Always evaluates** response quality
- **Auto-escalates** when quality is insufficient
- **Guarantees** quality-approved responses reach users

The design emphasizes:

- **Quality First:** Never sacrifice quality for speed
- **Modularity:** Clean separation of concerns (Analyzer, Planner, Evaluator, Synthesizer)
- **Composition:** Clean architecture without inheritance complexity
- **Observability:** Comprehensive logging, metrics, and debugging
- **Adaptability:** Self-tuning through threshold adjustments
- **Testability:** Extensive testing at each level

By implementing Phase 1, Nexus evolves from a Level 1 "Connected Problem-Solver" to a Level 2 "Strategic Problem-Solver" with built-in quality guarantees and adaptive intelligence. This provides a solid foundation for future evolution toward multi-agent cognitive architectures (Phase 2/3).
