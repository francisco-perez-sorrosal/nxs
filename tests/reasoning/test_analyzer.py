"""Tests for QueryComplexityAnalyzer."""

import pytest

from nxs.application.reasoning.analyzer import QueryComplexityAnalyzer
from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.types import ComplexityLevel, ExecutionStrategy


@pytest.mark.asyncio
async def test_analyzer_simple_query(mock_claude, mock_complexity_response):
    """Test that simple queries are classified as SIMPLE."""
    llm = mock_claude(response_generator=mock_complexity_response)
    analyzer = QueryComplexityAnalyzer(llm, ReasoningConfig())

    result = await analyzer.analyze("What is 2+2?")

    assert result.complexity_level == ComplexityLevel.SIMPLE
    assert result.recommended_strategy == ExecutionStrategy.DIRECT
    assert result.estimated_iterations == 1
    assert result.confidence >= 0.9
    assert result.requires_research is False


@pytest.mark.asyncio
async def test_analyzer_medium_query(mock_claude, mock_complexity_response, sample_queries):
    """Test that medium complexity queries are classified correctly."""
    llm = mock_claude(response_generator=mock_complexity_response)
    analyzer = QueryComplexityAnalyzer(llm, ReasoningConfig())

    result = await analyzer.analyze(sample_queries["medium"][0])

    assert result.complexity_level == ComplexityLevel.MEDIUM
    assert result.recommended_strategy == ExecutionStrategy.LIGHT_PLANNING
    assert result.estimated_iterations >= 2
    assert result.multi_part_query is True


@pytest.mark.asyncio
async def test_analyzer_complex_query(mock_claude, mock_complexity_response, sample_queries):
    """Test that complex multi-part queries are classified correctly."""
    llm = mock_claude(response_generator=mock_complexity_response)
    analyzer = QueryComplexityAnalyzer(llm, ReasoningConfig())

    result = await analyzer.analyze(sample_queries["complex"][0])

    assert result.complexity_level == ComplexityLevel.COMPLEX
    assert result.recommended_strategy == ExecutionStrategy.DEEP_REASONING
    assert result.estimated_iterations >= 3
    assert result.requires_research is True
    assert result.multi_part_query is True


@pytest.mark.asyncio
async def test_analyzer_with_tools(mock_claude, mock_complexity_response):
    """Test analyzer considers available tools."""
    llm = mock_claude(response_generator=mock_complexity_response)
    analyzer = QueryComplexityAnalyzer(llm, ReasoningConfig())

    tools = ["search", "calculator", "weather"]
    result = await analyzer.analyze("Calculate the weather average", available_tools=tools)

    assert result is not None
    # Verify tools were passed in the prompt
    assert llm.call_count == 1
    assert "search" in llm.calls[0]["query"]


@pytest.mark.asyncio
async def test_analyzer_error_handling(mock_claude):
    """Test analyzer handles LLM errors gracefully."""

    async def failing_create_message(*args, **kwargs):
        raise Exception("API Error")

    llm = mock_claude()
    llm.create_message = failing_create_message

    analyzer = QueryComplexityAnalyzer(llm, ReasoningConfig())

    # Should not raise, but return fallback
    result = await analyzer.analyze("Any query")

    assert result is not None
    assert result.complexity_level == ComplexityLevel.MEDIUM
    assert result.confidence == 0.0  # Indicates fallback


@pytest.mark.asyncio
async def test_analyzer_parsing_variations(mock_claude):
    """Test analyzer can parse various response formats."""
    # Test with lowercase
    llm = mock_claude(
        responses=[
            """**complexity level:** simple
**recommended strategy:** direct
**estimated iterations:** 1
**confidence:** 0.9
**reasoning:** Simple query."""
        ]
    )
    analyzer = QueryComplexityAnalyzer(llm, ReasoningConfig())

    result = await analyzer.analyze("Test")

    assert result.complexity_level == ComplexityLevel.SIMPLE
    assert result.recommended_strategy == ExecutionStrategy.DIRECT


@pytest.mark.asyncio
async def test_analyzer_tracks_calls(mock_claude, mock_complexity_response):
    """Test that analyzer tracks LLM calls for debugging."""
    llm = mock_claude(response_generator=mock_complexity_response)
    analyzer = QueryComplexityAnalyzer(llm, ReasoningConfig())

    await analyzer.analyze("Query 1")
    await analyzer.analyze("Query 2")

    assert llm.call_count == 2
    assert len(llm.calls) == 2
    assert "Query 1" in llm.calls[0]["query"]
    assert "Query 2" in llm.calls[1]["query"]

