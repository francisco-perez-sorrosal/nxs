"""Tests for Synthesizer."""

import pytest

from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.synthesizer import Synthesizer


@pytest.mark.asyncio
async def test_synthesizer_single_result(mock_claude):
    """Test synthesizer with single result returns it directly."""
    llm = mock_claude()
    synthesizer = Synthesizer(llm, ReasoningConfig())

    results = [{"query": "Q1", "result": "Single answer"}]

    output = await synthesizer.synthesize("Test query", results)

    assert output == "Single answer"
    assert llm.call_count == 0  # No LLM call needed for single result


@pytest.mark.asyncio
async def test_synthesizer_multiple_results(mock_claude, mock_synthesis_response):
    """Test synthesizer combines multiple results."""
    llm = mock_claude(responses=[mock_synthesis_response])
    synthesizer = Synthesizer(llm, ReasoningConfig())

    results = [
        {"query": "Q1", "result": "Answer 1"},
        {"query": "Q2", "result": "Answer 2"},
        {"query": "Q3", "result": "Answer 3"},
    ]

    output = await synthesizer.synthesize("Test query", results)

    assert output is not None
    assert len(output) > 0
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_synthesizer_empty_results(mock_claude):
    """Test synthesizer handles empty results."""
    llm = mock_claude()
    synthesizer = Synthesizer(llm, ReasoningConfig())

    output = await synthesizer.synthesize("Test query", [])

    assert output == "No results available to synthesize."
    assert llm.call_count == 0


@pytest.mark.asyncio
async def test_synthesizer_error_handling(mock_claude):
    """Test synthesizer handles errors with fallback."""

    async def failing_create_message(*args, **kwargs):
        raise Exception("API Error")

    llm = mock_claude()
    llm.create_message = failing_create_message

    synthesizer = Synthesizer(llm, ReasoningConfig())

    results = [
        {"query": "Q1", "result": "A1"},
        {"query": "Q2", "result": "A2"},
    ]

    # Should not raise, use fallback
    output = await synthesizer.synthesize("Test", results)

    assert output is not None
    assert "A1" in output
    assert "A2" in output


@pytest.mark.asyncio
async def test_filter_results_few_results(mock_claude):
    """Test filter_results returns all when few results."""
    llm = mock_claude()
    synthesizer = Synthesizer(llm, ReasoningConfig())

    results = [
        {"query": "Q1", "result": "A1"},
        {"query": "Q2", "result": "A2"},
    ]

    filtered = await synthesizer.filter_results("Test", results)

    assert len(filtered) == 2
    assert llm.call_count == 0  # No filtering needed


@pytest.mark.asyncio
async def test_filter_results_many_results(mock_claude):
    """Test filter_results filters when many results."""
    # Mock response with ranked results
    llm = mock_claude(
        responses=[
            """Result ID: 0
Relevance: 9
Key Information: Most relevant
Reasoning: Directly answers query

Result ID: 2
Relevance: 8
Key Information: Also relevant
Reasoning: Provides context

Result ID: 4
Relevance: 7
Key Information: Supporting info
Reasoning: Additional details

Ranked list: 0, 2, 4"""
        ]
    )
    synthesizer = Synthesizer(llm, ReasoningConfig())

    results = [
        {"query": f"Q{i}", "result": f"A{i}"} for i in range(10)
    ]  # 10 results

    filtered = await synthesizer.filter_results("Test", results)

    assert len(filtered) <= 7  # Max 7 results
    assert len(filtered) > 0
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_filter_results_error_handling(mock_claude):
    """Test filter_results handles errors gracefully."""

    async def failing_create_message(*args, **kwargs):
        raise Exception("API Error")

    llm = mock_claude()
    llm.create_message = failing_create_message

    synthesizer = Synthesizer(llm, ReasoningConfig())

    results = [{"query": f"Q{i}", "result": f"A{i}"} for i in range(5)]

    # Should return all results as fallback
    filtered = await synthesizer.filter_results("Test", results)

    assert len(filtered) == 5


@pytest.mark.asyncio
async def test_synthesizer_formats_results_for_prompt(mock_claude, mock_synthesis_response):
    """Test synthesizer formats results correctly in prompt."""
    llm = mock_claude(responses=[mock_synthesis_response])
    synthesizer = Synthesizer(llm, ReasoningConfig())

    results = [
        {"query": "Question 1", "result": "Answer 1"},
        {"query": "Question 2", "result": "Answer 2"},
    ]

    await synthesizer.synthesize("Test query", results)

    # Verify results were included in prompt
    assert llm.call_count == 1
    prompt = llm.calls[0]["query"]
    assert "Question 1" in prompt
    assert "Answer 1" in prompt
    assert "Question 2" in prompt
    assert "Answer 2" in prompt


@pytest.mark.asyncio
async def test_fallback_synthesis_format(mock_claude):
    """Test fallback synthesis produces usable output."""

    async def failing_create_message(*args, **kwargs):
        raise Exception("API Error")

    llm = mock_claude()
    llm.create_message = failing_create_message

    synthesizer = Synthesizer(llm, ReasoningConfig())

    results = [
        {"query": "What is X?", "result": "X is this"},
        {"query": "What is Y?", "result": "Y is that"},
    ]

    output = await synthesizer.synthesize("Explain X and Y", results)

    # Should have query and numbered results
    assert "Explain X and Y" in output
    assert "1." in output
    assert "2." in output
    assert "X is this" in output
    assert "Y is that" in output

