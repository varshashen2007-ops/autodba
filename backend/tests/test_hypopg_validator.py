"""
Tests for HypoPG Counterfactual Validator Service
=================================================
Covers:
  - Test 1: HypoPG availability
  - Test 2: Successful hypothetical index creation & validation
  - Test 3: Confirmation that NO physical index was created
  - Test 4: Plan comparison (before vs after captured)
  - Test 5: Cost comparison calculation correctness
  - Test 6: Plan shape change detection (e.g. Seq Scan → Index/Bitmap Scan)
  - Test 7: No improvement verdict scenario
  - Test 8: Regression verdict scenario
  - Test 9: Invalid candidate rejection
  - Test 10: SQL injection resistance
  - Test 11: HypoPG state cleanup after validation
  - Test 12: HypoPG cleanup on exception/failure
  - Test 13: Multiple sequential validations without contamination
  - Test 14: Determinism of validation results
"""

import pytest
from sqlalchemy import text
from app.db.database import engine
from app.schemas.optimization import (
    HypotheticalIndexRequest,
    IndexMethod,
    PlanComparison,
    PlanNode,
    ValidationVerdict,
)
from app.services.hypopg_validator import (
    HypoPGValidatorService,
    InvalidCandidateError,
)


# ---------------------------------------------------------------------------
# Test 1: HypoPG availability
# ---------------------------------------------------------------------------

def test_hypopg_extension_available():
    """Verify that hypopg extension is installed and available in PostgreSQL."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'hypopg';")
        ).fetchone()
        assert row is not None, "hypopg extension is not installed in the database"
        assert row[0] == "hypopg"


# ---------------------------------------------------------------------------
# Test 2: Successful hypothetical index validation
# ---------------------------------------------------------------------------

def test_successful_hypothetical_index_validation():
    """Given 'SELECT * FROM orders WHERE customer_id = 42;' and orders(customer_id),

    verify that HypoPG successfully evaluates the candidate and returns VALIDATED.
    """
    request = HypotheticalIndexRequest(
        query="SELECT * FROM orders WHERE customer_id = 42",
        table="orders",
        columns=["customer_id"],
        index_method=IndexMethod.BTREE,
    )

    result = HypoPGValidatorService.validate_candidate(request)

    assert result.verdict in (ValidationVerdict.VALIDATED, ValidationVerdict.NO_IMPROVEMENT)
    assert result.candidate_index == "CREATE INDEX ON orders (customer_id)"
    assert result.hypothetical_index_name is not None
    assert "btree_orders_customer_id" in result.hypothetical_index_name
    assert result.comparison is not None
    assert result.original_plan is not None
    assert result.hypothetical_plan is not None
    # For orders(customer_id) with 5,000 rows, HypoPG achieves a massive cost reduction
    assert result.verdict == ValidationVerdict.VALIDATED
    assert result.comparison.cost_improvement_percent > 50.0


# ---------------------------------------------------------------------------
# Test 3: No physical index created
# ---------------------------------------------------------------------------

def test_no_physical_index_created():
    """Verify that running HypoPG validation NEVER creates a physical index in PostgreSQL."""
    request = HypotheticalIndexRequest(
        query="SELECT * FROM orders WHERE customer_id = 42",
        table="orders",
        columns=["customer_id"],
    )

    # 1. Inspect existing physical indexes on orders before validation
    with engine.connect() as conn:
        before_indexes = conn.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'orders';")
        ).fetchall()

    # 2. Run HypoPG counterfactual validation
    result = HypoPGValidatorService.validate_candidate(request)
    assert result.verdict == ValidationVerdict.VALIDATED

    # 3. Verify physical indexes on orders are completely identical
    with engine.connect() as conn:
        after_indexes = conn.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'orders';")
        ).fetchall()

    assert before_indexes == after_indexes, "Physical indexes changed after HypoPG validation!"
    index_names = [row[0] for row in after_indexes]
    assert "orders_pkey" in index_names
    assert not any("customer_id" in name for name in index_names), (
        f"A physical index containing 'customer_id' was created! Indexes: {index_names}"
    )


# ---------------------------------------------------------------------------
# Test 4: Plan comparison captured
# ---------------------------------------------------------------------------

def test_plan_comparison_captured():
    """Verify that both before and after plan structures are faithfully recorded."""
    request = HypotheticalIndexRequest(
        query="SELECT * FROM orders WHERE customer_id = 42",
        table="orders",
        columns=["customer_id"],
    )

    result = HypoPGValidatorService.validate_candidate(request)

    assert result.comparison is not None
    assert result.comparison.original_cost > 0.0
    assert result.comparison.hypothetical_cost > 0.0
    assert result.original_plan.node_type != ""
    assert result.hypothetical_plan.node_type != ""


# ---------------------------------------------------------------------------
# Test 5: Cost comparison calculations
# ---------------------------------------------------------------------------

def test_cost_comparison_calculations():
    """Verify exact formula for cost_difference and cost_improvement_percent."""
    orig = PlanNode(node_type="Seq Scan", total_cost=100.0)
    hypo = PlanNode(node_type="Index Scan", total_cost=20.0)

    comparison = HypoPGValidatorService._compare_plans(orig, hypo, table="orders")

    assert comparison.original_cost == 100.0
    assert comparison.hypothetical_cost == 20.0
    assert comparison.cost_difference == 80.0
    assert comparison.cost_improvement_percent == 80.0
    assert comparison.plan_changed is True


def test_cost_comparison_handles_zero_original_cost():
    """Zero cost original plan must not cause ZeroDivisionError."""
    orig = PlanNode(node_type="Result", total_cost=0.0)
    hypo = PlanNode(node_type="Result", total_cost=0.0)

    comparison = HypoPGValidatorService._compare_plans(orig, hypo, table="test")
    assert comparison.cost_difference == 0.0
    assert comparison.cost_improvement_percent == 0.0


# ---------------------------------------------------------------------------
# Test 6: Plan shape change detection
# ---------------------------------------------------------------------------

def test_plan_shape_change_detected():
    """Verify that the planner's transition from Seq Scan to an index scan is detected."""
    request = HypotheticalIndexRequest(
        query="SELECT * FROM orders WHERE customer_id = 42",
        table="orders",
        columns=["customer_id"],
    )

    result = HypoPGValidatorService.validate_candidate(request)

    assert result.comparison is not None
    assert result.comparison.plan_changed is True
    assert result.comparison.original_scan_type == "Seq Scan"
    # In PostgreSQL, with the hypothetical index, the planner chooses Bitmap Heap Scan or Index Scan
    assert result.comparison.hypothetical_scan_type in (
        "Index Scan", "Bitmap Heap Scan", "Bitmap Index Scan", "Index Only Scan"
    )
    assert result.comparison.plan_change_summary is not None
    assert "orders" in result.comparison.plan_change_summary


