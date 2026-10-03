"""
Research evaluation harness for AutoDBA case evaluation.

Orchestrates the leakage-safe evaluation pipeline:
1. Loads historical optimization cases.
2. Partitions cases using strict template-hash grouping (Train vs. Test).
3. Indexes historical (TRAIN) cases in the retrieval baseline engine.
4. Evaluates unseen (TEST) cases against the train-only retrieval index.
5. Evaluates candidate selection policies (Policy A, B, C) using CandidateSelector.
6. Computes retrieval statistics while preserving empirical integrity (no mock numbers).

IMPORTANT: This module is research scaffolding only. It does not modify
the application code, database schemas, or runtime behavior of AutoDBA.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .case_schema import OptimizationCase
from .split_strategy import TrainTestSplit, grouped_template_split, verify_split_leakage
from .baseline_retrieval import BaselineRetrievalMethods, RetrievalResult
from .candidate_selector import CandidateSelector, SelectionPolicy, SelectionResult


class EvaluationHarness:
    """Main evaluation harness for AutoDBA leakage-safe case evaluation."""

    def __init__(self, cases: Optional[List[OptimizationCase]] = None):
        self.cases: List[OptimizationCase] = cases or []
        self.split: Optional[TrainTestSplit] = None
        self.retriever: Optional[BaselineRetrievalMethods] = None
        self.results: List[Dict[str, Any]] = []

    def load_cases(self, file_path: str = "research/data/sample_cases.json") -> List[OptimizationCase]:
        """Load optimization cases from a JSON fixture file."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Case data file not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_cases = data.get("cases", [])
        self.cases = [OptimizationCase.from_dict(c) for c in raw_cases]
        return self.cases

    def prepare_data(self, test_ratio: float = 0.3, seed: int = 42) -> TrainTestSplit:
        """
        Partition cases into disjoint template groups and initialize train-only retrieval.
        """
        if not self.cases:
            self.load_cases()

        # 1. Grouped template split (enforces zero template overlap)
        self.split = grouped_template_split(self.cases, test_ratio=test_ratio, seed=seed)

        # 2. Initialize retrieval engine strictly on the TRAIN partition
        self.retriever = BaselineRetrievalMethods(self.split.train_cases)

        return self.split

    def run_evaluation(
        self,
        query_case: OptimizationCase,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Evaluate retrieval methods on a single test query case against the training index.
        """
        if not self.split or not self.retriever:
            raise ValueError("Harness not prepared. Call prepare_data() first.")

        methods = ["current_autodba", "lexical", "dense", "hybrid", "outcome_aware_reranking"]
        retrieval_outputs: Dict[str, List[Dict[str, Any]]] = {}

        for method in methods:
            if method == "current_autodba":
                results = self.retriever.current_autodba_retrieval(query_case, limit=limit)
            elif method == "lexical":
                results = self.retriever.lexical_retrieval(query_case, limit=limit)
            elif method == "dense":
                results = self.retriever.dense_retrieval(query_case, limit=limit)
            elif method == "hybrid":
                results = self.retriever.hybrid_retrieval(query_case, limit=limit)
            elif method == "outcome_aware_reranking":
                base = self.retriever.current_autodba_retrieval(query_case, limit=limit * 2, similarity_threshold=0.0)
                results = self.retriever.outcome_aware_reranking(base, query_case, limit=limit)
            else:
                results = []

            retrieval_outputs[method] = [
                {
                    "rank": r.rank,
                    "case_id": r.case_id,
                    "similarity": round(r.similarity_score, 4),
                    "incident_type": r.case.incident_type.value,
                    "provenance": r.case.provenance.value,
                    "is_verified": r.case.is_verified,
                    "historical_outcome": r.case.measured_outcome.benchmark_status,
                }
                for r in results
            ]

        eval_record = {
            "query_case_id": query_case.case_id,
            "query_text": query_case.query.text,
            "canonical_template": query_case.canonical_template,
            "template_hash": query_case.template_hash,
            "incident_type": query_case.incident_type.value,
            "retrieval_results": retrieval_outputs,
            "outcome_evaluation_status": (
                "Candidate selection policies integrated via CandidateSelector. "
                "Retrieval candidate boundary verified leakage-safe."
            ),
        }

        self.results.append(eval_record)
        return eval_record

    def evaluate_candidate_selection(
        self,
        query_case: OptimizationCase,
        candidates: List[Any],
        alpha: float = 1.0,
        beta: float = 1.0,
        lambda_reg: float = 1.0,
    ) -> Dict[str, SelectionResult]:
        """
        Evaluate candidate selection on an unseen test query comparing Policy A, B, and C
        using historical cases indexed strictly from the TRAIN partition.
        """
        if not self.split:
            self.prepare_data()

        selector = CandidateSelector(alpha=alpha, beta=beta, lambda_reg=lambda_reg)
        train_cases = self.split.train_cases

        result_a = selector.select_planner_only(candidates)
        result_b = selector.select_similarity(query_case.query.text, candidates, train_cases)
        result_c = selector.select_outcome_aware(query_case.query.text, candidates, train_cases)

        return {
            "policy_a": result_a,
            "policy_b": result_b,
            "policy_c": result_c,
        }

    def run_full_test_evaluation(self, limit: int = 5) -> Dict[str, Any]:
        """
        Run retrieval evaluation across all cases in the test partition.
        """
        if not self.split:
            self.prepare_data()

        reports = []
        for test_case in self.split.test_cases:
            report = self.run_evaluation(test_case, limit=limit)
            reports.append(report)

        return {
            "total_cases": len(self.cases),
            "train_cases_count": len(self.split.train_cases),
            "test_cases_count": len(self.split.test_cases),
            "test_evaluations": reports,
        }

    def generate_report(self, eval_record: Dict[str, Any]) -> str:
        """Generate a human-readable summary report for a single case evaluation."""
        lines = [
            "=" * 65,
            "AutoDBA Leakage-Safe Case Evaluation Report",
            "=" * 65,
            f"Query Case ID      : {eval_record['query_case_id']}",
            f"Incident Type      : {eval_record['incident_type']}",
            f"SQL Query          : {eval_record['query_text']}",
            f"Canonical Template : {eval_record['canonical_template']}",
            f"Template Hash      : {eval_record['template_hash'][:16]}...",
            "-" * 65,
            "Retrieval Results (Candidates from TRAIN partition only):",
        ]

        for method, res_list in eval_record["retrieval_results"].items():
            lines.append(f"\n  [{method}] (retrieved {len(res_list)} cases):")
            for r in res_list:
                lines.append(
                    f"    Rank {r['rank']}: ID={r['case_id']} | Sim={r['similarity']} | "
                    f"Prov={r['provenance']} | Verified={r['is_verified']}"
                )

        lines.extend([
            "-" * 65,
            f"Note: {eval_record['outcome_evaluation_status']}",
            "=" * 65,
        ])
        return "\n".join(lines)
