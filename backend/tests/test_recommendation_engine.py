"""
Unit and integration tests for RecommendationEngine (Phase 2 Step 3).

Test catalogue (15 required + extras):
  1.  Validated missing-index recommendation (HypoPG VALIDATED)
  2.  No-improvement candidate (HypoPG NO_IMPROVEMENT) -> REJECTED
  3.  HypoPG cost regression -> REJECTED + HIGH risk
  4.  No HypoPG result -> UNVALIDATED, confidence != HIGH
  5.  SQL preview generation (orders/customer_id)
  6.  SQL injection in candidate column -> rejected
  7.  No hallucinated columns when no filter columns extractable
  8.  EXPENSIVE_SORT -> diagnostic, no invented ORDER BY columns
  9.  EXPENSIVE_NESTED_LOOP -> evidence-based diagnostic
  10. LARGE_ROW_ESTIMATE -> statistics/cardinality investigation
  11. Risk classification LOW / MEDIUM / HIGH cases
  12. Confidence classification LOW / MEDIUM / HIGH cases
  13. Evidence chain contains factual data from finding and validation
  14. Determinism: identical inputs produce identical outputs
  15. Human approval required on all database-modifying recommendations
  16. Multi-column index -> MEDIUM risk even when validated
  17. extract_candidate_columns from simple filter predicate
  18. extract_candidate_columns returns empty list for no-column filter
  19. HypoPG INVALID_CANDIDATE verdict -> REJECTED
  20. Real PostgreSQL integration test (markers: integration)
"""

from __future__ import annotations

import pytest

from app.schemas.optimization import (
    BottleneckFinding,
    BottleneckType,
    Confidence,
    HypoPGValidationResult,
    IndexMethod,
    PlanComparison,
    PlanNode,
    RecommendationConfidence,
    RecommendationRisk,
    RecommendationStatus,
    Severity,
    ValidationVerdict,
)
from app.services.hypopg_validator import InvalidCandidateError
from app.services.recommendation_engine import RecommendationEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seq_scan_finding(
    relation: str = "orders",
    filter_expr: str = "(customer_id = 42)",
    cost: float = 107.5,
    rows: int = 5000,
    severity: Severity = Severity.MEDIUM,
    confidence: Confidence = Confidence.HIGH,
    finding_type: BottleneckType = BottleneckType.MISSING_INDEX,
) -> BottleneckFinding:
    return BottleneckFinding(
        finding_type=finding_type,
        severity=severity,
        confidence=confidence,
        title=f"Potential missing-index candidate on \"{relation}\"",
        description="Sequential scan with filter detected.",
        relation=relation,
        evidence={
            "node_type": "Seq Scan",
            "relation": relation,
            "filter": filter_expr,
            "estimated_rows": rows,
            "total_cost": cost,
        },
        estimated_impact="Candidate for review.",
    )


def _plan_comparison(
    orig: float = 107.5,
    hypo: float = 28.16,
) -> PlanComparison:
    diff = orig - hypo
    pct = (diff / orig) * 100
    return PlanComparison(
        original_cost=orig,
        hypothetical_cost=hypo,
        cost_difference=diff,
        cost_improvement_percent=pct,
        original_root_node_type="Seq Scan",
        hypothetical_root_node_type="Bitmap Heap Scan",
        original_scan_type="Seq Scan",
        hypothetical_scan_type="Bitmap Heap Scan",
        plan_changed=True,
        plan_change_summary=(
            "Seq Scan on orders -> Bitmap Heap Scan on orders"
        ),
    )


def _orig_plan() -> PlanNode:
    return PlanNode(
        node_type="Seq Scan",
        relation_name="orders",
        startup_cost=0.0,
        total_cost=107.5,
        plan_rows=5000,
        filter="(customer_id = 42)",
    )


def _hypo_plan() -> PlanNode:
    return PlanNode(
        node_type="Bitmap Heap Scan",
        relation_name="orders",
        startup_cost=4.58,
        total_cost=28.16,
        plan_rows=1,
    )


