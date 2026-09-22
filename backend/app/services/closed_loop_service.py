"""
Phase 4.2 Closed-Loop Self-Improvement Orchestration.

Connects the existing authoritative AutoDBA stages:

    Approved Recommendation
        -> Physical Remediation
        -> Runtime Benchmark
        -> Outcome Determination
        -> Persistent Optimization Memory

This service orchestrates existing services only. It does not:
- approve recommendations,
- construct arbitrary SQL,
- bypass safety checks,
- execute LLM-generated SQL,
- duplicate benchmark logic.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.engine import Engine

from app.core.config import Settings, get_settings
from app.db.database import engine as default_engine
from app.schemas.optimization import (
    ApprovalRequest,
    BenchmarkResult,
    OptimizationMemory,
    OptimizationOutcome,
    OptimizationRecommendation,
    RemediationResult,
)
from app.services.approval_service import default_approval_service
from app.services.benchmark_service import BenchmarkService
from app.services.memory_service import MemoryService
from app.services.remediation_service import RemediationService


class ClosedLoopError(Exception):
    """Base exception for closed-loop orchestration errors."""


class ClosedLoopApprovalError(ClosedLoopError):
    """Raised when an approval cannot be used for remediation."""


class ClosedLoopBenchmarkError(ClosedLoopError):
    """Raised when benchmarking cannot be completed."""


class ClosedLoopService:
    """Orchestrates the complete post-approval optimization feedback loop."""

    def __init__(
        self,
        db,
        *,
        settings: Optional[Settings] = None,
        db_engine: Optional[Engine] = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.db_engine = db_engine or default_engine
        self.memory_service = MemoryService(db)

    def execute(
        self,
        *,
        approval_id: str,
        query_text: str,
        incident_type: str,
        diagnosis: Dict[str, Any],
        recommendation: Optional[OptimizationRecommendation] = None,
    ) -> Dict[str, Any]:
        """
        Execute the closed loop using an already-approved request.

        Human approval is never created or granted here.
        """

        # ------------------------------------------------------------
        # 1. Retrieve the existing approval from the shared store.
        # ------------------------------------------------------------
        approval = default_approval_service.get_approval_request(approval_id)

        if approval is None:
            raise ClosedLoopApprovalError(
                f"Approval request '{approval_id}' was not found."
            )

        # The remediation service performs the authoritative approval,
        # expiration, snapshot, and safety checks again.
        current_recommendation = recommendation

        # ------------------------------------------------------------
        # 2. Apply the approved physical remediation.
        # ------------------------------------------------------------
        remediation = RemediationService.apply_approved_recommendation(
            approval_request=approval,
            current_recommendation=current_recommendation,
            settings=self.settings,
            db_engine=self.db_engine,
        )

        # ------------------------------------------------------------
        # 3. Benchmark the exact query against the real database.
        # ------------------------------------------------------------
        try:
            benchmark = BenchmarkService.benchmark(
                query=query_text,
                remediation=remediation,
                settings=self.settings,
                db_engine=self.db_engine,
            )
        except Exception as exc:
            raise ClosedLoopBenchmarkError(
                f"Closed-loop benchmarking failed after remediation "
                f"'{remediation.remediation_id}': {exc}"
            ) from exc

        # ------------------------------------------------------------
        # 4. Convert authoritative benchmark evidence to a memory
        #    record. MemoryService derives the outcome itself.
        # ------------------------------------------------------------
        benchmark_dict = benchmark.model_dump(mode="json")
        validation = {
            "hypopg_validated": approval.recommendation.hypopg_validated,
            "approval_id": approval.approval_id,
            "approval_status": approval.status.value,
            "approved_by": approval.approved_by,
        }

        recommendation_dict = approval.recommendation.model_dump(mode="json")

        memory = self.memory_service.create_memory(
            incident_type=incident_type,
            query_text=query_text,
            diagnosis=diagnosis,
            recommendation=recommendation_dict,
            validation=validation,
            benchmark=benchmark_dict,
            outcome=None,
            outcome_summary=self._build_outcome_summary(benchmark),
        )

        return {
            "approval": approval,
            "remediation": remediation,
            "benchmark": benchmark,
            "outcome": memory.outcome,
            "memory": memory,
        }

    @staticmethod
    def _build_outcome_summary(benchmark: BenchmarkResult) -> str:
        """Create a factual summary from benchmark evidence."""

        runtime = benchmark.runtime_improvement_percent
        planner = benchmark.planner_cost_improvement_percent

        if benchmark.status.value != "completed":
            return f"Benchmark status: {benchmark.status.value}."

        if runtime is None:
            return (
                "Benchmark completed, but runtime improvement could not "
                "be calculated."
            )

        if runtime > 0:
            result = f"Measured runtime improved by {runtime:.2f}%."
        elif runtime < 0:
            result = f"Measured runtime regressed by {abs(runtime):.2f}%."
        else:
            result = "Measured runtime showed no improvement."

        if planner is not None:
            result += f" Planner cost change: {planner:.2f}%."

        return result


def get_closed_loop_service(db) -> ClosedLoopService:
    """Construct the closed-loop service for a database session."""
    return ClosedLoopService(db)
