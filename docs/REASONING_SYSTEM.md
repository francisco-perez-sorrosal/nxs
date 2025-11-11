# Adaptive Reasoning System Documentation

## Overview

The Nexus Adaptive Reasoning System provides intelligent, self-correcting query execution with automatic quality guarantees. The system analyzes query complexity, selects appropriate execution strategies, and automatically escalates to deeper reasoning when quality is insufficient.

## Key Features

1. **Adaptive Execution**: Automatically selects DIRECT, LIGHT_PLANNING, or DEEP_REASONING based on query complexity
2. **Self-Correction**: Evaluates response quality and automatically escalates if needed
3. **Quality Guarantees**: Never returns low-quality responses to users
4. **Real-time Feedback**: Visual reasoning trace panel shows the thinking process
5. **Performance Monitoring**: Built-in metrics collection and analysis

## Architecture

```
User Query
    ↓
CommandControlAgent
    ├─ Process commands (/cmd)
    ├─ Extract resources (@resource)
    └─ Delegate to AdaptiveReasoningLoop
        │
        ├─ Phase 0: Complexity Analysis
        │   └─ QueryComplexityAnalyzer
        │       → Recommends: DIRECT / LIGHT / DEEP
        │
        ├─ Phase 1: Execute with Strategy
        │   ├─ DIRECT: Fast single-pass execution
        │   ├─ LIGHT: 1-2 iterations with light planning
        │   └─ DEEP: Full planning with multiple iterations
        │
        ├─ Phase 2: Quality Evaluation
        │   └─ Evaluator.evaluate_response_quality()
        │       → Confidence score (0.0 - 1.0)
        │
        └─ Phase 3: Auto-Escalation (if needed)
            → DIRECT → LIGHT → DEEP
            → Repeat until quality sufficient
```

## Execution Strategies

### DIRECT Strategy
- **When**: Simple, factual queries
- **Latency**: Lowest (~0.5-1s)
- **Iterations**: 1
- **Quality Threshold**: 0.70 (configurable)
- **Example**: "What is the capital of France?"

### LIGHT_PLANNING Strategy
- **When**: Medium complexity, needs some analysis
- **Latency**: Moderate (~1-3s)
- **Iterations**: 1-2
- **Quality Threshold**: 0.75 (configurable)
- **Example**: "Compare the main features of Python and JavaScript"

### DEEP_REASONING Strategy
- **When**: Complex, multi-part queries
- **Latency**: Highest (~3-10s)
- **Iterations**: 2-5
- **Quality Threshold**: 0.60 (configurable)
- **Example**: "Design a scalable microservices architecture for an e-commerce platform"

## Self-Correction in Action

### Example 1: Auto-Escalation from DIRECT to LIGHT

```
User Query: "Explain quantum computing"

Step 1: Complexity Analysis
  → Classified as: SIMPLE
  → Initial Strategy: DIRECT

Step 2: Execute DIRECT
  → Response: "Quantum computing uses quantum mechanics..."
  → [Response buffered, not shown to user yet]

Step 3: Quality Evaluation
  → Quality Score: 0.45 (insufficient)
  → Reasoning: "Response is too brief, lacks key concepts"

Step 4: Auto-Escalation
  → Escalating: DIRECT → LIGHT_PLANNING
  → [Discarding buffered response]

Step 5: Execute LIGHT_PLANNING
  → Planning: Break into subtasks
  → Response: "Quantum computing is a revolutionary paradigm..."
  → [Comprehensive explanation with examples]

Step 6: Quality Re-Evaluation
  → Quality Score: 0.85 (sufficient!)
  → Now streaming to user...

Final: User sees only the high-quality response
  Attempts: 2
  Final Strategy: LIGHT_PLANNING
  Quality: 0.85
```

### Example 2: DIRECT Success (No Escalation)

```
User Query: "What is 2+2?"

Step 1: Complexity Analysis
  → Classified as: SIMPLE
  → Initial Strategy: DIRECT

Step 2: Execute DIRECT
  → Response: "2 + 2 equals 4."

Step 3: Quality Evaluation
  → Quality Score: 0.95 (excellent!)

Step 4: No Escalation Needed
  → Streaming response to user immediately

Final: Fast response, no wasted effort
  Attempts: 1
  Final Strategy: DIRECT
  Quality: 0.95
```

## Using the Reasoning Trace Panel

The Reasoning Trace Panel (`Ctrl+R` to toggle) shows real-time reasoning events:

### Event Types

1. **Complexity Analysis** (Blue)
   - Shows: Complexity level, recommended strategy, estimated iterations
   - Color-coded: SIMPLE (green), MEDIUM (yellow), COMPLEX (red)

2. **Strategy Selection** (Color-coded by strategy)
   - Shows: Which strategy is being executed
   - Colors: DIRECT (green), LIGHT (yellow), DEEP (red)

3. **Planning Events** (Yellow/Red for light/deep)
   - Shows: Number of subtasks, planning mode