def _validated_result(
    orig: float = 107.5,
    hypo: float = 28.16,
) -> HypoPGValidationResult:
    return HypoPGValidationResult(
        verdict=ValidationVerdict.VALIDATED,
        candidate_index="CREATE INDEX ON orders (customer_id)",
        hypothetical_index_name="<13630>btree_orders_customer_id",
        hypothetical_index_oid=13630,
        original_query="SELECT * FROM orders WHERE customer_id = 42",
        comparison=_plan_comparison(orig, hypo),
        original_plan=_orig_plan(),
        hypothetical_plan=_hypo_plan(),
        evidence={
            "original_cost": orig,
            "hypothetical_cost": hypo,
            "cost_improvement_percent": ((orig - hypo) / orig) * 100,
        },
    )


def _no_improvement_result() -> HypoPGValidationResult:
    comp = _plan_comparison(100.0, 99.5)
    return HypoPGValidationResult(
        verdict=ValidationVerdict.NO_IMPROVEMENT,
        candidate_index="CREATE INDEX ON orders (customer_id)",
        original_query="SELECT * FROM orders WHERE customer_id = 42",
        comparison=comp,
        original_plan=_orig_plan(),
        hypothetical_plan=_orig_plan(),
        evidence={"cost_improvement_percent": comp.cost_improvement_percent},
    )


def _regression_result() -> HypoPGValidationResult:
    comp = _plan_comparison(100.0, 120.0)
    return HypoPGValidationResult(
        verdict=ValidationVerdict.REGRESSION,
        candidate_index="CREATE INDEX ON orders (customer_id)",
        original_query="SELECT * FROM orders WHERE customer_id = 42",
        comparison=comp,
        original_plan=_orig_plan(),
        hypothetical_plan=_orig_plan(),
        evidence={"cost_improvement_percent": comp.cost_improvement_percent},
    )


def _invalid_candidate_result() -> HypoPGValidationResult:
    return HypoPGValidationResult(
        verdict=ValidationVerdict.INVALID_CANDIDATE,
        candidate_index="INVALID SQL",
        original_query="SELECT 1",
        error_message="Candidate index definition is invalid.",
        evidence={},
    )


# ---------------------------------------------------------------------------
# Test 1 – Validated missing-index recommendation
# ---------------------------------------------------------------------------

def test_validated_missing_index():
    finding = _seq_scan_finding()
    validation = _validated_result()

    rec = RecommendationEngine.recommend(finding, validation)

    assert rec.status == RecommendationStatus.VALIDATED
    assert rec.confidence == RecommendationConfidence.HIGH
    assert rec.hypopg_validated is True
    assert rec.requires_human_approval is True
    assert rec.sql_preview is not None
    assert "orders" in rec.sql_preview.lower()
    assert "customer_id" in rec.sql_preview.lower()
    assert rec.original_cost is not None
    assert rec.hypothetical_cost is not None
    assert rec.cost_improvement_percent is not None
    assert rec.cost_improvement_percent > 0


# ---------------------------------------------------------------------------
# Test 2 – No-improvement candidate -> REJECTED
# ---------------------------------------------------------------------------

def test_no_improvement_rejected():
    finding = _seq_scan_finding(cost=100.0)
    validation = _no_improvement_result()

    rec = RecommendationEngine.recommend(finding, validation)

    assert rec.status == RecommendationStatus.REJECTED
    assert rec.hypopg_validated is False
    assert rec.sql_preview is None
    assert rec.requires_human_approval is True
    # description must explain absence of benefit
    assert "no" in rec.description.lower() or "not" in rec.description.lower()


# ---------------------------------------------------------------------------
# Test 3 – HypoPG regression -> REJECTED + HIGH risk
# ---------------------------------------------------------------------------

def test_regression_rejected_high_risk():
    finding = _seq_scan_finding(cost=100.0)
    validation = _regression_result()

    rec = RecommendationEngine.recommend(finding, validation)

    assert rec.status == RecommendationStatus.REJECTED
    assert rec.risk == RecommendationRisk.HIGH
    assert rec.hypopg_validated is False
    assert rec.requires_human_approval is True


# ---------------------------------------------------------------------------
# Test 4 – No HypoPG result -> UNVALIDATED, confidence != HIGH
# ---------------------------------------------------------------------------

def test_no_hypopg_unvalidated():
    finding = _seq_scan_finding()

    rec = RecommendationEngine.recommend(finding, None)

    assert rec.status == RecommendationStatus.UNVALIDATED
    assert rec.confidence != RecommendationConfidence.HIGH
    assert rec.hypopg_validated is False
    assert rec.requires_human_approval is True


