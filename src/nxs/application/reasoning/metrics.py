"""Metrics monitoring system for adaptive reasoning.

Tracks and analyzes:
- Strategy distribution (initial vs final)
- Escalation patterns
- Quality scores
- Latency statistics
- Error rates
"""

import time
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

from nxs.application.reasoning.types import ExecutionStrategy, ComplexityLevel
from nxs.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExecutionMetrics:
    """Metrics for a single execution."""
    
    query_id: str
    timestamp: datetime
    query: str
    initial_strategy: ExecutionStrategy
    final_strategy: ExecutionStrategy
    complexity_level: ComplexityLevel
    execution_time: float
    escalated: bool
    escalation_count: int
    final_quality_score: float
    iterations: int
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "query_id": self.query_id,
            "timestamp": self.timestamp.isoformat(),
            "query": self.query[:100],  # Truncated
            "initial_strategy": self.initial_strategy.value,
            "final_strategy": self.final_strategy.value,
            "complexity_level": self.complexity_level.value,
            "execution_time": self.execution_time,
            "escalated": self.escalated,
            "escalation_count": self.escalation_count,
            "final_quality_score": self.final_quality_score,
            "iterations": self.iterations,
            "error": self.error,
        }


@dataclass
class AggregateMetrics:
    """Aggregate metrics across multiple executions."""
    
    total_executions: int = 0
    
    # Strategy distribution
    initial_strategy_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    final_strategy_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Escalation metrics
    escalation_count: int = 0
    escalation_rate: float = 0.0
    escalation_patterns: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Quality metrics
    quality_scores: List[float] = field(default_factory=list)
    avg_quality: float = 0.0
    min_quality: float = 1.0
    max_quality: float = 0.0
    
    # Latency metrics
    execution_times: List[float] = field(default_factory=list)
    avg_latency: float = 0.0
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    
    # Strategy-specific latency
    latency_by_strategy: Dict[str, List[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    
    # Error tracking
    error_count: int = 0
    error_rate: float = 0.0
    
    def update(self, metrics: ExecutionMetrics):
        """Update aggregate metrics with a new execution."""
        self.total_executions += 1
        
        # Update strategy counts
        self.initial_strategy_counts[metrics.initial_strategy.value] += 1
        self.final_strategy_counts[metrics.final_strategy.value] += 1
        
        # Update escalation metrics
        if metrics.escalated:
            self.escalation_count += 1
            pattern = f"{metrics.initial_strategy.value}->{metrics.final_strategy.value}"
            self.escalation_patterns[pattern] += 1
        
        self.escalation_rate = self.escalation_count / self.total_executions
        
        # Update quality metrics
        self.quality_scores.append(metrics.final_quality_score)
        self.avg_quality = statistics.mean(self.quality_scores)
        self.min_quality = min(self.quality_scores)
        self.max_quality = max(self.quality_scores)
        
        # Update latency metrics
        self.execution_times.append(metrics.execution_time)
        self.avg_latency = statistics.mean(self.execution_times)
        
        if len(self.execution_times) >= 2:
            sorted_times = sorted(self.execution_times)
            self.p50_latency = statistics.median(sorted_times)
            
            if len(sorted_times) >= 20:
                self.p95_latency = sorted_times[int(len(sorted_times) * 0.95)]
                self.p99_latency = sorted_times[int(len(sorted_times) * 0.99)]
        
        # Update strategy-specific latency
        self.latency_by_strategy[metrics.final_strategy.value].append(
            metrics.execution_time
        )
        
        # Update error metrics
        if metrics.error:
            self.error_count += 1
        self.error_rate = self.error_count / self.total_executions
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "total_executions": self.total_executions,
            "initial_strategy_distribution": dict(self.initial_strategy_counts),
            "final_strategy_distribution": dict(self.final_strategy_counts),
            "escalation_rate": self.escalation_rate,
            "escalation_patterns": dict(self.escalation_patterns),
            "quality_metrics": {
                "avg": self.avg_quality,
                "min": self.min_quality,
                "max": self.max_quality,
            },
            "latency_metrics": {
                "avg": self.avg_latency,
                "p50": self.p50_latency,
                "p95": self.p95_latency,
                "p99": self.p99_latency,
            },
            "latency_by_strategy": {
                k: statistics.mean(v) if v else 0.0
                for k, v in self.latency_by_strategy.items()
            },
            "error_rate": self.error_rate,
        }


class MetricsCollector:
    """Collects and stores reasoning metrics."""
    
    def __init__(self):
        """Initialize metrics collector."""
        self.executions: List[ExecutionMetrics] = []
        self.aggregate = AggregateMetrics()
        self._query_counter = 0
    
    def start_execution(self, query: str) -> tuple[str, float]:
        """Start tracking a new execution.
        
        Returns:
            Tuple of (query_id, start_time)
        """
        self._query_counter += 1
        query_id = f"query_{self._query_counter}_{int(time.time())}"
        start_time = time.time()
        return query_id, start_time
    
    def record_execution(
        self,
        query_id: str,
        start_time: float,
        query: str,
        initial_strategy: ExecutionStrategy,
        final_strategy: ExecutionStrategy,
        complexity_level: ComplexityLevel,
        escalated: bool,
        escalation_count: int,
        final_quality_score: float,
        iterations: int,
        error: Optional[str] = None,
    ):
        """Record a completed execution."""
        execution_time = time.time() - start_time
        
        metrics = ExecutionMetrics(
            query_id=query_id,
            timestamp=datetime.now(),
            query=query,
            initial_strategy=initial_strategy,
            final_strategy=final_strategy,
            complexity_level=complexity_level,
            execution_time=execution_time,
            escalated=escalated,
            escalation_count=escalation_count,
            final_quality_score=final_quality_score,
            iterations=iterations,
            error=error,
        )
        
        self.executions.append(metrics)
        self.aggregate.update(metrics)
        
        logger.debug(
            f"Recorded execution: {query_id}, "
            f"strategy={final_strategy.value}, "
            f"time={execution_time:.2f}s, "
            f"quality={final_quality_score:.2f}"
        )
    
    def get_summary(self) -> Dict:
        """Get summary of all metrics."""
        return {
            "aggregate": self.aggregate.to_dict(),
            "recent_executions": [
                e.to_dict() for e in self.executions[-10:]
            ],
        }
    
    def get_strategy_analysis(self) -> Dict:
        """Analyze strategy effectiveness."""
        strategy_quality = defaultdict(list)
        strategy_latency = defaultdict(list)
        
        for exec_metrics in self.executions:
            strategy = exec_metrics.final_strategy.value
            strategy_quality[strategy].append(exec_metrics.final_quality_score)
            strategy_latency[strategy].append(exec_metrics.execution_time)
        
        analysis = {}
        for strategy in ["DIRECT", "LIGHT_PLANNING", "DEEP_REASONING"]:
            if strategy in strategy_quality:
                analysis[strategy] = {
                    "avg_quality": statistics.mean(strategy_quality[strategy]),
                    "avg_latency": statistics.mean(strategy_latency[strategy]),
                    "count": len(strategy_quality[strategy]),
                }
        
        return analysis
    
    def get_escalation_analysis(self) -> Dict:
        """Analyze escalation patterns."""
        escalations = [e for e in self.executions if e.escalated]
        
        if not escalations:
            return {
                "total_escalations": 0,
                "escalation_rate": 0.0,
                "patterns": {},
            }
        
        # Calculate quality improvement from escalation
        quality_improvements = []
        for escalation in escalations:
            # Estimate: assume initial quality was below threshold
            estimated_initial_quality = self.aggregate.min_quality
            improvement = escalation.final_quality_score - estimated_initial_quality
            quality_improvements.append(improvement)
        
        return {
            "total_escalations": len(escalations),
            "escalation_rate": len(escalations) / len(self.executions),
            "patterns": dict(self.aggregate.escalation_patterns),
            "avg_quality_improvement": statistics.mean(quality_improvements) if quality_improvements else 0.0,
            "avg_escalation_overhead": statistics.mean([e.execution_time for e in escalations]),
        }
    
    def reset(self):
        """Reset all metrics."""
        self.executions.clear()
        self.aggregate = AggregateMetrics()
        self._query_counter = 0
        logger.info("Metrics reset")


# Global metrics collector instance
_global_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return _global_collector

