"""Evaluator for research completeness and response quality assessment."""

import re
from typing import Optional

from nxs.application.claude import Claude
from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.types import (
    ComplexityAnalysis,
    EvaluationResult,
    ResearchPlan,
)
from nxs.application.reasoning.utils import format_prompt, load_prompt
from nxs.logger import get_logger

logger = get_logger("reasoning.evaluator")


class Evaluator:
    """Dual-purpose evaluation: research completeness + response quality.

    Responsibilities:
    1. Research Evaluation:
       - Assess if results answer the query
       - Identify information gaps
       - Generate additional queries for missing info

    2. Response Quality Evaluation (for self-correction):
       - Assess response quality and completeness
       - Determine if escalation needed
       - Identify what's missing or inadequate
    """

    def __init__(self, llm: Claude, config: ReasoningConfig):
        """Initialize evaluator.

        Args:
            llm: Claude instance for evaluation
            config: Reasoning configuration
        """
        self.llm = llm
        self.config = config
        self.research_evaluation_prompt = load_prompt("reasoning/evaluation.txt")
        self.quality_evaluation_prompt = load_prompt("reasoning/quality_check.txt")

    async def evaluate(
        self,
        query: str,
        results: list[dict],
        current_plan: ResearchPlan,
    ) -> EvaluationResult:
        """Evaluate if research results are sufficient.

        Args:
            query: Original user query
            results: Accumulated results so far
            current_plan: Current execution plan

        Returns:
            EvaluationResult with completeness and next actions
        """
        logger.debug(f"Evaluating research completeness for: {query[:100]}...")

        # Format results for prompt
        results_str = self._format_results(results)
        plan_str = self._format_plan(current_plan)

        prompt = format_prompt(
            self.research_evaluation_prompt,
            query=query,
            results=results_str,
            plan=plan_str,
        )

        try:
            response = await self.llm.create_message(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            # Extract text from response
            response_text = getattr(response.content[0], "text", str(response.content[0]))

            # Parse response
            evaluation = self._parse_research_evaluation(response_text)
            logger.info(
                f"Research evaluation: complete={evaluation.is_complete}, "
                f"confidence={evaluation.confidence:.2f}"
            )
            return evaluation

        except Exception as e:
            logger.error(f"Research evaluation failed: {e}", exc_info=True)
            # Fallback: assume incomplete but continue
            return EvaluationResult(
                is_complete=False,
                confidence=0.5,
                reasoning=f"Evaluation failed ({str(e)}), assuming incomplete",
                additional_queries=[],
            )

    async def evaluate_response_quality(
        self,
        query: str,
        response: str,
        strategy_used: str,
        expected_complexity: Optional[ComplexityAnalysis] = None,
    ) -> EvaluationResult:
        """Evaluate response quality for self-correction.

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
        """
        logger.debug(f"Evaluating response quality (strategy: {strategy_used})...")

        complexity_str = (
            expected_complexity.complexity_level.value if expected_complexity else "unknown"
        )

        prompt = format_prompt(
            self.quality_evaluation_prompt,
            query=query,
            response=response[:2000],  # Truncate if too long
            strategy_used=strategy_used,
            expected_complexity=complexity_str,
        )

        try:
            response_obj = await self.llm.create_message(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            # Extract text from response
            response_text = getattr(response_obj.content[0], "text", str(response_obj.content[0]))

            # Parse response
            evaluation = self._parse_quality_evaluation(response_text)
            logger.info(
                f"Quality evaluation: sufficient={evaluation.is_complete}, "
                f"confidence={evaluation.confidence:.2f}"
            )
            return evaluation

        except Exception as e:
            logger.error(f"Quality evaluation failed: {e}", exc_info=True)
            # Fallback: assume quality is acceptable to avoid infinite loops
            return EvaluationResult(
                is_complete=True,
                confidence=0.5,
                reasoning=f"Evaluation failed ({str(e)}), accepting response",
                missing_aspects=[],
            )

    def _format_results(self, results: list[dict]) -> str:
        """Format results for prompt."""
        if not results:
            return "No results yet"

        formatted = []
        for i, result in enumerate(results, 1):
            query = result.get("query", "Unknown")
            content = result.get("result", "No content")
            formatted.append(f"{i}. Query: {query}\n   Result: {content[:500]}...")

        return "\n\n".join(formatted)

    def _format_plan(self, plan: ResearchPlan) -> str:
        """Format plan for prompt."""
        remaining = [f"- {task.query}" for task in plan.subtasks]
        return "\n".join(remaining) if remaining else "No remaining subtasks"

    def _parse_research_evaluation(self, response_text: str) -> EvaluationResult:
        """Parse research evaluation response."""
        # Check if complete - look in completeness assessment section
        is_complete = False
        assessment_match = re.search(
            r"Completeness Assessment\s*\n(.*?)(?:\n##|$)", 
            response_text, 
            re.DOTALL | re.IGNORECASE
        )
        if assessment_match:
            assessment_text = assessment_match.group(1).strip()
            is_complete = "COMPLETE" in assessment_text.upper()

        # Extract confidence
        confidence_match = re.search(r"Confidence Score\s*\n?\s*([\d.]+)", response_text, re.IGNORECASE)
        confidence = float(confidence_match.group(1)) if confidence_match else 0.5

        # Extract reasoning
        assessment_match = re.search(
            r"Completeness Assessment\s*\n(.*?)(?:\n##|$)", response_text, re.DOTALL | re.IGNORECASE
        )
        reasoning = assessment_match.group(1).strip() if assessment_match else "No assessment provided"

        # Extract additional queries
        additional_queries = []
        queries_section = re.search(
            r"Additional Queries Needed\s*\n(.*?)(?:\n##|$)", response_text, re.DOTALL | re.IGNORECASE
        )
        if queries_section:
            query_lines = queries_section.group(1).strip().split("\n")
            for line in query_lines:
                # Extract query from numbered list
                query_match = re.match(r"\d+\.\s*(.+)", line.strip())
                if query_match:
                    additional_queries.append(query_match.group(1))

        # Extract missing aspects
        missing_aspects = []
        aspects_section = re.search(
            r"Missing Aspects\s*\n(.*?)(?:\n##|$)", response_text, re.DOTALL | re.IGNORECASE
        )
        if aspects_section:
            aspect_lines = aspects_section.group(1).strip().split("\n")
            for line in aspect_lines:
                # Extract from bullet list
                aspect_match = re.match(r"[-*]\s*(.+)", line.strip())
                if aspect_match:
                    missing_aspects.append(aspect_match.group(1))

        return EvaluationResult(
            is_complete=is_complete,
            confidence=confidence,
            reasoning=reasoning,
            additional_queries=additional_queries,
            missing_aspects=missing_aspects,
        )

    def _parse_quality_evaluation(self, response_text: str) -> EvaluationResult:
        """Parse quality evaluation response."""
        # Check if sufficient
        assessment_match = re.search(
            r"\*\*Quality Assessment:\*\*\s*(SUFFICIENT|INSUFFICIENT)",
            response_text,
            re.IGNORECASE,
        )
        is_sufficient = (
            assessment_match.group(1).upper() == "SUFFICIENT" if assessment_match else True
        )

        # Extract confidence
        confidence_match = re.search(
            r"\*\*Confidence Score:\*\*\s*([\d.]+)", response_text, re.IGNORECASE
        )
        confidence = float(confidence_match.group(1)) if confidence_match else 0.5

        # Extract reasoning
        reasoning_match = re.search(
            r"\*\*Reasoning:\*\*\s*\n(.*?)(?:\n\*\*|$)", response_text, re.DOTALL
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else "No reasoning provided"

        # Extract missing aspects
        missing_aspects = []
        aspects_match = re.search(
            r"\*\*Missing Aspects:\*\*.*?\n(.*?)(?:\n\*\*|$)", response_text, re.DOTALL
        )
        if aspects_match:
            aspect_lines = aspects_match.group(1).strip().split("\n")
            for line in aspect_lines:
                aspect_match = re.match(r"[-*]\s*(.+)", line.strip())
                if aspect_match:
                    missing_aspects.append(aspect_match.group(1))

        return EvaluationResult(
            is_complete=is_sufficient,
            confidence=confidence,
            reasoning=reasoning,
            missing_aspects=missing_aspects,
        )

