"""
Ablation study designs for the AutoDBA research evaluation harness.

This module defines ablation experiments that isolate the value of different
components of the retrieval and recommendation pipeline:

1. Plan features - Does analyzing the execution plan structure add value?
2. Workload context - Does operational workload context improve recommendations?
3. Outcomes - Do historical success/failure outcomes improve retrieval quality?
4. Reranking - Does outcome-aware reranking improve result quality?

IMPORTANT: This module is research scaffolding only. It does not modify
the application code, database schemas, or runtime behavior of AutoDBA.
All ablation logic operates on the research case schema and does not
claim performance improvements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import json


@dataclass
class AblationConfig:
    """Configuration for an ablation study."""
    name: str
    description: str
    include_plan_features: bool = True
    include_workload_context: bool = True
    include_outcomes: bool = True
    include_reranking: bool = True
    ablate: str = "full"


@dataclass
class AblationResult:
    """Result of running a single ablation experiment."""
    config: AblationConfig
    retrieval_method: str
    retrieval_quality: Dict[str, float] = field(default_factory=dict)
    recommendation_quality: Dict[str, float] = field(default_factory=dict)
    metric_changes: Dict[str, float] = field(default_factory=dict)
    notes: str = ""


def create_default_ablation_configs() -> List[AblationConfig]:
    """Create default ablation configurations for evaluation."""
    configs = [
        AblationConfig(
            name="full_pipeline",
            description="All components included (baseline)",
            include_plan_features=True,
            include_workload_context=True,
            include_outcomes=True,
            include_reranking=True,
        ),
        AblationConfig(
            name="ablate_plan_features",
            description="Plan features ablated",
            include_plan_features=False,
            include_workload_context=True,
            include_outcomes=True,
            include_reranking=True,
        ),
        AblationConfig(
            name="ablate_workload_context",
            description="Workload context ablated",
            include_plan_features=True,
            include_workload_context=False,
            include_outcomes=True,
            include_reranking=True,
        ),
        AblationConfig(
            name="ablate_outcomes",
            description="Outcomes ablated",
            include_plan_features=True,
            include_workload_context=True,
            include_outcomes=False,
            include_reranking=True,
        ),
        AblationConfig(
            name="ablate_reranking",
            description="Reranking ablated",
            include_plan_features=True,
            include_workload_context=True,
            include_outcomes=True,
            include_reranking=False,
        ),
    ]
    return configs


def run_ablation(
    config: AblationConfig,
    cases: List[Dict[str, Any]],
    retrieval_methods: Dict[str, Any],
) -> AblationResult:
    """Run an ablation experiment with the given configuration."""
    result = AblationResult(
        config=config,
        retrieval_method=config.ablate,
    )

    if not config.include_plan_features:
        result.notes += "Plan features ablated. "
    if not config.include_workload_context:
        result.notes += "Workload context ablated. "
    if not config.include_outcomes:
        result.notes += "Outcome data ablated. "
    if not config.include_reranking:
        result.notes += "Reranking ablated. "

    return result


def ablation_summary(results: List[AblationResult]) -> Dict[str, Any]:
    """Produce a summary of all ablation results."""
    summary = {
        "configs_run": len(results),
        "component_impacts": {},
        "best_configuration": None,
    }

    for config in create_default_ablation_configs():
        for result in results:
            if result.config.name == config.name:
                summary["component_impacts"][config.name] = result.notes

    return summary


class AblationStudy:
    """Class to manage and run ablation studies."""

    def __init__(self, cases: List[Dict[str, Any]]):
        self.cases = cases
        self.results: List[AblationResult] = []
        self.configs = create_default_ablation_configs()

    def run_all(self) -> List[AblationResult]:
        """Run all default ablation configurations."""
        for config in self.configs:
            result = run_ablation(config, self.cases, {})
            self.results.append(result)
        return self.results

    def summarize(self) -> Dict[str, Any]:
        """Summarize all ablation study results."""
        return ablation_summary(self.results)