# ---------------------------------------------------------------------------
# Test 5 – SQL preview generation
# ---------------------------------------------------------------------------

def test_sql_preview_generation():
    finding = _seq_scan_finding()
    validation = _validated_result()

    rec = RecommendationEngine.recommend(finding, validation)

    assert rec.sql_preview is not None
    # Must look like a valid CREATE INDEX statement
    assert rec.sql_preview.upper().startswith("CREATE INDEX")
    assert "orders" in rec.sql_preview
    assert "customer_id" in rec.sql_preview
    # Must end with semicolon
    assert rec.sql_preview.rstrip().endswith(";")


def test_sql_preview_not_executed(monkeypatch):
    """Verify the engine never calls hypopg_create_index or executes SQL."""
    executed: list = []

    # Patch HypoPGValidatorService.validate_candidate to track calls
    import app.services.hypopg_validator as hv
    original = hv.HypoPGValidatorService.validate_candidate

    def _never_call(*args, **kwargs):
        executed.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(hv.HypoPGValidatorService, "validate_candidate", _never_call)

    finding = _seq_scan_finding()
    # The recommendation engine itself must not call validate_candidate
    RecommendationEngine.recommend(finding, None)

    assert len(executed) == 0, "RecommendationEngine must not call HypoPGValidatorService internally."


# ---------------------------------------------------------------------------
# Test 6 – SQL injection in candidate column
# ---------------------------------------------------------------------------

def test_sql_injection_rejected():
    """Injection safety tests for the recommendation engine.

    Security guarantees:
      1. Raw injection strings passed to validate_identifier MUST be rejected.
      2. When candidate_index contains injection (semicolons etc.), the engine's regex
         fails to parse it and falls back to safe filter-extracted columns.
         The resulting sql_preview (if any) MUST NOT contain injection tokens.
      3. Direct injection into columns/table via build_sql_preview is rejected.
    """
    # Guard 1: raw injection string rejected by validate_identifier
    with pytest.raises(InvalidCandidateError):
        from app.services.hypopg_validator import HypoPGValidatorService
        HypoPGValidatorService.validate_identifier(
            "customer_id); DROP TABLE orders; --", "column name"
        )

    # Guard 2: build_sql_preview rejects injection in table name
    with pytest.raises(InvalidCandidateError):
        RecommendationEngine.build_sql_preview(
            "orders; DROP TABLE orders;", ["customer_id"]
        )

    # Guard 3: build_sql_preview rejects injection in column name
    with pytest.raises(InvalidCandidateError):
        RecommendationEngine.build_sql_preview(
            "orders", ["customer_id); DROP TABLE orders; --"]
        )

    # Guard 4: When candidate_index contains injection tokens, the regex fails to
    # cleanly parse it (semicolons break the column group). The engine falls back
    # to safe filter-predicate extraction. The resulting recommendation's sql_preview
    # must never contain injection tokens.
    finding = BottleneckFinding(
        finding_type=BottleneckType.MISSING_INDEX,
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        title="Injection test",
        description="Injection test.",
        relation="orders",
        evidence={
            "node_type": "Seq Scan",
            "relation": "orders",
            "filter": "(customer_id = 42)",
            "estimated_rows": 5000,
            "total_cost": 107.5,
        },
        estimated_impact="High",
    )
    validation = HypoPGValidationResult(
        verdict=ValidationVerdict.VALIDATED,
        candidate_index="CREATE INDEX ON orders (customer_id); DROP TABLE orders; --",
        original_query="SELECT * FROM orders WHERE customer_id = 42",
        evidence={},
    )
    rec = RecommendationEngine.recommend(finding, validation)

    # sql_preview must never contain injection tokens
    if rec.sql_preview is not None:
        preview_upper = rec.sql_preview.upper()
        assert "DROP" not in preview_upper
        assert "TABLE" not in preview_upper or "CREATE INDEX" in preview_upper
        assert "--" not in rec.sql_preview
        # Must be a valid CREATE INDEX only
        assert rec.sql_preview.upper().startswith("CREATE INDEX")
        # Only one statement (no semicolons except trailing)
        assert rec.sql_preview.count(";") <= 1
        assert rec.sql_preview.rstrip().endswith(";")

    # Regardless of status, human approval is always required
    assert rec.requires_human_approval is True