# ---------------------------------------------------------------------------
# Test 7: No improvement scenario
# ---------------------------------------------------------------------------

def test_no_improvement_scenario():
    """Candidate index on an unrelated column that does not improve query cost

    must receive a NO_IMPROVEMENT verdict.
    """
    # Query filters by customer_id; index candidate is on order_date
    # Furthermore, set min_cost_improvement_percent very high to test threshold
    request = HypotheticalIndexRequest(
        query="SELECT * FROM orders WHERE customer_id = 42",
        table="orders",
        columns=["status"],  # Low cardinality column with no predicate in query
        min_cost_improvement_percent=50.0,
    )

    result = HypoPGValidatorService.validate_candidate(request)

    # An index on status does not help `customer_id = 42`, so planner cost remains identical
    assert result.verdict == ValidationVerdict.NO_IMPROVEMENT
    assert result.comparison is not None
    assert result.comparison.cost_improvement_percent < 50.0


# ---------------------------------------------------------------------------
# Test 8: Regression scenario
# ---------------------------------------------------------------------------

def test_regression_verdict_when_cost_increases():
    """Deterministic check: when hypothetical plan has higher cost, verdict is REGRESSION."""
    comparison = PlanComparison(
        original_cost=50.0,
        hypothetical_cost=80.0,
        cost_difference=-30.0,
        cost_improvement_percent=-60.0,
        original_root_node_type="Seq Scan",
        hypothetical_root_node_type="Index Scan",
        plan_changed=True,
    )

    verdict = HypoPGValidatorService._determine_verdict(comparison, min_improvement_percent=5.0)
    assert verdict == ValidationVerdict.REGRESSION


# ---------------------------------------------------------------------------
# Test 9: Invalid candidate rejection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_table,bad_columns",
    [
        ("", ["customer_id"]),
        ("   ", ["customer_id"]),
        ("orders; DROP TABLE orders", ["customer_id"]),
        ("orders", []),
        ("orders", [""]),
        ("orders", ["col; DROP TABLE orders"]),
        ("orders", ["col with spaces"]),
        ("orders", ["col--comment"]),
        ("orders", ["col/*comment*/"]),
        ("DROP", ["id"]),  # Disallowed SQL keyword as table
        ("orders", ["SELECT"]),  # Disallowed SQL keyword as column
    ],
)
def test_invalid_candidate_rejected_safely(bad_table, bad_columns):
    """Malformed candidate definitions must be rejected before reaching the database."""
    request = HypotheticalIndexRequest(
        query="SELECT * FROM orders",
        table=bad_table,
        columns=bad_columns,
    )

    result = HypoPGValidatorService.validate_candidate(request)
    assert result.verdict == ValidationVerdict.INVALID_CANDIDATE
    assert result.error_message is not None


