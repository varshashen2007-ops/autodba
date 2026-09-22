"""
Unit tests for PlanAnalyzer.

Covers:
  - Simple Seq Scan (single node)
  - Nested plan tree (Sort → Seq Scan)
  - Deep tree (Limit → Sort → Nested Loop → [Seq Scan, Index Scan])
  - Missing optional fields (no relation, no cost, no filter)
  - Multiple children (Hash Join with two children)
  - Summary statistics correctness
  - flatten_nodes helper
  - EXPLAIN ANALYZE output (actual_rows present)
"""

import pytest
from app.services.plan_analyzer import PlanAnalyzer, flatten_nodes
from app.schemas.optimization import PlanNode


# ---------------------------------------------------------------------------
# Fixtures: raw EXPLAIN JSON blobs
# ---------------------------------------------------------------------------

SEQ_SCAN_PLAN = [
    {
        "Plan": {
            "Node Type": "Seq Scan",
            "Relation Name": "orders",
            "Alias": "orders",
            "Startup Cost": 0.0,
            "Total Cost": 107.5,
            "Plan Rows": 5000,
            "Actual Rows": 4998,
            "Filter": "(customer_id = 42)",
            "Parallel Aware": False,
        }
    }
]

SORT_SEQ_SCAN_PLAN = [
    {
        "Plan": {
            "Node Type": "Sort",
            "Startup Cost": 432.39,
            "Total Cost": 444.89,
            "Plan Rows": 5000,
            "Sort Key": ["total_amount DESC"],
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Alias": "orders",
                    "Startup Cost": 0.0,
                    "Total Cost": 107.5,
                    "Plan Rows": 5000,
                    "Filter": "(status = 'completed')",
                }
            ],
        }
    }
]

LIMIT_SORT_SEQ_PLAN = [
    {
        "Plan": {
            "Node Type": "Limit",
            "Startup Cost": 432.39,
            "Total Cost": 432.41,
            "Plan Rows": 10,
            "Plans": [
                {
                    "Node Type": "Sort",
                    "Startup Cost": 432.39,
                    "Total Cost": 444.89,
                    "Plan Rows": 5000,
                    "Plans": [
                        {
                            "Node Type": "Seq Scan",
                            "Relation Name": "orders",
                            "Startup Cost": 0.0,
                            "Total Cost": 107.5,
                            "Plan Rows": 5000,
                        }
                    ],
                }
            ],
        }
    }
]

NESTED_LOOP_PLAN = [
    {
        "Plan": {
            "Node Type": "Nested Loop",
            "Startup Cost": 0.0,
            "Total Cost": 2500.0,
            "Plan Rows": 15000,
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
                    "Node Type": "Index Scan",
                    "Relation Name": "order_items",
                    "Alias": "oi",
                    "Startup Cost": 0.0,
                    "Total Cost": 0.45,
                    "Plan Rows": 3,
                    "Index Cond": "(order_id = orders.id)",
                },
            ],
        }
    }
]

MINIMAL_PLAN = [
    {
        "Plan": {
            "Node Type": "Result",
        }
    }
]

HASH_JOIN_PLAN = [
    {
        "Plan": {
            "Node Type": "Hash Join",
            "Startup Cost": 15.75,
            "Total Cost": 350.0,
            "Plan Rows": 500,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "customers",
                    "Startup Cost": 0.0,
                    "Total Cost": 12.5,
                    "Plan Rows": 500,
                },
                {
                    "Node Type": "Hash",
                    "Startup Cost": 10.0,
                    "Total Cost": 10.0,
                    "Plan Rows": 100,
                    "Plans": [
                        {
                            "Node Type": "Seq Scan",
                            "Relation Name": "products",
                            "Startup Cost": 0.0,
                            "Total Cost": 5.0,
                            "Plan Rows": 100,
                        }
                    ],
                },
            ],
        }
    }
]


# ---------------------------------------------------------------------------
# Simple Seq Scan
# ---------------------------------------------------------------------------

def test_parse_simple_seq_scan():
    root, count, summary = PlanAnalyzer.analyze(SEQ_SCAN_PLAN, query="SELECT * FROM orders")

    assert root.node_type == "Seq Scan"
    assert root.relation_name == "orders"
    assert root.alias == "orders"
    assert root.startup_cost == 0.0
    assert root.total_cost == 107.5
    assert root.plan_rows == 5000
    assert root.actual_rows == 4998
    assert root.filter == "(customer_id = 42)"
    assert root.children == []

    assert count == 1
    assert summary.total_nodes == 1
    assert summary.total_estimated_cost == 107.5
    assert summary.scan_nodes == 1
    assert summary.has_seq_scans is True
    assert summary.has_index_scans is False


def test_simple_seq_scan_extra_fields_captured():
    """Fields not in the first-class set must land in node.extra."""
    root, _, _ = PlanAnalyzer.analyze(SEQ_SCAN_PLAN, query="SELECT 1")
    assert "Parallel Aware" in root.extra


# ---------------------------------------------------------------------------
# Sort → Seq Scan
# ---------------------------------------------------------------------------

def test_parse_sort_seq_scan_tree():
    root, count, summary = PlanAnalyzer.analyze(SORT_SEQ_SCAN_PLAN, query="SELECT * FROM orders ORDER BY total_amount")

    assert root.node_type == "Sort"
    assert root.total_cost == 444.89
    assert len(root.children) == 1

    child = root.children[0]
    assert child.node_type == "Seq Scan"
    assert child.relation_name == "orders"
    assert child.filter == "(status = 'completed')"

    assert count == 2
    assert summary.scan_nodes == 1
    assert summary.sort_nodes == 1
    assert summary.has_seq_scans is True