# ---------------------------------------------------------------------------
# Test 7 – No hallucinated columns (no filter -> no columns)
# ---------------------------------------------------------------------------

def test_no_hallucinated_columns():
    """Engine must not invent columns when filter evidence is absent."""
    finding = BottleneckFinding(
        finding_type=BottleneckType.FILTERED_SEQ_SCAN,
        severity=Severity.LOW,
        confidence=Confidence.LOW,
        title="Full scan",
        description="Large full-table sequential scan.",
        relation="orders",
        evidence={
            "node_type": "Seq Scan",
            "relation": "orders",
            "estimated_rows": 50000,
            "total_cost": 500.0,
            # NO filter key -> no predicates to parse
        },
        estimated_impact="Low",
    )

    rec = RecommendationEngine.recommend(finding, None)

    assert rec.columns == []
    assert rec.sql_preview is None or rec.columns == []


# ---------------------------------------------------------------------------
# Test 8 – EXPENSIVE_SORT: diagnostic without invented columns
# ---------------------------------------------------------------------------

def test_expensive_sort_no_invented_columns():
    finding = BottleneckFinding(
        finding_type=BottleneckType.EXPENSIVE_SORT,
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        title="Expensive Sort",
        description="Sort exceeds threshold.",
        relation=None,
        evidence={
            "node_type": "Sort",
            "total_cost": 500.0,
            "estimated_rows": 10000,
            "sort_cost_threshold": 100.0,
        },
        estimated_impact="High",
    )

    rec = RecommendationEngine.recommend(finding, None)

    assert rec.optimization_type.value == "expensive_sort"
    assert rec.columns == []
    assert rec.sql_preview is None
    assert rec.status == RecommendationStatus.UNVALIDATED
    assert rec.requires_human_approval is True
    # Explanation should reference sort/ORDER BY
    assert "sort" in rec.recommended_action.lower() or "order" in rec.recommended_action.lower()


# ---------------------------------------------------------------------------
# Test 9 – EXPENSIVE_NESTED_LOOP: evidence-based diagnostic
# ---------------------------------------------------------------------------

def test_expensive_nested_loop_evidence_based():
    finding = BottleneckFinding(
        finding_type=BottleneckType.EXPENSIVE_NESTED_LOOP,
        severity=Severity.HIGH,
        confidence=Confidence.MEDIUM,
        title="Expensive Nested Loop",
        description="Nested loop exceeds threshold.",
        relation=None,
        evidence={
            "node_type": "Nested Loop",
            "total_cost": 2500.0,
            "estimated_rows": 50000,
            "nested_loop_cost_threshold": 500.0,
        },
        estimated_impact="High",
    )

    rec = RecommendationEngine.recommend(finding, None)

    assert rec.optimization_type.value == "expensive_nested_loop"
    assert rec.columns == []
    assert rec.sql_preview is None
    assert rec.requires_human_approval is True
    assert len(rec.evidence) > 0
    # Recommendation should reference join condition investigation
    assert "join" in rec.recommended_action.lower() or "inner" in rec.recommended_action.lower()


# ---------------------------------------------------------------------------
# Test 10 – LARGE_ROW_ESTIMATE: statistics/cardinality investigation
# ---------------------------------------------------------------------------

def test_large_row_estimate_stats_recommendation():
    finding = BottleneckFinding(
        finding_type=BottleneckType.LARGE_ROW_ESTIMATE,
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        title="Large row estimate",
        description="Very large row estimate detected.",
        relation="products",
        evidence={
            "node_type": "Seq Scan",
            "estimated_rows": 1000000,
            "total_cost": 9999.0,
        },
        estimated_impact="Medium",
    )

    rec = RecommendationEngine.recommend(finding, None)

    assert rec.optimization_type.value == "large_row_estimate"
    assert rec.columns == []
    # Must suggest statistics investigation
    action_lower = rec.recommended_action.lower()
    assert "statistic" in action_lower or "analyze" in action_lower or "cardinality" in action_lower
    assert rec.requires_human_approval is True