# ---------------------------------------------------------------------------
# Test 10: SQL injection resistance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "malicious_fragment",
    [
        "customer_id); DROP TABLE orders; --",
        "customer_id) WHERE id = 1; DELETE FROM orders; --",
        "customer_id); CREATE TABLE pwned (id int); --",
        "'; DROP TABLE orders; --",
    ],
)
def test_sql_injection_in_candidate_rejected(malicious_fragment):
    """Candidates containing SQL injection attempts must NEVER reach the database as DDL."""
    with pytest.raises(InvalidCandidateError):
        HypoPGValidatorService.build_candidate_index_sql(
            table="orders",
            columns=[malicious_fragment],
        )

    # Full validate_candidate call must return INVALID_CANDIDATE safely
    request = HypotheticalIndexRequest(
        query="SELECT * FROM orders WHERE customer_id = 42",
        table="orders",
        columns=[malicious_fragment],
    )
    result = HypoPGValidatorService.validate_candidate(request)
    assert result.verdict == ValidationVerdict.INVALID_CANDIDATE

    # Verify orders table exists and has 5,000 rows
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM orders;")).scalar()
        assert count == 5000, "Table was modified by injection attempt!"


# ---------------------------------------------------------------------------
# Test 11: Cleanup after validation
# ---------------------------------------------------------------------------

def test_hypopg_state_cleaned_up_after_validation():
    """Verify that after validation, no hypothetical indexes persist in the session."""
    request = HypotheticalIndexRequest(
        query="SELECT * FROM orders WHERE customer_id = 42",
        table="orders",
        columns=["customer_id"],
    )

    result = HypoPGValidatorService.validate_candidate(request)
    assert result.verdict == ValidationVerdict.VALIDATED

    # In a new connection, or inspecting hypopg(), there should be no indexes
    with engine.connect() as conn:
        indexes = conn.execute(text("SELECT * FROM hypopg();")).fetchall()
        assert len(indexes) == 0, f"HypoPG indexes were not cleaned up: {indexes}"


# ---------------------------------------------------------------------------
# Test 12: Cleanup on exception
# ---------------------------------------------------------------------------

def test_cleanup_occurs_even_on_database_exception():
    """Verify that if an error occurs during validation, hypopg_reset is still invoked."""
    with engine.connect() as conn:
        # Run validation with a query that causes a database error (e.g. non-existent table)
        request = HypotheticalIndexRequest(
            query="SELECT * FROM non_existent_table_xyz_123 WHERE id = 1",
            table="orders",
            columns=["customer_id"],
        )
        result = HypoPGValidatorService.validate_candidate(request)
        assert result.verdict == ValidationVerdict.ERROR

        # Verify state is clean
        indexes = conn.execute(text("SELECT * FROM hypopg();")).fetchall()
        assert len(indexes) == 0


# ---------------------------------------------------------------------------
# Test 13: Multiple validations do not contaminate each other
# ---------------------------------------------------------------------------

def test_multiple_validations_isolation():
    """Sequentially validating different candidates must not leak hypothetical indexes."""
    req1 = HypotheticalIndexRequest(
        query="SELECT * FROM orders WHERE customer_id = 42",
        table="orders",
        columns=["customer_id"],
    )
    req2 = HypotheticalIndexRequest(
        query="SELECT * FROM products WHERE category = 'Electronics'",
        table="products",
        columns=["category"],
    )

    res1 = HypoPGValidatorService.validate_candidate(req1)
    res2 = HypoPGValidatorService.validate_candidate(req2)

    assert res1.candidate_index == "CREATE INDEX ON orders (customer_id)"
    assert res2.candidate_index == "CREATE INDEX ON products (category)"

    # Verify no lingering indexes
    with engine.connect() as conn:
        indexes = conn.execute(text("SELECT * FROM hypopg();")).fetchall()
        assert len(indexes) == 0


# ---------------------------------------------------------------------------
# Test 14: Determinism
# ---------------------------------------------------------------------------

def test_validation_determinism():
    """Identical query + candidate index + database state must produce identical results."""
    request = HypotheticalIndexRequest(
        query="SELECT * FROM orders WHERE customer_id = 42",
        table="orders",
        columns=["customer_id"],
    )

    res1 = HypoPGValidatorService.validate_candidate(request)
    res2 = HypoPGValidatorService.validate_candidate(request)

    assert res1.verdict == res2.verdict
    assert res1.comparison.original_cost == res2.comparison.original_cost
    assert res1.comparison.hypothetical_cost == res2.comparison.hypothetical_cost
    assert res1.comparison.cost_improvement_percent == res2.comparison.cost_improvement_percent
    assert res1.comparison.plan_changed == res2.comparison.plan_changed
