"""Metrics for evaluating AutoDBA recommendation system."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Outcome(Enum):
    """Possible outcomes of a recommendation."""
    SUCCESS = "success"
    FAILURE = "failure"
    NOT_BENCHMARKED = "not_benchmarked"


@dataclass
class BenchmarkResult:
    """Results from a runtime benchmark."""
    before_runtime_ms: float
    after_runtime_ms: float
    runtime_improvement_pct: float  # positive = improvement
    planner_cost_improvement_pct: float
    plan_changed: bool
    index_used_before: bool
    index_used_after: bool


@dataclass
class RecommendationOutcome:
    """Outcome of a recommendation after execution."""
    recommendation: str
    runtime_improvement_pct: float
    planner_cost_improvement_pct: float
    index_created: bool
    actual_runtime_improvement_pct: Optional[float] = None
    notes: str = ""
    timestamp: str = ""


@dataclass
class EvaluationReport:
    """Comprehensive evaluation report for a single query."""
    query: str
    incident_type: str
    recommendation: str
    benchmark_result: Optional[BenchmarkResult] = None
    outcome: Outcome = Outcome.NOT_BENCHMARKED
    runtime_improvement_pct: Optional[float] = None
    planner_cost_improvement_pct: Optional[float] = None
    index_created: bool = False
    actual_runtime_improvement_pct: Optional[float] = None
    notes: str = ""
    timestamp: str = ""