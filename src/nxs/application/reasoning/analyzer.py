"""Query complexity analyzer for adaptive execution strategy selection."""

import re
from typing import Optional

from nxs.application.claude import Claude
from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.types import (
    ComplexityAnalysis,
    ComplexityLevel,
    ExecutionStrategy,
)
from nxs.application.reasoning.utils import format_prompt, load_prompt
from nxs.logger import get_logger

logger = get_logger("reasoning.analyzer")


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
    """

    def __init__(self, llm: Claude, config: ReasoningConfig):
        """Initialize analyzer.

        Args:
            llm: Claude instance for analysis
            config: Reasoning configuration
        """
        self.llm = llm
        self.config = config
        self.prompt_template = load_prompt("reasoning/complexity_analysis.txt")

    async def analyze(
        self,
        query: str,
        available_tools: Optional[list[str]] = None,
        conversation_context: Optional[dict] = None,
    ) -> ComplexityAnalysis:
        """Analyze query complexity and recommend strategy.

        Args:
            query: User's query
            available_tools: List of available tool names
            conversation_context: Recent conversation context

        Returns:
            ComplexityAnalysis with strategy recommendation
        """
        logger.debug(f"Analyzing query complexity: {query[:100]}...")

        # Format prompt
        tools_str = ", ".join(available_tools) if available_tools else "None"
        context_str = str(conversation_context) if conversation_context else "No prior context"

        prompt = format_prompt(
            self.prompt_template,
            query=query,
            tools=tools_str,
            context=context_str,
        )

        # Get analysis from LLM
        try:
            response = await self.llm.create_message(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            # Extract text from response - handle different content block types
            content_block = response.content[0]
            response_text = getattr(content_block, "text", str(content_block))

            # Parse response
            analysis = self._parse_analysis(response_text)
            logger.info(
                f"Complexity analysis: {analysis.complexity_level.value} → {analysis.recommended_strategy.value}"
            )
            return analysis

        except Exception as e:
            logger.error(f"Complexity analysis failed: {e}", exc_info=True)
            # Fallback to medium complexity
            return ComplexityAnalysis(
                complexity_level=ComplexityLevel.MEDIUM,
                reasoning_required=True,
                recommended_strategy=ExecutionStrategy.LIGHT_PLANNING,
                rationale=f"Analysis failed ({str(e)}), defaulting to medium complexity",
                estimated_iterations=2,
                confidence=0.0,
            )

    def _parse_analysis(self, response_text: str) -> ComplexityAnalysis:
        """Parse LLM response into ComplexityAnalysis.

        Args:
            response_text: Raw LLM response

        Returns:
            Parsed ComplexityAnalysis
        """
        # Extract complexity level
        complexity_match = re.search(
            r"\*\*Complexity Level:\*\*\s*(SIMPLE|MEDIUM|COMPLEX)",
            response_text,
            re.IGNORECASE,
        )
        complexity_str = complexity_match.group(1).upper() if complexity_match else "MEDIUM"
        complexity_level = ComplexityLevel[complexity_str]

        # Extract strategy
        strategy_match = re.search(
            r"\*\*Recommended Strategy:\*\*\s*(DIRECT|LIGHT_PLANNING|DEEP_REASONING)",
            response_text,
            re.IGNORECASE,
        )
        strategy_str = strategy_match.group(1).upper() if strategy_match else "LIGHT_PLANNING"
        recommended_strategy = ExecutionStrategy[strategy_str]

        # Extract iterations
        iterations_match = re.search(r"\*\*Estimated Iterations:\*\*\s*(\d+)", response_text)
        estimated_iterations = int(iterations_match.group(1)) if iterations_match else 2

        # Extract confidence
        confidence_match = re.search(r"\*\*Confidence:\*\*\s*([\d.]+)", response_text)
        confidence = float(confidence_match.group(1)) if confidence_match else 0.5

        # Extract reasoning
        reasoning_match = re.search(
            r"\*\*Reasoning:\*\*\s*\n(.*?)(?:\n\*\*|$)", response_text, re.DOTALL
        )
        rationale = reasoning_match.group(1).strip() if reasoning_match else "No rationale provided"

        # Extract flags
        requires_research = "Requires Research: Yes" in response_text
        requires_synthesis = "Requires Synthesis: Yes" in response_text
        multi_part_query = "Multi-Part Query: Yes" in response_text

        # Extract tool count estimate
        tool_count_match = re.search(r"Tool Count Estimate:\s*(\d+)", response_text)
        tool_count_estimate = int(tool_count_match.group(1)) if tool_count_match else 0

        return ComplexityAnalysis(
            complexity_level=complexity_level,
            reasoning_required=complexity_level != ComplexityLevel.SIMPLE,
            recommended_strategy=recommended_strategy,
            rationale=rationale,
            estimated_iterations=estimated_iterations,
            confidence=confidence,
            requires_research=requires_research,
            requires_synthesis=requires_synthesis,
            multi_part_query=multi_part_query,
            tool_count_estimate=tool_count_estimate,
        )

