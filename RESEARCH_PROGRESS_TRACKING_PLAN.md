# Research Progress Tracking System - Implementation Plan

## Executive Summary

This document outlines a comprehensive plan to implement a **Research Progress Tracker** that preserves context, avoids redundant work, and enables intelligent escalation across query execution phases (DIRECT → LIGHT_PLANNING → DEEP_REASONING).

**Current Problem**: When queries escalate from one execution strategy to another, valuable context is lost:
- Evaluation feedback explaining WHY previous attempts failed
- Tool execution history and results
- Partial results from incomplete attempts
- Research plans and subtask progress
- Quality scores and missing aspects

**Proposed Solution**: Introduce a flexible, serializable data structure (`ResearchProgressTracker`) that:
1. Tracks execution state across all escalation phases
2. Records tool executions to avoid redundant calls
3. Preserves evaluation feedback to guide subsequent attempts
4. Maintains a plan skeleton showing completed/pending steps
5. Serializes to natural language context for LLM consumption

---

## 1. Architecture Overview

### 1.1 Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                 AdaptiveReasoningLoop                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         ResearchProgressTracker (NEW)                 │  │
│  │  - Execution history across phases                    │  │
│  │  - Tool execution log                                 │  │
│  │  - Evaluation feedback                                │  │
│  │  - Plan skeleton with step status                     │  │
│  │  - Serialization to context text                      │  │
│  └───────────────────────────────────────────────────────┘  │
│         ↓                  ↓                  ↓              │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐          │
│  │  DIRECT  │  →   │  LIGHT   │  →   │   DEEP   │          │
│  │ Strategy │      │ Planning │      │ Reasoning│          │
│  └──────────┘      └──────────┘      └──────────┘          │
│       │                 │                 │                 │
│       └─────────────────┴─────────────────┘                 │
│              All update tracker state                       │
└─────────────────────────────────────────────────────────────┘

Integration Points:
- QueryComplexityAnalyzer: Initial assessment → tracker
- Planner: Research plans → tracker plan skeleton
- AgentLoop: Tool executions → tracker tool log
- Evaluator: Quality feedback → tracker evaluations
- Synthesizer: Partial results → tracker insights
```

### 1.2 Data Flow

```
User Query
    ↓
[1. Initialize Tracker] → ResearchProgressTracker created
    ↓
[2. Analyze Complexity] → Store ComplexityAnalysis in tracker
    ↓
[3. Execute Strategy] → Update tracker with:
    │                    - Tool executions
    │                    - Partial results
    │                    - Plan progress
    ↓
[4. Evaluate Quality] → Store EvaluationResult in tracker
    ↓
[5. Escalate?] → YES: Pass tracker to next strategy
                      → Tracker serialized to context
                      → Next strategy reads "what's been tried"
    ↓
[6. Repeat 3-5] → Build upon previous work
    ↓
[7. Final Response] → Tracker available for session persistence
```

---

## 2. Data Structures Design

### 2.1 ResearchProgressTracker

**Location**: `src/nxs/application/progress_tracker.py`

```python
@dataclass
class ExecutionAttempt:
    """Record of a single execution attempt at a specific strategy level."""
    strategy: ExecutionStrategy
    started_at: datetime
    completed_at: Optional[datetime]
    status: Literal["in_progress", "completed", "failed", "escalated"]

    # What was produced
    response: Optional[str]
    accumulated_results: list[str]  # Intermediate results from iterations

    # Quality assessment
    evaluation: Optional[EvaluationResult]
    quality_score: Optional[float]

    # Why it ended
    outcome: str  # "Quality sufficient" | "Escalated due to low quality" | "Error occurred"


@dataclass
class ToolExecution:
    """Record of a tool call and its result."""
    tool_name: str
    arguments: dict[str, Any]
    executed_at: datetime
    strategy: ExecutionStrategy  # Which strategy level called it

    # Result tracking
    success: bool
    result: Optional[str]  # Tool output if successful
    error: Optional[str]   # Error message if failed

    # Metadata
    execution_time_ms: float
    result_hash: str  # Hash of arguments for deduplication


@dataclass
class PlanStep:
    """A step in the research plan with execution status."""
    id: str  # Unique identifier
    description: str
    status: Literal["pending", "in_progress", "completed", "skipped", "failed"]

    # Execution tracking
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    # Results
    findings: list[str]  # Key findings from this step
    tools_used: list[str]  # Tool names used in this step

    # Relationships
    depends_on: list[str]  # IDs of prerequisite steps
    spawned_from: Optional[str]  # ID of parent step if dynamically added


@dataclass
class ResearchPlanSkeleton:
    """High-level plan structure tracking progress."""
    created_at: datetime
    created_by: ExecutionStrategy  # Which strategy created this plan

    query: str
    complexity_analysis: ComplexityAnalysis

    steps: list[PlanStep]
    current_step_id: Optional[str]

    # Plan evolution
    revision_count: int  # Incremented when plan is refined
    last_updated: datetime

    def get_completed_steps(self) -> list[PlanStep]:
        """Return all completed steps."""
        return [s for s in self.steps if s.status == "completed"]

    def get_pending_steps(self) -> list[PlanStep]:
        """Return steps not yet started."""
        return [s for s in self.steps if s.status == "pending"]

    def add_dynamic_step(self, step: PlanStep, after_step_id: str):
        """Insert a new step discovered during execution."""
        # Implementation: Insert step after specified ID
        pass


@dataclass
class AccumulatedInsights:
    """Key insights gathered across all execution attempts."""

    # Categorical storage
    confirmed_facts: list[str]  # High-confidence findings
    partial_findings: list[str]  # Low-confidence or incomplete findings
    knowledge_gaps: list[str]   # Identified missing information

    # From evaluations
    quality_feedback: list[str]  # Reasons for quality issues
    recommended_improvements: list[str]  # Suggestions from evaluator

    # Tool-related
    successful_tool_results: dict[str, str]  # tool_name → best result
    failed_tool_attempts: dict[str, str]     # tool_name → error

    def add_from_evaluation(self, evaluation: EvaluationResult):
        """Extract insights from an evaluation result."""
        self.knowledge_gaps.extend(evaluation.missing_aspects)
        self.quality_feedback.append(evaluation.reasoning)
        self.recommended_improvements.extend(evaluation.additional_queries)


