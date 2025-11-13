"""Research Progress Tracker - Context preservation across execution strategies.

This module implements a comprehensive tracking system that preserves context,
avoids redundant work, and enables intelligent escalation across query execution
phases (DIRECT → LIGHT_PLANNING → DEEP_REASONING).

Key Features:
- Tracks execution history across all escalation phases
- Records tool executions to avoid redundant calls
- Preserves evaluation feedback to guide subsequent attempts
- Maintains a plan skeleton showing completed/pending steps
- Serializes to natural language context for LLM consumption
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional

from nxs.application.reasoning.types import (
    ComplexityAnalysis,
    EvaluationResult,
    ExecutionStrategy,
    ResearchPlan,
    SubTask,
)
from nxs.logger import get_logger

logger = get_logger("progress_tracker")


class ContextVerbosity:
    """Phase 5: Context verbosity levels for token optimization."""

    MINIMAL = "minimal"  # First attempt: query + complexity only
    COMPACT = "compact"  # DIRECT escalation: summary + top gaps
    MEDIUM = "medium"  # LIGHT_PLANNING: plan + gaps + tool summary
    FULL = "full"  # DEEP_REASONING: complete history + all details


@dataclass
class ExecutionAttempt:
    """Record of a single execution attempt at a specific strategy level."""

    strategy: ExecutionStrategy
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: Literal["in_progress", "completed", "failed", "escalated"] = "in_progress"

    # What was produced
    response: Optional[str] = None
    accumulated_results: list[str] = field(default_factory=list)

    # Quality assessment
    evaluation: Optional[EvaluationResult] = None
    quality_score: Optional[float] = None

    # Why it ended
    outcome: str = ""  # "Quality sufficient" | "Escalated due to low quality" | "Error occurred"


@dataclass
class ToolExecution:
    """Record of a tool call and its result."""

    tool_name: str
    arguments: dict[str, Any]
    executed_at: datetime
    strategy: ExecutionStrategy  # Which strategy level called it

    # Result tracking
    success: bool
    result: Optional[str] = None  # Tool output if successful
    error: Optional[str] = None  # Error message if failed

    # Metadata
    execution_time_ms: float = 0.0
    result_hash: str = ""  # Hash of arguments for deduplication


@dataclass
class PlanStep:
    """A step in the research plan with execution status."""

    id: str  # Unique identifier
    description: str
    status: Literal["pending", "in_progress", "completed", "skipped", "failed"] = "pending"

    # Execution tracking
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Results
    findings: list[str] = field(default_factory=list)  # Key findings from this step
    tools_used: list[str] = field(default_factory=list)  # Tool names used in this step

    # Relationships
    depends_on: list[str] = field(default_factory=list)  # IDs of prerequisite steps
    spawned_from: Optional[str] = None  # ID of parent step if dynamically added


@dataclass
class ResearchPlanSkeleton:
    """High-level plan structure tracking progress."""

    created_at: datetime
    created_by: ExecutionStrategy  # Which strategy created this plan

    query: str
    complexity_analysis: ComplexityAnalysis

    steps: list[PlanStep] = field(default_factory=list)
    current_step_id: Optional[str] = None

    # Plan evolution
    revision_count: int = 0  # Incremented when plan is refined
    last_updated: datetime = field(default_factory=datetime.now)

    def get_completed_steps(self) -> list[PlanStep]:
        """Return all completed steps."""
        return [s for s in self.steps if s.status == "completed"]

    def get_pending_steps(self) -> list[PlanStep]:
        """Return steps not yet started."""
        return [s for s in self.steps if s.status == "pending"]

    def add_dynamic_step(self, step: PlanStep, after_step_id: str):
        """Insert a new step discovered during execution."""
        # Find the index of the step to insert after
        for i, existing_step in enumerate(self.steps):
            if existing_step.id == after_step_id:
                # Insert after this step
                self.steps.insert(i + 1, step)
                self.last_updated = datetime.now()
                return

        # If step not found, append to end
        logger.warning(f"Step {after_step_id} not found, appending new step to end")
        self.steps.append(step)
        self.last_updated = datetime.now()


@dataclass
class AccumulatedInsights:
    """Key insights gathered across all execution attempts."""

    # Categorical storage
    confirmed_facts: list[str] = field(default_factory=list)  # High-confidence findings
    partial_findings: list[str] = field(default_factory=list)  # Low-confidence or incomplete findings
    knowledge_gaps: list[str] = field(default_factory=list)  # Identified missing information

    # From evaluations
    quality_feedback: list[str] = field(default_factory=list)  # Reasons for quality issues
    recommended_improvements: list[str] = field(default_factory=list)  # Suggestions from evaluator

    # Tool-related
    successful_tool_results: dict[str, str] = field(default_factory=dict)  # tool_name → best result
    failed_tool_attempts: dict[str, str] = field(default_factory=dict)  # tool_name → error

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
        """Initialize progress tracker.

        Args:
            query: Original user query
            complexity: Initial complexity analysis
        """
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
            failed_tool_attempts={},
        )

    # === Execution Management ===

    def start_attempt(self, strategy: ExecutionStrategy):
        """Begin a new execution attempt at specified strategy level.

        Args:
            strategy: Execution strategy for this attempt
        """
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
            outcome="",
        )
        self.attempts.append(self.current_attempt)
        logger.debug(f"Started execution attempt: {strategy.value}")

    def end_attempt(
        self,
        outcome: str,
        response: str | None = None,
        evaluation: EvaluationResult | None = None,
        quality_score: float | None = None,
    ):
        """Complete the current execution attempt.

        Args:
            outcome: Reason for ending (e.g., "Quality sufficient", "Escalated due to low quality")
            response: Generated response text
            evaluation: Evaluation result if available
            quality_score: Quality score (0.0 to 1.0)
        """
        if not self.current_attempt:
            logger.warning("end_attempt called but no current attempt exists")
            return

        self.current_attempt.completed_at = datetime.now()
        self.current_attempt.status = "completed" if quality_score and quality_score >= 0.6 else "escalated"
        self.current_attempt.response = response
        self.current_attempt.evaluation = evaluation
        self.current_attempt.quality_score = quality_score
        self.current_attempt.outcome = outcome

        # Extract insights from evaluation
        if evaluation:
            self.insights.add_from_evaluation(evaluation)

        strategy_name = self.current_strategy.value if self.current_strategy else "unknown"
        logger.debug(
            f"Ended execution attempt: {strategy_name}, "
            f"status={self.current_attempt.status}, quality={quality_score}"
        )

    # === Tool Tracking ===

    def should_execute_tool(self, tool_name: str, arguments: dict) -> tuple[bool, Optional[str]]:
        """
        Check if tool should be executed or if we have cached result.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            (should_execute, cached_result)
            - (True, None): Execute the tool
            - (False, result): Skip execution, use cached result
        """
        arg_hash = self._hash_arguments(tool_name, arguments)

        # Check cache
        if arg_hash in self._tool_result_cache:
            logger.debug(f"Cache hit for {tool_name} with hash {arg_hash[:8]}")
            return False, self._tool_result_cache[arg_hash]

        # Check if same tool+args failed before
        for exec_record in self.tool_executions:
            if exec_record.tool_name == tool_name and exec_record.result_hash == arg_hash:
                if not exec_record.success:
                    # Failed before, but might be worth retrying in different context
                    # Return True but log warning
                    logger.debug(f"Tool {tool_name} failed before, but retrying")
                    return True, None

        return True, None

    def log_tool_execution(
        self,
        tool_name: str,
        arguments: dict,
        success: bool,
        result: str | None = None,
        error: str | None = None,
        execution_time_ms: float = 0.0,
    ):
        """Record a tool execution.

        Args:
            tool_name: Name of the tool executed
            arguments: Tool arguments
            success: Whether execution succeeded
            result: Tool output if successful
            error: Error message if failed
            execution_time_ms: Execution time in milliseconds
        """
        arg_hash = self._hash_arguments(tool_name, arguments)

        execution = ToolExecution(
            tool_name=tool_name,
            arguments=arguments,
            executed_at=datetime.now(),
            strategy=self.current_strategy or ExecutionStrategy.DIRECT,
            success=success,
            result=result,
            error=error,
            execution_time_ms=execution_time_ms,
            result_hash=arg_hash,
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

        logger.debug(
            f"Logged tool execution: {tool_name}, success={success}, "
            f"time={execution_time_ms:.2f}ms"
        )

    def _hash_arguments(self, tool_name: str, arguments: dict) -> str:
        """Generate deterministic hash for tool+arguments.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            MD5 hash as hex string
        """
        combined = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
        return hashlib.md5(combined.encode()).hexdigest()

    # === Plan Management ===

    def set_plan(self, plan: ResearchPlan, strategy: ExecutionStrategy):
        """Initialize or update the research plan skeleton.

        Args:
            plan: ResearchPlan from planner
            strategy: Strategy that created this plan
        """
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
                        description=subtask.query,
                        status="pending",
                        started_at=None,
                        completed_at=None,
                        findings=[],
                        tools_used=[],
                        depends_on=[],
                        spawned_from=None,
                    )
                    for i, subtask in enumerate(plan.subtasks)
                ],
                current_step_id=None,
                revision_count=0,
                last_updated=datetime.now(),
            )
            logger.debug(f"Created new plan skeleton with {len(self.plan.steps)} steps")
        else:
            # Refine existing plan
            self._refine_plan(plan, strategy)

    def _refine_plan(self, new_plan: ResearchPlan, strategy: ExecutionStrategy):
        """Merge new plan with existing plan skeleton.

        Phase 4: Enhanced refinement with:
        - Smart merging of old and new plans
        - Step deduplication using similarity detection
        - Dependency tracking
        - Preserving completed steps

        Args:
            new_plan: New plan from planner
            strategy: Strategy that created this plan
        """
        if not self.plan:
            return

        # Phase 4: Get completed and in-progress steps (preserve these)
        completed_step_ids = {s.id for s in self.plan.get_completed_steps()}
        in_progress_step_ids = {
            s.id for s in self.plan.steps if s.status == "in_progress"
        }
        preserved_step_ids = completed_step_ids | in_progress_step_ids

        # Phase 4: Build mapping of existing steps by description (normalized)
        existing_steps_by_desc = {
            self._normalize_step_description(s.description): s
            for s in self.plan.steps
        }

        # Phase 4: Track which new subtasks match existing steps
        matched_steps = []
        new_steps = []
        skipped_steps = []

        for subtask in new_plan.subtasks:
            normalized_desc = self._normalize_step_description(subtask.query)

            # Check for exact match
            if normalized_desc in existing_steps_by_desc:
                existing_step = existing_steps_by_desc[normalized_desc]
                matched_steps.append(existing_step)
                # If step is pending and new plan suggests it, keep it
                # If step is completed, we'll skip it in execution
                continue

            # Phase 4: Check for similar steps (fuzzy matching)
            similar_step = self._find_similar_step(subtask.query, self.plan.steps)
            if similar_step:
                # Found similar step - update description if needed, but preserve status
                if similar_step.status in ["pending", "failed"]:
                    # Update description to match new plan's wording
                    similar_step.description = subtask.query
                    matched_steps.append(similar_step)
                else:
                    # Step is completed/in_progress - skip adding duplicate
                    skipped_steps.append(similar_step)
                continue

            # Phase 4: New step - add it
            new_step = PlanStep(
                id=f"step_{len(self.plan.steps) + len(new_steps)}",
                description=subtask.query,
                status="pending",
                started_at=None,
                completed_at=None,
                findings=[],
                tools_used=[],
                depends_on=self._extract_dependencies(subtask, matched_steps),
                spawned_from=self.plan.current_step_id,  # Track origin
            )
            new_steps.append(new_step)

        # Phase 4: Mark orphaned pending steps as skipped (if they're not in new plan)
        # Only skip if they're truly not needed (not completed/in_progress)
        orphaned_steps = []
        new_descriptions = {
            self._normalize_step_description(s.query) for s in new_plan.subtasks
        }
        for step in self.plan.steps:
            if (
                step.status == "pending"
                and step.id not in preserved_step_ids
                and self._normalize_step_description(step.description) not in new_descriptions
            ):
                # Check if it's similar to any new step
                is_similar = any(
                    self._are_steps_similar(step.description, s.query)
                    for s in new_plan.subtasks
                )
                if not is_similar:
                    orphaned_steps.append(step)

        # Mark orphaned steps as skipped (but don't remove them - they might be needed later)
        for step in orphaned_steps:
            if step.status == "pending":
                step.status = "skipped"
                logger.debug(f"Marked orphaned step as skipped: {step.description}")

        # Phase 4: Add new steps to plan
        self.plan.steps.extend(new_steps)
        self.plan.revision_count += 1
        self.plan.last_updated = datetime.now()

        logger.info(
            f"Refined plan: matched {len(matched_steps)} existing steps, "
            f"added {len(new_steps)} new steps, "
            f"skipped {len(skipped_steps)} duplicates, "
            f"marked {len(orphaned_steps)} as skipped, "
            f"revision_count={self.plan.revision_count}"
        )

    def _normalize_step_description(self, description: str) -> str:
        """Normalize step description for comparison.

        Args:
            description: Step description text

        Returns:
            Normalized description (lowercase, stripped, basic cleanup)
        """
        # Basic normalization: lowercase, strip, remove extra whitespace
        normalized = " ".join(description.lower().strip().split())
        # Remove common prefixes that don't affect meaning
        prefixes = ["step", "task", "subtask", "1.", "2.", "3.", "4.", "5."]
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].strip()
        return normalized

    def _find_similar_step(
        self, description: str, existing_steps: list[PlanStep]
    ) -> Optional[PlanStep]:
        """Find a similar step in existing steps using fuzzy matching.

        Args:
            description: New step description
            existing_steps: List of existing plan steps

        Returns:
            Similar step if found, None otherwise
        """
        normalized_new = self._normalize_step_description(description)

        for step in existing_steps:
            if self._are_steps_similar(description, step.description):
                return step

        return None

    def _are_steps_similar(self, desc1: str, desc2: str, threshold: float = 0.7) -> bool:
        """Check if two step descriptions are similar.

        Uses simple word overlap ratio for similarity detection.

        Args:
            desc1: First description
            desc2: Second description
            threshold: Similarity threshold (0.0 to 1.0)

        Returns:
            True if descriptions are similar enough
        """
        # Normalize both descriptions
        words1 = set(self._normalize_step_description(desc1).split())
        words2 = set(self._normalize_step_description(desc2).split())

        if not words1 or not words2:
            return False

        # Calculate Jaccard similarity (intersection over union)
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        if union == 0:
            return False

        similarity = intersection / union
        return similarity >= threshold

    def _extract_dependencies(
        self, subtask: SubTask, matched_steps: list[PlanStep]
    ) -> list[str]:
        """Extract dependency IDs for a subtask.

        Args:
            subtask: SubTask from new plan
            matched_steps: List of matched existing steps

        Returns:
            List of step IDs this subtask depends on
        """
        # Use subtask.dependencies if available
        if subtask.dependencies:
            # Map dependency descriptions to step IDs
            dep_ids = []
            for dep_desc in subtask.dependencies:
                for step in matched_steps:
                    if self._are_steps_similar(dep_desc, step.description):
                        dep_ids.append(step.id)
            return dep_ids

        # If no explicit dependencies, infer from order
        # (later steps might depend on earlier ones)
        # For now, return empty - can be enhanced later
        return []

    def update_step_status(
        self,
        step_id: str,
        status: Literal["pending", "in_progress", "completed", "skipped", "failed"],
        findings: list[str] | None = None,
    ):
        """Update a plan step's status and findings.

        Args:
            step_id: ID of the step to update
            status: New status ("pending", "in_progress", "completed", "skipped", "failed")
            findings: Optional list of findings from this step
        """
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

    def to_context_text(
        self,
        strategy: ExecutionStrategy,
        verbosity: str | None = None,
        max_attempts: int | None = None,
        max_tool_executions: int | None = None,
    ) -> str:
        """
        Serialize tracker state to natural language context for LLM.

        Phase 5: Enhanced with verbosity levels and truncation strategies.

        Args:
            strategy: Current execution strategy
            verbosity: Verbosity level (MINIMAL, COMPACT, MEDIUM, FULL)
                      If None, auto-selects based on strategy
            max_attempts: Maximum number of attempts to include (truncation)
            max_tool_executions: Maximum tool executions to include (truncation)

        Returns:
            Formatted context text
        """
        # Phase 5: Auto-select verbosity based on strategy if not specified
        if verbosity is None:
            if len(self.attempts) == 1:
                verbosity = ContextVerbosity.MINIMAL
            elif strategy == ExecutionStrategy.DIRECT:
                verbosity = ContextVerbosity.COMPACT
            elif strategy == ExecutionStrategy.LIGHT_PLANNING:
                verbosity = ContextVerbosity.MEDIUM
            else:  # DEEP_REASONING
                verbosity = ContextVerbosity.FULL

        # Phase 5: Apply truncation limits
        max_attempts = max_attempts or (3 if verbosity == ContextVerbosity.FULL else 2)
        max_tool_executions = max_tool_executions or (
            50 if verbosity == ContextVerbosity.FULL else 20
        )

        sections = []

        # 1. Query and Complexity Overview (always included)
        sections.append("# Research Progress Context\n")
        sections.append(f"**Query**: {self.query}\n")
        sections.append(f"**Complexity**: {self.complexity.complexity_level.value}")
        sections.append(f"**Current Execution Level**: {strategy.value}\n")

        # 2. Execution History (truncated based on verbosity)
        if self.attempts and verbosity != ContextVerbosity.MINIMAL:
            sections.append("\n## Previous Execution Attempts\n")

            # Phase 5: Limit history depth
            attempts_to_show = self.attempts[:-1][-max_attempts:]  # Last N attempts

            # Phase 5: Summarize old attempts if needed
            if len(self.attempts[:-1]) > max_attempts:
                old_count = len(self.attempts[:-1]) - max_attempts
                sections.append(
                    f"*({old_count} earlier attempt(s) summarized below)*\n"
                )

            for i, attempt in enumerate(attempts_to_show, 1):
                sections.append(f"\n### Attempt {i}: {attempt.strategy.value}")
                sections.append(f"- **Status**: {attempt.status}")
                sections.append(f"- **Quality Score**: {attempt.quality_score or 'N/A'}")

                if attempt.evaluation:
                    # Phase 5: Truncate evaluation reasoning if too long
                    eval_reasoning = attempt.evaluation.reasoning
                    if len(eval_reasoning) > 200 and verbosity != ContextVerbosity.FULL:
                        eval_reasoning = eval_reasoning[:200] + "..."
                    sections.append(f"- **Evaluation**: {eval_reasoning}")
                    if attempt.evaluation.missing_aspects:
                        missing = attempt.evaluation.missing_aspects
                        # Phase 5: Limit missing aspects based on verbosity
                        if verbosity != ContextVerbosity.FULL:
                            missing = missing[:3]
                        sections.append(
                            f"- **Missing Aspects**: {', '.join(missing)}"
                        )

                sections.append(f"- **Outcome**: {attempt.outcome}\n")

        # 3. Research Plan Progress (verbosity-dependent)
        if self.plan and verbosity in [
            ContextVerbosity.MEDIUM,
            ContextVerbosity.FULL,
        ]:
            sections.append("\n## Research Plan Progress\n")

            completed = self.plan.get_completed_steps()
            pending = self.plan.get_pending_steps()

            sections.append(
                f"**Plan Status**: {len(completed)}/{len(self.plan.steps)} steps completed\n"
            )

            if completed:
                sections.append("\n### ✓ Completed Steps\n")
                # Phase 5: Limit completed steps shown based on verbosity
                steps_to_show = (
                    completed if verbosity == ContextVerbosity.FULL else completed[-5:]
                )
                if len(completed) > len(steps_to_show):
                    sections.append(
                        f"*Showing last {len(steps_to_show)} of {len(completed)} completed steps*\n"
                    )

                for step in steps_to_show:
                    sections.append(f"- **{step.description}**")
                    if step.findings and verbosity == ContextVerbosity.FULL:
                        # Phase 5: Truncate findings in medium verbosity
                        findings = step.findings
                        if verbosity == ContextVerbosity.MEDIUM:
                            findings = findings[-2:]  # Last 2 findings
                        sections.append(f"  - Findings: {'; '.join(findings)}")
                    if step.tools_used:
                        sections.append(f"  - Tools used: {', '.join(step.tools_used)}")
                sections.append("")

            if pending:
                sections.append("\n### ○ Pending Steps\n")
                # Phase 5: Limit pending steps shown
                pending_to_show = (
                    pending if verbosity == ContextVerbosity.FULL else pending[:10]
                )
                for step in pending_to_show:
                    sections.append(f"- {step.description}")
                if len(pending) > len(pending_to_show):
                    sections.append(f"*... and {len(pending) - len(pending_to_show)} more*")
                sections.append("")

        # 4. Tool Execution Summary (verbosity-dependent, truncated)
        if self.tool_executions and verbosity in [
            ContextVerbosity.MEDIUM,
            ContextVerbosity.FULL,
        ]:
            sections.append("\n## Tool Execution History\n")

            successful_tools = [e for e in self.tool_executions if e.success]
            failed_tools = [e for e in self.tool_executions if not e.success]

            sections.append(
                f"**Total tool calls**: {len(self.tool_executions)} "
                f"({len(successful_tools)} successful, {len(failed_tools)} failed)\n"
            )

            if successful_tools:
                sections.append("\n### Successful Tool Executions\n")
                # Group by tool name
                by_tool = defaultdict(list)
                # Phase 5: Limit tool executions shown
                recent_tools = successful_tools[-max_tool_executions:]
                for e in recent_tools:
                    by_tool[e.tool_name].append(e)

                if len(successful_tools) > max_tool_executions:
                    sections.append(
                        f"*Showing last {max_tool_executions} of {len(successful_tools)} tool calls*\n"
                    )

                for tool_name, executions in by_tool.items():
                    sections.append(f"- **{tool_name}**: {len(executions)} call(s)")
                    # Show most recent result (truncated based on verbosity)
                    latest = executions[-1]
                    if latest.result:
                        max_result_len = 200 if verbosity == ContextVerbosity.FULL else 100
                        preview = (
                            latest.result[:max_result_len] + "..."
                            if len(latest.result) > max_result_len
                            else latest.result
                        )
                        sections.append(f"  - Latest result: {preview}")
                sections.append("")

            if failed_tools:
                sections.append("\n### Failed Tool Executions\n")
                # Phase 5: Limit failed tools shown
                failed_to_show = (
                    failed_tools
                    if verbosity == ContextVerbosity.FULL
                    else failed_tools[-5:]
                )
                for e in failed_to_show:
                    sections.append(f"- **{e.tool_name}**: {e.error}")
                if len(failed_tools) > len(failed_to_show):
                    sections.append(f"*... and {len(failed_tools) - len(failed_to_show)} more failures*")
                sections.append("")

        # 5. Accumulated Insights (verbosity-dependent)
        if verbosity in [ContextVerbosity.MEDIUM, ContextVerbosity.FULL]:
            sections.append("\n## Accumulated Insights\n")

            if self.insights.confirmed_facts and verbosity == ContextVerbosity.FULL:
                sections.append("\n### Confirmed Facts\n")
                # Phase 5: Limit facts shown
                facts_to_show = self.insights.confirmed_facts[:10]
                for fact in facts_to_show:
                    sections.append(f"- {fact}")
                if len(self.insights.confirmed_facts) > 10:
                    sections.append(f"*... and {len(self.insights.confirmed_facts) - 10} more*")
                sections.append("")

            if self.insights.knowledge_gaps:
                sections.append("\n### Identified Knowledge Gaps\n")
                # Phase 5: Limit gaps shown based on verbosity
                gaps_to_show = (
                    self.insights.knowledge_gaps
                    if verbosity == ContextVerbosity.FULL
                    else self.insights.knowledge_gaps[:5]
                )
                for gap in gaps_to_show:
                    sections.append(f"- {gap}")
                if len(self.insights.knowledge_gaps) > len(gaps_to_show):
                    sections.append(
                        f"*... and {len(self.insights.knowledge_gaps) - len(gaps_to_show)} more gaps*"
                    )
                sections.append("")

            if self.insights.quality_feedback:
                sections.append("\n### Quality Feedback from Previous Attempts\n")
                # Phase 5: Limit feedback shown
                feedback_to_show = (
                    self.insights.quality_feedback
                    if verbosity == ContextVerbosity.FULL
                    else self.insights.quality_feedback[-3:]
                )
                for feedback in feedback_to_show:
                    # Phase 5: Truncate long feedback
                    if len(feedback) > 150 and verbosity != ContextVerbosity.FULL:
                        feedback = feedback[:150] + "..."
                    sections.append(f"- {feedback}")
                sections.append("")

        # 6. Guidance for Current Attempt (verbosity-dependent)
        if verbosity in [ContextVerbosity.MEDIUM, ContextVerbosity.FULL]:
            sections.append("\n## Guidance for Current Execution\n")

            if strategy != ExecutionStrategy.DIRECT:
                sections.append("**Building on previous work**:\n")
                sections.append("- Review completed steps and their findings above")
                sections.append("- Focus on identified knowledge gaps")
                sections.append("- Avoid redundant tool calls (check execution history)")
                sections.append("- Address quality feedback from previous evaluations")

                if self.insights.recommended_improvements:
                    sections.append("\n**Recommended improvements**:\n")
                    # Phase 5: Limit recommendations based on verbosity
                    recs_to_show = (
                        self.insights.recommended_improvements[:10]
                        if verbosity == ContextVerbosity.FULL
                        else self.insights.recommended_improvements[:5]
                    )
                    for rec in recs_to_show:
                        sections.append(f"- {rec}")

        return "\n".join(sections)

    def to_medium_context(self) -> str:
        """
        Phase 5: Medium verbosity context for LIGHT_PLANNING strategy.

        Includes:
        - Completed steps with findings
        - Pending steps
        - Tool execution summary (grouped by tool name)
        - Knowledge gaps

        Returns:
            Medium verbosity context text
        """
        return self.to_context_text(
            ExecutionStrategy.LIGHT_PLANNING, verbosity=ContextVerbosity.MEDIUM
        )

    def to_compact_context(self) -> str:
        """
        Phase 5: Compact version of context for DIRECT escalation.

        Includes:
        - Summary line: "Progress: X attempts, Y tool calls, Z/W steps"
        - Top 3 knowledge gaps
        - Available cached tool results

        Returns:
            Compact context summary
        """
        parts = []

        # Summary line
        completed_steps = len(self.plan.get_completed_steps()) if self.plan else 0
        total_steps = len(self.plan.steps) if self.plan else 0
        parts.append(
            f"Progress: {len(self.attempts)} attempts, "
            f"{len(self.tool_executions)} tool calls, "
            f"{completed_steps}/{total_steps} steps done"
        )

        # Key gaps (top 3)
        if self.insights.knowledge_gaps:
            parts.append(f"Gaps: {', '.join(self.insights.knowledge_gaps[:3])}")

        # Available cached results
        if self._tool_result_cache:
            parts.append(f"Cached: {len(self._tool_result_cache)} results")

        return " | ".join(parts)

    def to_minimal_context(self) -> str:
        """
        Phase 5: Minimal context for first attempt.

        Includes only:
        - Query
        - Complexity analysis

        Returns:
            Minimal context text
        """
        return (
            f"Query: {self.query}\n"
            f"Complexity: {self.complexity.complexity_level.value}"
        )

    def estimate_token_count(self, text: str) -> int:
        """
        Phase 5: Estimate token count for context text.

        Uses simple approximation: ~4 characters per token (conservative estimate).

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        # Simple approximation: ~4 chars per token
        # This is conservative - actual tokenization varies
        return len(text) // 4

    def get_context_token_count(
        self, strategy: ExecutionStrategy, verbosity: str | None = None
    ) -> int:
        """
        Phase 5: Get estimated token count for context at given verbosity.

        Args:
            strategy: Execution strategy
            verbosity: Verbosity level (None = auto-select)

        Returns:
            Estimated token count
        """
        context_text = self.to_context_text(strategy, verbosity=verbosity)
        return self.estimate_token_count(context_text)

    # === Persistence ===

    def _serialize_dataclass(self, obj: Any) -> Any:
        """Recursively serialize dataclass, converting datetime to ISO format.

        Args:
            obj: Object to serialize (dataclass, dict, list, etc.)

        Returns:
            Serialized object with datetime as ISO strings
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, ExecutionStrategy):
            return obj.value
        elif isinstance(obj, ComplexityAnalysis):
            # Handle special types that need custom serialization
            result = {}
            for key, value in asdict(obj).items():
                result[key] = self._serialize_dataclass(value)
            return result
        elif isinstance(obj, EvaluationResult):
            # Handle EvaluationResult separately
            result = {}
            for key, value in asdict(obj).items():
                result[key] = self._serialize_dataclass(value)
            return result
        elif hasattr(obj, "__dataclass_fields__"):
            # It's a dataclass
            result = {}
            for key, value in asdict(obj).items():
                result[key] = self._serialize_dataclass(value)
            return result
        elif isinstance(obj, dict):
            return {k: self._serialize_dataclass(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_dataclass(item) for item in obj]
        else:
            return obj

    def to_dict(self) -> dict:
        """Serialize to dictionary for session persistence.

        Returns:
            Dictionary representation of tracker state
        """
        return {
            "query": self.query,
            "complexity": self._serialize_dataclass(self.complexity),
            "created_at": self.created_at.isoformat(),
            "attempts": [self._serialize_dataclass(a) for a in self.attempts],
            "tool_executions": [self._serialize_dataclass(t) for t in self.tool_executions],
            "plan": self._serialize_dataclass(self.plan) if self.plan else None,
            "insights": self._serialize_dataclass(self.insights),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResearchProgressTracker":
        """Deserialize from dictionary.

        Args:
            data: Dictionary representation from to_dict()

        Returns:
            Reconstructed ResearchProgressTracker instance
        """
        # Reconstruct complexity
        from nxs.application.reasoning.types import ComplexityLevel

        complexity_data = data["complexity"]
        complexity = ComplexityAnalysis(
            complexity_level=ComplexityLevel(complexity_data["complexity_level"]),
            reasoning_required=complexity_data["reasoning_required"],
            recommended_strategy=ExecutionStrategy(complexity_data["recommended_strategy"]),
            rationale=complexity_data["rationale"],
            estimated_iterations=complexity_data.get("estimated_iterations", 1),
            confidence=complexity_data.get("confidence", 0.0),
            requires_research=complexity_data.get("requires_research", False),
            requires_synthesis=complexity_data.get("requires_synthesis", False),
            multi_part_query=complexity_data.get("multi_part_query", False),
            tool_count_estimate=complexity_data.get("tool_count_estimate", 0),
        )

        # Create tracker
        tracker = cls(data["query"], complexity)
        tracker.created_at = datetime.fromisoformat(data["created_at"])

        # Reconstruct attempts
        for attempt_data in data.get("attempts", []):
            # Handle strategy - could be enum value or string
            strategy_value = attempt_data["strategy"]
            if isinstance(strategy_value, str):
                strategy = ExecutionStrategy(strategy_value)
            else:
                strategy = ExecutionStrategy(strategy_value)

            # Reconstruct evaluation if present
            evaluation = None
            if attempt_data.get("evaluation"):
                eval_data = attempt_data["evaluation"]
                evaluation = EvaluationResult(
                    is_complete=eval_data.get("is_complete", False),
                    confidence=eval_data.get("confidence", 0.0),
                    reasoning=eval_data.get("reasoning", ""),
                    additional_queries=eval_data.get("additional_queries", []),
                    missing_aspects=eval_data.get("missing_aspects", []),
                )

            attempt = ExecutionAttempt(
                strategy=strategy,
                started_at=datetime.fromisoformat(attempt_data["started_at"]),
                completed_at=(
                    datetime.fromisoformat(attempt_data["completed_at"])
                    if attempt_data.get("completed_at")
                    else None
                ),
                status=attempt_data["status"],
                response=attempt_data.get("response"),
                accumulated_results=attempt_data.get("accumulated_results", []),
                evaluation=evaluation,
                quality_score=attempt_data.get("quality_score"),
                outcome=attempt_data.get("outcome", ""),
            )
            tracker.attempts.append(attempt)

        # Reconstruct tool executions
        for tool_data in data.get("tool_executions", []):
            # Handle strategy - could be enum value or string
            strategy_value = tool_data["strategy"]
            if isinstance(strategy_value, str):
                strategy = ExecutionStrategy(strategy_value)
            else:
                strategy = ExecutionStrategy(strategy_value)

            tool_exec = ToolExecution(
                tool_name=tool_data["tool_name"],
                arguments=tool_data["arguments"],
                executed_at=datetime.fromisoformat(tool_data["executed_at"]),
                strategy=strategy,
                success=tool_data["success"],
                result=tool_data.get("result"),
                error=tool_data.get("error"),
                execution_time_ms=tool_data.get("execution_time_ms", 0.0),
                result_hash=tool_data.get("result_hash", ""),
            )
            tracker.tool_executions.append(tool_exec)
            # Rebuild cache
            if tool_exec.success and tool_exec.result:
                tracker._tool_result_cache[tool_exec.result_hash] = tool_exec.result

        # Reconstruct plan
        if data.get("plan"):
            plan_data = data["plan"]
            plan_steps = []
            for step_data in plan_data.get("steps", []):
                step = PlanStep(
                    id=step_data["id"],
                    description=step_data["description"],
                    status=step_data["status"],
                    started_at=(
                        datetime.fromisoformat(step_data["started_at"])
                        if step_data.get("started_at")
                        else None
                    ),
                    completed_at=(
                        datetime.fromisoformat(step_data["completed_at"])
                        if step_data.get("completed_at")
                        else None
                    ),
                    findings=step_data.get("findings", []),
                    tools_used=step_data.get("tools_used", []),
                    depends_on=step_data.get("depends_on", []),
                    spawned_from=step_data.get("spawned_from"),
                )
                plan_steps.append(step)

            # Handle strategy - could be enum value or string
            created_by_value = plan_data["created_by"]
            if isinstance(created_by_value, str):
                created_by = ExecutionStrategy(created_by_value)
            else:
                created_by = ExecutionStrategy(created_by_value)

            tracker.plan = ResearchPlanSkeleton(
                created_at=datetime.fromisoformat(plan_data["created_at"]),
                created_by=created_by,
                query=plan_data["query"],
                complexity_analysis=complexity,  # Reuse reconstructed complexity
                steps=plan_steps,
                current_step_id=plan_data.get("current_step_id"),
                revision_count=plan_data.get("revision_count", 0),
                last_updated=datetime.fromisoformat(plan_data["last_updated"]),
            )

        # Reconstruct insights
        insights_data = data.get("insights", {})
        tracker.insights = AccumulatedInsights(
            confirmed_facts=insights_data.get("confirmed_facts", []),
            partial_findings=insights_data.get("partial_findings", []),
            knowledge_gaps=insights_data.get("knowledge_gaps", []),
            quality_feedback=insights_data.get("quality_feedback", []),
            recommended_improvements=insights_data.get("recommended_improvements", []),
            successful_tool_results=insights_data.get("successful_tool_results", {}),
            failed_tool_attempts=insights_data.get("failed_tool_attempts", {}),
        )

        return tracker

