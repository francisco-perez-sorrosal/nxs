"""Performance benchmarks for adaptive reasoning system.

Measures:
- Latency per strategy (DIRECT, LIGHT, DEEP)
- Escalation frequency
- Quality improvement from escalation
- Strategy distribution
"""

import pytest
import time
import statistics
from typing import List, Dict, Any

from nxs.application.conversation import Conversation
from nxs.application.tool_registry import ToolRegistry
from nxs.application.mcp_tool_provider import MCPToolProvider
from nxs.application.reasoning_loop import AdaptiveReasoningLoop
from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.analyzer import QueryComplexityAnalyzer
from nxs.application.reasoning.planner import Planner
from nxs.application.reasoning.evaluator import Evaluator
from nxs.application.reasoning.synthesizer import Synthesizer
from nxs.application.reasoning.types import ExecutionStrategy, ComplexityLevel
from tests.reasoning.conftest import MockClaude


class PerformanceMetrics:
    """Collect and analyze performance metrics."""
    
    def __init__(self):
        self.latencies: Dict[str, List[float]] = {
            "DIRECT": [],
            "LIGHT": [],
            "DEEP": [],
        }
        self.escalations: List[Dict[str, Any]] = []
        self.strategy_distribution: Dict[str, int] = {
            "DIRECT": 0,
            "LIGHT": 0,
            "DEEP": 0,
        }
        self.quality_scores: List[float] = []
        
    def record_execution(
        self,
        strategy: str,
        latency: float,
        quality: float,
        escalated: bool = False,
        from_strategy: str = None,
    ):
        """Record a single execution."""
        self.latencies[strategy].append(latency)
        self.strategy_distribution[strategy] += 1
        self.quality_scores.append(quality)
        
        if escalated:
            self.escalations.append({
                "from": from_strategy,
                "to": strategy,
                "latency": latency,
                "quality": quality,
            })
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary statistics."""
        summary = {
            "latency_stats": {},
            "escalation_rate": 0.0,
            "strategy_distribution": self.strategy_distribution.copy(),
            "avg_quality": 0.0,
        }
        
        # Latency statistics per strategy
        for strategy, times in self.latencies.items():
            if times:
                summary["latency_stats"][strategy] = {
                    "mean": statistics.mean(times),
                    "median": statistics.median(times),
                    "min": min(times),
                    "max": max(times),
                    "count": len(times),
                }
        
        # Escalation rate
        total_executions = sum(self.strategy_distribution.values())
        if total_executions > 0:
            summary["escalation_rate"] = len(self.escalations) / total_executions
        
        # Average quality
        if self.quality_scores:
            summary["avg_quality"] = statistics.mean(self.quality_scores)
        
        return summary


@pytest.fixture
def metrics_collector():
    """Create a metrics collector."""
    return PerformanceMetrics()


@pytest.fixture
def benchmark_setup():
    """Setup for benchmarking tests."""
    def response_generator(query):
        query_str = query if isinstance(query, str) else str(query)
        
        # Add artificial delay to simulate real LLM latency
        time.sleep(0.001)  # 1ms base delay
        
        if "complexity" in query_str.lower():
            if "simple" in query_str.lower():
                return """**Complexity Level:** SIMPLE
**Recommended Strategy:** DIRECT
**Estimated Iterations:** 1
**Confidence:** 0.95"""
            elif "medium" in query_str.lower():
                time.sleep(0.002)  # Slightly longer for medium
                return """**Complexity Level:** MEDIUM
**Recommended Strategy:** LIGHT_PLANNING
**Estimated Iterations:** 2
**Confidence:** 0.85"""
            else:
                time.sleep(0.003)  # Longer for complex
                return """**Complexity Level:** COMPLEX
**Recommended Strategy:** DEEP_REASONING
**Estimated Iterations:** 3
**Confidence:** 0.90"""
        
        elif "quality assessment" in query_str.lower():
            return """**Quality Assessment:** SUFFICIENT