class ResearchProgressTracker:
    """
    Central tracker for research progress across execution strategies.

    Responsibilities:
    - Track execution history across all escalation phases
    - Log tool executions to avoid redundant calls
    - Maintain research plan skeleton with step progress
    - Preserve evaluation feedback and insights
    - Serialize state to context for LLM consumption
    """

    def __init__(self, query: str, complexity: ComplexityAnalysis):
        self.query = query
        self.complexity = complexity
        self.created_at = datetime.now()

        # Execution tracking
        self.attempts: list[ExecutionAttempt] = []
        self.current_attempt: Optional[ExecutionAttempt] = None
        self.current_strategy: Optional[ExecutionStrategy] = None

        # Tool tracking
        self.tool_executions: list[ToolExecution] = []
        self._tool_result_cache: dict[str, str] = {}  # Hash → result

        # Plan tracking
        self.plan: Optional[ResearchPlanSkeleton] = None

        # Insights accumulation
        self.insights = AccumulatedInsights(
            confirmed_facts=[],
            partial_findings=[],
            knowledge_gaps=[],
            quality_feedback=[],
            recommended_improvements=[],
            successful_tool_results={},
            failed_tool_attempts={}
        )

    # === Execution Management ===

    def start_attempt(self, strategy: ExecutionStrategy):
        """Begin a new execution attempt at specified strategy level."""
        self.current_strategy = strategy
        self.current_attempt = ExecutionAttempt(
            strategy=strategy,
            started_at=datetime.now(),
            completed_at=None,
            status="in_progress",
            response=None,
            accumulated_results=[],
            evaluation=None,
            quality_score=None,
            outcome=""
        )
        self.attempts.append(self.current_attempt)

    def end_attempt(self, outcome: str, response: str = None,
                   evaluation: EvaluationResult = None, quality_score: float = None):
        """Complete the current execution attempt."""
        if self.current_attempt:
            self.current_attempt.completed_at = datetime.now()
            self.current_attempt.status = "completed" if quality_score and quality_score >= 0.6 else "escalated"
            self.current_attempt.response = response
            self.current_attempt.evaluation = evaluation
            self.current_attempt.quality_score = quality_score
            self.current_attempt.outcome = outcome

            # Extract insights from evaluation
            if evaluation:
                self.insights.add_from_evaluation(evaluation)

    # === Tool Tracking ===

    def should_execute_tool(self, tool_name: str, arguments: dict) -> tuple[bool, Optional[str]]:
        """
        Check if tool should be executed or if we have cached result.

        Returns:
            (should_execute, cached_result)
            - (True, None): Execute the tool
            - (False, result): Skip execution, use cached result
        """
        arg_hash = self._hash_arguments(tool_name, arguments)

        # Check cache
        if arg_hash in self._tool_result_cache:
            return False, self._tool_result_cache[arg_hash]

        # Check if same tool+args failed before
        for exec in self.tool_executions:
            if exec.tool_name == tool_name and exec.result_hash == arg_hash:
                if not exec.success:
                    # Failed before, but might be worth retrying in different context
                    # Return True but log warning
                    return True, None

        return True, None

    def log_tool_execution(self, tool_name: str, arguments: dict,
                          success: bool, result: str = None, error: str = None,
                          execution_time_ms: float = 0):
        """Record a tool execution."""
        arg_hash = self._hash_arguments(tool_name, arguments)

        execution = ToolExecution(
            tool_name=tool_name,
            arguments=arguments,
            executed_at=datetime.now(),
            strategy=self.current_strategy,
            success=success,
            result=result,
            error=error,
            execution_time_ms=execution_time_ms,
            result_hash=arg_hash
        )

        self.tool_executions.append(execution)

        # Cache successful results
        if success and result:
            self._tool_result_cache[arg_hash] = result
            self.insights.successful_tool_results[tool_name] = result
        elif not success and error:
            self.insights.failed_tool_attempts[tool_name] = error

        # Update current attempt
        if self.current_attempt:
            self.current_attempt.accumulated_results.append(result or f"Error: {error}")

    def _hash_arguments(self, tool_name: str, arguments: dict) -> str:
        """Generate deterministic hash for tool+arguments."""
        import hashlib
        import json
        combined = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
        return hashlib.md5(combined.encode()).hexdigest()

    # === Plan Management ===

    def set_plan(self, plan: ResearchPlan, strategy: ExecutionStrategy):
        """Initialize or update the research plan skeleton."""
        if self.plan is None:
            # First plan - convert ResearchPlan to PlanSkeleton
            self.plan = ResearchPlanSkeleton(
                created_at=datetime.now(),
                created_by=strategy,
                query=plan.original_query,
                complexity_analysis=plan.complexity_analysis or self.complexity,
                steps=[
                    PlanStep(
                        id=f"step_{i}",
                        description=subtask.description,
                        status="pending",
                        started_at=None,
                        completed_at=None,
                        findings=[],
                        tools_used=[],
                        depends_on=[],
                        spawned_from=None
                    )
                    for i, subtask in enumerate(plan.subtasks)
                ],
                current_step_id=None,
                revision_count=0,
                last_updated=datetime.now()
            )
        else:
            # Refine existing plan
            self._refine_plan(plan, strategy)

    def _refine_plan(self, new_plan: ResearchPlan, strategy: ExecutionStrategy):
        """Merge new plan with existing plan skeleton."""
        # Strategy: Keep completed steps, add new steps from refined plan

        completed_step_ids = {s.id for s in self.plan.get_completed_steps()}

        # Add new steps not in original plan
        existing_descriptions = {s.description for s in self.plan.steps}
        new_steps = []

        for i, subtask in enumerate(new_plan.subtasks):
            if subtask.description not in existing_descriptions:
                new_step = PlanStep(
                    id=f"step_{len(self.plan.steps) + len(new_steps)}",
                    description=subtask.description,
                    status="pending",
                    started_at=None,
                    completed_at=None,
                    findings=[],
                    tools_used=[],
                    depends_on=[],
                    spawned_from=self.plan.current_step_id  # Track origin
                )
                new_steps.append(new_step)

        self.plan.steps.extend(new_steps)
        self.plan.revision_count += 1
        self.plan.last_updated = datetime.now()

    def update_step_status(self, step_id: str, status: str, findings: list[str] = None):
        """Update a plan step's status and findings."""
        if not self.plan:
            return

        for step in self.plan.steps:
            if step.id == step_id:
                step.status = status
                if status == "in_progress" and not step.started_at:
                    step.started_at = datetime.now()
                    self.plan.current_step_id = step_id
                elif status == "completed":
                    step.completed_at = datetime.now()
                    if findings:
                        step.findings.extend(findings)
                break

    # === Context Serialization ===

    def to_context_text(self, strategy: ExecutionStrategy) -> str:
        """
        Serialize tracker state to natural language context for LLM.

        This text is included in the system prompt or user message to inform
        the LLM about what has already been tried and what remains.
        """
        sections = []

        # 1. Query and Complexity Overview
        sections.append(f"# Research Progress Context\n")
        sections.append(f"**Query**: {self.query}\n")
        sections.append(f"**Complexity**: {self.complexity.complexity_level.value}")
        sections.append(f"**Current Execution Level**: {strategy.value}\n")

        # 2. Execution History
        if self.attempts:
            sections.append("\n## Previous Execution Attempts\n")
            for i, attempt in enumerate(self.attempts[:-1], 1):  # Exclude current
                sections.append(f"\n### Attempt {i}: {attempt.strategy.value}")
                sections.append(f"- **Status**: {attempt.status}")
                sections.append(f"- **Quality Score**: {attempt.quality_score or 'N/A'}")

                if attempt.evaluation:
                    sections.append(f"- **Evaluation**: {attempt.evaluation.reasoning}")
                    if attempt.evaluation.missing_aspects:
                        sections.append(f"- **Missing Aspects**: {', '.join(attempt.evaluation.missing_aspects)}")

                sections.append(f"- **Outcome**: {attempt.outcome}\n")

        # 3. Research Plan Progress
        if self.plan:
            sections.append("\n## Research Plan Progress\n")

            completed = self.plan.get_completed_steps()
            pending = self.plan.get_pending_steps()

            sections.append(f"**Plan Status**: {len(completed)}/{len(self.plan.steps)} steps completed\n")

            if completed:
                sections.append("\n### ✓ Completed Steps\n")
                for step in completed:
                    sections.append(f"- **{step.description}**")
                    if step.findings:
                        sections.append(f"  - Findings: {'; '.join(step.findings)}")
                    if step.tools_used:
                        sections.append(f"  - Tools used: {', '.join(step.tools_used)}")
                sections.append("")

            if pending:
                sections.append("\n### ○ Pending Steps\n")
                for step in pending:
                    sections.append(f"- {step.description}")
                sections.append("")

        # 4. Tool Execution Summary
        if self.tool_executions:
            sections.append("\n## Tool Execution History\n")

            successful_tools = [e for e in self.tool_executions if e.success]
            failed_tools = [e for e in self.tool_executions if not e.success]

            sections.append(f"**Total tool calls**: {len(self.tool_executions)} "
                          f"({len(successful_tools)} successful, {len(failed_tools)} failed)\n")

            if successful_tools:
                sections.append("\n### Successful Tool Executions\n")
                # Group by tool name
                from collections import defaultdict
                by_tool = defaultdict(list)
                for e in successful_tools:
                    by_tool[e.tool_name].append(e)

                for tool_name, executions in by_tool.items():
                    sections.append(f"- **{tool_name}**: {len(executions)} call(s)")
                    # Show most recent result (truncated)
                    latest = executions[-1]
                    if latest.result:
                        preview = latest.result[:200] + "..." if len(latest.result) > 200 else latest.result
                        sections.append(f"  - Latest result: {preview}")
                sections.append("")

            if failed_tools:
                sections.append("\n### Failed Tool Executions\n")
                for e in failed_tools:
                    sections.append(f"- **{e.tool_name}**: {e.error}")
                sections.append("")

        # 5. Accumulated Insights
        sections.append("\n## Accumulated Insights\n")

        if self.insights.confirmed_facts:
            sections.append("\n### Confirmed Facts\n")
            for fact in self.insights.confirmed_facts:
                sections.append(f"- {fact}")
            sections.append("")

        if self.insights.knowledge_gaps:
            sections.append("\n### Identified Knowledge Gaps\n")
            for gap in self.insights.knowledge_gaps:
                sections.append(f"- {gap}")
            sections.append("")

        if self.insights.quality_feedback:
            sections.append("\n### Quality Feedback from Previous Attempts\n")
            for feedback in self.insights.quality_feedback[-3:]:  # Last 3
                sections.append(f"- {feedback}")
            sections.append("")

        # 6. Guidance for Current Attempt
        sections.append("\n## Guidance for Current Execution\n")

        if strategy != ExecutionStrategy.DIRECT:
            sections.append("**Building on previous work**:\n")
            sections.append("- Review completed steps and their findings above")
            sections.append("- Focus on identified knowledge gaps")
            sections.append("- Avoid redundant tool calls (check execution history)")
            sections.append("- Address quality feedback from previous evaluations")

            if self.insights.recommended_improvements:
                sections.append("\n**Recommended improvements**:\n")
                for rec in self.insights.recommended_improvements[:5]:  # Top 5
                    sections.append(f"- {rec}")

        return "\n".join(sections)

    def to_compact_context(self) -> str:
        """
        Compact version of context for token efficiency.

        Use this when full context would be too verbose.
        """
        parts = []

        # Summary line
        completed_steps = len(self.plan.get_completed_steps()) if self.plan else 0
        total_steps = len(self.plan.steps) if self.plan else 0
        parts.append(f"Progress: {len(self.attempts)} attempts, "
                    f"{len(self.tool_executions)} tool calls, "
                    f"{completed_steps}/{total_steps} steps done")

        # Key gaps
        if self.insights.knowledge_gaps:
            parts.append(f"Gaps: {', '.join(self.insights.knowledge_gaps[:3])}")

        # Available cached results
        if self._tool_result_cache:
            parts.append(f"Cached: {', '.join(self._tool_result_cache.keys())}")

        return " | ".join(parts)

    # === Persistence ===

    def to_dict(self) -> dict:
        """Serialize to dictionary for session persistence."""
        from dataclasses import asdict
        return {
            "query": self.query,
            "complexity": asdict(self.complexity),
            "created_at": self.created_at.isoformat(),
            "attempts": [asdict(a) for a in self.attempts],
            "tool_executions": [asdict(t) for t in self.tool_executions],
            "plan": asdict(self.plan) if self.plan else None,
            "insights": asdict(self.insights)
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResearchProgressTracker":
        """Deserialize from dictionary."""
        # Implementation: Reconstruct tracker from saved state
        pass
```

---

## 3. Integration Plan

### 3.1 AdaptiveReasoningLoop Integration

**File**: `src/nxs/application/reasoning_loop.py`

**Changes Required**:

```python
class AdaptiveReasoningLoop(AgentLoop):

    async def run(
        self,
        query: str,
        *,
        stream: bool = True,
        initial_strategy: ExecutionStrategy | None = None,
        enable_reasoning: bool = False,
    ) -> str:
        """Execute query with adaptive reasoning and quality evaluation."""

        # STEP 1: Analyze complexity (existing)
        complexity = await self.analyzer.analyze(query, available_tools)

        # NEW: Initialize progress tracker
        tracker = ResearchProgressTracker(query, complexity)

        # STEP 2: Determine initial strategy (existing)
        current_strategy = self._determine_initial_strategy(...)

        # STEP 3: Execution loop with escalation
        max_escalations = 2
        for escalation_level in range(max_escalations + 1):

            # NEW: Start execution attempt
            tracker.start_attempt(current_strategy)

            # Execute strategy (existing, but now with tracker)
            if current_strategy == ExecutionStrategy.DIRECT:
                response = await self._execute_direct(query, tracker)
            elif current_strategy == ExecutionStrategy.LIGHT_PLANNING:
                response = await self._execute_light_planning(query, complexity, tracker)
            else:
                response = await self._execute_deep_reasoning(query, complexity, tracker)

            # Evaluate quality (existing)
            evaluation = await self._evaluate_response_quality(...)
            quality_score = evaluation.confidence

            # NEW: Record attempt outcome
            tracker.end_attempt(
                outcome="Quality sufficient" if evaluation.is_complete else "Escalated",
                response=response,
                evaluation=evaluation,
                quality_score=quality_score
            )

            # Check if escalation needed (existing logic)
            if evaluation.is_complete or quality_score >= threshold:
                # Success! Return response
                # NEW: Optionally persist tracker for session history
                await self._persist_tracker(tracker)
                return response

            # Escalate (existing)
            next_strategy = self._get_next_strategy(current_strategy)
            if next_strategy == current_strategy:
                # Already at highest level
                return response

            # NEW: Log escalation reason from evaluation
            logger.info(f"Escalating from {current_strategy} to {next_strategy}: "
                       f"{evaluation.reasoning}")

            current_strategy = next_strategy
            # Loop continues with tracker carrying forward all context

        return response
```

**Key Points**:
- Create tracker at beginning of `run()`
- Pass tracker to all strategy execution methods
- Tracker accumulates state across escalations
- Tracker persisted at end for session history

### 3.2 Strategy Method Integration

**File**: `src/nxs/application/reasoning_loop.py`

#### 3.2.1 Direct Strategy

```python
async def _execute_direct(
    self,
    query: str,
    tracker: ResearchProgressTracker  # NEW parameter
) -> str:
    """Execute query directly without explicit planning."""

    # NEW: Add tracker context if this is an escalation
    if len(tracker.attempts) > 1:
        # This is a retry after failed attempt
        context_text = tracker.to_compact_context()
        enhanced_query = f"{query}\n\n[Previous attempt context: {context_text}]"
    else:
        enhanced_query = query

    # Execute via base AgentLoop (existing)
    # NEW: Wrap to intercept tool calls
    response = await self._execute_with_tool_tracking(
        enhanced_query,
        tracker=tracker,
        stream=False
    )

    return response
```

#### 3.2.2 Light Planning Strategy

```python
async def _execute_light_planning(
    self,
    query: str,
    complexity: ComplexityAnalysis,
    tracker: ResearchProgressTracker  # NEW parameter
) -> str:
    """Execute query with lightweight planning."""

    # Generate or refine plan
    if tracker.plan is None:
        # First planning attempt
        plan = await self.planner.generate_plan(query, context={"mode": "light", ...})
        tracker.set_plan(plan, ExecutionStrategy.LIGHT_PLANNING)
    else:
        # Refine existing plan based on gaps
        plan_context = {
            "mode": "light",
            "previous_attempts": len(tracker.attempts),
            "knowledge_gaps": tracker.insights.knowledge_gaps,
            "completed_steps": [s.description for s in tracker.plan.get_completed_steps()]
        }
        plan = await self.planner.generate_plan(query, context=plan_context)
        tracker.set_plan(plan, ExecutionStrategy.LIGHT_PLANNING)

    # Execute plan steps
    accumulated_results = []
    max_iters = min(2, complexity.estimated_iterations)

    for i in range(max_iters):
        if i >= len(tracker.plan.steps):
            break

        step = tracker.plan.steps[i]

        # Skip already completed steps
        if step.status == "completed":
            accumulated_results.append(f"[Cached] {step.description}: {'; '.join(step.findings)}")
            continue

        # Execute step
        tracker.update_step_status(step.id, "in_progress")

        subtask_query = self._build_subtask_query(step, tracker)
        result = await self._execute_with_tool_tracking(
            subtask_query,
            tracker=tracker,
            stream=False
        )

        accumulated_results.append(result)
        tracker.update_step_status(step.id, "completed", findings=[result])

    # Synthesize (existing)
    response = await self.synthesizer.synthesize(query, accumulated_results, mode="light")

    return response


def _build_subtask_query(self, step: PlanStep, tracker: ResearchProgressTracker) -> str:
    """Build query for a subtask incorporating tracker context."""

    base_query = step.description

    # Add context from completed steps
    completed = tracker.plan.get_completed_steps()
    if completed:
        context_parts = [f"- {s.description}: {'; '.join(s.findings)}" for s in completed[-3:]]
        context = "\n".join(context_parts)
        base_query = f"{base_query}\n\nRelevant findings from previous steps:\n{context}"

    # Add knowledge gaps to address
    if tracker.insights.knowledge_gaps:
        gaps = "\n".join(f"- {g}" for g in tracker.insights.knowledge_gaps[:3])
        base_query = f"{base_query}\n\nAddress these knowledge gaps if relevant:\n{gaps}"

    return base_query
```

#### 3.2.3 Deep Reasoning Strategy

```python
async def _execute_deep_reasoning(
    self,
    query: str,
    complexity: ComplexityAnalysis,
    tracker: ResearchProgressTracker  # NEW parameter
) -> str:
    """Execute query with deep reasoning and iterative refinement."""

    # Generate comprehensive plan
    plan_context = {
        "mode": "deep",
        "complexity": complexity,
        "available_tools": [t["name"] for t in self.tool_registry.get_tool_definitions_for_api()],
    }

    # NEW: Add previous attempt context if escalated
    if len(tracker.attempts) > 1:
        plan_context["previous_attempts"] = [
            {
                "strategy": a.strategy.value,
                "quality": a.quality_score,
                "evaluation": a.evaluation.reasoning if a.evaluation else None
            }
            for a in tracker.attempts[:-1]  # Exclude current
        ]
        plan_context["knowledge_gaps"] = tracker.insights.knowledge_gaps
        plan_context["completed_steps"] = [
            s.description for s in tracker.plan.get_completed_steps()
        ] if tracker.plan else []

    plan = await self.planner.generate_plan(query, context=plan_context)

    if tracker.plan is None:
        tracker.set_plan(plan, ExecutionStrategy.DEEP_REASONING)
    else:
        # Refine existing plan
        tracker.set_plan(plan, ExecutionStrategy.DEEP_REASONING)

    # Iterative execution with evaluation
    accumulated_results = []
    max_iterations = min(3, len(tracker.plan.steps))

    for iteration in range(max_iterations):
        # Find next pending step
        pending_steps = tracker.plan.get_pending_steps()
        if not pending_steps:
            break

        step = pending_steps[0]
        tracker.update_step_status(step.id, "in_progress")

        # Execute step with full context
        subtask_query = self._build_subtask_query_with_full_context(step, tracker)
        result = await self._execute_with_tool_tracking(
            subtask_query,
            tracker=tracker,
            stream=False
        )

        accumulated_results.append(result)
        tracker.update_step_status(step.id, "completed", findings=[result])

        # Evaluate research completeness (existing)
        eval_result = await self.evaluator.evaluate(query, accumulated_results, tracker.plan)

        # NEW: Store evaluation insights
        tracker.insights.add_from_evaluation(eval_result)

        if eval_result.is_complete:
            break

        # Add dynamic subtasks if needed
        if eval_result.additional_queries:
            for add_query in eval_result.additional_queries:
                new_step = PlanStep(
                    id=f"step_dynamic_{iteration}_{len(tracker.plan.steps)}",
                    description=add_query,
                    status="pending",
                    started_at=None,
                    completed_at=None,
                    findings=[],
                    tools_used=[],
                    depends_on=[step.id],
                    spawned_from=step.id
                )
                tracker.plan.steps.append(new_step)

    # Advanced synthesis (existing)
    filtered = await self.synthesizer.filter_results(accumulated_results, query)
    response = await self.synthesizer.synthesize(query, filtered, mode="deep")

    return response


def _build_subtask_query_with_full_context(
    self,
    step: PlanStep,
    tracker: ResearchProgressTracker
) -> str:
    """Build subtask query with comprehensive tracker context."""

    # Use full context serialization
    context_text = tracker.to_context_text(ExecutionStrategy.DEEP_REASONING)

    subtask_query = f"""
{step.description}

{context_text}

Focus on addressing the identified knowledge gaps and building upon completed work.
Avoid redundant tool calls - check the tool execution history above.
"""

    return subtask_query
```

### 3.3 Tool Execution Interception

**File**: `src/nxs/core/agentic_loop.py`

**New Method in AgentLoop**:

```python
class AgentLoop:

    def __init__(self, ...):
        # ...existing...
        self._current_tracker: Optional[ResearchProgressTracker] = None

    async def _execute_with_tool_tracking(
        self,
        query: str,
        tracker: ResearchProgressTracker,
        stream: bool = False
    ) -> str:
        """
        Execute query with tool call tracking.

        Wrapper around base run() that intercepts tool executions
        and logs them to the tracker.
        """
        self._current_tracker = tracker

        try:
            response = await self.run(query, stream=stream)
            return response
        finally:
            self._current_tracker = None


    async def _execute_tools(
        self,
        tool_blocks: list[ToolUseBlock],
        callbacks: AgentCallbacks | None = None,
    ) -> list[ToolResultBlockParam]:
        """
        Execute tool calls (MODIFIED to integrate tracker).
        """
        results = []

        for tool_block in tool_blocks:
            tool_name = tool_block.name
            arguments = tool_block.input

            # NEW: Check tracker for cached result
            if self._current_tracker:
                should_execute, cached_result = self._current_tracker.should_execute_tool(
                    tool_name, arguments
                )

                if not should_execute:
                    logger.info(f"Using cached result for {tool_name}")
                    results.append(
                        ToolResultBlockParam(
                            type="tool_result",
                            tool_use_id=tool_block.id,
                            content=cached_result,
                        )
                    )
                    continue

            # Check approval (existing)
            if self.approval_manager:
                approved = await self.approval_manager.request_approval(...)
                if not approved:
                    # ...existing denial logic...
                    continue

            # Execute tool (existing)
            start_time = time.time()
            try:
                result_content = await self.tool_registry.execute_tool(tool_name, arguments)
                execution_time = (time.time() - start_time) * 1000
                success = True
                error = None

            except Exception as e:
                result_content = f"Error: {str(e)}"
                execution_time = (time.time() - start_time) * 1000
                success = False
                error = str(e)

            # NEW: Log to tracker
            if self._current_tracker:
                self._current_tracker.log_tool_execution(
                    tool_name=tool_name,
                    arguments=arguments,
                    success=success,
                    result=result_content if success else None,
                    error=error,
                    execution_time_ms=execution_time
                )

            # Add to conversation (existing)
            results.append(
                ToolResultBlockParam(
                    type="tool_result",
                    tool_use_id=tool_block.id,
                    content=result_content,
                )
            )

        return results
```

### 3.4 Planner Integration

**File**: `src/nxs/application/planner.py`

**Modify `generate_plan()` to accept tracker context**:

```python
class Planner:

    async def generate_plan(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> ResearchPlan:
        """
        Generate research plan with optional context from tracker.

        Context can include:
        - mode: "light" | "deep"
        - previous_attempts: list of attempt summaries
        - knowledge_gaps: identified gaps from evaluations
        - completed_steps: steps already done in previous attempts
        - available_tools: tool names available
        """
        context = context or {}
        mode = context.get("mode", "deep")

        # Build prompt with tracker context
        prompt_parts = [self._base_planning_prompt(query)]

        # Add previous attempt context
        if "previous_attempts" in context:
            prompt_parts.append("\n## Previous Execution Attempts\n")
            for attempt in context["previous_attempts"]:
                prompt_parts.append(
                    f"- {attempt['strategy']}: Quality {attempt['quality']}, "
                    f"Evaluation: {attempt['evaluation']}"
                )

        # Add completed work
        if "completed_steps" in context and context["completed_steps"]:
            prompt_parts.append("\n## Already Completed Steps\n")
            prompt_parts.append("Build upon these completed steps:\n")
            for step_desc in context["completed_steps"]:
                prompt_parts.append(f"- {step_desc}")

        # Add knowledge gaps
        if "knowledge_gaps" in context and context["knowledge_gaps"]:
            prompt_parts.append("\n## Knowledge Gaps to Address\n")
            for gap in context["knowledge_gaps"]:
                prompt_parts.append(f"- {gap}")

        # Add available tools
        if "available_tools" in context:
            prompt_parts.append(f"\n## Available Tools\n")
            prompt_parts.append(f"{', '.join(context['available_tools'])}")

        enhanced_prompt = "\n".join(prompt_parts)

        # Call LLM to generate plan (existing logic)
        # ...
```

---

## 4. Context Injection Strategy

### 4.1 When to Include Tracker Context

**Decision Tree**:

```
Is this the first attempt (no escalation)?
├─ YES → Use minimal context (query + complexity only)
└─ NO  → Include tracker context
    ├─ Strategy = DIRECT → Use compact context
    ├─ Strategy = LIGHT_PLANNING → Use medium context (plan + gaps)
    └─ Strategy = DEEP_REASONING → Use full context
```

### 4.2 Context Verbosity Levels

1. **Minimal** (first attempt):
   - Query
   - Complexity analysis

2. **Compact** (DIRECT escalation):
   - Summary line: "Progress: X attempts, Y tool calls, Z/W steps"
   - Top 3 knowledge gaps
   - Available cached tool results

3. **Medium** (LIGHT_PLANNING):
   - Completed steps with findings
   - Pending steps
   - Tool execution summary (grouped by tool name)
   - Knowledge gaps

4. **Full** (DEEP_REASONING):
   - Complete execution history
   - Detailed plan progress
   - Full tool execution log
   - All accumulated insights
   - Quality feedback from evaluations

### 4.3 Token Budget Management

**Strategy**: Use Anthropic's prompt caching to reduce costs

```python
def _build_messages_with_tracker_context(
    self,
    query: str,
    tracker: ResearchProgressTracker,
    strategy: ExecutionStrategy
) -> list[MessageParam]:
    """Build message list with tracker context and cache control."""

    messages = []

    # System message with tracker context (CACHED)
    context_text = self._get_context_for_strategy(tracker, strategy)

    system_message = {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": context_text,
                "cache_control": {"type": "ephemeral"}  # Cache this
            }
        ]
    }

    # User query (NOT cached - changes each time)
    user_message = {
        "role": "user",
        "content": query
    }

    messages.extend([system_message, user_message])

    return messages


