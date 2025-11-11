"""Threshold tuning utilities for adaptive reasoning.

Provides tools to:
- Analyze current threshold performance
- Recommend threshold adjustments
- Test different threshold configurations
- Export/import threshold profiles
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.metrics import MetricsCollector, AggregateMetrics
from nxs.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ThresholdProfile:
    """A named threshold configuration profile."""
    
    name: str
    description: str
    min_quality_direct: float
    min_quality_light: float
    min_quality_deep: float
    max_iterations: int
    
    @classmethod
    def from_config(cls, config: ReasoningConfig, name: str, description: str) -> "ThresholdProfile":
        """Create profile from ReasoningConfig."""
        return cls(
            name=name,
            description=description,
            min_quality_direct=config.min_quality_direct,
            min_quality_light=config.min_quality_light,
            min_quality_deep=config.min_quality_deep,
            max_iterations=config.max_iterations,
        )
    
    def to_config(self) -> ReasoningConfig:
        """Convert profile to ReasoningConfig."""
        return ReasoningConfig(
            min_quality_direct=self.min_quality_direct,
            min_quality_light=self.min_quality_light,
            min_quality_deep=self.min_quality_deep,
            max_iterations=self.max_iterations,
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ThresholdProfile":
        """Create from dictionary."""
        return cls(**data)


class ThresholdTuner:
    """Analyzes metrics and recommends threshold adjustments."""
    
    # Predefined profiles
    PROFILES = {
        "strict": ThresholdProfile(
            name="strict",
            description="High quality standards, more escalations",
            min_quality_direct=0.80,
            min_quality_light=0.85,
            min_quality_deep=0.70,
            max_iterations=5,
        ),
        "balanced": ThresholdProfile(
            name="balanced",
            description="Balanced quality and performance",
            min_quality_direct=0.70,
            min_quality_light=0.75,
            min_quality_deep=0.60,
            max_iterations=3,
        ),
        "permissive": ThresholdProfile(
            name="permissive",
            description="Lower thresholds, faster responses",
            min_quality_direct=0.60,
            min_quality_light=0.65,
            min_quality_deep=0.50,
            max_iterations=2,
        ),
        "production": ThresholdProfile(
            name="production",
            description="Production-optimized settings",
            min_quality_direct=0.75,
            min_quality_light=0.80,
            min_quality_deep=0.65,
            max_iterations=3,
        ),
    }
    
    def __init__(self, metrics: MetricsCollector):
        """Initialize tuner with metrics collector."""
        self.metrics = metrics
    
    def analyze_current_thresholds(self, config: ReasoningConfig) -> Dict:
        """Analyze how current thresholds are performing.
        
        Returns:
            Analysis dict with performance indicators
        """
        aggregate = self.metrics.aggregate
        
        if aggregate.total_executions == 0:
            return {
                "error": "No executions recorded yet",
                "recommendation": "Run some queries first to collect metrics",
            }
        
        analysis = {
            "current_config": {
                "min_quality_direct": config.min_quality_direct,
                "min_quality_light": config.min_quality_light,
                "min_quality_deep": config.min_quality_deep,
                "max_iterations": config.max_iterations,
            },
            "performance": {
                "total_executions": aggregate.total_executions,
                "escalation_rate": aggregate.escalation_rate,
                "avg_quality": aggregate.avg_quality,
                "avg_latency": aggregate.avg_latency,
            },
            "assessment": self._assess_thresholds(aggregate, config),
            "recommendations": self._generate_recommendations(aggregate, config),
        }
        
        return analysis
    
    def _assess_thresholds(self, aggregate: AggregateMetrics, config: ReasoningConfig) -> Dict:
        """Assess if thresholds are appropriate."""
        assessment = {
            "escalation_frequency": "unknown",
            "quality_level": "unknown",
            "latency_impact": "unknown",
        }
        
        # Assess escalation frequency
        if aggregate.escalation_rate < 0.1:
            assessment["escalation_frequency"] = "low (thresholds may be too permissive)"
        elif aggregate.escalation_rate < 0.3:
            assessment["escalation_frequency"] = "optimal"
        elif aggregate.escalation_rate < 0.5:
            assessment["escalation_frequency"] = "moderate (consider adjusting thresholds)"
        else:
            assessment["escalation_frequency"] = "high (thresholds may be too strict)"
        
        # Assess quality level
        if aggregate.avg_quality < 0.6:
            assessment["quality_level"] = "low (increase thresholds)"
        elif aggregate.avg_quality < 0.75:
            assessment["quality_level"] = "moderate"
        elif aggregate.avg_quality < 0.85:
            assessment["quality_level"] = "good"
        else:
            assessment["quality_level"] = "excellent"
        
        # Assess latency impact
        if aggregate.avg_latency < 0.5:
            assessment["latency_impact"] = "low (fast responses)"
        elif aggregate.avg_latency < 2.0:
            assessment["latency_impact"] = "moderate"
        else:
            assessment["latency_impact"] = "high (consider lowering thresholds for speed)"
        
        return assessment
    
    def _generate_recommendations(self, aggregate: AggregateMetrics, config: ReasoningConfig) -> List[str]:
        """Generate threshold adjustment recommendations."""
        recommendations = []
        
        # High escalation rate
        if aggregate.escalation_rate > 0.4:
            recommendations.append(
                f"High escalation rate ({aggregate.escalation_rate:.1%}): "
                "Consider lowering quality thresholds by 0.05-0.10"
            )
        
        # Low escalation rate with low quality
        if aggregate.escalation_rate < 0.1 and aggregate.avg_quality < 0.75:
            recommendations.append(
                f"Low escalation rate ({aggregate.escalation_rate:.1%}) but quality below target: "
                "Consider increasing quality thresholds by 0.05-0.10"
            )
        
        # High latency
        if aggregate.avg_latency > 2.0:
            recommendations.append(
                f"High average latency ({aggregate.avg_latency:.2f}s): "
                "Consider using 'permissive' profile or reducing max_iterations"
            )
        
        # Low quality scores
        if aggregate.avg_quality < 0.7:
            recommendations.append(
                f"Quality scores below 0.7 (avg: {aggregate.avg_quality:.2f}): "
                "Increase thresholds or improve prompts"
            )
        
        # Everything looks good
        if not recommendations:
            recommendations.append(
                "Current thresholds appear well-tuned! "
                f"Escalation rate: {aggregate.escalation_rate:.1%}, "
                f"Avg quality: {aggregate.avg_quality:.2f}"
            )
        
        return recommendations
    
    def recommend_profile(self) -> Tuple[str, ThresholdProfile]:
        """Recommend a predefined profile based on current metrics.
        
        Returns:
            Tuple of (profile_name, profile)
        """
        aggregate = self.metrics.aggregate
        
        if aggregate.total_executions == 0:
            # Default to balanced
            return ("balanced", self.PROFILES["balanced"])
        
        # High quality focus
        if aggregate.avg_quality < 0.75:
            return ("strict", self.PROFILES["strict"])
        
        # Speed focus
        if aggregate.avg_latency > 2.0:
            return ("permissive", self.PROFILES["permissive"])
        
        # Balanced (default)
        return ("balanced", self.PROFILES["balanced"])
    
    def export_profile(self, config: ReasoningConfig, name: str, description: str, filepath: Path):
        """Export current config as a named profile."""
        profile = ThresholdProfile.from_config(config, name, description)
        
        with open(filepath, "w") as f:
            json.dump(profile.to_dict(), f, indent=2)
        
        logger.info(f"Exported profile '{name}' to {filepath}")
    
    def import_profile(self, filepath: Path) -> ThresholdProfile:
        """Import a profile from file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        
        profile = ThresholdProfile.from_dict(data)
        logger.info(f"Imported profile '{profile.name}' from {filepath}")
        
        return profile
    
    @classmethod
    def get_profile(cls, name: str) -> Optional[ThresholdProfile]:
        """Get a predefined profile by name."""
        return cls.PROFILES.get(name)
    
    @classmethod
    def list_profiles(cls) -> List[str]:
        """List available predefined profiles."""
        return list(cls.PROFILES.keys())
    
    def compare_profiles(self, profile_a: str, profile_b: str) -> Dict:
        """Compare two predefined profiles."""
        prof_a = self.PROFILES.get(profile_a)
        prof_b = self.PROFILES.get(profile_b)
        
        if not prof_a or not prof_b:
            return {"error": "One or both profiles not found"}
        
        return {
            "profile_a": prof_a.to_dict(),
            "profile_b": prof_b.to_dict(),
            "differences": {
                "min_quality_direct": prof_b.min_quality_direct - prof_a.min_quality_direct,
                "min_quality_light": prof_b.min_quality_light - prof_a.min_quality_light,
                "min_quality_deep": prof_b.min_quality_deep - prof_a.min_quality_deep,
                "max_iterations": prof_b.max_iterations - prof_a.max_iterations,
            },
        }
    
    def generate_tuning_report(self, config: ReasoningConfig) -> str:
        """Generate a human-readable tuning report."""
        analysis = self.analyze_current_thresholds(config)
        
        if "error" in analysis:
            return f"Error: {analysis['error']}\n{analysis.get('recommendation', '')}"
        
        report = []
        report.append("=" * 70)
        report.append("THRESHOLD TUNING REPORT")
        report.append("=" * 70)
        report.append("")
        
        # Current config
        report.append("Current Configuration:")
        for key, value in analysis["current_config"].items():
            report.append(f"  {key}: {value}")
        report.append("")
        
        # Performance
        report.append("Performance Metrics:")
        for key, value in analysis["performance"].items():
            if isinstance(value, float):
                report.append(f"  {key}: {value:.2f}")
            else:
                report.append(f"  {key}: {value}")
        report.append("")
        
        # Assessment
        report.append("Assessment:")
        for key, value in analysis["assessment"].items():
            report.append(f"  {key}: {value}")
        report.append("")
        
        # Recommendations
        report.append("Recommendations:")
        for i, rec in enumerate(analysis["recommendations"], 1):
            report.append(f"  {i}. {rec}")
        report.append("")
        
        # Suggested profile
        profile_name, profile = self.recommend_profile()
        report.append(f"Recommended Profile: {profile_name}")
        report.append(f"  Description: {profile.description}")
        report.append("")
        
        report.append("=" * 70)
        
        return "\n".join(report)


