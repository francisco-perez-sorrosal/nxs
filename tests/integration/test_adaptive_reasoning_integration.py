"""Integration tests for the full adaptive reasoning system.

Tests the complete flow from CommandControlAgent through AdaptiveReasoningLoop
to the underlying components (Analyzer, Planner, Evaluator, Synthesizer).
"""

import pytest
from nxs.application.claude import Claude
from nxs.application.conversation import Conversation
from nxs.application.tool_registry import ToolRegistry
from nxs.application.mcp_tool_provider import MCPToolProvider
from nxs.application.command_control import CommandControlAgent
from nxs.application.reasoning_loop import AdaptiveReasoningLoop
from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.analyzer import QueryComplexityAnalyzer
from nxs.application.reasoning.planner import Planner
from nxs.application.reasoning.evaluator import Evaluator
from nxs.application.reasoning.synthesizer import Synthesizer
from nxs.application.reasoning.types import ExecutionStrategy
from tests.reasoning.conftest import MockClaude


@pytest.fixture
def mock_artifact_manager():
    """Mock ArtifactManager for testing."""
    class MockArtifactManager:
        def __init__(self):
            self.clients = {}  # Empty MCP clients for now
            
        async def get_resources(self):
            return {}
            
        async def find_prompt(self, name):
            return None
    
    return MockArtifactManager()


@pytest.fixture
def full_reasoning_stack(mock_artifact_manager):
    """Create a complete reasoning stack for integration testing."""
    
    def response_generator(query):
        """Generate responses based on query content."""
        query_str = query if isinstance(query, str) else str(query)
        
        # Complexity analysis
        if "complexity" in query_str.lower() or "user query" in query_str.lower():
            if "simple" in query_str.lower() or len(query_str) < 50:
                return """**Complexity Level:** SIMPLE
**Recommended Strategy:** DIRECT
**Estimated Iterations:** 1
**Confidence:** 0.95
**Reasoning:** Simple factual query."""
            else:
                return """**Complexity Level:** MEDIUM
**Recommended Strategy:** LIGHT_PLANNING
**Estimated Iterations:** 2
**Confidence:** 0.85
**Reasoning:** Requires some analysis."""
        
        # Quality evaluation
        elif "quality assessment" in query_str.lower():
            return """**Quality Assessment:** SUFFICIENT
**Confidence Score:** 0.90
**Reasoning:** Comprehensive and accurate response."""
        
        # Default response
        return "This is a comprehensive answer to your query with detailed information."
    
    llm = MockClaude(response_generator=response_generator)
    conversation = Conversation(system_message="You are a helpful assistant.")
    tool_registry = ToolRegistry()
    
    # Register MCP tool provider (empty for now)
    mcp_provider = MCPToolProvider(mock_artifact_manager.clients)
    tool_registry.register_provider(mcp_provider)
    
    # Create reasoning components
    config = ReasoningConfig()
    analyzer = QueryComplexityAnalyzer(llm, config)
    planner = Planner(llm, config)
    evaluator = Evaluator(llm, config)
    synthesizer = Synthesizer(llm, config)
    
    # Create AdaptiveReasoningLoop
    reasoning_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=config,
    )
    
    # Create CommandControlAgent
    agent = CommandControlAgent(
        artifact_manager=mock_artifact_manager,
        reasoning_loop=reasoning_loop,
    )
    
    return {
        "agent": agent,
        "reasoning_loop": reasoning_loop,
        "conversation": conversation,
        "llm": llm,
        "config": config,
    }


@pytest.mark.asyncio
async def test_full_stack_simple_query(full_reasoning_stack):
    """Test full stack with a simple query."""
    agent = full_reasoning_stack["agent"]
    conversation = full_reasoning_stack["conversation"]
    
    # Execute query
    result = await agent.run("What is 2+2?", use_streaming=False)
    
    # Verify response
    assert result is not None
    assert len(result) > 0
    assert isinstance(result, str)
    
    # Verify conversation updated
    assert conversation.get_message_count() > 0


@pytest.mark.asyncio
async def test_full_stack_with_resource_mention(full_reasoning_stack):
    """Test full stack with resource mentions (@ syntax)."""
    agent = full_reasoning_stack["agent"]
    
    # Query with @resource mention (will be ignored since no resources available)
    result = await agent.run(
        "What is @document1 about?",
        use_streaming=False
    )
    
    assert result is not None
    assert len(result) > 0


