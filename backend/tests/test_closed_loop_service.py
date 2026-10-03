"""Closed-loop orchestration regression tests (live PostgreSQL).

Exercises the full same-process loop:

    diagnosis -> candidate validation -> safety -> approval creation
    -> explicit approval -> controlled remediation -> real benchmark
    -> optimization memory creation

Regression coverage
-------------------
Physical remediation executes DDL on independent engine connections while the
caller's SQLAlchemy session still holds the read-only transaction opened by
diagnosis.  That transaction is left deassociated from its connection by
session-scoped HypoPG validation, which previously made
``MemoryService.create_memory()``'s ``commit()`` raise
``InvalidRequestError: This transaction is inactive`` and no optimization
memory was ever persisted for a successful remediation.
"""

import pytest
from sqlalchemy import text

from app.db.database import SessionLocal, engine
from app.schemas.optimization import (
    CaseProvenance,
    DiagnoseRequest,
    OutcomeVerificationState,
    OptimizationOutcome,
)
from app.services.approval_service import default_approval_service
from app.services.closed_loop_service import ClosedLoopService
from app.services.intelligence_service import IntelligenceService
from app.services.memory_service import MemoryService

QUERY = "SELECT * FROM orders WHERE total_amount >= 450.00"
INDEX_NAME = "idx_autodba_orders_total_amount"
@pytest.fixture
def missing_index_state():
    """Guarantee the missing-index incident and leave no residual AutoDBA index.

    The suite-wide baseline is "no idx_autodba_* indexes present", so the
    remediation index created by the closed loop is always removed again.
    """
    with engine.begin() as conn:
        conn.execute(text(f"DROP INDEX IF EXISTS {INDEX_NAME}"))
    yield
    with engine.begin() as conn:
        conn.execute(text(f"DROP INDEX IF EXISTS {INDEX_NAME}"))


@pytest.fixture(autouse=True)
def isolated_approval_store():
    """Keep the in-memory approval store test-scoped."""
    default_approval_service.clear()
    yield
    default_approval_service.clear()


@pytest.mark.integration
def test_closed_loop_creates_verified_measured_memory(missing_index_state):
    """A successful closed loop must persist real measured + verified memory."""
    with SessionLocal() as db:
        diagnosis = IntelligenceService(db).diagnose(
            request=DiagnoseRequest(query=QUERY, include_rag=False)
        ).diagnosis

        assert diagnosis.incident_type == "missing_index"
        assert diagnosis.candidate_evaluations, "No deterministic candidate evaluations produced"

        candidate = diagnosis.candidate_evaluations[0]
        assert candidate.validation is not None
        assert candidate.validation.verdict.value == "validated"
        assert candidate.recommendation.hypopg_validated is True
        assert candidate.safety_assessment.eligible_for_approval is True
        assert candidate.recommendation.relation == "orders"
        assert candidate.recommendation.columns == ["total_amount"]

        # Human approval is never implicit: PENDING, then an explicit approval.
        approval = default_approval_service.create_approval_request(
            recommendation=candidate.recommendation,
            safety_assessment=candidate.safety_assessment,
        )
        assert approval.status.value == "pending"
        approved = default_approval_service.approve(
            approval.approval_id, approved_by="closed-loop-regression"
        )
        assert approved.status.value == "approved"

        result = ClosedLoopService(db).execute(
            approval_id=approved.approval_id,
            query_text=QUERY,
            incident_type="missing_index",
            diagnosis=diagnosis.model_dump(mode="json"),
            recommendation=candidate.recommendation,
        )

        remediation = result["remediation"]
        benchmark = result["benchmark"]
        memory = result["memory"]

        # --- Controlled physical remediation really happened ----------------
        assert remediation.status.value in ("applied", "already_applied")
        assert remediation.verification_passed is True
        assert remediation.target_relation == "orders"
        assert remediation.target_columns == ["total_amount"]
        assert remediation.index_name == INDEX_NAME
        with engine.connect() as conn:
            assert conn.execute(
                text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
                {"n": INDEX_NAME},
            ).scalar() is not None

        # --- Real runtime benchmark evidence --------------------------------
        assert benchmark.status.value == "completed"
        assert benchmark.before.runs == 10 and benchmark.after.runs == 10
        assert benchmark.before.warmup_runs == 2 and benchmark.after.warmup_runs == 2
        assert benchmark.before.mean_execution_time_ms > 0
        assert benchmark.before.planner_cost is not None
        assert benchmark.after.planner_cost is not None
        assert benchmark.runtime_improvement_percent is not None
        assert benchmark.planner_cost_improvement_percent is not None
        assert benchmark.plan_changed is True
        assert benchmark.index_usage_changed is True
        assert benchmark.after.index_used == INDEX_NAME
        assert benchmark.before.index_used != INDEX_NAME

        # --- Memory provenance is measured and verified ---------------------
        assert memory.provenance == CaseProvenance.MEASURED
        assert memory.is_verified is True
        assert memory.verification_state == OutcomeVerificationState.VERIFIED_MEASURED

        if benchmark.runtime_improvement_percent > 0:
            assert memory.outcome == OptimizationOutcome.SUCCESS
        elif benchmark.runtime_improvement_percent == 0:
            assert memory.outcome == OptimizationOutcome.NO_IMPROVEMENT
        else:
            assert memory.outcome == OptimizationOutcome.REGRESSION

        memory_id = memory.id

    try:
        # The memory must be durably persisted with verified provenance.
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT provenance, is_verified, verification_state, outcome "
                    "FROM optimization_memories WHERE id = :i"
                ),
                {"i": memory_id},
            ).fetchone()
        assert row is not None, "Closed loop did not persist an optimization memory"
        assert row[0] == "measured"
        assert row[1] is True
        assert row[2] == "verified_measured"
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM optimization_memories WHERE id = :i"), {"i": memory_id}
            )
@pytest.mark.integration
@pytest.mark.parametrize(
    "provenance",
    [
        CaseProvenance.SEEDED,
        CaseProvenance.SYNTHETIC,
        CaseProvenance.UNVERIFIED,
    ],
)
def test_memory_service_never_verifies_non_measured_cases(provenance):
    """Only MEASURED provenance may ever become verified evidence."""
    with SessionLocal() as db:
        service = MemoryService(db)
        memory = service.create_memory(
            incident_type="missing_index",
            query_text="SELECT * FROM orders WHERE total_amount >= 450.00",
            diagnosis={"regression_test": True},
            recommendation={"relation": "orders", "columns": ["total_amount"]},
            benchmark={
                "status": "completed",
                "runtime_improvement_percent": 42.0,
                "before": {"mean_execution_time_ms": 1.0},
                "after": {"mean_execution_time_ms": 0.58},
            },
            provenance=provenance,
            is_verified=True,
        )

        assert memory.is_verified is False
        if provenance in (CaseProvenance.SEEDED, CaseProvenance.SYNTHETIC):
            assert memory.provenance == provenance
            assert memory.verification_state == OutcomeVerificationState.SYNTHETIC
        else:
            assert memory.provenance == CaseProvenance.UNVERIFIED
            assert memory.verification_state == OutcomeVerificationState.UNVERIFIED

        memory_id = memory.id

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM optimization_memories WHERE id = :i"), {"i": memory_id}
        )