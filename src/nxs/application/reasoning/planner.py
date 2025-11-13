"""Strategic query planning and task decomposition."""

import re
from typing import Callable, Optional

from nxs.application.claude import Claude
from nxs.application.cost_calculator import CostCalculator
from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.types import ResearchPlan, SubTask
from nxs.application.reasoning.utils import format_prompt, load_prompt
from nxs.logger import get_logger

logger = get_logger("reasoning.planner")


class Planner:
    """Strategic query planning and task decomposition.

    Responsibilities:
    - Analyze user query for complexity
    - Generate initial research queries
    - Decompose complex tasks into subtasks
    - Prioritize execution order
    """

    def __init__(
        self,
        llm: Claude,
        config: ReasoningConfig,
        on_usage: Optional[Callable[[dict, float], None]] = None,
    ):
        """Initialize planner.

        Args:
            llm: Claude instance for planning
            config: Reasoning configuration
            on_usage: Optional callback for tracking API usage (usage dict, cost)
        """
        self.llm = llm
        self.config = config
        self.on_usage = on_usage
        self.cost_calculator = CostCalculator()
        self.prompt_template = load_prompt("reasoning/planning.txt")

    async def generate_plan(
        self,
        query: str,
        context: Optional[dict] = None,
    ) -> ResearchPlan:
        """Generate execution plan for query.

        Args:
            query: User's question or goal
            context: Optional context (resources, history, complexity info, mode)
                    Phase 4: Now supports tracker context:
                    - previous_attempts: List of previous attempt summaries
                    - knowledge_gaps: Identified gaps from evaluations
                    - completed_steps: Steps already done in previous attempts
                    - available_tools: Tool names available

        Returns:
            ResearchPlan with ordered subtasks/queries
        """
        logger.debug(f"Generating plan for: {query[:100]}...")

        # Extract context info
        context = context or {}
        mode = context.get("mode", "deep")  # "light" or "deep"
        available_tools = context.get("tools", []) or context.get("available_tools", [])
        complexity_info = context.get("complexity")

        # Phase 4: Extract tracker context
        previous_attempts = context.get("previous_attempts", [])
        knowledge_gaps = context.get("knowledge_gaps", [])
        completed_steps = context.get("completed_steps", [])

        # Adjust max subtasks based on mode
        max_subtasks = 2 if mode == "light" else self.config.max_subtasks

        # Phase 4: Build enhanced context string with tracker information
        context_parts = [f"Mode: {mode}"]
        if complexity_info:
            context_parts.append(f"Complexity: {complexity_info}")

        # Add previous attempts context
        if previous_attempts:
            context_parts.append("\n## Previous Execution Attempts")
            for attempt in previous_attempts:
                strategy = attempt.get("strategy", "unknown")
                quality = attempt.get("quality", "N/A")
                evaluation = attempt.get("evaluation", "")
                context_parts.append(
                    f"- {strategy}: Quality {quality}"
                    + (f", Evaluation: {evaluation}" if evaluation else "")
                )

        # Add completed steps context
        if completed_steps:
            context_parts.append("\n## Already Completed Steps")
            context_parts.append("Build upon these completed steps:")
            for step_desc in completed_steps:
                context_parts.append(f"- {step_desc}")

        # Add knowledge gaps context
        if knowledge_gaps:
            context_parts.append("\n## Knowledge Gaps to Address")
            for gap in knowledge_gaps:
                context_parts.append(f"- {gap}")

        context_str = "\n".join(context_parts)

        # Format prompt
        tools_str = ", ".join(available_tools) if available_tools else "Available tools not specified"

        prompt = format_prompt(
            self.prompt_template,
            query=query,
            tools=tools_str,
            context=context_str,
        )

        try:
            response = await self.llm.create_message(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
            )
            
            # Track cost for reasoning API call
            if hasattr(response, "usage") and response.usage:
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                cost = self.cost_calculator.calculate_cost(
                    self.llm.model, input_tokens, output_tokens
                )
                if self.on_usage:
                    usage = {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    }
                    try:
                        self.on_usage(usage, cost)
                    except Exception as e:
                        logger.warning(f"Error in reasoning cost callback: {e}")
                logger.debug(
                    f"Reasoning (planner) cost: {input_tokens} input, "
                    f"{output_tokens} output tokens, ${cost:.6f}"
                )
            
            # Extract text from response
            response_text = getattr(response.content[0], "text", str(response.content[0]))

            # Parse response into subtasks
            subtasks = self._parse_plan(response_text, max_subtasks)

            # Estimate complexity
            estimated_complexity = self._estimate_complexity(len(subtasks))

            plan = ResearchPlan(
                original_query=query,
                subtasks=subtasks,
                max_iterations=self.config.max_iterations,
                estimated_complexity=estimated_complexity,
            )

            logger.info(
                f"Generated plan: {len(subtasks)} subtasks, complexity={estimated_complexity}"
            )
            return plan

        except Exception as e:
            logger.error(f"Planning failed: {e}", exc_info=True)
            # Fallback: create single subtask with original query
            return ResearchPlan(
                original_query=query,
                subtasks=[
                    SubTask(
                        query=query,
                        priority=1,
                        tool_hints=None,
                    )
                ],
                max_iterations=1,
                estimated_complexity="low",
            )

    def _parse_plan(self, response_text: str, max_subtasks: int) -> list[SubTask]:
        """Parse LLM response into list of subtasks.

        Args:
            response_text: Raw LLM response
            max_subtasks: Maximum number of subtasks to extract

        Returns:
            List of SubTask objects
        """
        subtasks = []

        # Find numbered items with priority and description
        # Pattern: 1. [HIGH PRIORITY] Task description
        #          Tools: tool1, tool2
        pattern = r"(\d+)\.\s*\[([^\]]+)\]\s*([^\n]+)(?:\s*Tools:\s*([^\n]+))?"

        matches = re.finditer(pattern, response_text, re.MULTILINE)

        for match in matches:
            if len(subtasks) >= max_subtasks:
                break

            num, priority_str, description, tools_str = match.groups()

            # Map priority string to numeric value
            # Extract just the priority level (HIGH, MEDIUM, LOW) from strings like "HIGH PRIORITY"
            priority_str_clean = priority_str.upper().strip()
            if "HIGH" in priority_str_clean:
                priority = 1
            elif "MEDIUM" in priority_str_clean:
                priority = 2
            elif "LOW" in priority_str_clean:
                priority = 3
            else:
                priority = 2  # Default to medium

            # Parse tools
            tool_hints = None
            if tools_str:
                tools_str = tools_str.strip()
                if tools_str and tools_str.lower() != "none":
                    tool_hints = [t.strip() for t in tools_str.split(",")]

            subtasks.append(
                SubTask(
                    query=description.strip(),
                    priority=priority,
                    tool_hints=tool_hints,
                )
            )

        # If no subtasks found, try simpler pattern (just numbered list)
        if not subtasks:
            simple_pattern = r"(\d+)\.\s*(.+?)(?:\n|$)"
            matches = re.finditer(simple_pattern, response_text, re.MULTILINE)

            priority_counter = 1  # Assign priorities in order
            for match in matches:
                if len(subtasks) >= max_subtasks:
                    break

                num, description = match.groups()
                # Skip if it looks like metadata rather than a task
                if any(
                    keyword in description.lower()
                    for keyword in ["tools:", "priority:", "strategy:", "output"]
                ):
                    continue

                subtasks.append(
                    SubTask(
                        query=description.strip(),
                        priority=priority_counter,  # Sequential priority
                    )
                )
                priority_counter += 1

        # Ensure at least one subtask
        if not subtasks:
            logger.warning("No subtasks parsed, using original query")
            # This shouldn't happen with the fallback in generate_plan, but just in case
            subtasks = []

        # Sort by priority (lower number = higher priority)
        subtasks.sort(key=lambda x: x.priority)

        logger.debug(f"Parsed {len(subtasks)} subtasks from plan")
        return subtasks

    def _estimate_complexity(self, subtask_count: int) -> str:
        """Estimate overall complexity based on subtask count.

        Args:
            subtask_count: Number of subtasks in plan

        Returns:
            Complexity estimate: "low", "medium", or "high"
        """
        if subtask_count <= 1:
            return "low"
        elif subtask_count <= 3:
            return "medium"
        else:
            return "high"

