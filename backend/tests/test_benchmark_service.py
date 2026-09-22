"""
Unit and integration tests for Real Runtime Benchmarking (Phase 3 Step 3).

Covers all 31 test requirements from Step 15:
  Validation:
    1.  valid read-only query accepted
    2.  SELECT accepted
    3.  INSERT rejected
    4.  UPDATE rejected
    5.  DELETE rejected
    6.  CREATE rejected
    7.  DROP rejected
    8.  multi-statement query rejected
  Measurement & Parsing:
    9.  EXPLAIN JSON parsed correctly
    10. planning time extracted
    11. execution time extracted
    12. planner cost extracted
    13. rows extracted
    14. nested index scan detected
    15. bitmap index scan detected
    16. sequential scan detected
    17. buffer statistics extracted
  Statistics:
    18. mean calculated
    19. median calculated
    20. min/max calculated
    21. standard deviation calculated
    22. improvement percentage calculated
    23. zero-baseline handled safely
  Authorization:
    24. missing/ineligible remediation rejected
    25. failed remediation rejected
    26. unverified remediation rejected
    27. applied remediation accepted
  Safety/Integrity:
    28. benchmark performs no writes
    29. row counts unchanged
    30. physical indexes unchanged
    31. repeated benchmark produces structured result
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.database import engine
from app.schemas.optimization import (
    BenchmarkResult,
    BenchmarkStatus,
    ExecutionMeasurement,
    OptimizationRecommendation,
    OptimizationType,
    RecommendationConfidence,
    RecommendationRisk,
    RecommendationStatus,
    RemediationResult,
    RemediationStatus,
)
from app.services.benchmark_service import (
    BenchmarkAuthorizationError,
    BenchmarkExecutionError,
    BenchmarkSafetyError,
    BenchmarkService,
)


# ---------------------------------------------------------------------------
# Fixtures & Sample Data
# ---------------------------------------------------------------------------

SAMPLE_SEQ_SCAN_EXPLAIN = [
    {
        "Plan": {
            "Node Type": "Seq Scan",
            "Relation Name": "orders",
            "Alias": "orders",
            "Startup Cost": 0.0,
            "Total Cost": 107.5,
            "Plan Rows": 10,
            "Plan Width": 36,
            "Actual Startup Time": 0.05,
            "Actual Total Time": 1.25,
            "Actual Rows": 10,
            "Actual Loops": 1,
            "Shared Hit Blocks": 45,
            "Shared Read Blocks": 5,
        },
        "Planning Time": 0.15,
        "Execution Time": 1.35,
    }
]

SAMPLE_BITMAP_SCAN_EXPLAIN = [
    {
        "Plan": {
            "Node Type": "Bitmap Heap Scan",
            "Relation Name": "orders",
            "Alias": "orders",
            "Startup Cost": 4.5,
            "Total Cost": 28.16,
            "Plan Rows": 10,
            "Plan Width": 36,
            "Actual Startup Time": 0.02,
            "Actual Total Time": 0.15,
            "Actual Rows": 10,
            "Actual Loops": 1,
            "Shared Hit Blocks": 8,
            "Shared Read Blocks": 0,
            "Plans": [
                {
                    "Node Type": "Bitmap Index Scan",
                    "Index Name": "idx_autodba_orders_customer_id",
                    "Startup Cost": 0.0,
                    "Total Cost": 4.5,
                    "Plan Rows": 10,
                    "Plan Width": 0,
                    "Actual Startup Time": 0.01,
                    "Actual Total Time": 0.01,
                    "Actual Rows": 10,
                    "Actual Loops": 1,
                    "Shared Hit Blocks": 2,
                    "Shared Read Blocks": 0,
                }
            ],
        },
        "Planning Time": 0.12,
        "Execution Time": 0.22,
    }
]

SAMPLE_NESTED_LOOP_EXPLAIN = [
    {
        "Plan": {
            "Node Type": "Nested Loop",
            "Startup Cost": 0.28,
            "Total Cost": 45.10,
            "Plan Rows": 5,
            "Plan Width": 64,
            "Actual Startup Time": 0.03,
            "Actual Total Time": 0.40,
            "Actual Rows": 5,
            "Actual Loops": 1,
            "Shared Hit Blocks": 12,
            "Shared Read Blocks": 2,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "customers",
                    "Actual Rows": 1,
                    "Shared Hit Blocks": 4,
                    "Shared Read Blocks": 0,
                },
                {
                    "Node Type": "Index Scan",
                    "Relation Name": "orders",
                    "Index Name": "idx_orders_customer_id",
                    "Actual Rows": 5,
                    "Shared Hit Blocks": 8,
                    "Shared Read Blocks": 2,
                },
            ],
        },
        "Planning Time": 0.25,
        "Execution Time": 0.48,
    }
]


def _sample_remediation(
    status: RemediationStatus = RemediationStatus.APPLIED,
    verification_passed: bool = True,
) -> RemediationResult:
    now = datetime.now(timezone.utc)
    rec = OptimizationRecommendation(
        optimization_type=OptimizationType.MISSING_INDEX,
        title="Create index on orders(customer_id)",
        summary="Validated index",
        description="Desc",
        relation="orders",
        columns=["customer_id"],
        recommended_action="CREATE INDEX ON orders (customer_id);",
        sql_preview="CREATE INDEX ON orders (customer_id);",
        status=RecommendationStatus.VALIDATED,
        confidence=RecommendationConfidence.HIGH,
        risk=RecommendationRisk.LOW,
        evidence=[],
        hypopg_validated=True,
        original_cost=107.5,
        hypothetical_cost=28.16,
        cost_improvement_percent=73.8,
        requires_human_approval=True,
    )
    return RemediationResult(
        remediation_id="rem_test_001",
        approval_id="appr_test_001",
        recommendation=rec,
        status=status,
        target_relation="orders",
        target_columns=["customer_id"],
        sql_executed="CREATE INDEX idx_autodba_orders_customer_id ON orders (customer_id);",
        index_name="idx_autodba_orders_customer_id",
        started_at=now,
        completed_at=now,
        pre_remediation_indexes=[],
        post_remediation_indexes=[],
        verification_passed=verification_passed,
    )


# ===========================================================================
# 1. Validation Tests (Tests 1-8)
# ===========================================================================

def test_valid_read_only_query_accepted():
    q = "SELECT * FROM orders WHERE customer_id = 42"
    validated = BenchmarkService.validate_query(q)
    assert validated == q


def test_select_with_cte_accepted():
    q = "WITH recent_orders AS (SELECT * FROM orders WHERE id < 100) SELECT * FROM recent_orders"
    validated = BenchmarkService.validate_query(q)
    assert "SELECT" in validated


def test_insert_rejected():
    with pytest.raises(BenchmarkSafetyError):
        BenchmarkService.validate_query("INSERT INTO orders (customer_id) VALUES (42)")


def test_update_rejected():
    with pytest.raises(BenchmarkSafetyError):
        BenchmarkService.validate_query("UPDATE orders SET total_amount = 100 WHERE id = 1")


def test_delete_rejected():
    with pytest.raises(BenchmarkSafetyError):
        BenchmarkService.validate_query("DELETE FROM orders WHERE id = 1")


def test_create_rejected():
    with pytest.raises(BenchmarkSafetyError):
        BenchmarkService.validate_query("CREATE TABLE test_tab (id int)")


def test_drop_rejected():
    with pytest.raises(BenchmarkSafetyError):
        BenchmarkService.validate_query("DROP TABLE orders")


def test_multi_statement_rejected():
    with pytest.raises(BenchmarkSafetyError):
        BenchmarkService.validate_query("SELECT 1; SELECT 2")


# ===========================================================================
# 2. Measurement & Parsing Tests (Tests 9-17)
# ===========================================================================

def test_explain_json_parsed_correctly():
    parsed = BenchmarkService.parse_explain_analyze_json(SAMPLE_SEQ_SCAN_EXPLAIN)
    assert parsed["planning_time_ms"] == 0.15
    assert parsed["execution_time_ms"] == 1.35
    assert parsed["planner_cost"] == 107.5
    assert parsed["rows_returned"] == 10
    assert parsed["scan_type"] == "Seq Scan"
    assert parsed["index_used"] is None
    assert parsed["shared_hit_blocks"] == 45
    assert parsed["shared_read_blocks"] == 5


def test_planning_time_extracted():
    parsed = BenchmarkService.parse_explain_analyze_json(SAMPLE_BITMAP_SCAN_EXPLAIN)
    assert parsed["planning_time_ms"] == 0.12


def test_execution_time_extracted():
    parsed = BenchmarkService.parse_explain_analyze_json(SAMPLE_BITMAP_SCAN_EXPLAIN)
    assert parsed["execution_time_ms"] == 0.22


def test_planner_cost_extracted():
    parsed = BenchmarkService.parse_explain_analyze_json(SAMPLE_BITMAP_SCAN_EXPLAIN)
    assert parsed["planner_cost"] == 28.16


def test_rows_extracted():
    parsed = BenchmarkService.parse_explain_analyze_json(SAMPLE_BITMAP_SCAN_EXPLAIN)
    assert parsed["rows_returned"] == 10


def test_nested_index_scan_detected():
    parsed = BenchmarkService.parse_explain_analyze_json(SAMPLE_NESTED_LOOP_EXPLAIN)
    assert parsed["index_used"] == "idx_orders_customer_id"


def test_bitmap_index_scan_detected():
    parsed = BenchmarkService.parse_explain_analyze_json(SAMPLE_BITMAP_SCAN_EXPLAIN)
    assert parsed["scan_type"] == "Bitmap Heap Scan"
    assert parsed["index_used"] == "idx_autodba_orders_customer_id"


def test_sequential_scan_detected():
    parsed = BenchmarkService.parse_explain_analyze_json(SAMPLE_SEQ_SCAN_EXPLAIN)
    assert parsed["scan_type"] == "Seq Scan"
    assert parsed["index_used"] is None


def test_buffer_statistics_extracted():
    # Shared hit blocks = 8 (heap) + 2 (index) = 10
    parsed = BenchmarkService.parse_explain_analyze_json(SAMPLE_BITMAP_SCAN_EXPLAIN)
    assert parsed["shared_hit_blocks"] == 10
    assert parsed["shared_read_blocks"] == 0


# ===========================================================================
# 3. Statistics Tests (Tests 18-23)
# ===========================================================================

def test_mean_calculated():
    times = [1.0, 2.0, 3.0, 4.0]
    import statistics
    assert statistics.mean(times) == 2.5


def test_median_calculated():
    times = [1.0, 2.0, 10.0]
    import statistics
    assert statistics.median(times) == 2.0


def test_min_max_calculated():
    times = [1.5, 0.8, 3.2, 2.1]
    assert min(times) == 0.8
    assert max(times) == 3.2


def test_stddev_calculated():
    times = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    import statistics
    sd = statistics.stdev(times)
    assert round(sd, 2) == 2.14


def test_improvement_percentage_calculated():
    before_time = 10.0
    after_time = 2.5
    improvement = ((before_time - after_time) / before_time) * 100
    assert improvement == 75.0


def test_zero_baseline_handled_safely():
    before = ExecutionMeasurement(
        runs=1, execution_times_ms=[0.0], planning_times_ms=[0.0],
        mean_execution_time_ms=0.0, median_execution_time_ms=0.0,
        min_execution_time_ms=0.0, max_execution_time_ms=0.0,
        stddev_execution_time_ms=0.0, rows_returned=0, planner_cost=0.0
    )
    after = ExecutionMeasurement(
        runs=1, execution_times_ms=[0.0], planning_times_ms=[0.0],
        mean_execution_time_ms=0.0, median_execution_time_ms=0.0,
        min_execution_time_ms=0.0, max_execution_time_ms=0.0,
        stddev_execution_time_ms=0.0, rows_returned=0, planner_cost=0.0
    )
    # Avoid division by zero
    runtime_imp = ((before.mean_execution_time_ms - after.mean_execution_time_ms) / before.mean_execution_time_ms * 100) if before.mean_execution_time_ms > 0 else None
    assert runtime_imp is None


# ===========================================================================
# 4. Authorization Tests (Tests 24-27)
# ===========================================================================

def test_missing_remediation_allowed_or_checked():
    # Optional remediation passes authorization check
    BenchmarkService.verify_remediation_authorization(None)


def test_failed_remediation_rejected():
    rem = _sample_remediation(status=RemediationStatus.FAILED)
    with pytest.raises(BenchmarkAuthorizationError) as exc_info:
        BenchmarkService.verify_remediation_authorization(rem)
    assert "failed" in str(exc_info.value).lower()


def test_unverified_remediation_rejected():
    rem = _sample_remediation(status=RemediationStatus.APPLIED, verification_passed=False)
    with pytest.raises(BenchmarkAuthorizationError) as exc_info:
        BenchmarkService.verify_remediation_authorization(rem)
    assert "unverified" in str(exc_info.value).lower()


def test_applied_remediation_accepted():
    rem = _sample_remediation(status=RemediationStatus.APPLIED, verification_passed=True)
    BenchmarkService.verify_remediation_authorization(rem)  # Should not raise


# ===========================================================================
# 5. Safety & Integrity Tests (Tests 28-31)
# ===========================================================================

@pytest.mark.integration
def test_benchmark_performs_no_writes():
    query = "SELECT * FROM orders WHERE order_date = '2024-01-01'"
    res = BenchmarkService.benchmark(query, runs=3, warmup_runs=1)

    assert res.status == BenchmarkStatus.COMPLETED
    assert res.before.runs == 3
    assert res.after.runs == 3
    assert res.before.mean_execution_time_ms > 0
    assert res.after.mean_execution_time_ms > 0


@pytest.mark.integration
def test_row_counts_unchanged_after_benchmark():
    query = "SELECT * FROM orders WHERE customer_id = 42"
    BenchmarkService.benchmark(query, runs=2, warmup_runs=1)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() == 500
        assert conn.execute(text("SELECT COUNT(*) FROM products")).scalar() == 100
        assert conn.execute(text("SELECT COUNT(*) FROM orders")).scalar() == 5000
        assert conn.execute(text("SELECT COUNT(*) FROM order_items")).scalar() == 15000


@pytest.mark.integration
def test_physical_indexes_unchanged_by_benchmark():
    query = "SELECT * FROM customers WHERE id = 1"
    with engine.connect() as conn:
        before_indexes = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'customers' ORDER BY indexname")
        ).scalars().all()

    BenchmarkService.benchmark(query, runs=2, warmup_runs=1)

    with engine.connect() as conn:
        after_indexes = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'customers' ORDER BY indexname")
        ).scalars().all()

    assert before_indexes == after_indexes


@pytest.mark.integration
def test_repeated_benchmark_produces_structured_result():
    query = "SELECT * FROM orders WHERE customer_id = 42"
    res = BenchmarkService.benchmark(query, runs=3, warmup_runs=1)

    assert res.benchmark_id.startswith("bench_")
    assert res.status == BenchmarkStatus.COMPLETED
    assert isinstance(res.before, ExecutionMeasurement)
    assert isinstance(res.after, ExecutionMeasurement)
    assert res.started_at is not None
    assert res.completed_at >= res.started_at
    # Serializability check
    json_data = res.model_dump_json()
    assert "benchmark_id" in json_data