4. **Quality Evaluation** (Green/Red for sufficient/insufficient)
   - Shows: Quality status, confidence score, reasoning

5. **Auto-Escalation** (Red, blinking)
   - **CRITICAL**: Highlights when quality is insufficient
   - Shows: from → to strategy, confidence score, reason

6. **Final Response** (Green)
   - Shows: Final strategy used, attempts, quality score, escalation flag

### Keyboard Shortcuts

- `Ctrl+R`: Toggle reasoning trace visibility
- `Ctrl+L`: Clear chat history
- `Ctrl+Q`: Quit application

## Configuration

### ReasoningConfig

```python
from nxs.application.reasoning.config import ReasoningConfig

# Default configuration (balanced)
config = ReasoningConfig(
    max_iterations=3,              # Max iterations for planning
    min_quality_direct=0.70,       # Quality threshold for DIRECT
    min_quality_light=0.75,        # Quality threshold for LIGHT
    min_quality_deep=0.60,         # Quality threshold for DEEP
    enable_caching=True,           # Enable prompt caching
)

# Strict configuration (higher quality)
strict_config = ReasoningConfig(
    max_iterations=5,
    min_quality_direct=0.80,
    min_quality_light=0.85,
    min_quality_deep=0.70,
)

# Permissive configuration (faster, lower quality bar)
permissive_config = ReasoningConfig(
    max_iterations=2,
    min_quality_direct=0.60,
    min_quality_light=0.65,
    min_quality_deep=0.50,
)
```

### Environment Variables

```bash
# Override default config via environment
export REASONING_MAX_ITERATIONS=5
export REASONING_MIN_QUALITY_DIRECT=0.80
export REASONING_MIN_QUALITY_LIGHT=0.85
export REASONING_MIN_QUALITY_DEEP=0.70
```

## Threshold Tuning Guide

### Step 1: Collect Metrics

Run the system with your typical workload. Metrics are automatically collected.

### Step 2: Analyze Performance

```python
from nxs.application.reasoning.metrics import get_metrics_collector
from nxs.application.reasoning.tuning import ThresholdTuner
from nxs.application.reasoning.config import ReasoningConfig

# Get metrics
collector = get_metrics_collector()
tuner = ThresholdTuner(collector)
config = ReasoningConfig()

# Generate tuning report
report = tuner.generate_tuning_report(config)
print(report)
```

### Step 3: Interpret Metrics

**Key Metrics:**

1. **Escalation Rate**
   - **Optimal**: 10-30%
   - **Too Low** (<10%): Thresholds too permissive, quality may suffer
   - **Too High** (>40%): Thresholds too strict, wasting resources

2. **Average Quality**
   - **Target**: 0.75-0.85
   - **Below 0.70**: Increase thresholds
   - **Above 0.90**: Consider lowering thresholds for speed

3. **Average Latency**
   - **Fast**: <1s
   - **Moderate**: 1-3s
   - **Slow**: >3s (consider lowering thresholds)

### Step 4: Apply Threshold Profiles

```python
from nxs.application.reasoning.tuning import ThresholdTuner

# List available profiles
print(ThresholdTuner.list_profiles())
# Output: ['strict', 'balanced', 'permissive', 'production']

# Get recommended profile
profile_name, profile = tuner.recommend_profile()
config = profile.to_config()

# Or use a specific profile
strict_profile = ThresholdTuner.get_profile('strict')
config = strict_profile.to_config()
```

### Step 5: Monitor and Iterate

After applying new thresholds:
1. Run for 50-100 queries
2. Re-analyze metrics
3. Fine-tune if needed

## Metrics Monitoring

### Collecting Metrics

Metrics are automatically collected during execution. Access them via:

```python
from nxs.application.reasoning.metrics import get_metrics_collector

collector = get_metrics_collector()

# Get summary
summary = collector.get_summary()
print(f"Total executions: {summary['aggregate']['total_executions']}")
print(f"Escalation rate: {summary['aggregate']['escalation_rate']:.1%}")
print(f"Average quality: {summary['aggregate']['quality_metrics']['avg']:.2f}")

# Strategy analysis
strategy_analysis = collector.get_strategy_analysis()
for strategy, stats in strategy_analysis.items():
    print(f"{strategy}: avg_quality={stats['avg_quality']:.2f}, "
          f"avg_latency={stats['avg_latency']:.2f}s")

# Escalation analysis
escalation_analysis = collector.get_escalation_analysis()
print(f"Total escalations: {escalation_analysis['total_escalations']}")
print(f"Escalation rate: {escalation_analysis['escalation_rate']:.1%}")
```

### Exporting Metrics

```python
import json

# Export summary to file
with open("reasoning_metrics.json", "w") as f:
    json.dump(collector.get_summary(), f, indent=2)

# Export strategy analysis
with open("strategy_analysis.json", "w") as f:
    json.dump(collector.get_strategy_analysis(), f, indent=2)
```

## Best Practices

### 1. Start with Balanced Profile

Use the default `balanced` profile initially, then tune based on your specific needs.