# ---------------------------------------------------------------------------
# Test 11 – Risk classification
# ---------------------------------------------------------------------------

def test_risk_low_single_column_validated():
    finding = _seq_scan_finding()
    validation = _validated_result()
    rec = RecommendationEngine.recommend(finding, validation)
    assert rec.risk == RecommendationRisk.LOW


def test_risk_medium_multi_column_validated():
    finding = BottleneckFinding(
        finding_type=BottleneckType.MISSING_INDEX,
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        title="Multi-column candidate",
        description="Multi-column index candidate.",
        relation="orders",
        evidence={
            "node_type": "Seq Scan",
            "relation": "orders",
            "filter": "(customer_id = 42)",
            "estimated_rows": 5000,
            "total_cost": 107.5,
        },
        estimated_impact="High",
    )
    # Provide validation with multi-column candidate
    validation = HypoPGValidationResult(
        verdict=ValidationVerdict.VALIDATED,
        candidate_index="CREATE INDEX ON orders (customer_id, status)",
        hypothetical_index_name="<99999>btree_orders_multi",
        hypothetical_index_oid=99999,
        original_query="SELECT * FROM orders WHERE customer_id = 42",
        comparison=_plan_comparison(107.5, 28.16),
        original_plan=_orig_plan(),
        hypothetical_plan=_hypo_plan(),
        evidence={"cost_improvement_percent": 73.8},
    )
    rec = RecommendationEngine.recommend(finding, validation)
    assert rec.status == RecommendationStatus.VALIDATED
    assert rec.risk == RecommendationRisk.MEDIUM  # multi-column


def test_risk_high_unvalidated():
    finding = _seq_scan_finding()
    rec = RecommendationEngine.recommend(finding, None)
    assert rec.risk == RecommendationRisk.HIGH  # unvalidated


def test_risk_high_regression():
    finding = _seq_scan_finding(cost=100.0)
    rec = RecommendationEngine.recommend(finding, _regression_result())
    assert rec.risk == RecommendationRisk.HIGH


# ---------------------------------------------------------------------------
# Test 12 – Confidence classification
# ---------------------------------------------------------------------------

def test_confidence_high_only_when_validated():
    finding = _seq_scan_finding()
    validation = _validated_result()
    rec = RecommendationEngine.recommend(finding, validation)
    assert rec.confidence == RecommendationConfidence.HIGH


def test_confidence_not_high_without_validation():
    finding = _seq_scan_finding()
    rec = RecommendationEngine.recommend(finding, None)
    assert rec.confidence != RecommendationConfidence.HIGH


def test_confidence_medium_no_improvement():
    finding = _seq_scan_finding(cost=100.0)
    rec = RecommendationEngine.recommend(finding, _no_improvement_result())
    assert rec.confidence == RecommendationConfidence.MEDIUM


def test_confidence_high_regression():
    """Regression means HIGH confidence in the REJECTION decision."""
    finding = _seq_scan_finding(cost=100.0)
    rec = RecommendationEngine.recommend(finding, _regression_result())
    assert rec.confidence == RecommendationConfidence.HIGH


# ---------------------------------------------------------------------------
# Test 13 – Evidence chain contains factual data
# ---------------------------------------------------------------------------

def test_evidence_chain_from_finding_and_validation():
    finding = _seq_scan_finding()
    validation = _validated_result()

    rec = RecommendationEngine.recommend(finding, validation)

    evidence_text = " ".join(rec.evidence).lower()
    # Must reference scan type
    assert "seq scan" in evidence_text
    # Must reference filter
    assert "customer_id" in evidence_text
    # Must reference cost
    assert "107" in evidence_text
    # Must reference HypoPG simulation result
    assert any("hypopg" in e.lower() or "simulated" in e.lower() for e in rec.evidence)
    # Must reference cost improvement
    assert any("%" in e or "improvement" in e.lower() for e in rec.evidence)


def test_evidence_chain_no_hallucination_without_validation():
    finding = _seq_scan_finding()
    rec = RecommendationEngine.recommend(finding, None)

    evidence_text = " ".join(rec.evidence).lower()
    # Must NOT claim HypoPG was performed
    assert "validated" not in evidence_text or "not" in evidence_text or "has not" in evidence_text