def _get_context_for_strategy(
    self,
    tracker: ResearchProgressTracker,
    strategy: ExecutionStrategy
) -> str:
    """Get appropriate context verbosity for strategy."""

    if len(tracker.attempts) == 1:
        # First attempt - minimal context
        return f"Query: {tracker.query}\nComplexity: {tracker.complexity.complexity_level.value}"

    if strategy == ExecutionStrategy.DIRECT:
        return tracker.to_compact_context()
    elif strategy == ExecutionStrategy.LIGHT_PLANNING:
        return tracker.to_context_text(strategy)  # Medium detail
    else:  # DEEP_REASONING
        return tracker.to_context_text(strategy)  # Full detail
```

**Benefits**:
- Tracker context is marked for caching
- Reduces token costs on repeated calls
- Context reused across subtask iterations

---

## 5. Benefits and Expected Outcomes

### 5.1 Eliminates Redundant Work

**Before**:
```
LIGHT strategy:
  - Calls tool "web_search" with query "X"
  - Gets result R1
  - Quality insufficient → Escalate

DEEP strategy:
  - Starts fresh
  - Calls tool "web_search" with query "X" AGAIN
  - Gets same result R1 (redundant API call)
```

**After**:
```
LIGHT strategy:
  - Calls tool "web_search" with query "X"
  - Gets result R1
  - Tracker logs: tool_executions.append(ToolExecution(...))
  - Quality insufficient → Escalate

