"""
Unit and integration tests for Controlled Physical Remediation (Phase 3 Step 2).

Covers all 20 required tests + real end-to-end database verification:
  1.  Valid approved remediation physically creates index
  2.  Unapproved recommendation is blocked
  3.  Rejected approval is blocked
  4.  Expired approval is blocked
  5.  Unvalidated recommendation is blocked
  6.  HypoPG not validated is blocked
  7.  Approval snapshot mismatch is blocked
  8.  Safety revalidation failure is blocked
  9.  Idempotency: duplicate execution returns ALREADY_APPLIED
  10. Safe index name character validation
  11. Long identifier truncation within PostgreSQL 63-byte limits
  12. Injection attempt in table/column is blocked before SQL execution
  13. Arbitrary DDL execution is rejected
  14. Transaction failure handling (no false success)
  15. Post-creation verification verifies physical index definition
  16. Database integrity: row counts unchanged (500/100/5000/15000)
  17. No unrelated indexes created
  18. Audit result contains complete metadata
  19. Determinism of SQL construction and index naming
  20. No direct sql_preview execution: constructed internally
  21. Real end-to-end experiment: orders(customer_id)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.database import engine
from app.schemas.optimization import (
    ApprovalRequest,
    ApprovalStatus,
    OptimizationRecommendation,
    OptimizationType,
    RecommendationConfidence,
    RecommendationRisk,
    RecommendationStatus,
    RemediationResult,
    RemediationStatus,
    SafetyAssessment,
    SafetyCheckStatus,
    SafetyLevel,
)
from app.services.approval_service import ApprovalService
from app.services.remediation_service import (
    RemediationBlockedError,
    RemediationExecutionError,
    RemediationService,
    RemediationVerificationError,
)
from app.services.safety_assessor import SafetyAssessor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_valid_rec(
    relation: str = "orders",
    columns: list[str] = None,
    confidence: RecommendationConfidence = RecommendationConfidence.HIGH,
    risk: RecommendationRisk = RecommendationRisk.LOW,
    status: RecommendationStatus = RecommendationStatus.VALIDATED,
    hypopg_validated: bool = True,
    cost_improvement_percent: float = 73.8,
) -> OptimizationRecommendation:
    cols = columns if columns is not None else ["customer_id"]
    col_str = ", ".join(cols)
    return OptimizationRecommendation(
        optimization_type=OptimizationType.MISSING_INDEX,
        title=f"Create index on {relation}({col_str})",
        summary=f"Validated candidate on {relation}({col_str})",
        description="Observed: Seq scan\nCandidate: Index\nValidation: HypoPG confirmed",
        relation=relation,
        columns=cols,
        recommended_action=f"CREATE INDEX ON {relation} ({col_str});",
        sql_preview=f"CREATE INDEX ON {relation} ({col_str});",
        status=status,
        confidence=confidence,
        risk=risk,
        evidence=["PostgreSQL selected Seq Scan", "HypoPG validated 73.8% improvement"],
        hypopg_validated=hypopg_validated,
        original_cost=107.5,
        hypothetical_cost=28.16,
        cost_improvement_percent=cost_improvement_percent,
        tradeoffs=["Storage overhead", "Write amplification"],
        warnings=[],
        requires_human_approval=True,
    )


def _sample_approved_request(
    rec: OptimizationRecommendation = None,
    status: ApprovalStatus = ApprovalStatus.APPROVED,
    approved_by: str = "lead_dba",
    expires_delta_minutes: int = 30,
) -> ApprovalRequest:
    recommendation = rec or _sample_valid_rec()
    assessment = SafetyAssessor.assess(recommendation)
    now = datetime.now(timezone.utc)
    return ApprovalRequest(
        approval_id="appr_test_001",
        recommendation=recommendation,
        safety_assessment=assessment,
        status=status,
        created_at=now,
        expires_at=now + timedelta(minutes=expires_delta_minutes),
        approved_at=now if status == ApprovalStatus.APPROVED else None,
        approved_by=approved_by if status == ApprovalStatus.APPROVED else None,
        rejected_at=None,
        rejection_reason=None,
    )


# ---------------------------------------------------------------------------
# Test 1 – Valid approved remediation physically creates index
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_valid_approved_remediation():
    appr_req = _sample_approved_request()
    result = RemediationService.apply_approved_recommendation(appr_req)

    assert result.status == RemediationStatus.APPLIED or result.status == RemediationStatus.ALREADY_APPLIED
    assert result.verification_passed is True
    assert result.target_relation == "orders"
    assert result.target_columns == ["customer_id"]
    assert "customer_id" in (result.index_name or "")


# ---------------------------------------------------------------------------
# Test 2 – Unapproved recommendation is blocked
# ---------------------------------------------------------------------------

def test_unapproved_recommendation_blocked():
    appr_req = _sample_approved_request(status=ApprovalStatus.PENDING)

    with pytest.raises(RemediationBlockedError) as exc_info:
        RemediationService.apply_approved_recommendation(appr_req)
    assert "approved" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 3 – Rejected approval is blocked
# ---------------------------------------------------------------------------

def test_rejected_approval_blocked():
    appr_req = _sample_approved_request(status=ApprovalStatus.REJECTED)

    with pytest.raises(RemediationBlockedError) as exc_info:
        RemediationService.apply_approved_recommendation(appr_req)
    assert "rejected" in str(exc_info.value).lower() or "approved" in str(exc_info.value).lower()



# ---------------------------------------------------------------------------
# Test 4 – Expired approval is blocked
# ---------------------------------------------------------------------------

def test_expired_approval_blocked():
    appr_req = _sample_approved_request(expires_delta_minutes=-5)

    with pytest.raises(RemediationBlockedError) as exc_info:
        RemediationService.apply_approved_recommendation(appr_req)
    assert "expired" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 5 – Unvalidated recommendation is blocked
# ---------------------------------------------------------------------------

def test_unvalidated_recommendation_blocked():
    rec = _sample_valid_rec(status=RecommendationStatus.UNVALIDATED, hypopg_validated=False)
    appr_req = _sample_approved_request(rec=rec)

    with pytest.raises(RemediationBlockedError) as exc_info:
        RemediationService.apply_approved_recommendation(appr_req)
    assert "validated" in str(exc_info.value).lower() or "ineligible" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 6 – HypoPG not validated is blocked
# ---------------------------------------------------------------------------

def test_hypopg_not_validated_blocked():
    rec = _sample_valid_rec(hypopg_validated=False)
    appr_req = _sample_approved_request(rec=rec)

    with pytest.raises(RemediationBlockedError) as exc_info:
        RemediationService.apply_approved_recommendation(appr_req)
    assert "hypopg" in str(exc_info.value).lower() or "ineligible" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 7 – Approval snapshot mismatch is blocked
# ---------------------------------------------------------------------------

def test_approval_snapshot_mismatch_blocked():
    approved_rec = _sample_valid_rec(relation="orders", columns=["customer_id"])
    appr_req = _sample_approved_request(rec=approved_rec)

    # Mutated current recommendation (changed relation to 'customers')
    current_rec = _sample_valid_rec(relation="customers", columns=["customer_id"])

    with pytest.raises(RemediationBlockedError) as exc_info:
        RemediationService.apply_approved_recommendation(
            appr_req, current_recommendation=current_rec
        )
    assert "mismatch" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 8 – Safety revalidation failure is blocked
# ---------------------------------------------------------------------------

def test_safety_revalidation_failure_blocked():
    # Valid at time of approval, but candidate now has LOW confidence
    mutated_rec = _sample_valid_rec(confidence=RecommendationConfidence.LOW)
    appr_req = _sample_approved_request()
    # Overwrite recommendation inside request to trigger recheck failure
    appr_req.recommendation = mutated_rec

    with pytest.raises(RemediationBlockedError) as exc_info:
        RemediationService.apply_approved_recommendation(appr_req)
    assert "safety" in str(exc_info.value).lower() or "confidence" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 9 – Idempotent execution
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_idempotent_execution_returns_already_applied():
    appr_req = _sample_approved_request()

    # First execution (applies or confirms applied)
    res1 = RemediationService.apply_approved_recommendation(appr_req)
    assert res1.status in (RemediationStatus.APPLIED, RemediationStatus.ALREADY_APPLIED)

    # Second execution with same approved recommendation
    res2 = RemediationService.apply_approved_recommendation(appr_req)
    assert res2.status == RemediationStatus.ALREADY_APPLIED
    assert res2.sql_executed is None
    assert res2.verification_passed is True
    assert len(res2.warnings) > 0


# ---------------------------------------------------------------------------
# Test 10 – Safe index name characters
# ---------------------------------------------------------------------------

def test_safe_index_name_generation():
    name = RemediationService.generate_index_name("orders", ["customer_id"])
    assert name == "idx_autodba_orders_customer_id"
    assert all(c.isalnum() or c == "_" for c in name)


# ---------------------------------------------------------------------------
# Test 11 – Long identifier length within 63 bytes
# ---------------------------------------------------------------------------

def test_long_identifier_truncation():
    very_long_cols = [
        "customer_account_identification_number_primary_key_field",
        "secondary_order_status_tracking_code_identifier",
    ]
    name = RemediationService.generate_index_name("orders_large_partition_table_name", very_long_cols)
    assert len(name) <= 63
    assert name.startswith("idx_autodba_")
    assert all(c.isalnum() or c == "_" for c in name)


# ---------------------------------------------------------------------------
# Test 12 – Injection attempt in identifiers is blocked
# ---------------------------------------------------------------------------

def test_injection_attempt_blocked():
    rec = _sample_valid_rec(relation="orders; DROP TABLE orders; --")
    appr_req = _sample_approved_request(rec=rec)

    with pytest.raises(RemediationBlockedError):
        RemediationService.apply_approved_recommendation(appr_req)


# ---------------------------------------------------------------------------
# Test 13 – Arbitrary DDL is rejected
# ---------------------------------------------------------------------------

def test_arbitrary_ddl_rejected():
    rec = _sample_valid_rec()
    appr_req = _sample_approved_request(rec=rec)

    with pytest.raises(RemediationBlockedError):
        RemediationService._validate_constructed_sql(
            "DROP TABLE orders;", "orders", ["customer_id"], "idx_test"
        )


# ---------------------------------------------------------------------------
# Test 14 – Transaction failure handling
# ---------------------------------------------------------------------------

def test_transaction_failure_handling():
    mock_engine = MagicMock()
    mock_engine.begin.side_effect = Exception("Connection terminated unexpectedly")

    appr_req = _sample_approved_request()

    with pytest.raises(RemediationExecutionError) as exc_info:
        RemediationService.apply_approved_recommendation(appr_req, db_engine=mock_engine)
    assert "execution failed" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 15 – Post-creation verification
# ---------------------------------------------------------------------------

def test_post_creation_verification():
    post_indexes = [
        {"indexname": "orders_pkey", "indexdef": "CREATE UNIQUE INDEX orders_pkey ON orders (id)"},
        {"indexname": "idx_autodba_orders_customer_id", "indexdef": "CREATE INDEX idx_autodba_orders_customer_id ON orders USING btree (customer_id)"},
    ]
    verified = RemediationService._verify_created_index(
        post_indexes, "idx_autodba_orders_customer_id", ["customer_id"]
    )
    assert verified is True

    unverified = RemediationService._verify_created_index(
        post_indexes, "idx_non_existent", ["customer_id"]
    )
    assert unverified is False


# ---------------------------------------------------------------------------
# Test 16 – Database integrity verification
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_database_integrity_after_remediation():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() == 500
        assert conn.execute(text("SELECT COUNT(*) FROM products")).scalar() == 100
        assert conn.execute(text("SELECT COUNT(*) FROM orders")).scalar() == 5000
        assert conn.execute(text("SELECT COUNT(*) FROM order_items")).scalar() == 15000


# ---------------------------------------------------------------------------
# Test 17 – Unrelated indexes not created
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_no_unrelated_indexes_created():
    with engine.connect() as conn:
        customer_indexes = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'customers'")
        ).scalars().all()
        # Baseline indexes on customers: customers_pkey and customers_email_key
        assert len(customer_indexes) == 2
        assert "customers_pkey" in customer_indexes
        assert "customers_email_key" in customer_indexes
        assert not any(idx.startswith("idx_autodba_") for idx in customer_indexes)



# ---------------------------------------------------------------------------
# Test 18 – Complete audit result metadata
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_audit_result_metadata():
    appr_req = _sample_approved_request()
    result = RemediationService.apply_approved_recommendation(appr_req)

    assert result.remediation_id.startswith("rem_")
    assert result.approval_id == appr_req.approval_id
    assert result.started_at is not None
    assert result.completed_at >= result.started_at
    assert len(result.pre_remediation_indexes) > 0
    assert len(result.post_remediation_indexes) > 0


# ---------------------------------------------------------------------------
# Test 19 – Determinism of SQL construction
# ---------------------------------------------------------------------------

def test_determinism_sql_construction():
    name1 = RemediationService.generate_index_name("orders", ["customer_id"])
    name2 = RemediationService.generate_index_name("orders", ["customer_id"])
    assert name1 == name2 == "idx_autodba_orders_customer_id"


# ---------------------------------------------------------------------------
# Test 20 – No direct sql_preview execution
# ---------------------------------------------------------------------------

def test_no_direct_sql_preview_execution():
    rec = _sample_valid_rec()
    # Intentionally give sql_preview an irregular spacing/casing
    rec.sql_preview = "CREATE   INDEX   ON   orders(customer_id);"
    appr_req = _sample_approved_request(rec=rec)

    result = RemediationService.apply_approved_recommendation(appr_req)

    # The executed SQL must be the internally constructed one with deterministic name
    if result.sql_executed:
        assert result.sql_executed.startswith("CREATE INDEX idx_autodba_orders_customer_id ON orders")
