"""
Unit tests for BottleneckDetector.

Covers:
  Rule A/E — Filtered sequential scan / missing index candidate
  Rule B   — Expensive sort
  Rule C   — Expensive nested loop
  Rule D   — Large row estimate
  Integration — Multiple rules firing from one plan
  Negative cases — Small tables and low-cost nodes NOT flagged
  Evidence and confidence fields populated correctly
  Configurable threshold override via custom Settings
"""

import pytest
from app.core.config import Settings
from app.services.plan_analyzer import PlanAnalyzer
from app.services.bottleneck_detector import BottleneckDetector
from app.schemas.optimization import (
    BottleneckType,
    Confidence,
    Severity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(**overrides) -> Settings:
    """Build a Settings instance with all env-var fields overridden explicitly."""
    base = dict(
        DATABASE_URL="postgresql+psycopg://test:test@localhost:5432/test",
        PLAN_LARGE_ROW_THRESHOLD=10_000,
        PLAN_HIGH_COST_THRESHOLD=1_000.0,
        PLAN_SORT_COST_THRESHOLD=500.0,
        PLAN_NESTED_LOOP_COST_THRESHOLD=1_000.0,
        PLAN_SEQ_SCAN_MIN_ROWS=500,
        PLAN_SEQ_SCAN_MIN_COST=50.0,
    )
    base.update(overrides)
    return Settings(**base)


DEFAULT_SETTINGS = _settings()


def _parse(raw_plan, query="q"):
    root, count, summary = PlanAnalyzer.analyze(raw_plan, query=query)
    return root, count, summary


# ---------------------------------------------------------------------------
# Fixtures: raw plans
# ---------------------------------------------------------------------------

# Large filtered seq scan — should trigger FILTERED_SEQ_SCAN + MISSING_INDEX
ORDERS_FILTERED_PLAN = [
    {
        "Plan": {
            "Node Type": "Seq Scan",
            "Relation Name": "orders",
            "Startup Cost": 0.0,
            "Total Cost": 107.5,
            "Plan Rows": 5000,
            "Filter": "(customer_id = 42)",
        }
    }
]

# Small table seq scan (10 rows) — must NOT be flagged
SMALL_TABLE_PLAN = [
    {
        "Plan": {
            "Node Type": "Seq Scan",
            "Relation Name": "config_flags",
            "Startup Cost": 0.0,
            "Total Cost": 1.1,
            "Plan Rows": 10,
            "Filter": "(active = true)",
        }
    }
]

# Seq scan with no filter but large rows — should produce LOW filtered_seq_scan
UNFILTERED_LARGE_SCAN_PLAN = [
    {
        "Plan": {
            "Node Type": "Seq Scan",
            "Relation Name": "events",
            "Startup Cost": 0.0,
            "Total Cost": 5000.0,
            "Plan Rows": 50_000,
        }
    }
]

# Expensive sort plan
EXPENSIVE_SORT_PLAN = [
    {
        "Plan": {
            "Node Type": "Sort",
            "Startup Cost": 1200.0,
            "Total Cost": 1500.0,
            "Plan Rows": 5000,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Startup Cost": 0.0,
                    "Total Cost": 107.5,
                    "Plan Rows": 5000,
                    "Filter": "(status = 'completed')",
                }
            ],
        }
    }
]

# Cheap sort plan — must NOT be flagged
CHEAP_SORT_PLAN = [
    {
        "Plan": {
            "Node Type": "Sort",
            "Startup Cost": 10.0,
            "Total Cost": 12.0,
            "Plan Rows": 50,
        }
    }
]

# Expensive nested loop
EXPENSIVE_NL_PLAN = [
    {
        "Plan": {
            "Node Type": "Nested Loop",
            "Startup Cost": 0.0,
            "Total Cost": 25_000.0,
            "Plan Rows": 50_000,
            "Join Type": "Inner",
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Startup Cost": 0.0,
                    "Total Cost": 107.5,
                    "Plan Rows": 5000,
                },
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "order_items",
                    "Startup Cost": 0.0,
                    "Total Cost": 200.0,
                    "Plan Rows": 15_000,
                },
            ],
        }
    }
]

# Small nested loop — must NOT be flagged
CHEAP_NL_PLAN = [
    {
        "Plan": {
            "Node Type": "Nested Loop",
            "Startup Cost": 0.0,
            "Total Cost": 5.0,
            "Plan Rows": 3,
            "Join Type": "Inner",
            "Plans": [],
        }
    }
]

