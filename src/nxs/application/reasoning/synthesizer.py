"""Result synthesis and answer generation."""

import re
from typing import Optional

from nxs.application.claude import Claude
from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.utils import format_prompt, load_prompt
from nxs.logger import get_logger

logger = get_logger("reasoning.synthesizer")


class Synthesizer:
    """Result synthesis and answer generation.

    Responsibilities:
    - Filter results by relevance
    - Rank information by importance
    - Combine multiple sources coherently
    - Generate final comprehensive answer
    """

    def __init__(self, llm: Claude, config: ReasoningConfig):
        """Initialize synthesizer.

        Args:
            llm: Claude instance for synthesis
            config: Reasoning configuration
        """
        self.llm = llm
        self.config = config
        self.filter_prompt = load_prompt("reasoning/filter.txt")
        self.synthesis_prompt = load_prompt("reasoning/synthesis.txt")

    async def filter_results(
        self,
        query: str,
        results: list[dict],
    ) -> list[dict]:
        """Filter results by relevance to query.

        Args:
            query: Original user query
            results: Accumulated results to filter

        Returns:
            Filtered list of most relevant results
        """
        if not results:
            return []

        if len(results) <= 3:
            # No need to filter if we have few results
            return results

        logger.debug(f"Filtering {len(results)} results for relevance...")

        # Format results for prompt
        results_str = self._format_results_for_filtering(results)

        prompt = format_prompt(
            self.filter_prompt,
            query=query,
            results=results_str,
        )

        try:
            response = await self.llm.create_message(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            # Extract text from response
            response_text = getattr(response.content[0], "text", str(response.content[0]))

            # Parse ranked result IDs
            ranked_ids = self._parse_ranked_results(response_text, len(results))

            # Reorder results based on ranking
            filtered = []
            for result_id in ranked_ids[:7]:  # Keep top 7 max
                if 0 <= result_id < len(results):
                    filtered.append(results[result_id])

            logger.info(f"Filtered to {len(filtered)} most relevant results")
            return filtered

        except Exception as e:
            logger.error(f"Result filtering failed: {e}", exc_info=True)
            # Fallback: return all results
            return results

    async def synthesize(
        self,
        query: str,
        filtered_results: list[dict],
    ) -> str:
        """Generate final answer from filtered results.

        Args:
            query: Original user query
            filtered_results: Filtered and ranked results

        Returns:
            Final synthesized answer as string
        """
        if not filtered_results:
            return "No results available to synthesize."

        if len(filtered_results) == 1:
            # Single result, just return it
            return filtered_results[0].get("result", "")

        logger.debug(f"Synthesizing {len(filtered_results)} results...")

        # Format results for synthesis
        results_str = self._format_results_for_synthesis(filtered_results)

        prompt = format_prompt(
            self.synthesis_prompt,
            query=query,
            results=results_str,
        )

        try:
            response = await self.llm.create_message(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
            # Extract text from response
            synthesized = getattr(response.content[0], "text", str(response.content[0]))

            logger.info(f"Synthesized final answer: {len(synthesized)} chars")
            return synthesized

        except Exception as e:
            logger.error(f"Synthesis failed: {e}", exc_info=True)
            # Fallback: concatenate results with basic formatting
            fallback = self._fallback_synthesis(query, filtered_results)
            return fallback

    def _format_results_for_filtering(self, results: list[dict]) -> str:
        """Format results for filtering prompt."""
        formatted = []
        for i, result in enumerate(results):
            query = result.get("query", "Unknown query")
            content = result.get("result", "No content")
            formatted.append(f"Result {i}:\nQuery: {query}\nContent: {content[:300]}...\n")

        return "\n".join(formatted)

    def _format_results_for_synthesis(self, results: list[dict]) -> str:
        """Format results for synthesis prompt."""
        formatted = []
        for i, result in enumerate(results, 1):
            query = result.get("query", "Unknown query")
            content = result.get("result", "No content")
            formatted.append(f"Source {i} (from: {query}):\n{content}\n")

        return "\n---\n".join(formatted)

    def _parse_ranked_results(self, response_text: str, total_results: int) -> list[int]:
        """Parse ranked result IDs from filter response.

        Args:
            response_text: LLM response with rankings
            total_results: Total number of results

        Returns:
            List of result IDs in priority order
        """
        ranked_ids = []

        # Look for explicit ranked list at the end
        ranked_section = re.search(
            r"ranked list.*?:\s*\n(.*?)$", response_text, re.DOTALL | re.IGNORECASE
        )

        if ranked_section:
            # Parse comma-separated or newline-separated list of IDs
            ids_text = ranked_section.group(1)
            id_matches = re.findall(r"\b(\d+)\b", ids_text)
            ranked_ids = [int(m) for m in id_matches]

        # If no ranked list found, look for Result ID mentions
        if not ranked_ids:
            result_mentions = re.finditer(r"Result ID:\s*(\d+)", response_text)
            ranked_ids = [int(m.group(1)) for m in result_mentions]

        # If still nothing, return original order
        if not ranked_ids:
            ranked_ids = list(range(total_results))

        return ranked_ids

    def _fallback_synthesis(self, query: str, results: list[dict]) -> str:
        """Fallback synthesis when LLM synthesis fails.

        Args:
            query: Original query
            results: Results to combine

        Returns:
            Simple concatenated answer
        """
        parts = [f"Based on the query: {query}\n\nHere are the findings:\n"]

        for i, result in enumerate(results, 1):
            content = result.get("result", "No content")
            parts.append(f"\n{i}. {content}")

        return "\n".join(parts)