DEEP strategy:
  - Checks tracker: should_execute_tool("web_search", {"query": "X"})
  - Returns: (False, R1)  # Cached!
  - Uses R1 without re-executing
```

**Impact**:
- Reduces API calls to expensive tools (web search, database queries)
- Faster execution (no wait for redundant operations)
- Lower costs

### 5.2 Intelligent Escalation

**Before**:
```
Evaluation: "Response lacks depth and doesn't address X"
→ Escalate to DEEP
→ DEEP has no idea what "lacks depth" means or what X is
```

**After**:
```
Evaluation: "Response lacks depth and doesn't address X"
→ Tracker stores: insights.knowledge_gaps.append("X not addressed")
→ Escalate to DEEP
→ DEEP reads context: "Previous attempt missing: X not addressed"
→ DEEP focuses specifically on addressing X
```

**Impact**:
- Targeted improvement instead of random retry
- Higher success rate on escalation
- Fewer unnecessary escalations

### 5.3 Progressive Refinement

**Before**:
```
LIGHT planning:
  - Creates plan: [Step 1, Step 2]
  - Executes Step 1 → Finding F1
  - Quality insufficient → Escalate
  - Plan discarded

DEEP reasoning:
  - Creates new plan: [Step A, Step B, Step C]
  - Re-executes Step 1 (which is Step A) → Same finding F1
