"""
Controlled Physical Remediation Service (Phase 3 Step 2)
========================================================
Safely and deterministically applies already validated and explicitly approved
optimization recommendations to the PostgreSQL database.

Guarantees:
  - Authorization-aware: strictly requires APPROVED status, valid actor, and active approval.
  - Snapshot integrity: verifies recommendation fields have not mutated since approval.
  - Safety revalidation: re-evaluates all safety checks before opening a write transaction.
  - Safe SQL construction: constructs SQL internally from validated identifiers; never
    executes arbitrary SQL or blindly runs sql_preview.
  - Idempotent: detects equivalent physical indexes and returns ALREADY_APPLIED without duplication.
  - Narrowly scoped: only supports CREATE INDEX on approved relation and columns.
  - Atomic transaction: executes inside an explicit transaction with rollback on error.
  - Post-remediation verification: verifies physical index presence in pg_indexes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import Settings, get_settings
from app.core.logging import log_operation, logger
from app.db.database import engine as default_engine
from app.schemas.optimization import (
    ApprovalRequest,
    ApprovalStatus,
    OptimizationRecommendation,
    OptimizationType,
    RecommendationStatus,
    RemediationResult,
    RemediationStatus,
    SafetyCheckStatus,
    SafetyLevel,
)
from app.services.hypopg_validator import HypoPGValidatorService, InvalidCandidateError
from app.services.safety_assessor import SafetyAssessor


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RemediationError(Exception):
    """Base exception for physical remediation errors."""
    pass


class RemediationBlockedError(RemediationError):
    """Raised when a remediation request is blocked by authorization or safety rules."""
    pass


class RemediationExecutionError(RemediationError):
    """Raised when physical DDL execution fails on the database."""
    pass


class RemediationVerificationError(RemediationError):
    """Raised when post-remediation database index verification fails."""
    pass


# ---------------------------------------------------------------------------
# Service Implementation
# ---------------------------------------------------------------------------

class RemediationService:
    """Service governing controlled physical index creation for approved recommendations."""

    @classmethod
    def apply_approved_recommendation(
        cls,
        approval_request: ApprovalRequest,
        current_recommendation: Optional[OptimizationRecommendation] = None,
        settings: Optional[Settings] = None,
        db_engine: Optional[Engine] = None,
    ) -> RemediationResult:
        """Applies an approved recommendation to the database in a controlled, idempotent manner.

        Args:
            approval_request: The authorizing ApprovalRequest (must be APPROVED).
            current_recommendation: Optional current recommendation to verify snapshot integrity.
            settings: Application settings override.
            db_engine: SQLAlchemy Engine override (defaults to app engine).

        Returns:
            RemediationResult containing full execution and audit details.

        Raises:
            RemediationBlockedError: If authorization, snapshot, or safety recheck fails.
            RemediationExecutionError: If database execution fails.
            RemediationVerificationError: If verification fails post-creation.
        """
        cfg = settings or get_settings()
        engine = db_engine or default_engine
        started_at = datetime.now(timezone.utc)
        remediation_id = f"rem_{uuid4().hex[:12]}"
        rec = approval_request.recommendation

        with log_operation("apply_remediation"):
            # -------------------------------------------------------------------
            # Step 3: Authorization Checks
            # -------------------------------------------------------------------
            cls._check_authorization(approval_request)

            # -------------------------------------------------------------------
            # Step 4: Approval Snapshot Integrity Check
            # -------------------------------------------------------------------
            if current_recommendation is not None:
                cls._check_snapshot_integrity(approval_request.recommendation, current_recommendation)

            # -------------------------------------------------------------------
            # Step 5: Safety Revalidation
            # -------------------------------------------------------------------
            cls._revalidate_safety(rec, cfg)

            # -------------------------------------------------------------------
            # Identifier Validation
            # -------------------------------------------------------------------
            table = rec.relation
            columns = rec.columns
            if not table or not columns:
                raise RemediationBlockedError("Recommendation lacks valid relation or columns.")

            try:
                safe_table = HypoPGValidatorService.validate_identifier(table, "table name")
                safe_columns = [
                    HypoPGValidatorService.validate_identifier(col, "column name")
                    for col in columns
                ]
            except InvalidCandidateError as e:
                raise RemediationBlockedError(f"Identifier validation failed: {str(e)}") from e

            # -------------------------------------------------------------------
            # Step 6: Pre-Remediation Database State Capture
            # -------------------------------------------------------------------
            pre_indexes = cls._fetch_table_indexes(engine, safe_table)

            # -------------------------------------------------------------------
            # Step 7: Idempotency Check
            # -------------------------------------------------------------------
            existing_index_name = cls._find_equivalent_index(pre_indexes, safe_table, safe_columns)
            if existing_index_name:
                completed_at = datetime.now(timezone.utc)
                logger.info(
                    "Equivalent index already exists",
                    extra={"table": safe_table, "index_name": existing_index_name},
                )
                return RemediationResult(
                    remediation_id=remediation_id,
                    approval_id=approval_request.approval_id,
                    recommendation=rec,
                    status=RemediationStatus.ALREADY_APPLIED,
                    target_relation=safe_table,
                    target_columns=safe_columns,
                    sql_executed=None,
                    index_name=existing_index_name,
                    started_at=started_at,
                    completed_at=completed_at,
                    pre_remediation_indexes=pre_indexes,
                    post_remediation_indexes=pre_indexes,
                    error=None,
                    warnings=[
                        f"Equivalent physical index '{existing_index_name}' already exists on '{safe_table}'."
                    ],
                    verification_passed=True,
                )

            # -------------------------------------------------------------------
            # Step 8 & 9: Safe SQL Construction & Index Name Generation
            # -------------------------------------------------------------------
            index_name = cls.generate_index_name(safe_table, safe_columns, pre_indexes)
            sql_to_execute = f"CREATE INDEX {index_name} ON {safe_table} ({', '.join(safe_columns)});"

            # Defense-in-depth: verify constructed SQL conforms to strict pattern
            cls._validate_constructed_sql(sql_to_execute, safe_table, safe_columns, index_name)

            # -------------------------------------------------------------------
            # Step 10 & 11: Transactional Physical Index Creation
            # -------------------------------------------------------------------
            try:
                with engine.begin() as conn:
                    conn.execute(text(sql_to_execute))
            except Exception as e:
                completed_at = datetime.now(timezone.utc)
                err_msg = f"Database execution failed: {str(e)}"
                logger.error("Remediation execution failed", extra={"error": err_msg})
                raise RemediationExecutionError(err_msg) from e

            # -------------------------------------------------------------------
            # Step 12: Post-Remediation Verification
            # -------------------------------------------------------------------
            post_indexes = cls._fetch_table_indexes(engine, safe_table)
            is_verified = cls._verify_created_index(post_indexes, index_name, safe_columns)
            completed_at = datetime.now(timezone.utc)

            if not is_verified:
                raise RemediationVerificationError(
                    f"Post-remediation verification failed: index '{index_name}' not found on '{safe_table}'."
                )

            logger.info(
                "Physical remediation successfully applied",
                extra={"remediation_id": remediation_id, "index_name": index_name},
            )

            return RemediationResult(
                remediation_id=remediation_id,
                approval_id=approval_request.approval_id,
                recommendation=rec,
                status=RemediationStatus.APPLIED,
                target_relation=safe_table,
                target_columns=safe_columns,
                sql_executed=sql_to_execute,
                index_name=index_name,
                started_at=started_at,
                completed_at=completed_at,
                pre_remediation_indexes=pre_indexes,
                post_remediation_indexes=post_indexes,
                error=None,
                warnings=[],
                verification_passed=True,
            )

    # -----------------------------------------------------------------------
    # Helper: Authorization Checks
    # -----------------------------------------------------------------------

    @classmethod
    def _check_authorization(cls, req: ApprovalRequest) -> None:
        """Strict authorization validation prior to any database operation."""
        # 1. Approval status must be APPROVED
        if req.status != ApprovalStatus.APPROVED:
            raise RemediationBlockedError(
                f"Remediation blocked: ApprovalRequest '{req.approval_id}' status is "
                f"'{req.status.value}', expected 'approved'."
            )

        # 2. Expiration check
        now = datetime.now(timezone.utc)
        if now >= req.expires_at:
            raise RemediationBlockedError(
                f"Remediation blocked: ApprovalRequest '{req.approval_id}' has expired."
            )

        # 3. Approved by must be non-empty
        if not req.approved_by or not req.approved_by.strip():
            raise RemediationBlockedError(
                f"Remediation blocked: ApprovalRequest '{req.approval_id}' lacks approved_by actor."
            )

        # 4. Safety assessment must be eligible
        if not req.safety_assessment.eligible_for_approval:
            raise RemediationBlockedError(
                f"Remediation blocked: safety assessment indicates recommendation is ineligible."
            )

        # 5. Recommendation status must be VALIDATED
        if req.recommendation.status != RecommendationStatus.VALIDATED:
            raise RemediationBlockedError(
                f"Remediation blocked: recommendation status is '{req.recommendation.status.value}', "
                "expected 'validated'."
            )

        # 6. HypoPG validation confirmed
        if req.recommendation.hypopg_validated is not True:
            raise RemediationBlockedError(
                "Remediation blocked: recommendation was not validated by HypoPG simulation."
            )

        # 7. Human approval required
        if req.recommendation.requires_human_approval is not True:
            raise RemediationBlockedError(
                "Remediation blocked: recommendation requires_human_approval is not True."
            )

    # -----------------------------------------------------------------------
    # Helper: Snapshot Integrity Check
    # -----------------------------------------------------------------------

    @classmethod
    def _check_snapshot_integrity(
        cls,
        approved: OptimizationRecommendation,
        current: OptimizationRecommendation,
    ) -> None:
        """Verifies that the recommendation attempting execution matches what was approved."""
        mismatches: List[str] = []

        if approved.optimization_type != current.optimization_type:
            mismatches.append(f"optimization_type: {approved.optimization_type} vs {current.optimization_type}")
        if approved.relation != current.relation:
            mismatches.append(f"relation: {approved.relation} vs {current.relation}")
        if approved.columns != current.columns:
            mismatches.append(f"columns: {approved.columns} vs {current.columns}")
        if approved.status != current.status:
            mismatches.append(f"status: {approved.status} vs {current.status}")
        if approved.hypopg_validated != current.hypopg_validated:
            mismatches.append(f"hypopg_validated: {approved.hypopg_validated} vs {current.hypopg_validated}")
        if approved.original_cost != current.original_cost:
            mismatches.append(f"original_cost: {approved.original_cost} vs {current.original_cost}")
        if approved.hypothetical_cost != current.hypothetical_cost:
            mismatches.append(f"hypothetical_cost: {approved.hypothetical_cost} vs {current.hypothetical_cost}")
        if approved.cost_improvement_percent != current.cost_improvement_percent:
            mismatches.append(f"cost_improvement_percent: {approved.cost_improvement_percent} vs {current.cost_improvement_percent}")
        if approved.sql_preview != current.sql_preview:
            mismatches.append(f"sql_preview: {approved.sql_preview} vs {current.sql_preview}")

        if mismatches:
            raise RemediationBlockedError(
                f"Remediation blocked: approval snapshot mismatch ({'; '.join(mismatches)})."
            )

    # -----------------------------------------------------------------------
    # Helper: Safety Revalidation
    # -----------------------------------------------------------------------

    @classmethod
    def _revalidate_safety(cls, rec: OptimizationRecommendation, cfg: Settings) -> None:
        """Re-runs safety evaluation immediately prior to database modification."""
        assessment = SafetyAssessor.assess(rec, cfg)
        if not assessment.eligible_for_approval:
            reasons = "; ".join(assessment.blocking_reasons) or "Safety criteria not met"
            raise RemediationBlockedError(f"Remediation blocked: safety recheck failed ({reasons}).")

    # -----------------------------------------------------------------------
    # Helper: Database Index Inspection
    # -----------------------------------------------------------------------

    @classmethod
    def _fetch_table_indexes(cls, engine: Engine, table: str) -> List[Dict[str, Any]]:
        """Fetches existing physical indexes on the specified table from pg_indexes."""
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = :tbl"),
                {"tbl": table},
            )
            return [{"indexname": row[0], "indexdef": row[1]} for row in result.fetchall()]

    # -----------------------------------------------------------------------
    # Helper: Idempotency Identification
    # -----------------------------------------------------------------------

    @classmethod
    def _find_equivalent_index(
        cls,
        indexes: List[Dict[str, Any]],
        table: str,
        columns: List[str],
    ) -> Optional[str]:
        """Checks whether an index already covers the target table and columns in order."""
        target_cols_lower = [c.lower() for c in columns]

        for idx in indexes:
            indexdef = idx.get("indexdef", "")
            m = re.search(r"\(([^)]+)\)$", indexdef.strip())
            if m:
                idx_cols = [c.strip().lower() for c in m.group(1).split(",") if c.strip()]
                if idx_cols == target_cols_lower:
                    return idx["indexname"]
        return None

    # -----------------------------------------------------------------------
    # Helper: Deterministic Index Name Generation
    # -----------------------------------------------------------------------

    @classmethod
    def generate_index_name(
        cls,
        table: str,
        columns: List[str],
        existing_indexes: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Generates a safe, deterministic AutoDBA index name within PostgreSQL 63-byte limits."""
        existing_names = {idx["indexname"] for idx in (existing_indexes or [])}
        cols_joined = "_".join(columns)
        base_name = f"idx_autodba_{table}_{cols_joined}"

        # Ensure identifier contains only safe characters
        base_name = re.sub(r"[^a-zA-Z0-9_]", "_", base_name)

        # PostgreSQL NAMEDATALEN limit is 63 chars (64 bytes including null terminator)
        if len(base_name) > 63:
            # Deterministic truncation with hash suffix to prevent collisions
            digest = hashlib.md5(f"{table}_{cols_joined}".encode()).hexdigest()[:8]
            prefix = base_name[:54]
            base_name = f"{prefix}_{digest}"

        # Handle name collision with an existing index of different definition
        candidate = base_name
        suffix_num = 2
        while candidate in existing_names:
            candidate = f"{base_name[:59]}_{suffix_num}"
            suffix_num += 1

        return candidate

    # -----------------------------------------------------------------------
    # Helper: SQL Construction Validation
    # -----------------------------------------------------------------------

    @classmethod
    def _validate_constructed_sql(
        cls,
        sql: str,
        table: str,
        columns: List[str],
        index_name: str,
    ) -> None:
        """Defense-in-depth verification of the constructed SQL statement."""
        # Must strictly start with CREATE INDEX
        if not sql.startswith("CREATE INDEX "):
            raise RemediationBlockedError("Constructed SQL must be a CREATE INDEX statement.")

        # Must contain the validated index name, table, and columns
        expected_sql = f"CREATE INDEX {index_name} ON {table} ({', '.join(columns)});"
        if sql.strip() != expected_sql:
            raise RemediationBlockedError("Constructed SQL deviates from expected deterministic template.")

        # Disallow multiple statements
        if sql.rstrip(";").count(";") > 0:
            raise RemediationBlockedError("Constructed SQL must contain only a single statement.")

        # Disallow comments or forbidden keywords
        if "--" in sql or "/*" in sql:
            raise RemediationBlockedError("Constructed SQL must not contain comments.")

    # -----------------------------------------------------------------------
    # Helper: Post-Remediation Verification
    # -----------------------------------------------------------------------

    @classmethod
    def _verify_created_index(
        cls,
        post_indexes: List[Dict[str, Any]],
        expected_index_name: str,
        expected_columns: List[str],
    ) -> bool:
        """Verifies that the created index exists in post_indexes with matching columns."""
        target_cols_lower = [c.lower() for c in expected_columns]

        for idx in post_indexes:
            if idx["indexname"] == expected_index_name:
                indexdef = idx.get("indexdef", "")
                m = re.search(r"\(([^)]+)\)$", indexdef.strip())
                if m:
                    cols = [c.strip().lower() for c in m.group(1).split(",") if c.strip()]
                    if cols == target_cols_lower:
                        return True
        return False