# ---------------------------------------------------------------------------
# Test 14 – Determinism
# ---------------------------------------------------------------------------

def test_determinism_identical_inputs():
    finding = _seq_scan_finding()
    validation = _validated_result()

    rec1 = RecommendationEngine.recommend(finding, validation)
    rec2 = RecommendationEngine.recommend(finding, validation)

    assert rec1.model_dump() == rec2.model_dump()


def test_determinism_no_validation():
    finding = _seq_scan_finding()
    rec1 = RecommendationEngine.recommend(finding, None)
    rec2 = RecommendationEngine.recommend(finding, None)

    assert rec1.model_dump() == rec2.model_dump()


# ---------------------------------------------------------------------------
# Test 15 – Human approval required on all recommendations
# ---------------------------------------------------------------------------

def test_human_approval_always_true_validated():
    rec = RecommendationEngine.recommend(_seq_scan_finding(), _validated_result())
    assert rec.requires_human_approval is True


def test_human_approval_always_true_rejected():
    rec = RecommendationEngine.recommend(_seq_scan_finding(), _no_improvement_result())
    assert rec.requires_human_approval is True


def test_human_approval_always_true_unvalidated():
    rec = RecommendationEngine.recommend(_seq_scan_finding(), None)
    assert rec.requires_human_approval is True


def test_human_approval_always_true_regression():
    rec = RecommendationEngine.recommend(_seq_scan_finding(cost=100.0), _regression_result())
    assert rec.requires_human_approval is True


def test_human_approval_always_true_sort():
    finding = BottleneckFinding(
        finding_type=BottleneckType.EXPENSIVE_SORT,
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        title="Sort",
        description="Expensive sort.",
        relation=None,
        evidence={"total_cost": 500.0, "estimated_rows": 1000, "sort_cost_threshold": 100.0},
        estimated_impact="High",
    )
    rec = RecommendationEngine.recommend(finding, None)
    assert rec.requires_human_approval is True


# ---------------------------------------------------------------------------
# Test 16 – Multi-column index -> MEDIUM risk
# ---------------------------------------------------------------------------

def test_multi_column_medium_risk():
    validation = HypoPGValidationResult(
        verdict=ValidationVerdict.VALIDATED,
        candidate_index="CREATE INDEX ON orders (customer_id, status)",
        original_query="SELECT * FROM orders WHERE customer_id = 42",
        comparison=_plan_comparison(107.5, 28.0),
        original_plan=_orig_plan(),
        hypothetical_plan=_hypo_plan(),
        evidence={"cost_improvement_percent": 73.9},
    )
    rec = RecommendationEngine.recommend(_seq_scan_finding(), validation)
    assert rec.risk == RecommendationRisk.MEDIUM
    assert len(rec.columns) == 2


# ---------------------------------------------------------------------------
# Test 17 – extract_candidate_columns from simple filter
# ---------------------------------------------------------------------------

def test_extract_columns_from_simple_filter():
    finding = _seq_scan_finding(filter_expr="(customer_id = 42)")
    cols = RecommendationEngine.extract_candidate_columns(finding)
    assert "customer_id" in cols


def test_extract_columns_single_evidence_column():
    finding = BottleneckFinding(
        finding_type=BottleneckType.MISSING_INDEX,
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        title="x",
        description="x",
        relation="orders",
        evidence={"column": "status"},
        estimated_impact="Low",
    )
    cols = RecommendationEngine.extract_candidate_columns(finding)
    assert cols == ["status"]


# ---------------------------------------------------------------------------
# Test 18 – extract_candidate_columns empty when no filter columns
# ---------------------------------------------------------------------------

def test_extract_columns_no_filter_returns_empty():
    finding = BottleneckFinding(
        finding_type=BottleneckType.FILTERED_SEQ_SCAN,
        severity=Severity.LOW,
        confidence=Confidence.LOW,
        title="Full scan",
        description="Large full scan.",
        relation="orders",
        evidence={"estimated_rows": 50000, "total_cost": 600.0},
        estimated_impact="Low",
    )
    cols = RecommendationEngine.extract_candidate_columns(finding)
    assert cols == []


