"""
Unit tests for SafetyAssessor (Phase 3 Step 1).

Covers tests 1-13 as specified in Phase 3 Step 1:
  1.  Validated low-risk recommendation (eligible_for_approval=True, safety_level=LOW)
  2.  Validated medium-risk recommendation (eligible_for_approval=True, safety_level=MEDIUM)
  3.  Unvalidated recommendation (eligible_for_approval=False)
  4.  Rejected recommendation (eligible_for_approval=False)
  5.  HypoPG not validated (FAILED, eligible_for_approval=False)
  6.  Insufficient planner improvement (FAILED, eligible_for_approval=False)
  7.  Low confidence recommendation (eligible_for_approval=False)
  8.  High-risk recommendation (eligible_for_approval=False)
  9.  SQL preview mismatch (table or columns differ) -> FAILED, eligible_for_approval=False
  10. Injection attempt in SQL preview -> CRITICAL, eligible_for_approval=False
  11. Multiple SQL statements -> rejected (CRITICAL, FAILED)
  12. Contradictory recommendation fields -> fail closed
  13. No SQL preview (fails for physical candidates; passes for non-physical diagnostics)
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.schemas.optimization import (
    OptimizationRecommendation,
    OptimizationType,
    PlanNode,
    RecommendationConfidence,
    RecommendationRisk,
    RecommendationStatus,
    SafetyCheckStatus,
    SafetyLevel,
)
from app.services.safety_assessor import SafetyAssessor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DEFAULT_PREVIEW = object()

def _sample_validated_rec(
    relation: str = "orders",
    columns: list[str] = None,
    risk: RecommendationRisk = RecommendationRisk.LOW,
    confidence: RecommendationConfidence = RecommendationConfidence.HIGH,
    cost_improvement_percent: float = 73.8,
    status: RecommendationStatus = RecommendationStatus.VALIDATED,
    hypopg_validated: bool = True,
    sql_preview: object = _DEFAULT_PREVIEW,
) -> OptimizationRecommendation:
    cols = columns if columns is not None else ["customer_id"]
    col_str = ", ".join(cols)
    if sql_preview is _DEFAULT_PREVIEW:
        preview = f"CREATE INDEX ON {relation} ({col_str});"
    else:
        preview = sql_preview

    return OptimizationRecommendation(
        optimization_type=OptimizationType.MISSING_INDEX,
        title=f"Create index on {relation}({col_str})",
        summary=f"Validated candidate on {relation}({col_str})",
        description="Observed: scan with filter\nCandidate: index\nValidation: HypoPG confirmed",
        relation=relation,
        columns=cols,
        recommended_action=f"CREATE INDEX ON {relation} ({col_str});",
        sql_preview=preview,
        status=status,
        confidence=confidence,
        risk=risk,
        evidence=["PostgreSQL selected Seq Scan", "HypoPG validated 73.8% improvement"],
        hypopg_validated=hypopg_validated,
        original_cost=107.5,
        hypothetical_cost=28.16,
        cost_improvement_percent=cost_improvement_percent,
        tradeoffs=["Storage overhead", "Write overhead"],
        warnings=[],
        requires_human_approval=True,
    )


# ---------------------------------------------------------------------------
# Test 1 – Validated low-risk recommendation
# ---------------------------------------------------------------------------

def test_validated_low_risk_recommendation():
    rec = _sample_validated_rec(risk=RecommendationRisk.LOW)
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is True
    assert assessment.safety_level == SafetyLevel.LOW
    assert assessment.overall_status == SafetyCheckStatus.PASSED
    assert len(assessment.blocking_reasons) == 0
    assert assessment.requires_human_approval is True


# ---------------------------------------------------------------------------
# Test 2 – Validated medium-risk recommendation
# ---------------------------------------------------------------------------

def test_validated_medium_risk_recommendation():
    rec = _sample_validated_rec(
        columns=["customer_id", "status"],
        risk=RecommendationRisk.MEDIUM,
    )
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is True
    assert assessment.safety_level == SafetyLevel.MEDIUM
    assert assessment.overall_status == SafetyCheckStatus.WARNING
    assert len(assessment.blocking_reasons) == 0
    assert len(assessment.warnings) > 0


# ---------------------------------------------------------------------------
# Test 3 – Unvalidated recommendation
# ---------------------------------------------------------------------------

def test_unvalidated_recommendation_ineligible():
    rec = _sample_validated_rec(
        status=RecommendationStatus.UNVALIDATED,
        hypopg_validated=False,
        confidence=RecommendationConfidence.MEDIUM,
    )
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    assert any("VALIDATED" in r for r in assessment.blocking_reasons)


# ---------------------------------------------------------------------------
# Test 4 – Rejected recommendation
# ---------------------------------------------------------------------------

def test_rejected_recommendation_ineligible():
    rec = _sample_validated_rec(
        status=RecommendationStatus.REJECTED,
        hypopg_validated=False,
        sql_preview=None,
    )
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    assert any("VALIDATED" in r for r in assessment.blocking_reasons)


# ---------------------------------------------------------------------------
# Test 5 – HypoPG not validated
# ---------------------------------------------------------------------------

def test_hypopg_not_validated_failed():
    rec = _sample_validated_rec(hypopg_validated=False)
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    hypo_check = next((c for c in assessment.checks if c.check_name == "hypopg_validation"), None)
    assert hypo_check is not None
    assert hypo_check.status == SafetyCheckStatus.FAILED


# ---------------------------------------------------------------------------
# Test 6 – Insufficient planner improvement
# ---------------------------------------------------------------------------

def test_insufficient_planner_improvement():
    rec = _sample_validated_rec(cost_improvement_percent=1.5)  # threshold is 5.0%
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    imp_check = next((c for c in assessment.checks if c.check_name == "planner_improvement"), None)
    assert imp_check is not None
    assert imp_check.status == SafetyCheckStatus.FAILED
    assert any("threshold" in r.lower() for r in assessment.blocking_reasons)


# ---------------------------------------------------------------------------
# Test 7 – Low / Medium confidence recommendations ineligible
# ---------------------------------------------------------------------------

def test_low_confidence_ineligible():
    rec = _sample_validated_rec(confidence=RecommendationConfidence.LOW)
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    conf_check = next((c for c in assessment.checks if c.check_name == "recommendation_confidence"), None)
    assert conf_check is not None
    assert conf_check.status == SafetyCheckStatus.FAILED


def test_medium_confidence_ineligible():
    rec = _sample_validated_rec(confidence=RecommendationConfidence.MEDIUM)
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False


# ---------------------------------------------------------------------------
# Test 8 – High-risk recommendation
# ---------------------------------------------------------------------------

def test_high_risk_recommendation_ineligible():
    rec = _sample_validated_rec(risk=RecommendationRisk.HIGH)
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    assert assessment.safety_level == SafetyLevel.HIGH
    assert any("HIGH" in r for r in assessment.blocking_reasons)


# ---------------------------------------------------------------------------
# Test 9 – SQL preview mismatch
# ---------------------------------------------------------------------------

def test_sql_preview_mismatched_table():
    # Table in recommendation is 'orders', but preview targets 'customers'
    rec = _sample_validated_rec(
        relation="orders",
        sql_preview="CREATE INDEX ON customers (customer_id);",
    )
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    assert assessment.safety_level == SafetyLevel.CRITICAL
    sql_check = next((c for c in assessment.checks if c.check_name == "sql_preview_validation"), None)
    assert sql_check is not None
    assert sql_check.status == SafetyCheckStatus.FAILED


def test_sql_preview_mismatched_columns():
    # Columns in recommendation: ['customer_id'], but preview has 'status'
    rec = _sample_validated_rec(
        relation="orders",
        columns=["customer_id"],
        sql_preview="CREATE INDEX ON orders (status);",
    )
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    sql_check = next((c for c in assessment.checks if c.check_name == "sql_preview_validation"), None)
    assert sql_check is not None
    assert sql_check.status == SafetyCheckStatus.FAILED


# ---------------------------------------------------------------------------
# Test 10 – Injection attempt in SQL preview
# ---------------------------------------------------------------------------

def test_sql_preview_injection_attempt():
    rec = _sample_validated_rec(
        sql_preview="CREATE INDEX ON orders(customer_id); DROP TABLE orders;",
    )
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    assert assessment.safety_level == SafetyLevel.CRITICAL
    sql_check = next((c for c in assessment.checks if c.check_name == "sql_preview_validation"), None)
    assert sql_check is not None
    assert sql_check.status == SafetyCheckStatus.FAILED
    assert sql_check.severity == SafetyLevel.CRITICAL


# ---------------------------------------------------------------------------
# Test 11 – Multiple SQL statements
# ---------------------------------------------------------------------------

def test_multiple_sql_statements_rejected():
    rec = _sample_validated_rec(
        sql_preview="CREATE INDEX ON orders (customer_id); CREATE INDEX ON orders (status);",
    )
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    assert assessment.safety_level == SafetyLevel.CRITICAL


# ---------------------------------------------------------------------------
# Test 12 – Contradictory recommendation fields
# ---------------------------------------------------------------------------

def test_contradictory_recommendation_fields_fail_closed():
    # Marked VALIDATED, but hypothetical_cost > original_cost (cost regression)
    rec = OptimizationRecommendation(
        optimization_type=OptimizationType.MISSING_INDEX,
        title="Inconsistent Rec",
        summary="Inconsistent Rec",
        description="Inconsistent",
        relation="orders",
        columns=["customer_id"],
        recommended_action="CREATE INDEX ON orders (customer_id);",
        sql_preview="CREATE INDEX ON orders (customer_id);",
        status=RecommendationStatus.VALIDATED,
        confidence=RecommendationConfidence.HIGH,
        risk=RecommendationRisk.LOW,
        evidence=[],
        hypopg_validated=True,
        original_cost=100.0,
        hypothetical_cost=150.0,  # Regression!
        cost_improvement_percent=-50.0,
        requires_human_approval=True,
    )
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    consistency_check = next((c for c in assessment.checks if c.check_name == "internal_consistency"), None)
    assert consistency_check is not None
    assert consistency_check.status == SafetyCheckStatus.FAILED


# ---------------------------------------------------------------------------
# Test 13 – No SQL preview handling
# ---------------------------------------------------------------------------

def test_missing_sql_preview_fails_for_physical_index():
    rec = _sample_validated_rec(sql_preview=None)
    assessment = SafetyAssessor.assess(rec)

    assert assessment.eligible_for_approval is False
    sql_check = next((c for c in assessment.checks if c.check_name == "sql_preview_validation"), None)
    assert sql_check is not None
    assert sql_check.status == SafetyCheckStatus.FAILED


def test_no_sql_preview_allowed_for_diagnostic_rec():
    rec = OptimizationRecommendation(
        optimization_type=OptimizationType.EXPENSIVE_SORT,
        title="Investigate Sort",
        summary="Expensive sort",
        description="Sort cost exceeds threshold",
        relation=None,
        columns=[],
        recommended_action="Investigate ORDER BY alignment",
        sql_preview=None,  # Intentionally None for diagnostic
        status=RecommendationStatus.UNVALIDATED,
        confidence=RecommendationConfidence.MEDIUM,
        risk=RecommendationRisk.MEDIUM,
        evidence=[],
        hypopg_validated=False,
        requires_human_approval=True,
    )
    assessment = SafetyAssessor.assess(rec)

    # sql_preview check passes because it's non-physical
    sql_check = next((c for c in assessment.checks if c.check_name == "sql_preview_validation"), None)
    assert sql_check is not None
    assert sql_check.status == SafetyCheckStatus.PASSED

    # But overall ineligible because status is UNVALIDATED and confidence is MEDIUM
    assert assessment.eligible_for_approval is False