```

**After**:
```
LIGHT planning:
  - Creates plan skeleton: [Step 1, Step 2]
  - Executes Step 1 → Finding F1
  - Marks Step 1 as completed
  - Quality insufficient → Escalate

DEEP reasoning:
  - Receives plan skeleton with Step 1 completed
  - Refines plan: [Step 1 (✓), Step 2, Step 3 (new)]
  - Skips Step 1 (already done)
  - Uses F1 as context for Step 2
  - Executes only Step 2 and 3
```

**Impact**:
- Builds upon previous work
- Faster completion (skip done steps)
- Consistent progress tracking

### 5.4 Better LLM Guidance

**Context-aware prompts**:

```
# Without tracker
Query: "Analyze the performance of our API"

# With tracker (after escalation)
Query: "Analyze the performance of our API"

Context:
## Previous Attempt (LIGHT_PLANNING)
- Quality Score: 0.65
- Missing Aspects: latency distribution, error rates
- Tools Used: logs_query (successful)

## Completed Steps
✓ Retrieved recent API logs (200 requests)
  - Findings: Average response time 250ms

## Knowledge Gaps
- Latency distribution across endpoints
- Error rates by endpoint
- Performance during peak hours

## Guidance
Focus on the identified gaps. Logs are already retrieved (cached).
```

**Impact**:
- LLM knows exactly what to focus on
- Avoids repeating successful parts
- Produces more targeted responses

---

## 6. Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

**Goals**: Implement basic data structures and tracker lifecycle

**Tasks**:
1. Create `progress_tracker.py` with core classes:
   - `ExecutionAttempt`
   - `ToolExecution`
   - `PlanStep`
   - `ResearchPlanSkeleton`
   - `AccumulatedInsights`
   - `ResearchProgressTracker`

2. Implement tracker methods:
   - `start_attempt()` / `end_attempt()`
   - `log_tool_execution()`
   - `set_plan()` / `update_step_status()`
   - `to_dict()` / `from_dict()` for persistence

3. Add basic serialization:
   - `to_context_text()` - full version
   - `to_compact_context()` - minimal version

**Testing**:
- Unit tests for tracker state management
- Serialization round-trip tests
- Edge cases (empty tracker, no tools, etc.)

### Phase 2: AgentLoop Integration (Week 2)

**Goals**: Integrate tracker into tool execution flow

**Tasks**:
1. Modify `AgentLoop`:
   - Add `_current_tracker` field
   - Implement `_execute_with_tool_tracking()`
   - Modify `_execute_tools()` to check cache and log executions

2. Add tool result caching:
   - Implement `should_execute_tool()`
   - Argument hashing
   - Cache hit/miss logging

3. Update `ToolRegistry` if needed:
   - Ensure execution time tracking
   - Success/failure metadata

**Testing**:
- Integration tests with mock tools
- Verify tool calls are cached correctly
- Test cache invalidation scenarios

### Phase 3: AdaptiveReasoningLoop Integration (Week 3)

**Goals**: Connect tracker to escalation mechanism

**Tasks**:
1. Modify `AdaptiveReasoningLoop.run()`:
   - Initialize tracker at start
   - Pass tracker to strategy methods
   - Record attempt outcomes

2. Update strategy methods:
   - `_execute_direct()`: Add compact context
   - `_execute_light_planning()`: Use plan skeleton
   - `_execute_deep_reasoning()`: Full context integration

3. Implement context injection:
   - `_build_messages_with_tracker_context()`
   - `_get_context_for_strategy()`
   - Prompt caching setup

**Testing**:
- End-to-end escalation tests
- Verify context passed correctly
- Check plan skeleton persistence

### Phase 4: Planner Integration (Week 4)

**Goals**: Enable plan refinement using tracker context

**Tasks**:
1. Modify `Planner.generate_plan()`:
   - Accept tracker context in `context` dict
   - Build enhanced prompts with previous attempts
   - Include completed steps and gaps

2. Implement plan refinement:
   - Merge new plans with existing skeleton
   - Preserve completed steps
   - Add dynamic steps

3. Update `_refine_plan()` logic:
   - Smart merging of old and new plans
   - Step deduplication
   - Dependency tracking

**Testing**:
- Plan generation with various contexts
- Refinement scenarios
- Edge cases (empty previous plan, etc.)

### Phase 5: Context Optimization (Week 5)

**Goals**: Optimize context size and token usage

**Tasks**:
1. Implement verbosity levels:
   - Minimal, Compact, Medium, Full
   - Dynamic selection based on strategy

2. Add prompt caching:
   - Mark tracker context for caching
   - Measure cache hit rates
   - Cost analysis

3. Context truncation strategies:
   - Limit history depth
   - Summarize old attempts
   - Prune redundant information

**Testing**:
- Token counting tests
- Cache effectiveness metrics
- Performance benchmarks

### Phase 6: Persistence and UI (Week 6)

**Goals**: Save tracker state and display in TUI

**Tasks**:
1. Session persistence:
   - Save tracker to disk on completion
   - Load tracker for session resume
   - Cleanup old trackers

2. TUI integration:
   - Display progress in status panel
   - Show completed/pending steps
   - Tool execution log viewer

3. Debugging tools:
   - Export tracker to JSON
   - Visualization utilities
   - Progress reports

**Testing**:
- Persistence round-trip tests
- TUI display verification
- Large tracker performance

---

## 7. Edge Cases and Considerations

### 7.1 Tool Execution Edge Cases

**Case 1: Non-deterministic Tools**

Some tools may return different results for same arguments (e.g., real-time data, random sampling).

**Solution**:
```python
# Add tool metadata
TOOL_CACHING_POLICY = {
    "web_search": "cache",      # Deterministic enough
    "get_current_time": "no-cache",  # Always fresh
    "random_sample": "no-cache",     # Non-deterministic
}

