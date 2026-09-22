"""
Safety Assessment Service (Phase 3 Step 1)
===========================================
Deterministic, conservative, fail-closed safety gate between optimization
recommendations and human approval.

Guarantees:
  - Completely deterministic and auditable.
  - Zero database write handles: cannot modify the database or execute DDL.
  - Independent of any LLM or probabilistic reasoning.
  - Fails closed: if any required validation is missing or inconsistent,
    eligibility for approval is blocked.
  - Validates SQL previews with defense-in-depth checks (no multi-statements,
    no comments, no dangerous keywords, relation and column matching).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.core.config import Settings, get_settings
from app.core.logging import log_operation
from app.schemas.optimization import (
    OptimizationRecommendation,
    OptimizationType,
    RecommendationConfidence,
    RecommendationRisk,
    RecommendationStatus,
    SafetyAssessment,
    SafetyCheck,
    SafetyCheckStatus,
    SafetyLevel,
)
from app.services.hypopg_validator import HypoPGValidatorService, InvalidCandidateError


# Forbidden SQL tokens in index preview (defense in depth)
_FORBIDDEN_SQL_KEYWORDS_PATTERN = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|ALTER|UPDATE|INSERT|EXEC|EXECUTE|GRANT|REVOKE|COPY|VACUUM|CALL|DO)\b",
    re.IGNORECASE,
)

# SQL comment patterns
_SQL_COMMENT_PATTERN = re.compile(r"(--|/\*|\*/)")


class SafetyAssessor:
    """Deterministic safety assessor evaluating recommendation eligibility for human approval."""

    @classmethod
    def assess(
        cls,
        recommendation: OptimizationRecommendation,
        settings: Optional[Settings] = None,
    ) -> SafetyAssessment:
        """Performs a comprehensive, fail-closed safety assessment of an optimization recommendation.

        Returns:
            SafetyAssessment containing check outcomes, aggregated safety tier,
            approval eligibility flag, and blocking reasons if any.
        """
        cfg = settings or get_settings()
        checks: List[SafetyCheck] = []
        blocking_reasons: List[str] = []
        assessment_warnings: List[str] = list(recommendation.warnings)

        with log_operation("safety_assessment"):
            # -------------------------------------------------------------------
            # Check 1 — Recommendation Status
            # -------------------------------------------------------------------
            cls._check_recommendation_status(recommendation, checks, blocking_reasons)

            # -------------------------------------------------------------------
            # Check 2 — HypoPG Counterfactual Validation
            # -------------------------------------------------------------------
            cls._check_hypopg_validation(recommendation, checks, blocking_reasons)

            # -------------------------------------------------------------------
            # Check 3 — Planner Cost Improvement Threshold
            # -------------------------------------------------------------------
            cls._check_planner_improvement(recommendation, cfg, checks, blocking_reasons)

            # -------------------------------------------------------------------
            # Check 4 — Recommendation Confidence Tier
            # -------------------------------------------------------------------
            cls._check_confidence(recommendation, checks, blocking_reasons)

            # -------------------------------------------------------------------
            # Check 5 — Risk Tier Evaluation
            # -------------------------------------------------------------------
            cls._check_risk(recommendation, checks, blocking_reasons, assessment_warnings)

            # -------------------------------------------------------------------
            # Check 6 — SQL Preview Defense-in-Depth Validation
            # -------------------------------------------------------------------
            cls._check_sql_preview(recommendation, checks, blocking_reasons)

            # -------------------------------------------------------------------
            # Check 7 — Recommendation Internal Consistency
            # -------------------------------------------------------------------
            cls._check_internal_consistency(recommendation, checks, blocking_reasons)

            # -------------------------------------------------------------------
            # Aggregation & Eligibility Determination
            # -------------------------------------------------------------------
            safety_level = cls._aggregate_safety_level(checks, recommendation.risk)
            overall_status = cls._aggregate_overall_status(checks)

            # Fail-closed eligibility rule:
            # Must have passed/warning overall status, LOW or MEDIUM safety level,
            # and zero blocking reasons.
            is_eligible = (
                overall_status in (SafetyCheckStatus.PASSED, SafetyCheckStatus.WARNING)
                and safety_level in (SafetyLevel.LOW, SafetyLevel.MEDIUM)
                and len(blocking_reasons) == 0
            )

            return SafetyAssessment(
                recommendation=recommendation,
                safety_level=safety_level,
                checks=checks,
                overall_status=overall_status,
                eligible_for_approval=is_eligible,
                requires_human_approval=True,
                blocking_reasons=blocking_reasons,
                warnings=assessment_warnings,
                tradeoffs=list(recommendation.tradeoffs),
            )

    # -----------------------------------------------------------------------
    # Individual Safety Rules
    # -----------------------------------------------------------------------

    @classmethod
    def _check_recommendation_status(
        cls,
        rec: OptimizationRecommendation,
        checks: List[SafetyCheck],
        blocking: List[str],
    ) -> None:
        """Check 1: Only VALIDATED recommendations are eligible for approval."""
        if rec.status == RecommendationStatus.VALIDATED:
            checks.append(
                SafetyCheck(
                    check_name="recommendation_status",
                    status=SafetyCheckStatus.PASSED,
                    severity=SafetyLevel.LOW,
                    message="Recommendation is validated by planner simulation.",
                    evidence={"status": rec.status.value},
                )
            )
        else:
            reason = (
                f"Recommendation status is '{rec.status.value}'. "
                "Only VALIDATED recommendations are eligible for human approval."
            )
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="recommendation_status",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.HIGH,
                    message=reason,
                    evidence={"status": rec.status.value},
                )
            )

    @classmethod
    def _check_hypopg_validation(
        cls,
        rec: OptimizationRecommendation,
        checks: List[SafetyCheck],
        blocking: List[str],
    ) -> None:
        """Check 2: Physical index candidates must have confirmed HypoPG validation."""
        is_index_candidate = (
            rec.optimization_type in (OptimizationType.MISSING_INDEX, OptimizationType.FILTERED_SEQ_SCAN)
            or rec.sql_preview is not None
        )

        if is_index_candidate:
            if rec.hypopg_validated is True:
                checks.append(
                    SafetyCheck(
                        check_name="hypopg_validation",
                        status=SafetyCheckStatus.PASSED,
                        severity=SafetyLevel.LOW,
                        message="HypoPG counterfactual planner validation confirmed.",
                        evidence={"hypopg_validated": True},
                    )
                )
            else:
                reason = "HypoPG counterfactual validation was not confirmed for this index candidate."
                blocking.append(reason)
                checks.append(
                    SafetyCheck(
                        check_name="hypopg_validation",
                        status=SafetyCheckStatus.FAILED,
                        severity=SafetyLevel.HIGH,
                        message=reason,
                        evidence={"hypopg_validated": False},
                    )
                )
        else:
            # Diagnostic non-physical recommendations do not require HypoPG
            checks.append(
                SafetyCheck(
                    check_name="hypopg_validation",
                    status=SafetyCheckStatus.PASSED,
                    severity=SafetyLevel.LOW,
                    message="Non-physical recommendation does not require HypoPG validation.",
                    evidence={"optimization_type": rec.optimization_type.value},
                )
            )

    @classmethod
    def _check_planner_improvement(
        cls,
        rec: OptimizationRecommendation,
        settings: Settings,
        checks: List[SafetyCheck],
        blocking: List[str],
    ) -> None:
        """Check 3: Planner cost improvement must meet the configured threshold."""
        min_thresh = settings.HYPOPG_MIN_COST_IMPROVEMENT_PERCENT
        is_index_candidate = (
            rec.optimization_type in (OptimizationType.MISSING_INDEX, OptimizationType.FILTERED_SEQ_SCAN)
            or rec.sql_preview is not None
        )

        if is_index_candidate:
            improvement = rec.cost_improvement_percent
            if improvement is not None and improvement >= min_thresh:
                checks.append(
                    SafetyCheck(
                        check_name="planner_improvement",
                        status=SafetyCheckStatus.PASSED,
                        severity=SafetyLevel.LOW,
                        message=(
                            f"Planner cost improvement of {improvement:.1f}% "
                            f"satisfies configured threshold ({min_thresh:.1f}%)."
                        ),
                        evidence={
                            "cost_improvement_percent": improvement,
                            "threshold_percent": min_thresh,
                        },
                    )
                )
            else:
                val_str = f"{improvement:.1f}%" if improvement is not None else "None"
                reason = (
                    f"Planner cost improvement ({val_str}) is below the "
                    f"minimum threshold of {min_thresh:.1f}%."
                )
                blocking.append(reason)
                checks.append(
                    SafetyCheck(
                        check_name="planner_improvement",
                        status=SafetyCheckStatus.FAILED,
                        severity=SafetyLevel.HIGH,
                        message=reason,
                        evidence={
                            "cost_improvement_percent": improvement,
                            "threshold_percent": min_thresh,
                        },
                    )
                )
        else:
            checks.append(
                SafetyCheck(
                    check_name="planner_improvement",
                    status=SafetyCheckStatus.PASSED,
                    severity=SafetyLevel.LOW,
                    message="Non-physical diagnostic recommendation does not require planner cost improvement threshold.",
                    evidence={},
                )
            )

    @classmethod
    def _check_confidence(
        cls,
        rec: OptimizationRecommendation,
        checks: List[SafetyCheck],
        blocking: List[str],
    ) -> None:
        """Check 4: Approval eligibility strictly requires HIGH recommendation confidence."""
        if rec.confidence == RecommendationConfidence.HIGH:
            checks.append(
                SafetyCheck(
                    check_name="recommendation_confidence",
                    status=SafetyCheckStatus.PASSED,
                    severity=SafetyLevel.LOW,
                    message="Recommendation confidence is HIGH.",
                    evidence={"confidence": rec.confidence.value},
                )
            )
        else:
            reason = (
                f"Recommendation confidence is '{rec.confidence.value}'. "
                "Only HIGH confidence recommendations are eligible for approval."
            )
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="recommendation_confidence",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.MEDIUM,
                    message=reason,
                    evidence={"confidence": rec.confidence.value},
                )
            )

    @classmethod
    def _check_risk(
        cls,
        rec: OptimizationRecommendation,
        checks: List[SafetyCheck],
        blocking: List[str],
        warnings: List[str],
    ) -> None:
        """Check 5: Evaluates operational risk level."""
        if rec.risk == RecommendationRisk.LOW:
            checks.append(
                SafetyCheck(
                    check_name="risk_classification",
                    status=SafetyCheckStatus.PASSED,
                    severity=SafetyLevel.LOW,
                    message="Operational risk is LOW (single-column B-tree index).",
                    evidence={"risk": rec.risk.value},
                )
            )
        elif rec.risk == RecommendationRisk.MEDIUM:
            warn_msg = (
                "Operational risk is MEDIUM (multi-column or non-trivial overhead). "
                "Review trade-offs prior to approval."
            )
            warnings.append(warn_msg)
            checks.append(
                SafetyCheck(
                    check_name="risk_classification",
                    status=SafetyCheckStatus.WARNING,
                    severity=SafetyLevel.MEDIUM,
                    message=warn_msg,
                    evidence={"risk": rec.risk.value},
                )
            )
        elif rec.risk == RecommendationRisk.HIGH:
            reason = "Operational risk is HIGH. Ineligible for remediation by default."
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="risk_classification",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.HIGH,
                    message=reason,
                    evidence={"risk": rec.risk.value},
                )
            )
        else:
            reason = f"Operational risk is '{rec.risk.value}'. Blocked from remediation."
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="risk_classification",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.CRITICAL,
                    message=reason,
                    evidence={"risk": rec.risk.value},
                )
            )

    @classmethod
    def _check_sql_preview(
        cls,
        rec: OptimizationRecommendation,
        checks: List[SafetyCheck],
        blocking: List[str],
    ) -> None:
        """Check 6: Defense-in-depth validation of SQL preview syntax, safety, and alignment."""
        is_index_rec = rec.optimization_type in (
            OptimizationType.MISSING_INDEX, OptimizationType.FILTERED_SEQ_SCAN
        )

        # Case: Physical index recommendation has NO SQL preview
        if is_index_rec and rec.status == RecommendationStatus.VALIDATED and not rec.sql_preview:
            reason = "Physical index recommendation is missing required sql_preview."
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="sql_preview_validation",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.HIGH,
                    message=reason,
                    evidence={"sql_preview": None},
                )
            )
            return

        # Case: Non-physical recommendation without SQL preview (allowed)
        if not rec.sql_preview:
            checks.append(
                SafetyCheck(
                    check_name="sql_preview_validation",
                    status=SafetyCheckStatus.PASSED,
                    severity=SafetyLevel.LOW,
                    message="No SQL preview required for non-physical recommendation.",
                    evidence={},
                )
            )
            return

        raw_sql = rec.sql_preview.strip()

        # 1. SQL comments guard (-- or /* */)
        if _SQL_COMMENT_PATTERN.search(raw_sql):
            reason = "SQL preview contains disallowed SQL comments."
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="sql_preview_validation",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.CRITICAL,
                    message=reason,
                    evidence={"sql_preview": raw_sql},
                )
            )
            return

        # 2. Multi-statement guard (semicolon inside query)
        body_without_trailing_semi = raw_sql.rstrip(";")
        if ";" in body_without_trailing_semi:
            reason = "SQL preview contains multiple statements."
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="sql_preview_validation",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.CRITICAL,
                    message=reason,
                    evidence={"sql_preview": raw_sql},
                )
            )
            return

        # 3. Dangerous / destructive keyword guard
        dangerous_match = _FORBIDDEN_SQL_KEYWORDS_PATTERN.search(raw_sql)
        if dangerous_match:
            kw = dangerous_match.group(1).upper()
            reason = f"SQL preview contains dangerous SQL keyword '{kw}'."
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="sql_preview_validation",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.CRITICAL,
                    message=reason,
                    evidence={"sql_preview": raw_sql, "forbidden_keyword": kw},
                )
            )
            return

        # 4. Valid CREATE INDEX syntax check
        create_index_pattern = re.compile(
            r"^CREATE\s+INDEX\s+ON\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+USING\s+\w+)?\s*\(([^)]+)\);?$",
            re.IGNORECASE,
        )
        m = create_index_pattern.match(raw_sql)
        if not m:
            reason = "SQL preview does not match valid CREATE INDEX syntax."
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="sql_preview_validation",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.HIGH,
                    message=reason,
                    evidence={"sql_preview": raw_sql},
                )
            )
            return

        parsed_table = m.group(1).strip()
        parsed_cols = [c.strip() for c in m.group(2).split(",") if c.strip()]

        # 5. Consistency check: preview table vs. recommendation.relation
        rec_rel = (rec.relation or "").strip()
        if parsed_table.lower() != rec_rel.lower():
            reason = (
                f"SQL preview target table '{parsed_table}' does not match "
                f"recommendation relation '{rec_rel}'."
            )
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="sql_preview_validation",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.CRITICAL,
                    message=reason,
                    evidence={
                        "preview_table": parsed_table,
                        "recommendation_relation": rec_rel,
                    },
                )
            )
            return

        # 6. Consistency check: preview columns vs. recommendation.columns
        rec_cols = [c.strip() for c in rec.columns if c.strip()]
        if [c.lower() for c in parsed_cols] != [c.lower() for c in rec_cols]:
            reason = (
                f"SQL preview columns {parsed_cols} do not match "
                f"recommendation columns {rec_cols}."
            )
            blocking.append(reason)
            checks.append(
                SafetyCheck(
                    check_name="sql_preview_validation",
                    status=SafetyCheckStatus.FAILED,
                    severity=SafetyLevel.HIGH,
                    message=reason,
                    evidence={
                        "preview_columns": parsed_cols,
                        "recommendation_columns": rec_cols,
                    },
                )
            )
            return

        checks.append(
            SafetyCheck(
                check_name="sql_preview_validation",
                status=SafetyCheckStatus.PASSED,
                severity=SafetyLevel.LOW,
                message="SQL preview passed syntax, safety, and alignment checks.",
                evidence={"sql_preview": raw_sql},
            )
        )

    @classmethod
    def _check_internal_consistency(
        cls,
        rec: OptimizationRecommendation,
        checks: List[SafetyCheck],
        blocking: List[str],
    ) -> None:
        """Check 7: Verifies that recommendation fields are free of internal contradictions."""
        # Rule: VALIDATED status must have hypopg_validated=True and valid cost metrics
        if rec.status == RecommendationStatus.VALIDATED:
            contradictions: List[str] = []
            if rec.hypopg_validated is not True:
                contradictions.append("status is VALIDATED but hypopg_validated is False")
            if rec.original_cost is None:
                contradictions.append("status is VALIDATED but original_cost is missing")
            if rec.hypothetical_cost is None:
                contradictions.append("status is VALIDATED but hypothetical_cost is missing")
            if (
                rec.original_cost is not None
                and rec.hypothetical_cost is not None
                and rec.original_cost < rec.hypothetical_cost
            ):
                contradictions.append("status is VALIDATED but hypothetical_cost exceeds original_cost (regression)")

            if contradictions:
                reason = f"Internal contradiction detected: {'; '.join(contradictions)}."
                blocking.append(reason)
                checks.append(
                    SafetyCheck(
                        check_name="internal_consistency",
                        status=SafetyCheckStatus.FAILED,
                        severity=SafetyLevel.HIGH,
                        message=reason,
                        evidence={"contradictions": contradictions},
                    )
                )
                return

        checks.append(
            SafetyCheck(
                check_name="internal_consistency",
                status=SafetyCheckStatus.PASSED,
                severity=SafetyLevel.LOW,
                message="Recommendation fields are internally consistent.",
                evidence={},
            )
        )

    # -----------------------------------------------------------------------
    # Aggregators
    # -----------------------------------------------------------------------

    @classmethod
    def _aggregate_safety_level(
        cls,
        checks: List[SafetyCheck],
        rec_risk: RecommendationRisk,
    ) -> SafetyLevel:
        """Aggregates check severities and recommendation risk into an overall safety level."""
        # Any failed CRITICAL check elevates safety level to CRITICAL immediately
        for c in checks:
            if c.status == SafetyCheckStatus.FAILED and c.severity == SafetyLevel.CRITICAL:
                return SafetyLevel.CRITICAL

        # Any failed check or HIGH risk -> HIGH
        if rec_risk == RecommendationRisk.HIGH:
            return SafetyLevel.HIGH
        for c in checks:
            if c.status == SafetyCheckStatus.FAILED:
                return SafetyLevel.HIGH

        # Any WARNING or MEDIUM risk -> MEDIUM
        if rec_risk == RecommendationRisk.MEDIUM:
            return SafetyLevel.MEDIUM
        for c in checks:
            if c.status == SafetyCheckStatus.WARNING:
                return SafetyLevel.MEDIUM

        return SafetyLevel.LOW

    @classmethod
    def _aggregate_overall_status(cls, checks: List[SafetyCheck]) -> SafetyCheckStatus:
        """Aggregates individual check statuses into an overall status."""
        has_failed = any(c.status == SafetyCheckStatus.FAILED for c in checks)
        if has_failed:
            return SafetyCheckStatus.FAILED

        has_warning = any(c.status == SafetyCheckStatus.WARNING for c in checks)
        if has_warning:
            return SafetyCheckStatus.WARNING

        return SafetyCheckStatus.PASSED
