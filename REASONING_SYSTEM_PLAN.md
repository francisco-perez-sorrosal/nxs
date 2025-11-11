# Reasoning Multi-Agent System Evolution Plan

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

```python
class AdaptiveReasoningLoop(AgentLoop):
    """Self-correcting adaptive agent loop with quality feedback.
    
    Key Innovations:
    1. Automatically analyzes query complexity and adapts execution
    2. ALWAYS evaluates responses - even for "simple" queries
    3. Self-corrects: If simple execution produces poor result, automatically escalates
    4. Guarantees quality: No response sent without passing evaluation
    
    Execution Flow (ALL paths include evaluation):
    1. DIRECT → Execute → Evaluate → (Pass: Return | Fail: Escalate to LIGHT)
    2. LIGHT → Plan → Execute → Evaluate → (Pass: Return | Fail: Escalate to DEEP)
    3. DEEP → Full reasoning cycle → Evaluate → Return (no further escalation)
    
    Self-Correction Example:
    - Query: "What is quantum computing?"
    - Initial: Classified as SIMPLE
    - Execute: Quick response via AgentLoop
    - Evaluate: "Response is superficial, lacks key concepts"
    - Auto-escalate: Re-execute as LIGHT with research
    - Re-evaluate: "Now comprehensive and accurate"
    - Return: Final quality-checked response
    
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

### 1.4 Configuration and Integration

**New Config:** `src/nxs/application/reasoning/config.py`

```python
from dataclasses import dataclass

@dataclass
class ReasoningConfig:
    """Configuration for reasoning components."""
    
    # Iteration control
    max_iterations: int = 3
    min_confidence: float = 0.7
    
    # Complexity thresholds (NEW - for automatic routing)
    simple_threshold: float = 0.3  # Below this = SIMPLE
    complex_threshold: float = 0.7  # Above this = COMPLEX, between = MEDIUM
    
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

**Update:** `src/nxs/main.py`

Simplified initialization with adaptive reasoning:

```python
async def main():
    """Main entry point for Nexus application."""
    
    # Existing initialization...
    artifact_manager = await initialize_artifact_manager()
    claude = Claude(model=CLAUDE_MODEL)
    
    # NEW: Reasoning config (always initialized, adapts automatically)
    from nxs.application.reasoning.config import ReasoningConfig
    
    reasoning_config = ReasoningConfig(
        max_iterations=int(os.getenv("MAX_REASONING_ITERATIONS", "3")),
        min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.7")),
        # Complexity thresholds
        simple_threshold=float(os.getenv("SIMPLE_THRESHOLD", "0.3")),
        complex_threshold=float(os.getenv("COMPLEX_THRESHOLD", "0.7")),
        # Model selection (can use smaller models for analysis)
        analysis_model=os.getenv("ANALYSIS_MODEL", "claude-haiku-3.5"),  # Fast, cheap
        planning_model=os.getenv("PLANNING_MODEL", CLAUDE_MODEL),
        evaluation_model=os.getenv("EVALUATION_MODEL", CLAUDE_MODEL),
        synthesis_model=os.getenv("SYNTHESIS_MODEL", CLAUDE_MODEL),
    )
    
    # Adaptive reasoning is now THE ONLY path (no fallback needed!)
    logger.info(
        "Adaptive reasoning enabled with self-correction "
        "(automatic strategy selection and quality control)"
    )
    
    # Create command agent (now simpler - no fallback parameter)
    agent = CommandControlAgent(
        artifact_manager=artifact_manager,
        claude_service=claude,
        reasoning_config=reasoning_config,
        callbacks=callbacks
    )
    
    # Rest of initialization...
```

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

### Stage 2: Integration (Phase 1 - Week 2-3)

**Week 2-3:**
- [ ] **Simplify CommandControlAgent architecture**
- [ ] Remove AgentLoop inheritance (composition over inheritance)
- [ ] Single execution path via AdaptiveReasoningLoop
- [ ] Remove all enable/disable flags and fallback modes
- [ ] Update main.py with simplified initialization (no flags)
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

---

## Testing Strategy

### Unit Tests

**For Each Component:**
- Isolated testing with mocked dependencies
- Mock LLM responses for deterministic tests
- Test error handling and edge cases
- Test configuration variations

**Example Test Structure:**
```python
# tests/reasoning/test_planner.py
async def test_planner_simple_query():
    """Test planner with simple single-step query."""
    llm = MockClaude(responses=["1. Search for information..."])
    planner = Planner(llm, ReasoningConfig())
    
    plan = await planner.generate_plan("What is Python?")
    
    assert len(plan.subtasks) == 1
    assert plan.estimated_complexity == "low"

async def test_planner_complex_query():
    """Test planner with complex multi-step query."""
    # ...
```

### Integration Tests

**Full System Testing:**
- Full reasoning loop execution
- Adaptive strategy selection and escalation
- Resource extraction + reasoning
- Command processing + reasoning

**Example Integration Test:**
```python
# tests/integration/test_adaptive_reasoning.py
async def test_adaptive_reasoning_with_escalation():
    """Test adaptive reasoning loop with quality-driven escalation."""
    # Setup
    claude = Claude(model="claude-sonnet-4.5")
    conversation = Conversation()
    tool_registry = ToolRegistry()
    # ... setup reasoning components
    
    adaptive_loop = AdaptiveReasoningLoop(...)
    
    result = await adaptive_loop.run("Research topic X")
    
    assert len(result) > 0
    assert adaptive_loop.analyzer.call_count > 0
    assert adaptive_loop.evaluator.call_count > 0
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