# ---------------------------------------------------------------------------
# Limit → Sort → Seq Scan (three levels)
# ---------------------------------------------------------------------------

def test_parse_three_level_tree():
    root, count, summary = PlanAnalyzer.analyze(LIMIT_SORT_SEQ_PLAN, query="SELECT * FROM orders LIMIT 10")

    assert root.node_type == "Limit"
    assert count == 3

    sort_node = root.children[0]
    assert sort_node.node_type == "Sort"

    seq_node = sort_node.children[0]
    assert seq_node.node_type == "Seq Scan"
    assert seq_node.relation_name == "orders"

    assert summary.sort_nodes == 1
    assert summary.scan_nodes == 1


# ---------------------------------------------------------------------------
# Nested Loop with two children
# ---------------------------------------------------------------------------

def test_parse_nested_loop():
    root, count, summary = PlanAnalyzer.analyze(NESTED_LOOP_PLAN, query="SELECT * FROM orders JOIN order_items")

    assert root.node_type == "Nested Loop"
    assert root.join_type == "Inner"
    assert len(root.children) == 2
    assert count == 3

    seq_child = root.children[0]
    assert seq_child.node_type == "Seq Scan"
    assert seq_child.relation_name == "orders"

    idx_child = root.children[1]
    assert idx_child.node_type == "Index Scan"
    assert idx_child.relation_name == "order_items"
    assert idx_child.index_cond == "(order_id = orders.id)"

    assert summary.join_nodes == 1
    assert summary.scan_nodes == 2
    assert summary.has_index_scans is True
    assert summary.has_seq_scans is True


# ---------------------------------------------------------------------------
# Minimal plan — missing optional fields
# ---------------------------------------------------------------------------

def test_parse_minimal_plan_missing_fields():
    """A plan node with only Node Type must not raise."""
    root, count, summary = PlanAnalyzer.analyze(MINIMAL_PLAN, query="SELECT 1")

    assert root.node_type == "Result"
    assert root.relation_name is None
    assert root.startup_cost is None
    assert root.total_cost is None
    assert root.plan_rows is None
    assert root.filter is None
    assert root.index_cond is None
    assert root.children == []
    assert count == 1
    assert summary.total_estimated_cost == 0.0


# ---------------------------------------------------------------------------
# Hash Join with nested Hash child (multiple children at different depths)
# ---------------------------------------------------------------------------

def test_parse_hash_join_multiple_children():
    root, count, summary = PlanAnalyzer.analyze(HASH_JOIN_PLAN, query="SELECT * FROM customers JOIN products")

    assert root.node_type == "Hash Join"
    assert len(root.children) == 2
    # Total nodes: Hash Join + Seq Scan (customers) + Hash + Seq Scan (products) = 4
    assert count == 4

    # customers child
    assert root.children[0].node_type == "Seq Scan"
    assert root.children[0].relation_name == "customers"

    # Hash child wrapping products seq scan
    hash_node = root.children[1]
    assert hash_node.node_type == "Hash"
    assert len(hash_node.children) == 1
    assert hash_node.children[0].relation_name == "products"

    assert summary.scan_nodes == 2
    assert summary.join_nodes == 1


# ---------------------------------------------------------------------------
# Summary max_estimated_rows
# ---------------------------------------------------------------------------

def test_summary_max_estimated_rows():
    _, _, summary = PlanAnalyzer.analyze(NESTED_LOOP_PLAN, query="q")
    # Nested Loop: 15000, Seq Scan orders: 5000, Index Scan order_items: 3
    assert summary.max_estimated_rows == 15000


# ---------------------------------------------------------------------------
# flatten_nodes helper
# ---------------------------------------------------------------------------

def test_flatten_nodes_order():
    """flatten_nodes must return nodes in pre-order (root first, depth-first)."""
    root, _, _ = PlanAnalyzer.analyze(SORT_SEQ_SCAN_PLAN, query="q")
    flat = flatten_nodes(root)
    assert len(flat) == 2
    assert flat[0].node_type == "Sort"
    assert flat[1].node_type == "Seq Scan"


def test_flatten_nodes_three_levels():
    root, _, _ = PlanAnalyzer.analyze(LIMIT_SORT_SEQ_PLAN, query="q")
    flat = flatten_nodes(root)
    types = [n.node_type for n in flat]
    assert types == ["Limit", "Sort", "Seq Scan"]


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_empty_plan_raises():
    with pytest.raises(ValueError, match="empty"):
        PlanAnalyzer.analyze([], query="SELECT 1")


def test_plan_without_plan_key_raises():
    with pytest.raises(ValueError, match="'Plan'"):
        PlanAnalyzer.analyze([{"NoPlan": {}}], query="SELECT 1")


# ---------------------------------------------------------------------------
# EXPLAIN ANALYZE output (actual rows)
# ---------------------------------------------------------------------------

def test_actual_rows_parsed_from_analyze_output():
    """Actual Rows from EXPLAIN ANALYZE must be captured in actual_rows."""
    plan = [
        {
            "Plan": {
                "Node Type": "Seq Scan",
                "Relation Name": "orders",
                "Plan Rows": 5000,
                "Actual Rows": 4998,
                "Actual Startup Time": 0.05,
                "Actual Total Time": 2.34,
                "Actual Loops": 1,
            }
        }
    ]
    root, _, _ = PlanAnalyzer.analyze(plan, query="SELECT * FROM orders")
    assert root.actual_rows == 4998
    assert "Actual Startup Time" in root.extra