def should_execute_tool(self, tool_name, arguments):
    policy = TOOL_CACHING_POLICY.get(tool_name, "cache")

    if policy == "no-cache":
        return True, None  # Always execute

    # Normal caching logic
    ...
```

**Case 2: Tool Failures**

If a tool failed in LIGHT, should we retry in DEEP?

**Solution**:
```python
def should_execute_tool(self, tool_name, arguments):
    arg_hash = self._hash_arguments(tool_name, arguments)

    # Check for previous failures
    for exec in self.tool_executions:
        if exec.tool_name == tool_name and exec.result_hash == arg_hash:
            if not exec.success:
                # Failed before
                time_since_failure = (datetime.now() - exec.executed_at).seconds

                if time_since_failure < 300:  # 5 minutes
                    # Too recent, don't retry
                    return False, f"Tool failed recently: {exec.error}"
                else:
                    # Old failure, worth retrying
                    return True, None

    return True, None
```

### 7.2 Plan Skeleton Edge Cases

**Case 1: Plan Structure Changes Drastically**

LIGHT creates plan [A, B], but DEEP thinks plan should be [X, Y, Z].

**Solution**:
- Keep completed steps regardless of new plan
- Add new steps to skeleton
- Mark orphaned pending steps as "skipped"

**Case 2: Circular Dependencies**

Dynamic step addition could create loops.

**Solution**:
```python
def add_dynamic_step(self, step: PlanStep, after_step_id: str):
    # Check for circular dependency
    if self._creates_cycle(step, after_step_id):
        logger.warning(f"Skipping step {step.id}: would create dependency cycle")
        return

    # Insert step
    ...