def create_tuning_cli():
    """Create a CLI tool for threshold tuning."""
    import typer
    from nxs.application.reasoning.metrics import get_metrics_collector
    
    app = typer.Typer(name="tune", help="Threshold tuning utilities")
    
    @app.command()
    def analyze():
        """Analyze current threshold performance."""
        collector = get_metrics_collector()
        tuner = ThresholdTuner(collector)
        config = ReasoningConfig()
        
        report = tuner.generate_tuning_report(config)
        typer.echo(report)
    
    @app.command()
    def list_profiles():
        """List available threshold profiles."""
        typer.echo("Available Profiles:")
        typer.echo("")
        for name in ThresholdTuner.list_profiles():
            profile = ThresholdTuner.get_profile(name)
            typer.echo(f"  {name}:")
            typer.echo(f"    {profile.description}")
            typer.echo(f"    Quality thresholds: {profile.min_quality_direct:.2f} / "
                      f"{profile.min_quality_light:.2f} / {profile.min_quality_deep:.2f}")
            typer.echo("")
    
    @app.command()
    def recommend():
        """Recommend a profile based on current metrics."""
        collector = get_metrics_collector()
        tuner = ThresholdTuner(collector)
        
        profile_name, profile = tuner.recommend_profile()
        typer.echo(f"Recommended Profile: {profile_name}")
        typer.echo(f"Description: {profile.description}")
        typer.echo("")
        typer.echo("Configuration:")
        typer.echo(f"  min_quality_direct: {profile.min_quality_direct}")
        typer.echo(f"  min_quality_light: {profile.min_quality_light}")
        typer.echo(f"  min_quality_deep: {profile.min_quality_deep}")
        typer.echo(f"  max_iterations: {profile.max_iterations}")
    
    return app


if __name__ == "__main__":
    cli = create_tuning_cli()
    cli()

