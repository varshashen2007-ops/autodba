"""
Approval Service (Phase 3 Step 1)
==================================
Manages the lifecycle, state transitions, and audit records of human approval requests.

Guarantees:
  - Fails closed: only recommendations with SafetyAssessment.eligible_for_approval=True
    can have an ApprovalRequest created.
  - State transitions are strictly controlled:
      PENDING -> APPROVED (explicit approval only; records approved_at and approved_by)
      PENDING -> REJECTED (explicit rejection only; records rejected_at and rejection_reason)
      PENDING -> EXPIRED  (when expiration timeout passes; cannot be approved)
  - Blank or anonymous approvals are rejected.
  - Re-approvals or re-rejections are rejected.
  - CRITICAL: Approval authorizes future remediation; it DOES NOT execute database DDL or DML.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading
from typing import Dict, List, Optional
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.core.logging import log_operation, logger
from app.schemas.optimization import (
    ApprovalRequest,
    ApprovalStatus,
    OptimizationRecommendation,
    SafetyAssessment,
)
from app.services.safety_assessor import SafetyAssessor


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ApprovalError(Exception):
    """Base exception for approval workflow errors."""
    pass


class IneligibleForApprovalError(ApprovalError):
    """Raised when attempting to create an approval request for an ineligible recommendation."""
    pass


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval request cannot be located."""
    pass


class ApprovalStateError(ApprovalError):
    """Raised when an illegal approval state transition is attempted."""
    pass


# ---------------------------------------------------------------------------
# Service Implementation
# ---------------------------------------------------------------------------

class ApprovalService:
    """Service managing the lifecycle, audit trail, and state of approval requests."""

    def __init__(self) -> None:
        self._store: Dict[str, ApprovalRequest] = {}
        self._lock = threading.RLock()

    def create_approval_request(
        self,
        recommendation: OptimizationRecommendation,
        safety_assessment: Optional[SafetyAssessment] = None,
        settings: Optional[Settings] = None,
    ) -> ApprovalRequest:
        """Creates a new ApprovalRequest in PENDING status.

        Requires safety_assessment.eligible_for_approval == True.
        Raises IneligibleForApprovalError if the recommendation is not eligible.
        """
        cfg = settings or get_settings()
        assessment = safety_assessment or SafetyAssessor.assess(recommendation, cfg)

        if not assessment.eligible_for_approval:
            reasons_str = "; ".join(assessment.blocking_reasons) or "Safety criteria not met"
            raise IneligibleForApprovalError(
                f"Recommendation is not eligible for human approval. Reasons: {reasons_str}"
            )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=cfg.APPROVAL_EXPIRATION_MINUTES)
        approval_id = f"appr_{uuid4().hex[:12]}"

        req = ApprovalRequest(
            approval_id=approval_id,
            recommendation=recommendation,
            safety_assessment=assessment,
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
            approved_at=None,
            rejected_at=None,
            approved_by=None,
            rejection_reason=None,
        )

        with self._lock:
            self._store[approval_id] = req

        logger.info("Created approval request", extra={"approval_id": approval_id, "status": req.status.value})
        return req

    def get_approval_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Retrieves an approval request by ID, evaluating expiration if currently PENDING."""
        with self._lock:
            req = self._store.get(approval_id)
            if not req:
                return None

            # Check expiration
            if req.status == ApprovalStatus.PENDING:
                now = datetime.now(timezone.utc)
                if now >= req.expires_at:
                    req.status = ApprovalStatus.EXPIRED

            return req

    def approve(self, approval_id: str, approved_by: str) -> ApprovalRequest:
        """Approves a pending approval request.

        Guarantees:
          - approved_by must be non-empty and non-blank.
          - Request must exist and be in PENDING status.
          - Expired requests cannot be approved.
          - Ineligible recommendations cannot be approved.
          - DOES NOT modify the database.
        """
        if not approved_by or not isinstance(approved_by, str) or not approved_by.strip():
            raise ValueError("approved_by cannot be empty or anonymous.")

        with self._lock:
            req = self.get_approval_request(approval_id)
            if not req:
                raise ApprovalNotFoundError(f"Approval request '{approval_id}' was not found.")

            if req.status == ApprovalStatus.EXPIRED:
                raise ApprovalStateError(
                    f"Cannot approve request '{approval_id}': request has expired."
                )
            if req.status == ApprovalStatus.APPROVED:
                raise ApprovalStateError(
                    f"Cannot approve request '{approval_id}': request is already approved."
                )
            if req.status == ApprovalStatus.REJECTED:
                raise ApprovalStateError(
                    f"Cannot approve request '{approval_id}': request was already rejected."
                )

            if not req.safety_assessment.eligible_for_approval:
                raise ApprovalStateError(
                    f"Cannot approve request '{approval_id}': recommendation is not eligible for approval."
                )

            req.status = ApprovalStatus.APPROVED
            req.approved_at = datetime.now(timezone.utc)
            req.approved_by = approved_by.strip()

        logger.info(
            "Approval granted",
            extra={"approval_id": approval_id, "approved_by": req.approved_by},
        )
        return req

    def reject(self, approval_id: str, rejection_reason: str) -> ApprovalRequest:
        """Rejects a pending approval request.

        Guarantees:
          - rejection_reason must be non-empty and non-blank.
          - Request must exist and be in PENDING status.
          - Expired requests cannot be rejected.
        """
        if not rejection_reason or not isinstance(rejection_reason, str) or not rejection_reason.strip():
            raise ValueError("rejection_reason cannot be empty.")

        with self._lock:
            req = self.get_approval_request(approval_id)
            if not req:
                raise ApprovalNotFoundError(f"Approval request '{approval_id}' was not found.")

            if req.status == ApprovalStatus.EXPIRED:
                raise ApprovalStateError(
                    f"Cannot reject request '{approval_id}': request has expired."
                )
            if req.status == ApprovalStatus.APPROVED:
                raise ApprovalStateError(
                    f"Cannot reject request '{approval_id}': request is already approved."
                )
            if req.status == ApprovalStatus.REJECTED:
                raise ApprovalStateError(
                    f"Cannot reject request '{approval_id}': request was already rejected."
                )

            req.status = ApprovalStatus.REJECTED
            req.rejected_at = datetime.now(timezone.utc)
            req.rejection_reason = rejection_reason.strip()

        logger.info(
            "Approval rejected",
            extra={"approval_id": approval_id, "rejection_reason": req.rejection_reason},
        )
        return req

    def list_requests(self) -> List[ApprovalRequest]:
        """Returns a list of all stored approval requests with current statuses."""
        with self._lock:
            now = datetime.now(timezone.utc)
            results: List[ApprovalRequest] = []
            for req in self._store.values():
                if req.status == ApprovalStatus.PENDING and now >= req.expires_at:
                    req.status = ApprovalStatus.EXPIRED
                results.append(req)
            return results

    def clear(self) -> None:
        """Clears all stored requests (primarily for test isolation)."""
        with self._lock:
            self._store.clear()


# Module-level default instance
default_approval_service = ApprovalService()