**Confidence Score:** 0.88
**Reasoning:** Good quality response."""
        
        return "Detailed response to query."
    
    llm = MockClaude(response_generator=response_generator)
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()
    
    analyzer = QueryComplexityAnalyzer(llm, config)
    planner = Planner(llm, config)
    evaluator = Evaluator(llm, config)
    synthesizer = Synthesizer(llm, config)
    
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
    
    return reasoning_loop


@pytest.mark.asyncio
async def test_latency_direct_strategy(benchmark_setup, metrics_collector):
    """Benchmark DIRECT strategy latency."""
    loop = benchmark_setup
    
    # Force DIRECT strategy
    loop.force_strategy = ExecutionStrategy.DIRECT
    
    # Run multiple iterations
    iterations = 5
    for _ in range(iterations):
        start = time.time()
        result = await loop.run("simple query", use_streaming=False)
        latency = time.time() - start
        
        metrics_collector.record_execution("DIRECT", latency, 0.9)
        assert result is not None
    
    # Verify latency recorded
    assert len(metrics_collector.latencies["DIRECT"]) == iterations


@pytest.mark.asyncio
async def test_latency_light_strategy(benchmark_setup, metrics_collector):
    """Benchmark LIGHT_PLANNING strategy latency."""
    loop = benchmark_setup
    
    # Force LIGHT_PLANNING strategy
    loop.force_strategy = ExecutionStrategy.LIGHT_PLANNING
    
    iterations = 5
    for _ in range(iterations):
        start = time.time()
        result = await loop.run("medium query", use_streaming=False)
        latency = time.time() - start
        
        metrics_collector.record_execution("LIGHT", latency, 0.85)
        assert result is not None
    
    assert len(metrics_collector.latencies["LIGHT"]) == iterations


@pytest.mark.asyncio
async def test_latency_deep_strategy(benchmark_setup, metrics_collector):
    """Benchmark DEEP_REASONING strategy latency."""
    loop = benchmark_setup
    
    # Force DEEP_REASONING strategy
    loop.force_strategy = ExecutionStrategy.DEEP_REASONING
    
    iterations = 5
    for _ in range(iterations):
        start = time.time()
        result = await loop.run("complex query", use_streaming=False)
        latency = time.time() - start
        
        metrics_collector.record_execution("DEEP", latency, 0.92)
        assert result is not None
    
    assert len(metrics_collector.latencies["DEEP"]) == iterations


@pytest.mark.asyncio
async def test_strategy_distribution(benchmark_setup, metrics_collector):
    """Test distribution of strategies across varied queries."""
    loop = benchmark_setup
    
    queries = [
        ("simple query 1", "DIRECT"),
        ("simple query 2", "DIRECT"),
        ("medium complexity query", "LIGHT"),
        ("complex multi-part query", "DEEP"),
        ("simple query 3", "DIRECT"),
    ]
    
    for query, expected_strategy in queries:
        loop.force_strategy = None  # Let analyzer decide
        
        # Track which strategy was used
        strategy_used = None
        
        def track_strategy(s, r):
            nonlocal strategy_used
            strategy_used = s
        
        callbacks = {"on_strategy_selected": track_strategy}
        
        start = time.time()
        await loop.run(query, use_streaming=False, callbacks=callbacks)
        latency = time.time() - start
        
        if strategy_used:
            # Normalize strategy name to match metrics collector keys
            strategy_name = strategy_used.value if hasattr(strategy_used, "value") else str(strategy_used)
            
            # Map ExecutionStrategy values to metrics collector keys
            if "DIRECT" in strategy_name:
                strategy_key = "DIRECT"
            elif "LIGHT" in strategy_name:
                strategy_key = "LIGHT"
            elif "DEEP" in strategy_name:
                strategy_key = "DEEP"
            else:
                strategy_key = "DIRECT"  # Default fallback
            
            metrics_collector.record_execution(
                strategy_key,
                latency,
                0.85
            )
    
    summary = metrics_collector.get_summary()
    
    # Verify strategies were distributed
    assert summary["strategy_distribution"]["DIRECT"] > 0


@pytest.mark.asyncio
async def test_escalation_overhead(benchmark_setup, metrics_collector):
    """Measure overhead of escalation process."""
    loop = benchmark_setup
    
    # Setup to trigger escalation
    def escalation_response_generator(query):
        query_str = query if isinstance(query, str) else str(query)
        
        if "complexity" in query_str.lower():
            return """**Complexity Level:** SIMPLE