def test_extract_columns_ignores_function_calls():
    """Tokens followed by ( are function calls, not column names."""
    finding = BottleneckFinding(
        finding_type=BottleneckType.MISSING_INDEX,
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        title="x",
        description="x",
        relation="orders",
        evidence={"filter": "(random() < 0.5)"},
        estimated_impact="Low",
    )
    cols = RecommendationEngine.extract_candidate_columns(finding)
    assert "random" not in cols


# ---------------------------------------------------------------------------
# Test 19 – HypoPG INVALID_CANDIDATE verdict -> REJECTED
# ---------------------------------------------------------------------------

def test_invalid_candidate_verdict_rejected():
    finding = _seq_scan_finding()
    validation = _invalid_candidate_result()

    rec = RecommendationEngine.recommend(finding, validation)

    assert rec.status == RecommendationStatus.REJECTED
    assert rec.hypopg_validated is False
    assert rec.requires_human_approval is True


# ---------------------------------------------------------------------------
# Test 20 – build_sql_preview safety
# ---------------------------------------------------------------------------

def test_build_sql_preview_valid():
    preview = RecommendationEngine.build_sql_preview("orders", ["customer_id"])
    assert preview == "CREATE INDEX ON orders (customer_id);"


def test_build_sql_preview_multi_column():
    preview = RecommendationEngine.build_sql_preview("orders", ["customer_id", "status"])
    assert preview == "CREATE INDEX ON orders (customer_id, status);"


def test_build_sql_preview_rejects_injection():
    with pytest.raises(InvalidCandidateError):
        RecommendationEngine.build_sql_preview("orders; DROP TABLE orders;", ["customer_id"])

    with pytest.raises(InvalidCandidateError):
        RecommendationEngine.build_sql_preview("orders", ["customer_id); DROP TABLE orders; --"])


def test_build_sql_preview_requires_columns():
    with pytest.raises(InvalidCandidateError):
        RecommendationEngine.build_sql_preview("orders", [])


# ---------------------------------------------------------------------------
# Test 21 – recommend_all convenience method
# ---------------------------------------------------------------------------

def test_recommend_all():
    findings = [_seq_scan_finding(), _seq_scan_finding(relation="customers", cost=200.0)]
    recs = RecommendationEngine.recommend_all(findings)
    assert len(recs) == 2
    for rec in recs:
        assert rec.requires_human_approval is True


# ---------------------------------------------------------------------------
# Test 22 – Description structure contains expected sections
# ---------------------------------------------------------------------------

def test_description_structure():
    finding = _seq_scan_finding()
    validation = _validated_result()

    rec = RecommendationEngine.recommend(finding, validation)

    assert "Observed:" in rec.description
    assert "Candidate:" in rec.description
    assert "Validation:" in rec.description
    assert "Recommendation:" in rec.description


# ---------------------------------------------------------------------------
# Test 23 – Tradeoffs present on validated recommendations
# ---------------------------------------------------------------------------

def test_tradeoffs_present_on_validated():
    finding = _seq_scan_finding()
    validation = _validated_result()

    rec = RecommendationEngine.recommend(finding, validation)

    assert len(rec.tradeoffs) > 0
    tradeoff_text = " ".join(rec.tradeoffs).lower()
    # Must mention storage and write overhead
    assert "storage" in tradeoff_text or "disk" in tradeoff_text
    assert "write" in tradeoff_text or "insert" in tradeoff_text or "amplification" in tradeoff_text


# ---------------------------------------------------------------------------
# Test 24 – INVALID_CANDIDATE / ERROR status behavior
# ---------------------------------------------------------------------------

def test_error_verdict_rejected():
    finding = _seq_scan_finding()
    validation = HypoPGValidationResult(
        verdict=ValidationVerdict.ERROR,
        candidate_index="CREATE INDEX ON orders (customer_id)",
        original_query="SELECT * FROM orders WHERE customer_id = 42",
        error_message="Connection error during HypoPG validation.",
        evidence={},
    )
    rec = RecommendationEngine.recommend(finding, validation)

    assert rec.status == RecommendationStatus.REJECTED
    assert rec.hypopg_validated is False
    assert rec.requires_human_approval is True