# Large row estimate without filter (rule D)
LARGE_ROW_PLAN = [
    {
        "Plan": {
            "Node Type": "Hash",
            "Startup Cost": 0.0,
            "Total Cost": 800.0,
            "Plan Rows": 100_000,
        }
    }
]


# ---------------------------------------------------------------------------
# Rule A/E — Filtered sequential scan
# ---------------------------------------------------------------------------

class TestFilteredSeqScan:
    def test_large_filtered_seq_scan_produces_findings(self):
        root, _, _ = _parse(ORDERS_FILTERED_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        types = {f.finding_type for f in findings}
        assert BottleneckType.FILTERED_SEQ_SCAN in types

    def test_large_filtered_seq_scan_produces_missing_index(self):
        """5000 rows >= 500 * 2 threshold, so MISSING_INDEX must also fire."""
        root, _, _ = _parse(ORDERS_FILTERED_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        types = {f.finding_type for f in findings}
        assert BottleneckType.MISSING_INDEX in types

    def test_small_table_not_flagged(self):
        """10-row table must not generate a missing-index finding."""
        root, _, _ = _parse(SMALL_TABLE_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        types = {f.finding_type for f in findings}
        assert BottleneckType.MISSING_INDEX not in types
        assert BottleneckType.FILTERED_SEQ_SCAN not in types

    def test_unfiltered_large_scan_produces_low_severity_finding(self):
        """Full table scan without filter → LOW severity FILTERED_SEQ_SCAN."""
        root, _, _ = _parse(UNFILTERED_LARGE_SCAN_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        filtered_findings = [f for f in findings if f.finding_type == BottleneckType.FILTERED_SEQ_SCAN]
        assert len(filtered_findings) == 1
        assert filtered_findings[0].severity == Severity.LOW
        # No missing index: no filter to put an index on
        assert not any(f.finding_type == BottleneckType.MISSING_INDEX for f in findings)

    def test_finding_contains_relation_and_filter_evidence(self):
        root, _, _ = _parse(ORDERS_FILTERED_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        seq_finding = next(f for f in findings if f.finding_type == BottleneckType.FILTERED_SEQ_SCAN)
        assert seq_finding.relation == "orders"
        assert "filter" in seq_finding.evidence
        assert "(customer_id = 42)" in str(seq_finding.evidence["filter"])
        assert seq_finding.evidence["estimated_rows"] == 5000

    def test_moderate_filtered_scan_not_high_by_default(self):
        """1. A 5,000-row table with cost 107.5 and a filter must NOT be HIGH/HIGH by default."""
        root, _, _ = _parse(ORDERS_FILTERED_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        seq_findings = [f for f in findings if f.relation == "orders"]
        assert seq_findings, "Expected findings for orders"
        for f in seq_findings:
            assert not (f.severity == Severity.HIGH and f.confidence == Confidence.HIGH), (
                f"Finding {f.title} had HIGH severity and HIGH confidence for a moderate 107.5-cost scan"
            )
            assert f.severity in (Severity.LOW, Severity.MEDIUM)
            assert f.confidence in (Confidence.LOW, Confidence.MEDIUM)

    def test_genuinely_expensive_filtered_scan_is_high_candidate(self):
        """2. Genuinely expensive filtered scan crossing high thresholds -> HIGH/HIGH candidate."""
        expensive_plan = [
            {
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "transactions",
                    "Startup Cost": 0.0,
                    "Total Cost": 5_000.0,
                    "Plan Rows": 50_000,
                    "Filter": "(account_id = 99999)",
                }
            }
        ]
        root, _, _ = _parse(expensive_plan)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        trans_findings = [f for f in findings if f.relation == "transactions"]
        assert trans_findings, "Expected findings for expensive scan"
        missing_idx = next(f for f in trans_findings if f.finding_type == BottleneckType.MISSING_INDEX)
        assert missing_idx.severity == Severity.HIGH
        assert missing_idx.confidence == Confidence.HIGH

    def test_small_unfiltered_seq_scan_no_high_severity(self):
        """3. Small unfiltered Seq Scan must never produce a high-severity finding."""
        small_unfiltered = [
            {
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "lookup_status",
                    "Startup Cost": 0.0,
                    "Total Cost": 15.0,
                    "Plan Rows": 80,
                }
            }
        ]
        root, _, _ = _parse(small_unfiltered)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        assert not any(f.severity == Severity.HIGH for f in findings)

    def test_filtered_scan_framed_as_candidate_requiring_hypopg_validation(self):
        """4. Filtered scan must be framed as candidate only, not claiming an index is definitely beneficial."""
        root, _, _ = _parse(ORDERS_FILTERED_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        missing_idx = next(f for f in findings if f.finding_type == BottleneckType.MISSING_INDEX)
        # Title must identify it as a candidate
        assert "candidate" in missing_idx.title.lower()
        # Recommendation must explicitly emphasize HypoPG validation
        assert "hypopg" in missing_idx.recommendation.lower()
        # Description must indicate benefit is not guaranteed
        assert "not guaranteed" in missing_idx.description.lower()

    def test_custom_threshold_changes_behavior(self):
        """With high thresholds, the scan must NOT be flagged."""
        high_threshold_settings = _settings(
            PLAN_SEQ_SCAN_MIN_ROWS=10_000,
            PLAN_SEQ_SCAN_MIN_COST=500.0,
        )
        root, _, _ = _parse(ORDERS_FILTERED_PLAN)
        findings = BottleneckDetector.detect(root, settings=high_threshold_settings)
        types = {f.finding_type for f in findings}
        assert BottleneckType.FILTERED_SEQ_SCAN not in types
        assert BottleneckType.MISSING_INDEX not in types


# ---------------------------------------------------------------------------
# Rule B — Expensive sort
# ---------------------------------------------------------------------------

class TestExpensiveSort:
    def test_expensive_sort_flagged(self):
        root, _, _ = _parse(EXPENSIVE_SORT_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        types = {f.finding_type for f in findings}
        assert BottleneckType.EXPENSIVE_SORT in types

    def test_cheap_sort_not_flagged(self):
        root, _, _ = _parse(CHEAP_SORT_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        assert not any(f.finding_type == BottleneckType.EXPENSIVE_SORT for f in findings)

    def test_sort_finding_evidence(self):
        root, _, _ = _parse(EXPENSIVE_SORT_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        sort_finding = next(f for f in findings if f.finding_type == BottleneckType.EXPENSIVE_SORT)
        assert sort_finding.evidence["total_cost"] == 1500.0
        assert sort_finding.evidence["estimated_rows"] == 5000
        assert "sort_cost_threshold" in sort_finding.evidence

    def test_sort_finding_has_severity(self):
        root, _, _ = _parse(EXPENSIVE_SORT_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        sort_finding = next(f for f in findings if f.finding_type == BottleneckType.EXPENSIVE_SORT)
        assert sort_finding.severity in (Severity.MEDIUM, Severity.HIGH)

    def test_sort_threshold_override(self):
        """With a very high threshold, the same sort must NOT be flagged."""
        high_settings = _settings(PLAN_SORT_COST_THRESHOLD=99_999.0)
        root, _, _ = _parse(EXPENSIVE_SORT_PLAN)
        findings = BottleneckDetector.detect(root, settings=high_settings)
        assert not any(f.finding_type == BottleneckType.EXPENSIVE_SORT for f in findings)


# ---------------------------------------------------------------------------
# Rule C — Expensive nested loop
# ---------------------------------------------------------------------------

class TestExpensiveNestedLoop:
    def test_expensive_nested_loop_flagged(self):
        root, _, _ = _parse(EXPENSIVE_NL_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        types = {f.finding_type for f in findings}
        assert BottleneckType.EXPENSIVE_NESTED_LOOP in types

    def test_cheap_nested_loop_not_flagged(self):
        root, _, _ = _parse(CHEAP_NL_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        assert not any(f.finding_type == BottleneckType.EXPENSIVE_NESTED_LOOP for f in findings)

    def test_nested_loop_evidence_fields(self):
        root, _, _ = _parse(EXPENSIVE_NL_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        nl_finding = next(f for f in findings if f.finding_type == BottleneckType.EXPENSIVE_NESTED_LOOP)
        assert nl_finding.evidence["total_cost"] == 25_000.0
        assert "nested_loop_cost_threshold" in nl_finding.evidence

    def test_nested_loop_confidence_is_medium(self):
        """Nested loops can be intentional; confidence must not exceed MEDIUM."""
        root, _, _ = _parse(EXPENSIVE_NL_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        nl_finding = next(f for f in findings if f.finding_type == BottleneckType.EXPENSIVE_NESTED_LOOP)
        assert nl_finding.confidence == Confidence.MEDIUM


# ---------------------------------------------------------------------------
# Rule D — Large row estimate
# ---------------------------------------------------------------------------

class TestLargeRowEstimate:
    def test_large_row_hash_node_flagged(self):
        root, _, _ = _parse(LARGE_ROW_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        types = {f.finding_type for f in findings}
        assert BottleneckType.LARGE_ROW_ESTIMATE in types

    def test_large_row_finding_evidence(self):
        root, _, _ = _parse(LARGE_ROW_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        lr_finding = next(f for f in findings if f.finding_type == BottleneckType.LARGE_ROW_ESTIMATE)
        assert lr_finding.evidence["estimated_rows"] == 100_000
        assert "large_row_threshold" in lr_finding.evidence

    def test_filtered_seq_scan_not_double_counted_as_large_row(self):
        """A filtered seq scan must fire FILTERED_SEQ_SCAN but NOT LARGE_ROW_ESTIMATE
        (to avoid duplicate noise for the same node)."""
        large_filtered_plan = [
            {
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "events",
                    "Plan Rows": 50_000,
                    "Filter": "(user_id = 99)",
                    "Total Cost": 500.0,
                }
            }
        ]
        root, _, _ = _parse(large_filtered_plan)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        types = [f.finding_type for f in findings]
        assert BottleneckType.FILTERED_SEQ_SCAN in types
        # Rule D must not also fire for a filtered seq scan
        assert BottleneckType.LARGE_ROW_ESTIMATE not in types


# ---------------------------------------------------------------------------
# Multiple findings from one plan
# ---------------------------------------------------------------------------

class TestMultipleFindings:
    def test_complex_plan_produces_multiple_findings(self):
        """EXPENSIVE_SORT + FILTERED_SEQ_SCAN + MISSING_INDEX from one plan."""
        root, _, _ = _parse(EXPENSIVE_SORT_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        # Sort fires on the Sort node, seq scan rules fire on the Seq Scan child
        types = {f.finding_type for f in findings}
        assert BottleneckType.EXPENSIVE_SORT in types
        assert BottleneckType.FILTERED_SEQ_SCAN in types or BottleneckType.MISSING_INDEX in types

    def test_findings_list_is_ordered_by_traversal(self):
        """Findings must appear in plan-tree pre-order (root node first)."""
        root, _, _ = _parse(EXPENSIVE_SORT_PLAN)
        findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)
        types = [f.finding_type for f in findings]
        # Sort fires first (root), then Seq Scan rules (child)
        sort_idx = next(i for i, t in enumerate(types) if t == BottleneckType.EXPENSIVE_SORT)
        seq_idx = next(
            (i for i, t in enumerate(types) if t in (BottleneckType.FILTERED_SEQ_SCAN, BottleneckType.MISSING_INDEX)),
            None,
        )
        if seq_idx is not None:
            assert sort_idx < seq_idx


# ---------------------------------------------------------------------------
# Real PostgreSQL plan (integration, skipped if no DB available)
# ---------------------------------------------------------------------------

def test_real_orders_plan_produces_filtered_seq_scan_finding():
    """Integration test: parse the real EXPLAIN output from PostgreSQL.

    Verifies that the analyzer and detector correctly identify the
    'orders' Seq Scan with customer_id filter as a bottleneck candidate.
    This test is intentionally kept separate from DB-free unit tests.
    """
    pytest.importorskip("sqlalchemy")

    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(
            "postgresql+psycopg://autodba:autodba@postgres:5432/autodba",
            connect_args={"connect_timeout": 3},
        )
        with engine.connect() as conn:
            row = conn.execute(
                text("EXPLAIN (FORMAT JSON) SELECT * FROM orders WHERE customer_id = 42;")
            ).fetchone()
        raw_plan = row[0]
    except Exception as exc:
        pytest.skip(f"PostgreSQL not reachable in this environment: {exc}")

    root, nodes_analyzed, summary = PlanAnalyzer.analyze(raw_plan, query="SELECT * FROM orders WHERE customer_id = 42")
    findings = BottleneckDetector.detect(root, settings=DEFAULT_SETTINGS)

    # Plan must have been parsed
    assert nodes_analyzed >= 1
    assert summary.has_seq_scans is True

    # Verify the orders seq scan is found somewhere in the tree
    from app.services.plan_analyzer import flatten_nodes
    all_nodes = flatten_nodes(root)
    orders_nodes = [n for n in all_nodes if n.relation_name == "orders"]
    assert orders_nodes, "Expected an 'orders' relation node in the plan"

    seq_scan_node = next((n for n in orders_nodes if "Scan" in n.node_type), None)
    assert seq_scan_node is not None, "Expected a Scan node on orders"
    assert seq_scan_node.filter is not None, "Expected a filter on the orders scan node"

    # Detector must produce at least one finding involving orders
    orders_findings = [f for f in findings if f.relation == "orders"]
    assert orders_findings, (
        f"Expected at least one finding for 'orders', got findings: {findings}"
    )

    types = {f.finding_type for f in orders_findings}
    assert BottleneckType.FILTERED_SEQ_SCAN in types or BottleneckType.MISSING_INDEX in types