```

### 7.3 Context Size Explosion

**Case 1: Long Execution History**

After many escalations, tracker becomes huge.

**Solution**:
```python
def to_context_text(self, strategy: ExecutionStrategy, max_attempts: int = 3) -> str:
    """Limit history to last N attempts."""

    recent_attempts = self.attempts[-max_attempts:]
    # Only serialize recent attempts
    ...
```

**Case 2: Many Tool Executions**

100+ tool calls → huge context.

**Solution**:
```python
# Group and summarize
tool_summary = defaultdict(lambda: {"count": 0, "latest_result": ""})

for exec in self.tool_executions:
    tool_summary[exec.tool_name]["count"] += 1
    if exec.success:
        tool_summary[exec.tool_name]["latest_result"] = exec.result[:200]

# Serialize summary instead of full log
```

### 7.4 Concurrency and State Management

**Case 1: Multiple Queries in Parallel**

If multiple queries run concurrently, need separate trackers.

**Solution**:
- Tracker is local to `AdaptiveReasoningLoop.run()` execution
- Each invocation gets its own tracker
- No shared state between queries

**Case 2: Streaming and Tracker Updates**

Streaming responses while tracker is being updated.

**Solution**:
- Tracker updates are synchronous and atomic
- Lock-free (single-threaded async)
- No race conditions in current architecture

---

## 8. Success Metrics

### 8.1 Performance Metrics

1. **Tool Call Reduction**:
   - Baseline: Count tool calls without tracker
   - Target: 30-50% reduction in redundant calls after escalation
   - Measure: `len(tracker.tool_executions)` vs expected without cache

2. **Escalation Success Rate**:
   - Baseline: % of escalations that succeed (quality improves)
   - Target: 20% increase in successful escalations
   - Measure: Track quality scores before/after escalation

3. **Execution Time**:
   - Baseline: Average time for multi-escalation queries
   - Target: 15-25% faster (due to cached tools, skipped steps)
   - Measure: End-to-end query completion time

### 8.2 Quality Metrics

1. **Response Completeness**:
   - Baseline: Evaluator completeness scores
   - Target: 10-15% improvement
   - Measure: Average `evaluation.is_complete` rate

2. **Knowledge Gap Addressing**:
   - Baseline: % of identified gaps addressed in final response
   - Target: 80%+ gap coverage
   - Measure: Parse `missing_aspects` before/after escalation

3. **Context Relevance**:
   - Baseline: Manual review of LLM behavior
   - Target: LLM acknowledges and builds upon previous work
   - Measure: Text analysis of responses for references to "previous attempt"

### 8.3 Cost Metrics

1. **Token Usage**:
   - Baseline: Total tokens for multi-escalation query
   - Target: 20-30% reduction (with caching)
   - Measure: Anthropic API token counts

2. **API Call Costs**:
   - Baseline: External API costs (web search, etc.)
   - Target: 40-60% reduction (cached tools)
   - Measure: API billing data

---

## 9. Future Enhancements

### 9.1 Cross-Query Learning

**Idea**: Share tracker insights across different queries in same session.

```python
class SessionMemory:
    """Track insights across multiple queries in a session."""

    def __init__(self):
        self.query_trackers: list[ResearchProgressTracker] = []
        self.global_tool_cache: dict[str, str] = {}
        self.session_insights: AccumulatedInsights = ...

    def add_tracker(self, tracker: ResearchProgressTracker):
        """Add completed tracker to session memory."""
        self.query_trackers.append(tracker)

        # Merge tool results into global cache
        self.global_tool_cache.update(tracker._tool_result_cache)

        # Aggregate confirmed facts
        self.session_insights.confirmed_facts.extend(tracker.insights.confirmed_facts)
