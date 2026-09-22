"""
Plan Analyzer Service
=====================
Parses PostgreSQL ``EXPLAIN (FORMAT JSON)`` output into a typed PlanNode tree
and computes summary statistics across the full tree.

The analyzer is deliberately decoupled from bottleneck detection: it only
parses and normalizes.  The BottleneckDetector applies rules on top.

PostgreSQL plan JSON structure
------------------------------
A top-level EXPLAIN result is a JSON *array* containing one element::

    [
        {
            "Plan": { ... },
            "Planning Time": 0.123,   # only with ANALYZE
            "Execution Time": 4.56    # only with ANALYZE
        }
    ]

Each plan node may contain a ``"Plans"`` array of child node objects (not
wrapped in the outer ``{"Plan": ...}`` envelope — they are raw node dicts).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas.optimization import PlanNode, PlanSummary


# ---------------------------------------------------------------------------
# Field mapping helpers
# ---------------------------------------------------------------------------

# Node types that perform a scan on a base relation
_SCAN_TYPES = frozenset(
    {
        "Seq Scan",
        "Parallel Seq Scan",
        "Index Scan",
        "Index Only Scan",
        "Bitmap Heap Scan",
        "Bitmap Index Scan",
        "Tid Scan",
        "Function Scan",
        "Values Scan",
        "CTE Scan",
        "Foreign Scan",
        "Custom Scan",
    }
)

# Node types that perform a join
_JOIN_TYPES = frozenset({"Nested Loop", "Hash Join", "Merge Join"})

# Node types that perform a sort
_SORT_TYPES = frozenset({"Sort", "Incremental Sort"})

# Node types that use an index
_INDEX_TYPES = frozenset({"Index Scan", "Index Only Scan", "Bitmap Index Scan"})


# ---------------------------------------------------------------------------
# PlanAnalyzer
# ---------------------------------------------------------------------------

class PlanAnalyzer:
    """Parses and normalizes PostgreSQL EXPLAIN JSON into a PlanNode tree.

    Usage::

        result = PlanAnalyzer.analyze(raw_plan, query="SELECT ...")
    """

    @classmethod
    def analyze(
        cls,
        raw_plan: List[Dict[str, Any]],
        query: str,
    ) -> tuple[PlanNode, int, PlanSummary]:
        """Parse a raw EXPLAIN JSON plan into a PlanNode tree.

        Parameters
        ----------
        raw_plan:
            The list returned by ``EXPLAIN (FORMAT JSON)``.
        query:
            The original SQL query string (for context only; not parsed here).

        Returns
        -------
        tuple of (root_node, nodes_analyzed, summary)
        """
        if not raw_plan:
            raise ValueError("raw_plan is empty — cannot parse an empty EXPLAIN result")

        # The top-level object wraps the root plan node
        top = raw_plan[0]
        root_dict = top.get("Plan")
        if root_dict is None:
            raise ValueError("EXPLAIN JSON does not contain a 'Plan' key in the first element")

        # Accumulators
        all_nodes: list[PlanNode] = []
        root_node = cls._parse_node(root_dict, all_nodes)

        summary = cls._build_summary(root_node, all_nodes)
        return root_node, len(all_nodes), summary

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _parse_node(
        cls,
        node_dict: Dict[str, Any],
        accumulator: list[PlanNode],
    ) -> PlanNode:
        """Recursively parse one plan node dict into a PlanNode.

        Missing fields are handled by defaulting to None rather than raising.
        """
        # Extract known first-class fields
        node_type = node_dict.get("Node Type", "Unknown")

        # Collect known fields into the model
        plan_rows_raw = node_dict.get("Plan Rows")
        actual_rows_raw = node_dict.get("Actual Rows")

        known_keys = {
            "Node Type", "Relation Name", "Alias",
            "Startup Cost", "Total Cost", "Plan Rows", "Actual Rows",
            "Filter", "Index Cond", "Join Type", "Plans",
        }
        extra = {k: v for k, v in node_dict.items() if k not in known_keys}

        # Recursively parse children
        children: list[PlanNode] = []
        for child_dict in node_dict.get("Plans", []):
            children.append(cls._parse_node(child_dict, accumulator))

        node = PlanNode(
            node_type=node_type,
            relation_name=node_dict.get("Relation Name"),
            alias=node_dict.get("Alias"),
            startup_cost=node_dict.get("Startup Cost"),
            total_cost=node_dict.get("Total Cost"),
            plan_rows=int(plan_rows_raw) if plan_rows_raw is not None else None,
            actual_rows=int(actual_rows_raw) if actual_rows_raw is not None else None,
            filter=node_dict.get("Filter"),
            index_cond=node_dict.get("Index Cond"),
            join_type=node_dict.get("Join Type"),
            children=children,
            extra=extra,
        )
        accumulator.append(node)
        return node

    @classmethod
    def _build_summary(
        cls,
        root: PlanNode,
        all_nodes: list[PlanNode],
    ) -> PlanSummary:
        """Compute aggregate statistics across all parsed plan nodes."""
        scan_count = sum(1 for n in all_nodes if n.node_type in _SCAN_TYPES)
        join_count = sum(1 for n in all_nodes if n.node_type in _JOIN_TYPES)
        sort_count = sum(1 for n in all_nodes if n.node_type in _SORT_TYPES)

        has_seq_scans = any(
            n.node_type in ("Seq Scan", "Parallel Seq Scan") for n in all_nodes
        )
        has_index_scans = any(n.node_type in _INDEX_TYPES for n in all_nodes)

        max_rows = max(
            (n.plan_rows for n in all_nodes if n.plan_rows is not None),
            default=0,
        )

        return PlanSummary(
            total_nodes=len(all_nodes),
            total_estimated_cost=root.total_cost or 0.0,
            max_estimated_rows=max_rows,
            scan_nodes=scan_count,
            join_nodes=join_count,
            sort_nodes=sort_count,
            has_seq_scans=has_seq_scans,
            has_index_scans=has_index_scans,
            findings_count=0,  # will be patched by caller after detection
        )


def flatten_nodes(root: PlanNode) -> List[PlanNode]:
    """Return all nodes in the plan tree in pre-order (root first)."""
    result: List[PlanNode] = [root]
    for child in root.children:
        result.extend(flatten_nodes(child))
    return result
