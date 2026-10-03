"""Main research harness for evaluating AutoDBA recommendations."""

import time
from typing import List, Optional

from .evaluation_framework import Evaluator, RecommendationOutcome, Outcome
from .metrics import BenchmarkResult


class ResearchHarness:
    """Harnesses the AutoDBA research infrastructure for evaluation."""

    def __init__(self):
        self.evaluator = Evaluator()
        self.metrics = {}

    def run_evaluation(self, query: str, incident_type: str) -> RecommendationOutcome:
        """Run a full evaluation cycle for a given query."""
        print(f"Evaluating query: {query}")
        print(f"Incident type: {incident_type}")
        outcome = self.evaluator.evaluate_query(query, incident_type)
        print(f"Outcome: {outcome.outcome.value}")
        print(f"Runtime improvement: {outcome.runtime_improvement_pct}%")
        print(f"Planner cost improvement: {outcome.planner_cost_improvement_pct}%")
        return outcome

    def run_comparison(self, query: str, incident_type: str) -> dict:
        """Run side-by-side comparison of AutoDBA recommendation vs manual intervention."""
        # Run AutoDBA recommendation
        auto_dba_outcome = self.run_evaluation(query, incident_type)

        # Simulate manual intervention (what a human might do)
        manual_outcome = self._simulate_manual_remediation(query, incident_type)

        return {
            "query": query,
            "incident_type": incident_type,
            "auto_dba_outcome": auto_dba_outcome,
            "manual_outcome": manual_outcome,
            "improvement_gap": self._calculate_improvement_gap(auto_dba_outcome, manual_outcome)
        }

    def _simulate_manual_remediation(self, query: str, incident_type: str) -> RecommendationOutcome:
        """Simulate what a human expert might do."""
        # Simple heuristic: if it's a missing index, recommend creating one
        if incident_type == "missing_index":
            return RecommendationOutcome(
                recommendation="CREATE INDEX ON orders(customer_id)",
                runtime_improvement_pct=45.0,
                planner_cost_improvement_pct=30.0,
                index_created=True,
                actual_runtime_improvement_pct=45.0,
                notes="Manual expert would create index based on query analysis"
            )
        elif incident_type == "expensive_sort":
            return RecommendationOutcome(
                recommendation="CREATE INDEX ON orders(order_date)",
                runtime_improvement_pct=35.0,
                planner_cost_improvement_pct=25.0,
                index_created=True,
                actual_runtime_improvement_pct=35.0,
                notes="Manual expert would create index based on query analysis"
            )
        else:
            return RecommendationOutcome(
                recommendation="CREATE INDEX ON orders(customer_id)",
                runtime_improvement_pct=40.0,
                planner_cost_improvement_pct=20.0,
                index_created=True,
                actual_runtime_improvement_pct=40.0,
                notes="Manual expert would create index based on query analysis"
            )

    def _calculate_improvement_gap(self, auto_dba: RecommendationOutcome, manual: RecommendationOutcome) -> float:
        """Calculate the gap between AutoDBA and manual outcomes."""
        if auto_dba.runtime_improvement_pct is None:
            return 0.0
        return abs(auto_dba.runtime_improvement_pct - manual.runtime_improvement_pct)

    def generate_report(self, eval_result: RecommendationOutcome) -> str:
        """Generate a human-readable evaluation report."""
        lines = []
        lines.append("=" * 60)
        lines.append("AutoDBA Recommendation Evaluation Report")
        lines.append("=" * 60)
        lines.append(f"Query: {eval_result.query}")
        lines.append(f"Incident Type: {eval_result.incident_type}")
        lines.append("-" * 60)
        lines.append(f"Recommendation: {eval_result.recommendation}")
        lines.append(f"Runtime Improvement: {eval_result.runtime_improvement_pct}%")
        lines.append(f"Planner Cost Improvement: {eval_result.planner_cost_improvement_pct}%")
        lines.append(f"Index Created: {eval_result.index_created}")
        lines.append(f"Actual Runtime Improvement: {eval_result.actual_runtime_improvement_pct}%")
        lines.append("-" * 60)
        if eval_result.outcome == Outcome.SUCCESS:
            lines.append("Status: SUCCESS")
        elif eval_result.outcome == Outcome.FAILURE:
            lines.append("Status: FAILURE")
        else:
            lines.append("Status: NOT_BENCHMARKED")
        lines.append("=" * 60)
        return "\n".join(lines)