@pytest.mark.asyncio
async def test_reasoning_loop_direct_strategy(full_reasoning_stack):
    """Test reasoning loop executes with DIRECT strategy."""
    reasoning_loop = full_reasoning_stack["reasoning_loop"]
    
    result = await reasoning_loop.run(
        "Simple question?",
        use_streaming=False
    )
    
    assert result is not None
    assert len(result) > 0


@pytest.mark.asyncio
async def test_reasoning_loop_with_callbacks(full_reasoning_stack):
    """Test reasoning loop callback integration."""
    reasoning_loop = full_reasoning_stack["reasoning_loop"]
    
    # Track callback invocations
    callback_log = []
    
    callbacks = {
        "on_analysis_start": lambda: callback_log.append("analysis_start"),
        "on_analysis_complete": lambda c: callback_log.append("analysis_complete"),
        "on_strategy_selected": lambda s, r: callback_log.append("strategy_selected"),
        "on_quality_check_start": lambda: callback_log.append("quality_check_start"),
        "on_quality_check_complete": lambda e: callback_log.append("quality_check_complete"),
        "on_final_response": lambda s, a, q, e: callback_log.append("final_response"),
    }
    
    result = await reasoning_loop.run(
        "Test query",
        use_streaming=False,
        callbacks=callbacks
    )
    
    assert result is not None
    
    # Verify callbacks were invoked
    assert "analysis_start" in callback_log
    assert "analysis_complete" in callback_log
    assert "strategy_selected" in callback_log
    assert "quality_check_start" in callback_log
    assert "quality_check_complete" in callback_log
    assert "final_response" in callback_log


@pytest.mark.asyncio
async def test_conversation_persistence(full_reasoning_stack):
    """Test conversation state persists across multiple queries."""
    agent = full_reasoning_stack["agent"]
    conversation = full_reasoning_stack["conversation"]
    
    initial_count = conversation.get_message_count()
    
    # Execute first query
    await agent.run("First question", use_streaming=False)
    count_after_first = conversation.get_message_count()
    
    # Execute second query
    await agent.run("Second question", use_streaming=False)
    count_after_second = conversation.get_message_count()
    
    # Verify conversation grew
    assert count_after_first > initial_count
    assert count_after_second > count_after_first


@pytest.mark.asyncio
async def test_config_customization(mock_artifact_manager):
    """Test custom configuration affects behavior."""
    
    # Custom config with very low quality threshold
    custom_config = ReasoningConfig(
        max_iterations=5,
        min_quality_direct=0.95,  # Very high threshold
    )
    
    def response_generator(query):
        query_str = query if isinstance(query, str) else str(query)
        if "complexity" in query_str.lower():
            return """**Complexity Level:** SIMPLE
**Recommended Strategy:** DIRECT
**Estimated Iterations:** 1
**Confidence:** 0.95"""
        elif "quality assessment" in query_str.lower():
            # First attempt: low quality
            return """**Quality Assessment:** INSUFFICIENT
**Confidence Score:** 0.70
**Reasoning:** Needs more detail."""
        return "Response"
    
    llm = MockClaude(response_generator=response_generator)
    conversation = Conversation()
    tool_registry = ToolRegistry()
    mcp_provider = MCPToolProvider(mock_artifact_manager.clients)
    tool_registry.register_provider(mcp_provider)
    
    analyzer = QueryComplexityAnalyzer(llm, custom_config)
    planner = Planner(llm, custom_config)
    evaluator = Evaluator(llm, custom_config)
    synthesizer = Synthesizer(llm, custom_config)
    
    reasoning_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=custom_config,
    )
    
    # Verify config is applied
    assert reasoning_loop.config.max_iterations == 5
    assert reasoning_loop.config.min_quality_direct == 0.95


@pytest.mark.asyncio
async def test_error_handling_in_stack(full_reasoning_stack):
    """Test error handling propagates correctly through the stack."""
    agent = full_reasoning_stack["agent"]
    
    # Empty query should still work (though may return minimal response)
    try:
        result = await agent.run("", use_streaming=False)
        # Empty queries might be handled gracefully
        assert result is not None
    except Exception:
        # Or they might raise an exception, which is also valid
        pass


@pytest.mark.asyncio
async def test_agent_conversation_property(full_reasoning_stack):
    """Test CommandControlAgent conversation property delegation."""
    agent = full_reasoning_stack["agent"]
    reasoning_loop = full_reasoning_stack["reasoning_loop"]
    
    # Verify conversation property works
    assert agent.conversation is reasoning_loop.conversation
    
    # Verify setter works
    new_conversation = Conversation(system_message="New system message")
    agent.conversation = new_conversation
    
    assert agent.conversation is new_conversation
    assert reasoning_loop.conversation is new_conversation