```

**Benefits**:
- Query 1 searches docs → Query 2 reuses cached docs
- Build knowledge base over session
- Cross-query context

### 9.2 Machine Learning for Escalation

**Idea**: Train model to predict if escalation will help.

```python
class EscalationPredictor:
    """Predict if escalation is worth it based on tracker state."""

    def should_escalate(self, tracker: ResearchProgressTracker, evaluation: EvaluationResult) -> bool:
        """Use ML model to predict escalation value."""

        features = {
            "quality_score": evaluation.confidence,
            "tool_call_count": len(tracker.tool_executions),
            "completed_steps": len(tracker.plan.get_completed_steps()) if tracker.plan else 0,
            "knowledge_gap_count": len(tracker.insights.knowledge_gaps),
            "complexity": tracker.complexity.complexity_level.value,
        }

        # Simple heuristic for now, ML later
        if features["quality_score"] < 0.4 and features["tool_call_count"] < 2:
            # Low quality, few tools tried → escalation likely helps
            return True
        elif features["quality_score"] > 0.55 and features["knowledge_gap_count"] < 2:
            # Decent quality, few gaps → escalation may not help
            return False

        return evaluation.confidence < threshold
```

### 9.3 Tracker Visualization

**Idea**: Rich TUI visualization of tracker state.

```
┌─ Research Progress ──────────────────────────────────────┐
│ Query: Analyze API performance                           │
│ Complexity: MODERATE | Current: DEEP_REASONING           │
├──────────────────────────────────────────────────────────┤
│ Execution Timeline:                                      │
│   DIRECT (0.62) ─X→ LIGHT (0.71) ─X→ DEEP (in progress) │
│                                                          │
│ Plan: 4/6 steps completed ████████░░░░ 67%              │
│   ✓ Retrieve API logs                                   │
│   ✓ Calculate average latency                           │
│   ✓ Identify slow endpoints                             │
│   ✓ Analyze error rates                                 │
│   ○ Compare to SLA targets                              │
│   ○ Generate recommendations                            │
│                                                          │
│ Tools: 8 executions (6 cached)                          │
│   logs_query: 3× ✓                                      │
│   calculate: 2× ✓                                       │
│   web_search: 1× ✗ (timeout)                            │
│                                                          │
│ Knowledge Gaps:                                          │
│   • SLA target values                                   │
│   • Historical performance trends                       │
└──────────────────────────────────────────────────────────┘
```

---

## 10. Conclusion

The **Research Progress Tracker** system provides a comprehensive solution to context loss during query escalation. By introducing a flexible, serializable data structure that tracks execution history, tool calls, plan progress, and accumulated insights, we enable:

1. **Intelligent Escalation**: Each higher strategy level builds upon previous work instead of starting fresh
2. **Efficiency**: Avoid redundant tool executions through smart caching
3. **Transparency**: Clear visibility into what's been tried and why
4. **Continuity**: Maintain research momentum across execution phases

The implementation integrates cleanly with the existing architecture:
- `ResearchProgressTracker` as central state container
- Minimal changes to `AgentLoop` (tool interception)
- Natural extension of `AdaptiveReasoningLoop` (tracker lifecycle)
- Enhanced `Planner` with context-aware planning

With careful attention to edge cases, context optimization, and phased implementation, this system will significantly improve the quality and efficiency of the adaptive reasoning loop.

---

**Next Steps**: Review this plan, clarify any questions, then proceed with Phase 1 implementation.
