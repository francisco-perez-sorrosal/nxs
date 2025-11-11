"""Shared fixtures and mocks for reasoning tests."""

import json
from pathlib import Path
from typing import Any, Callable, Optional

import pytest


class MockClaude:
    """Mock Claude for deterministic testing."""

    def __init__(
        self,
        responses: Optional[list[str]] = None,
        response_map: Optional[dict[str, str]] = None,
        response_generator: Optional[Callable[[str], str]] = None,
    ):
        """Initialize with canned responses.

        Args:
            responses: List of responses to return in order
            response_map: Dict mapping query patterns to responses
            response_generator: Function to generate response from query
        """
        self.responses = responses or []
        self.response_map = response_map or {}
        self.response_generator = response_generator
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []  # Track all calls
        self.api_key = "mock-api-key"
        self.max_tokens = 4096

    async def create_message(self, messages, **kwargs):
        """Mock create_message."""
        self.call_count += 1

        # Extract query from messages
        query = ""
        if messages:
            # Handle list of messages (from AgentLoop)
            if isinstance(messages, list):
                last_msg = messages[-1]
                if isinstance(last_msg, dict):
                    query = last_msg.get("content", "")
                else:
                    query = str(last_msg)
            # Handle single message dict (from reasoning components)
            elif isinstance(messages, dict):
                query = messages.get("content", "")
            else:
                query = str(messages)

        self.calls.append({"query": query, "kwargs": kwargs})

        # Determine response
        if self.response_generator:
            response_text = self.response_generator(query)
        elif query in self.response_map:
            response_text = self.response_map[query]
        elif self.responses:
            response_text = self.responses.pop(0)
        else:
            response_text = "Mock response"

        # Return in Claude message format
        class MockContent:
            def __init__(self, text):
                self.type = "text"
                self.text = text

        class MockMessage:
            def __init__(self, text):
                self.content = [MockContent(text)]
                self.stop_reason = "end_turn"  # Default stop reason

        return MockMessage(response_text)

    def with_model(self, model: str) -> "MockClaude":
        """Create a new MockClaude with same responses but different model."""
        return MockClaude(
            responses=self.responses.copy(),
            response_map=self.response_map.copy(),
            response_generator=self.response_generator,
        )


@pytest.fixture
def mock_claude():
    """Fixture providing MockClaude class."""
    return MockClaude


@pytest.fixture
def sample_queries():
    """Sample queries for testing."""
    return {
        "simple": [
            "What is 2+2?",
            "What is Python?",
            "Get the current time",
        ],
        "medium": [
            "Compare Python and Java for web development",
            "Summarize the document and list key points",
            "What's the weather and recommend activities",
        ],
        "complex": [
            "Research competitive landscape for quantum computing startups, analyze market trends, and recommend investment strategies",
            "Find similar companies to Tesla, compare their approaches to autonomous driving, and synthesize insights",
            "Investigate machine learning applications in healthcare comprehensively and provide detailed analysis",
        ],
    }


@pytest.fixture
def mock_complexity_response():
    """Mock response for complexity analysis."""

    def generator(query: str) -> str:
        # Check the actual query in the full prompt
        # Extract just the query part from the prompt
        query_match = query
        if "${query}" in query or "User Query" in query:
            # This is the full prompt, extract the actual query
            import re
            match = re.search(r"# User Query\s+(.+?)(?:\n#|$)", query, re.DOTALL)
            if match:
                query_match = match.group(1).strip()
        
        # Simple heuristic: short queries are simple, long ones are complex
        word_count = len(query_match.split())
        if word_count <= 5:
            return """**Complexity Level:** SIMPLE

**Recommended Strategy:** DIRECT

**Estimated Iterations:** 1

**Confidence:** 0.95

**Reasoning:**
This is a straightforward query that can be answered directly with general knowledge.

**Analysis Flags:**
- Requires Research: No
- Requires Synthesis: No
- Multi-Part Query: No
- Tool Count Estimate: 0"""
        elif word_count <= 12:
            return """**Complexity Level:** MEDIUM

**Recommended Strategy:** LIGHT_PLANNING

**Estimated Iterations:** 2

**Confidence:** 0.85

**Reasoning:**
This query has multiple parts that need coordination but is not overly complex.

**Analysis Flags:**
- Requires Research: Yes
- Requires Synthesis: Yes
- Multi-Part Query: Yes
- Tool Count Estimate: 2"""
        else:
            return """**Complexity Level:** COMPLEX

**Recommended Strategy:** DEEP_REASONING

**Estimated Iterations:** 3

**Confidence:** 0.90

**Reasoning:**
This is a multi-faceted query requiring deep research and synthesis.

**Analysis Flags:**
- Requires Research: Yes
- Requires Synthesis: Yes
- Multi-Part Query: Yes
- Tool Count Estimate: 5"""

    return generator


@pytest.fixture
def mock_quality_response():
    """Mock response for quality evaluation."""

    def generator(query: str) -> str:
        # Check if response seems adequate based on query context
        # This is simplified - in real tests, we'd check the actual response content
        return """**Quality Assessment:** SUFFICIENT

**Confidence Score:** 0.85

**Reasoning:**
The response adequately addresses the query with appropriate depth and accuracy.

**Missing Aspects:**
None identified

**Escalation Recommendation:**
No escalation needed - response quality is sufficient."""

    return generator


@pytest.fixture
def mock_planning_response():
    """Mock response for planning."""
    return """1. [HIGH PRIORITY] Research the topic fundamentals
   Tools: search, wikipedia

2. [MEDIUM PRIORITY] Gather specific examples and case studies
   Tools: search

3. [LOW PRIORITY] Synthesize findings into comprehensive answer
   Tools: none

Strategy: Start with foundational research, then gather specific evidence, and finally synthesize into a coherent response."""


@pytest.fixture
def mock_evaluation_response_incomplete():
    """Mock response for incomplete evaluation."""
    return """## Completeness Assessment
The results provide some information but are missing key aspects.

## Confidence Score
0.6

## Missing Aspects
- Historical context
- Comparative analysis
- Current trends

## Additional Queries Needed
1. What is the historical development of this topic?
2. How does this compare to similar approaches?
3. What are the current trends and future directions?"""


@pytest.fixture
def mock_evaluation_response_complete():
    """Mock response for complete evaluation."""
    return """## Completeness Assessment
COMPLETE

The accumulated results comprehensively answer all aspects of the original query with sufficient depth and accuracy.

## Confidence Score
0.95

## Missing Aspects
None - all key aspects have been addressed.

## Additional Queries Needed
None - the research is complete."""


@pytest.fixture
def mock_synthesis_response():
    """Mock response for synthesis."""
    return """Based on the accumulated research, here is a comprehensive answer:

The topic demonstrates several key characteristics. First, foundational research shows clear patterns.
Second, specific examples reinforce these patterns across different contexts. Finally, synthesis of
these findings reveals important insights that address the original query comprehensively.

In conclusion, the evidence strongly supports a nuanced understanding of the topic."""

