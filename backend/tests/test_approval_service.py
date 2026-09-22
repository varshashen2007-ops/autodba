"""
Unit and integration tests for ApprovalService (Phase 3 Step 1).

Covers tests 14-28:
  14. Create valid approval request (status = PENDING)
  15. Approve valid pending request (PENDING -> APPROVED)
  16. Reject valid pending request (PENDING -> REJECTED)
  17. Cannot approve rejected request
  18. Cannot approve expired request
  19. Cannot approve safety-ineligible recommendation
  20. Approval requires non-empty approved_by
  21. Rejection requires a reason
  22. Approval records timestamp and actor
  23. Rejection records timestamp and reason
  24. Expiration works correctly
  25. Repeated approval is rejected
  26. Repeated rejection is rejected
  27. Approval state transitions are deterministic
  28. No database modification test (Step 14 & 15: real PostgreSQL verification)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    SafetyCheckStatus,
    SafetyLevel,
)
from app.services.approval_service import (
    ApprovalNotFoundError,
    ApprovalService,
    ApprovalStateError,
    IneligibleForApprovalError,
)
from app.services.safety_assessor import SafetyAssessor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
    svc = ApprovalService()
    svc.clear()
    yield svc
    svc.clear()


def _sample_eligible_rec() -> OptimizationRecommendation:
    return OptimizationRecommendation(
        optimization_type=OptimizationType.MISSING_INDEX,
        title="Create index on orders(customer_id)",
        summary="Validated candidate index on orders(customer_id)",
        description="Observed: Seq Scan\nCandidate: Index\nValidation: HypoPG verified",
        relation="orders",
        columns=["customer_id"],
        recommended_action="CREATE INDEX ON orders (customer_id);",
        sql_preview="CREATE INDEX ON orders (customer_id);",
        status=RecommendationStatus.VALIDATED,
        confidence=RecommendationConfidence.HIGH,
        risk=RecommendationRisk.LOW,
        evidence=["PostgreSQL selected Seq Scan", "HypoPG validated 73.8% cost reduction"],
        hypopg_validated=True,
        original_cost=107.5,
        hypothetical_cost=28.16,
        cost_improvement_percent=73.8,
        tradeoffs=["Storage overhead", "Write amplification"],
        warnings=[],
        requires_human_approval=True,
    )


def _sample_ineligible_rec() -> OptimizationRecommendation:
    return OptimizationRecommendation(
        optimization_type=OptimizationType.MISSING_INDEX,
        title="Unvalidated candidate",
        summary="Unvalidated candidate",
        description="Unvalidated",
        relation="orders",
        columns=["customer_id"],
        recommended_action="Review candidate index",
        sql_preview=None,
        status=RecommendationStatus.UNVALIDATED,
        confidence=RecommendationConfidence.MEDIUM,
        risk=RecommendationRisk.HIGH,
        evidence=[],
        hypopg_validated=False,
        requires_human_approval=True,
    )


# ---------------------------------------------------------------------------
# Test 14 – Create valid approval request
# ---------------------------------------------------------------------------

def test_create_valid_approval_request(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)

    assert req.status == ApprovalStatus.PENDING
    assert req.approval_id.startswith("appr_")
    assert req.created_at is not None
    assert req.expires_at > req.created_at
    assert req.approved_at is None
    assert req.approved_by is None
    assert req.rejected_at is None
    assert req.rejection_reason is None
    assert req.safety_assessment.eligible_for_approval is True


# ---------------------------------------------------------------------------
# Test 15 – Approve valid pending request
# ---------------------------------------------------------------------------

def test_approve_valid_pending_request(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)

    approved = service.approve(req.approval_id, approved_by="dba_admin")

    assert approved.status == ApprovalStatus.APPROVED
    assert approved.approved_by == "dba_admin"
    assert approved.approved_at is not None
    assert approved.rejected_at is None


# ---------------------------------------------------------------------------
# Test 16 – Reject valid pending request
# ---------------------------------------------------------------------------

def test_reject_valid_pending_request(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)

    rejected = service.reject(req.approval_id, rejection_reason="Maintenance window unavailable.")

    assert rejected.status == ApprovalStatus.REJECTED
    assert rejected.rejection_reason == "Maintenance window unavailable."
    assert rejected.rejected_at is not None
    assert rejected.approved_at is None


# ---------------------------------------------------------------------------
# Test 17 – Cannot approve rejected request
# ---------------------------------------------------------------------------

def test_cannot_approve_rejected_request(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)
    service.reject(req.approval_id, rejection_reason="Table write rate too high.")

    with pytest.raises(ApprovalStateError) as exc_info:
        service.approve(req.approval_id, approved_by="dba_admin")
    assert "rejected" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 18 – Cannot approve expired request
# ---------------------------------------------------------------------------

def test_cannot_approve_expired_request(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)

    # Fast-forward expires_at to the past
    req.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    with pytest.raises(ApprovalStateError) as exc_info:
        service.approve(req.approval_id, approved_by="dba_admin")
    assert "expired" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 19 – Cannot approve safety-ineligible recommendation
# ---------------------------------------------------------------------------

def test_cannot_create_approval_for_ineligible_rec(service: ApprovalService):
    rec = _sample_ineligible_rec()
    with pytest.raises(IneligibleForApprovalError) as exc_info:
        service.create_approval_request(rec)
    assert "not eligible" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 20 – Approval requires non-empty approved_by
# ---------------------------------------------------------------------------

def test_approval_requires_non_empty_approved_by(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)

    with pytest.raises(ValueError):
        service.approve(req.approval_id, approved_by="")

    with pytest.raises(ValueError):
        service.approve(req.approval_id, approved_by="   ")

    with pytest.raises(ValueError):
        service.approve(req.approval_id, approved_by=None)


# ---------------------------------------------------------------------------
# Test 21 – Rejection requires a reason
# ---------------------------------------------------------------------------

def test_rejection_requires_reason(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)

    with pytest.raises(ValueError):
        service.reject(req.approval_id, rejection_reason="")

    with pytest.raises(ValueError):
        service.reject(req.approval_id, rejection_reason="   ")

    with pytest.raises(ValueError):
        service.reject(req.approval_id, rejection_reason=None)


# ---------------------------------------------------------------------------
# Test 22 – Approval records timestamp
# ---------------------------------------------------------------------------

def test_approval_records_timestamp(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)
    before = datetime.now(timezone.utc)
    approved = service.approve(req.approval_id, approved_by="lead_dba")
    after = datetime.now(timezone.utc)

    assert before <= approved.approved_at <= after


# ---------------------------------------------------------------------------
# Test 23 – Rejection records timestamp
# ---------------------------------------------------------------------------

def test_rejection_records_timestamp(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)
    before = datetime.now(timezone.utc)
    rejected = service.reject(req.approval_id, rejection_reason="Not needed")
    after = datetime.now(timezone.utc)

    assert before <= rejected.rejected_at <= after


# ---------------------------------------------------------------------------
# Test 24 – Expiration works correctly
# ---------------------------------------------------------------------------

def test_expiration_marks_status_expired(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)

    # Set expiration to past
    req.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    retrieved = service.get_approval_request(req.approval_id)
    assert retrieved.status == ApprovalStatus.EXPIRED


# ---------------------------------------------------------------------------
# Test 25 – Repeated approval is rejected
# ---------------------------------------------------------------------------

def test_repeated_approval_rejected(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)
    service.approve(req.approval_id, approved_by="dba_1")

    with pytest.raises(ApprovalStateError) as exc_info:
        service.approve(req.approval_id, approved_by="dba_2")
    assert "already approved" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 26 – Repeated rejection is rejected
# ---------------------------------------------------------------------------

def test_repeated_rejection_rejected(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)
    service.reject(req.approval_id, rejection_reason="Reason 1")

    with pytest.raises(ApprovalStateError) as exc_info:
        service.reject(req.approval_id, rejection_reason="Reason 2")
    assert "already rejected" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 27 – Approval state transitions are deterministic
# ---------------------------------------------------------------------------

def test_approval_state_transitions_deterministic(service: ApprovalService):
    rec = _sample_eligible_rec()
    req = service.create_approval_request(rec)
    assert req.status == ApprovalStatus.PENDING

    req = service.approve(req.approval_id, approved_by="dba_admin")
    assert req.status == ApprovalStatus.APPROVED

    # Cannot reject once approved
    with pytest.raises(ApprovalStateError):
        service.reject(req.approval_id, rejection_reason="Too late")


# ---------------------------------------------------------------------------
# Test 28 – Step 14 & 15: No database modification test
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_explicit_approval_does_not_modify_database(service: ApprovalService):
    """
    Runs complete flow:
      Recommendation -> Safety Assessment -> Approval Request -> Explicit Approval.

    Verifies:
      - Approval request transitions to APPROVED.
      - Absolutely NO database modification occurs!
      - orders table still has only orders_pkey and idx_orders_order_date.
      - No physical customer_id index exists.
      - HypoPG state is completely clean (count = 0).
      - Row counts remain exactly: customers=500, products=100, orders=5000, order_items=15000.
    """
    rec = _sample_eligible_rec()

    # Step 1: Safety assessment
    assessment = SafetyAssessor.assess(rec)
    assert assessment.eligible_for_approval is True

    # Step 2: Create approval request
    req = service.create_approval_request(rec, assessment)
    assert req.status == ApprovalStatus.PENDING

    # Step 3: Explicit human approval
    approved = service.approve(req.approval_id, approved_by="senior_dba")
    assert approved.status == ApprovalStatus.APPROVED

    # Step 4: Verify database integrity against live PostgreSQL
    with engine.connect() as conn:
        # Verify orders table physical indexes
        indexes = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'orders'")
        ).scalars().all()

        assert "orders_pkey" in indexes
        assert "idx_orders_order_date" in indexes
        assert len(indexes) == 2, f"Expected exactly 2 indexes on orders; found {indexes}"

        # Verify no customer_id index was created
        cid_idx = conn.execute(
            text("SELECT COUNT(*) FROM pg_indexes WHERE tablename = 'orders' AND indexdef LIKE '%customer_id%'")
        ).scalar()
        assert cid_idx == 0, "No customer_id physical index should exist after approval."

        # Verify HypoPG state is clean
        hypo_count = conn.execute(text("SELECT COUNT(*) FROM hypopg()")).scalar()
        assert hypo_count == 0, "HypoPG state must be clean."

        # Verify table row counts
        assert conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() == 500
        assert conn.execute(text("SELECT COUNT(*) FROM products")).scalar() == 100
        assert conn.execute(text("SELECT COUNT(*) FROM orders")).scalar() == 5000
        assert conn.execute(text("SELECT COUNT(*) FROM order_items")).scalar() == 15000