### 2. Monitor Escalation Rate

- **Too many escalations?** Lower thresholds
- **Too few escalations?** Raise thresholds (if quality is suffering)

### 3. Consider Latency Trade-offs

Higher thresholds = Better quality but slower responses. Find your sweet spot.

### 4. Use Reasoning Trace for Debugging

When responses aren't as expected, check the reasoning trace to see:
- Was complexity analysis accurate?
- Were escalations triggered appropriately?
- What was the final quality score?

### 5. Tune Prompts First, Thresholds Second

If quality is consistently low:
1. First, refine the reasoning prompts (complexity analysis, quality evaluation)
2. Then, adjust thresholds

### 6. Test with Representative Queries

Tune using queries representative of your actual workload, not edge cases.

## Troubleshooting

### Problem: Too many escalations

**Symptoms**: Escalation rate > 40%, high latency

**Solutions**:
1. Lower quality thresholds by 0.05-0.10
2. Switch to `permissive` profile
3. Reduce `max_iterations`

### Problem: Low quality responses

**Symptoms**: Average quality < 0.70, user complaints

**Solutions**:
1. Raise quality thresholds by 0.05-0.10
2. Switch to `strict` profile
3. Review and improve evaluation prompts

### Problem: High latency

**Symptoms**: Average latency > 3s

**Solutions**:
1. Use `permissive` profile
2. Reduce `max_iterations` to 2
3. Lower quality thresholds
4. Check if DEEP strategy is being overused

### Problem: Complexity analysis inaccurate

**Symptoms**: Simple queries classified as complex, or vice versa

**Solutions**:
1. Review complexity analysis prompt
2. Add more examples to the prompt
3. Adjust complexity classification logic

## API Reference

### AdaptiveReasoningLoop

```python
loop = AdaptiveReasoningLoop(
    llm=claude,
    conversation=conversation,
    tool_registry=tool_registry,
    analyzer=analyzer,
    planner=planner,
    evaluator=evaluator,
    synthesizer=synthesizer,
    config=config,
)

# Run with default settings
result = await loop.run("Your query here")

# Run with callbacks
callbacks = {
    "on_analysis_complete": lambda c: print(f"Complexity: {c.complexity_level}"),
    "on_auto_escalation": lambda f, t, r, c: print(f"Escalating: {f} -> {t}"),
}
result = await loop.run("Your query", callbacks=callbacks)

# Force specific strategy (for testing)
loop.force_strategy = ExecutionStrategy.DEEP_REASONING
result = await loop.run("Your query")
```

### ReasoningConfig

```python
config = ReasoningConfig(
    max_iterations=3,
    min_quality_direct=0.70,
    min_quality_light=0.75,
    min_quality_deep=0.60,
    enable_caching=True,
)
```

### MetricsCollector

```python
collector = get_metrics_collector()

# Start tracking an execution
query_id, start_time = collector.start_execution("Your query")

# Record completed execution
collector.record_execution(
    query_id=query_id,
    start_time=start_time,
    query="Your query",
    initial_strategy=ExecutionStrategy.DIRECT,
    final_strategy=ExecutionStrategy.LIGHT_PLANNING,
    complexity_level=ComplexityLevel.MEDIUM,
    escalated=True,
    escalation_count=1,
    final_quality_score=0.85,
    iterations=2,
)

# Get summary
summary = collector.get_summary()
```

### ThresholdTuner

```python
tuner = ThresholdTuner(collector)

# Analyze current thresholds
analysis = tuner.analyze_current_thresholds(config)

# Get recommendation
profile_name, profile = tuner.recommend_profile()

# Export/import profiles
tuner.export_profile(config, "my_profile", "Custom settings", Path("profile.json"))
profile = tuner.import_profile(Path("profile.json"))
```

## Examples

See the `examples/` directory for complete working examples:

- `examples/simple_query.py`: Basic query execution
- `examples/escalation_demo.py`: Demonstrating auto-escalation
- `examples/metrics_monitoring.py`: Collecting and analyzing metrics
- `examples/threshold_tuning.py`: Tuning thresholds for your workload

## Performance Benchmarks

Typical latencies on reference hardware (MacBook Pro M1):

| Strategy | Mean | P50 | P95 | P99 |
|----------|------|-----|-----|-----|
| DIRECT | 0.8s | 0.7s | 1.2s | 1.5s |
| LIGHT | 1.5s | 1.3s | 2.5s | 3.0s |
| DEEP | 3.5s | 3.0s | 5.5s | 7.0s |

*Note: Actual latencies depend on query complexity, model selection, and network conditions.*

## Future Enhancements

- [ ] Parallel tool execution for DEEP reasoning
- [ ] Learning-based threshold adaptation
- [ ] Multi-turn research with context retention
- [ ] Integration with external knowledge bases
- [ ] Custom strategy plugins

## Support

For issues, questions, or feature requests:
- GitHub Issues: [your-repo/issues]
- Documentation: [your-docs-url]
- Discord: [your-discord-channel]