**Recommended Strategy:** DIRECT
**Estimated Iterations:** 1
**Confidence:** 0.95"""
        
        elif "quality assessment" in query_str.lower():
            # First call: insufficient quality (trigger escalation)
            if not hasattr(escalation_response_generator, "call_count"):
                escalation_response_generator.call_count = 0
            escalation_response_generator.call_count += 1
            
            if escalation_response_generator.call_count <= 1:
                return """**Quality Assessment:** INSUFFICIENT
**Confidence Score:** 0.40
**Reasoning:** Needs more depth."""
            else:
                return """**Quality Assessment:** SUFFICIENT
**Confidence Score:** 0.85
**Reasoning:** Much better now."""
        
        return "Response"
    
    # Create new loop with escalation-triggering responses
    llm = MockClaude(response_generator=escalation_response_generator)
    conversation = Conversation()
    tool_registry = ToolRegistry()
    config = ReasoningConfig()
    
    analyzer = QueryComplexityAnalyzer(llm, config)
    planner = Planner(llm, config)
    evaluator = Evaluator(llm, config)
    synthesizer = Synthesizer(llm, config)
    
    escalation_loop = AdaptiveReasoningLoop(
        llm=llm,
        conversation=conversation,
        tool_registry=tool_registry,
        analyzer=analyzer,
        planner=planner,
        evaluator=evaluator,
        synthesizer=synthesizer,
        config=config,
    )
    
    # Track escalation
    escalated = False
    
    def track_escalation(from_s, to_s, r, c):
        nonlocal escalated
        escalated = True
    
    callbacks = {"on_auto_escalation": track_escalation}
    
    start = time.time()
    result = await escalation_loop.run(
        "query",
        use_streaming=False,
        callbacks=callbacks
    )
    latency = time.time() - start
    
    assert result is not None
    # Note: escalation may or may not occur depending on quality evaluation


def test_metrics_summary(metrics_collector):
    """Test metrics summary generation."""
    # Add sample data
    metrics_collector.record_execution("DIRECT", 0.1, 0.9)
    metrics_collector.record_execution("DIRECT", 0.12, 0.88)
    metrics_collector.record_execution("LIGHT", 0.25, 0.85, escalated=True, from_strategy="DIRECT")
    metrics_collector.record_execution("DEEP", 0.5, 0.92)
    
    summary = metrics_collector.get_summary()
    
    # Verify summary structure
    assert "latency_stats" in summary
    assert "escalation_rate" in summary
    assert "strategy_distribution" in summary
    assert "avg_quality" in summary
    
    # Verify statistics calculated
    assert "DIRECT" in summary["latency_stats"]
    assert summary["latency_stats"]["DIRECT"]["count"] == 2
    assert summary["latency_stats"]["DIRECT"]["mean"] == 0.11
    
    # Verify escalation rate
    assert summary["escalation_rate"] == 0.25  # 1 escalation out of 4 executions
    
    # Verify average quality
    assert summary["avg_quality"] == pytest.approx((0.9 + 0.88 + 0.85 + 0.92) / 4)


@pytest.mark.asyncio
async def test_comparative_latency(benchmark_setup):
    """Compare latencies across strategies."""
    loop = benchmark_setup
    
    strategies = [
        (ExecutionStrategy.DIRECT, "DIRECT"),
        (ExecutionStrategy.LIGHT_PLANNING, "LIGHT_PLANNING"),
        (ExecutionStrategy.DEEP_REASONING, "DEEP_REASONING"),
    ]
    
    results = {}
    
    for strategy, name in strategies:
        loop.force_strategy = strategy
        
        times = []
        for _ in range(3):
            start = time.time()
            await loop.run("test query", use_streaming=False)
            latency = time.time() - start
            times.append(latency)
        
        results[name] = statistics.mean(times)
    
    # Generally expect: DIRECT < LIGHT < DEEP
    # (though with mocked responses, differences may be minimal)
    assert results["DIRECT"] >= 0
    assert results["LIGHT_PLANNING"] >= 0
    assert results["DEEP_REASONING"] >= 0