# ---------------------------------------------------------------------------
# Test 25 – Integration test against real PostgreSQL
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_full_pipeline_integration():
    """
    Runs the full recommendation pipeline against the live PostgreSQL database.

    Flow:
      EXPLAIN -> PlanAnalyzer -> BottleneckDetector
      -> HypoPGValidatorService -> RecommendationEngine -> OptimizationRecommendation

    Verifies:
      - MISSING_INDEX recommendation on orders(customer_id)
      - status = VALIDATED
      - confidence = HIGH
      - risk = LOW (single-column B-tree)
      - requires_human_approval = True
      - No physical index created
    """
    from sqlalchemy import text

    from app.db.database import engine
    from app.schemas.optimization import HypotheticalIndexRequest, IndexMethod
    from app.services.bottleneck_detector import BottleneckDetector
    from app.services.hypopg_validator import HypoPGValidatorService
    from app.services.plan_analyzer import PlanAnalyzer

    query = "SELECT * FROM orders WHERE customer_id = 42"

    with engine.connect() as conn:
        # Step 1: EXPLAIN + PlanAnalyzer + BottleneckDetector
        result = conn.execute(text("EXPLAIN (FORMAT JSON) " + query))
        raw_plan = result.fetchone()[0]

        root_node, summary, all_nodes = PlanAnalyzer.analyze(raw_plan, query=query)

        detector = BottleneckDetector()
        findings = detector.detect(root_node)

        # Must have found a MISSING_INDEX or FILTERED_SEQ_SCAN
        index_findings = [
            f for f in findings
            if f.finding_type.value in ("missing_index", "filtered_seq_scan")
        ]
        assert len(index_findings) > 0, "Expected at least one missing index / filtered scan finding."

        finding = index_findings[0]

        # Step 2: HypoPG validation
        request = HypotheticalIndexRequest(
            query=query,
            table="orders",
            columns=["customer_id"],
            index_method=IndexMethod.BTREE,
        )
        validation = HypoPGValidatorService.validate_candidate(request)

        assert validation.verdict == ValidationVerdict.VALIDATED, (
            f"Expected HypoPG to validate; got {validation.verdict}"
        )

        # Step 3: Recommendation engine
        rec = RecommendationEngine.recommend(finding, validation)

        # --- Assertions ---
        assert rec.status == RecommendationStatus.VALIDATED
        assert rec.confidence == RecommendationConfidence.HIGH
        assert rec.risk in (RecommendationRisk.LOW, RecommendationRisk.MEDIUM)
        assert rec.hypopg_validated is True
        assert rec.requires_human_approval is True
        assert rec.relation == "orders"
        assert "customer_id" in rec.columns
        assert rec.sql_preview is not None
        assert "orders" in rec.sql_preview
        assert "customer_id" in rec.sql_preview
        assert rec.original_cost is not None
        assert rec.hypothetical_cost is not None
        assert rec.cost_improvement_percent is not None
        assert rec.cost_improvement_percent > 0

        # Verify no new physical index was created (baseline has only orders_pkey and idx_orders_order_date)
        idx_check = conn.execute(
            text(
                "SELECT COUNT(*) FROM pg_indexes "
                "WHERE tablename = 'orders' AND indexname NOT IN ('orders_pkey', 'idx_orders_order_date')"
            )
        )
        new_physical_idx_count = idx_check.scalar()
        assert new_physical_idx_count == 0, (
            f"Expected no new physical indexes; found {new_physical_idx_count}"
        )

        # Specifically verify no index on customer_id exists
        cid_check = conn.execute(
            text(
                "SELECT COUNT(*) FROM pg_indexes "
                "WHERE tablename = 'orders' AND indexdef LIKE '%customer_id%'"
            )
        )
        assert cid_check.scalar() == 0, "Physical index on customer_id must not exist."

        # Verify HypoPG state was cleaned up
        hypo_check = conn.execute(text("SELECT COUNT(*) FROM hypopg()"))
        hypo_count = hypo_check.scalar()
        assert hypo_count == 0, f"Expected no HypoPG indexes remaining; found {hypo_count}"

        # Step 15: Verify database integrity (row counts remain unchanged)
        assert conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() == 500
        assert conn.execute(text("SELECT COUNT(*) FROM products")).scalar() == 100
        assert conn.execute(text("SELECT COUNT(*) FROM orders")).scalar() == 5000
        assert conn.execute(text("SELECT COUNT(*) FROM order_items")).scalar() == 15000
