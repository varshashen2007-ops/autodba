"""
Bottleneck Detector Service
============================
A deterministic, rule-based engine that inspects a parsed plan tree and
produces :class:`BottleneckFinding` instances for potential performance issues.

Design principles
-----------------
- Rules produce *evidence + heuristic + confidence*, not absolute judgments.
- A sequential scan is not automatically bad.  The detector considers estimated
  row counts, filter presence, and cost before raising a finding.
- Every threshold is read from :class:`~app.core.config.Settings` so behaviour
  can be adjusted via environment variables without code changes.
- Rules are independent and composable: adding a new rule does not require
  modifying existing ones.

Rule catalogue (Phase 2 Step 1)
--------------------------------
A  FILTERED_SEQ_SCAN   Seq Scan / Parallel Seq Scan with a filter on a
                        relation large enough to be an index candidate.
B  EXPENSIVE_SORT       Sort / Incremental Sort above cost threshold.
C  EXPENSIVE_NESTED_LOOP  Nested Loop above cost threshold.
D  LARGE_ROW_ESTIMATE   Any node whose plan_rows exceeds the large-row threshold.
E  MISSING_INDEX        Seq Scan + filter where estimated rows suggest a real
                        table scan that an index might avoid.
"""

from __future__ import annotations

from typing import List

from app.core.config import Settings, get_settings
from app.schemas.optimization import (
    BottleneckFinding,
    BottleneckType,
    Confidence,
    PlanNode,
    Severity,
)
from app.services.plan_analyzer import flatten_nodes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_seq_scan(node: PlanNode) -> bool:
    return node.node_type in ("Seq Scan", "Parallel Seq Scan")


def _is_sort(node: PlanNode) -> bool:
    return node.node_type in ("Sort", "Incremental Sort")


def _is_nested_loop(node: PlanNode) -> bool:
    return node.node_type == "Nested Loop"


# ---------------------------------------------------------------------------
# Rule A + E  —  Filtered sequential scan / potential missing index
# ---------------------------------------------------------------------------

def _rule_filtered_seq_scan(
    node: PlanNode,
    settings: Settings,
) -> List[BottleneckFinding]:
    """Rule A / E: Seq Scan with a filter on a sufficiently large relation.

    Two overlapping findings may be produced:
    - FILTERED_SEQ_SCAN (always when filter present and rows >= threshold)
    - MISSING_INDEX (higher confidence, when rows >> threshold)

    A Seq Scan on a 10-row lookup table with no filter is optimal; we do not
    flag it.
    """
    findings: List[BottleneckFinding] = []
    if not _is_seq_scan(node):
        return findings

    rows = node.plan_rows or 0
    cost = node.total_cost or 0.0
    has_filter = bool(node.filter)
    relation = node.relation_name or "<unknown>"
    min_rows = settings.PLAN_SEQ_SCAN_MIN_ROWS
    min_cost = getattr(settings, "PLAN_SEQ_SCAN_MIN_COST", 50.0)
    high_cost_thresh = settings.PLAN_HIGH_COST_THRESHOLD
    large_row_thresh = settings.PLAN_LARGE_ROW_THRESHOLD

    if has_filter:
        # A filtered sequential scan is an evaluation candidate if either:
        # 1. Total cost indicates substantial scanning I/O (cost >= min_cost), OR
        # 2. Estimated rows exceed the minimum rows threshold.
        # For small tables (cost < min_cost AND rows < min_rows), suppress finding.
        if cost < min_cost and rows < min_rows:
            return findings

        evidence = {
            "node_type": node.node_type,
            "relation": relation,
            "filter": node.filter,
            "estimated_rows": rows,
            "total_cost": cost,
            "min_rows_threshold": min_rows,
            "min_cost_threshold": min_cost,
            "high_cost_threshold": high_cost_thresh,
            "large_row_threshold": large_row_thresh,
        }

        # Severity and confidence must NOT be HIGH solely from filter presence and moderate cost.
        # HIGH severity/confidence is reserved for genuinely expensive scans crossing high thresholds.
        is_genuinely_expensive = (cost >= high_cost_thresh) or (rows >= large_row_thresh)
        is_moderate = (cost >= min_cost * 2) or (rows >= min_rows)

        if is_genuinely_expensive:
            confidence = Confidence.HIGH
            severity = Severity.HIGH
        elif is_moderate:
            confidence = Confidence.MEDIUM
            severity = Severity.MEDIUM
        else:
            confidence = Confidence.LOW
            severity = Severity.LOW

        findings.append(
            BottleneckFinding(
                finding_type=BottleneckType.FILTERED_SEQ_SCAN,
                severity=severity,
                confidence=confidence,
                title=f"Filtered sequential scan on '{relation}' (candidate for review)",
                description=(
                    f"A sequential scan on '{relation}' evaluated filter '{node.filter}' "
                    f"with estimated cost {cost:.1f} and {rows:,} estimated rows. "
                    f"Sequential scans can be appropriate for smaller tables or queries with low selectivity, "
                    f"but may represent an optimization opportunity if execution frequency is high. "
                    f"Candidate requires validation to determine if an alternate plan is warranted."
                ),
                relation=relation,
                evidence=evidence,
                estimated_impact=(
                    f"Potential candidate: table '{relation}' was scanned sequentially (cost {cost:.1f}). "
                    f"Actual impact depends on execution frequency and selectivity."
                ),
            )
        )

        # MISSING_INDEX — frames as a potential candidate requiring HypoPG validation
        findings.append(
            BottleneckFinding(
                finding_type=BottleneckType.MISSING_INDEX,
                severity=severity,
                confidence=confidence,
                title=f"Potential missing-index candidate on '{relation}'",
                description=(
                    f"The planner chose a sequential scan on '{relation}' (cost {cost:.1f}) "
                    f"with filter '{node.filter}'. An index on the filtered column(s) may "
                    f"potentially allow an index scan, but index utility is not guaranteed "
                    f"and depends on selectivity, table size, and write overhead. "
                    f"HypoPG validation is required to demonstrate whether an index provides genuine benefit."
                ),
                relation=relation,
                evidence=evidence,
                estimated_impact=(
                    "Potential candidate for index evaluation. Benefit cannot be confirmed "
                    "until HypoPG simulation demonstrates an improved execution plan and cost."
                ),
                recommendation=(
                    f"Candidate only: test a candidate index on the column(s) in filter '{node.filter}' "
                    f"using HypoPG simulation to measure if the planner achieves a lower-cost plan "
                    f"before considering physical index creation."
                ),
            )
        )
    else:
        # Seq Scan without a filter — return all rows; only flag if rows are very large
        if rows < min_rows:
            return findings

        if rows >= large_row_thresh:
            findings.append(
                BottleneckFinding(
                    finding_type=BottleneckType.FILTERED_SEQ_SCAN,
                    severity=Severity.LOW,
                    confidence=Confidence.LOW,
                    title=f"Large full-table sequential scan on '{relation}'",
                    description=(
                        f"A sequential scan on '{relation}' returns an estimated "
                        f"{rows:,} rows without any row filter. This may be "
                        f"intentional (e.g. a bulk export), but could be a concern "
                        f"if the query is called frequently."
                    ),
                    relation=relation,
                    evidence={
                        "node_type": node.node_type,
                        "relation": relation,
                        "estimated_rows": rows,
                        "total_cost": cost,
                        "filter": None,
                    },
                    estimated_impact="Moderate: full table scan on a large relation.",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Rule B — Expensive Sort
# ---------------------------------------------------------------------------

def _rule_expensive_sort(
    node: PlanNode,
    settings: Settings,
) -> List[BottleneckFinding]:
    """Rule B: Sort or Incremental Sort node whose total cost exceeds the threshold."""
    if not _is_sort(node):
        return []

    cost = node.total_cost or 0.0
    rows = node.plan_rows or 0
    threshold = settings.PLAN_SORT_COST_THRESHOLD

    if cost < threshold:
        return []

    confidence = Confidence.HIGH if cost >= threshold * 2 else Confidence.MEDIUM
    severity = Severity.HIGH if cost >= threshold * 3 else Severity.MEDIUM

    return [
        BottleneckFinding(
            finding_type=BottleneckType.EXPENSIVE_SORT,
            severity=severity,
            confidence=confidence,
            title=f"Expensive {node.node_type} (cost {cost:.1f})",
            description=(
                f"A {node.node_type} node has an estimated cost of {cost:.1f}, "
                f"which exceeds the configured threshold of {threshold:.1f}. "
                f"This sort operates on an estimated {rows:,} rows. Adding a "
                f"covering index or rewriting the ORDER BY clause might eliminate "
                f"or reduce the sort."
            ),
            relation=node.relation_name,
            evidence={
                "node_type": node.node_type,
                "total_cost": cost,
                "estimated_rows": rows,
                "sort_cost_threshold": threshold,
            },
            estimated_impact=(
                f"Sort with cost {cost:.1f} may dominate query time for "
                f"large result sets."
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Rule C — Expensive Nested Loop
# ---------------------------------------------------------------------------

def _rule_expensive_nested_loop(
    node: PlanNode,
    settings: Settings,
) -> List[BottleneckFinding]:
    """Rule C: Nested Loop join whose total cost exceeds the threshold."""
    if not _is_nested_loop(node):
        return []

    cost = node.total_cost or 0.0
    rows = node.plan_rows or 0
    threshold = settings.PLAN_NESTED_LOOP_COST_THRESHOLD

    if cost < threshold:
        return []

    confidence = Confidence.MEDIUM  # Nested loops can be intentional
    severity = Severity.HIGH if cost >= threshold * 2 else Severity.MEDIUM

    return [
        BottleneckFinding(
            finding_type=BottleneckType.EXPENSIVE_NESTED_LOOP,
            severity=severity,
            confidence=confidence,
            title=f"Potentially expensive Nested Loop join (cost {cost:.1f})",
            description=(
                f"A Nested Loop join has an estimated cost of {cost:.1f}, exceeding "
                f"the threshold of {threshold:.1f}. Nested loops are sometimes "
                f"optimal for small inner relations, but can be expensive when the "
                f"outer side is large. An index on the inner-side join column may "
                f"help, or the planner may prefer a Hash Join at larger scales."
            ),
            relation=node.relation_name,
            evidence={
                "node_type": node.node_type,
                "total_cost": cost,
                "estimated_rows": rows,
                "nested_loop_cost_threshold": threshold,
                "join_type": node.join_type,
            },
            estimated_impact=(
                f"Nested loop with cost {cost:.1f} may scale poorly as the outer "
                f"relation grows."
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Rule D — Large row estimate
# ---------------------------------------------------------------------------

def _rule_large_row_estimate(
    node: PlanNode,
    settings: Settings,
) -> List[BottleneckFinding]:
    """Rule D: Any node whose estimated output exceeds the large-row threshold."""
    rows = node.plan_rows or 0
    threshold = settings.PLAN_LARGE_ROW_THRESHOLD

    if rows < threshold:
        return []

    # Don't double-report a filtered seq scan as both FILTERED_SEQ_SCAN and LARGE_ROW
    # if a seq scan with filter already fires rule A/E.
    if _is_seq_scan(node) and node.filter:
        return []

    confidence = Confidence.MEDIUM
    severity = Severity.MEDIUM if rows < threshold * 5 else Severity.HIGH

    return [
        BottleneckFinding(
            finding_type=BottleneckType.LARGE_ROW_ESTIMATE,
            severity=severity,
            confidence=confidence,
            title=f"Large estimated row count ({rows:,}) at '{node.node_type}'",
            description=(
                f"The plan node '{node.node_type}' is estimated to produce "
                f"{rows:,} rows, exceeding the threshold of {threshold:,}. "
                f"Large row estimates can propagate through the plan and inflate "
                f"memory usage and query time."
            ),
            relation=node.relation_name,
            evidence={
                "node_type": node.node_type,
                "estimated_rows": rows,
                "large_row_threshold": threshold,
                "total_cost": node.total_cost,
                "relation": node.relation_name,
            },
            estimated_impact=(
                f"Processing {rows:,} rows may cause memory pressure and "
                f"increased CPU time."
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

ALL_RULES = [
    _rule_filtered_seq_scan,
    _rule_expensive_sort,
    _rule_expensive_nested_loop,
    _rule_large_row_estimate,
]


class BottleneckDetector:
    """Applies all detection rules to a PlanNode tree.

    Usage::

        findings = BottleneckDetector.detect(root_node)
        findings = BottleneckDetector.detect(root_node, settings=custom_settings)
    """

    @classmethod
    def detect(
        cls,
        root_node: PlanNode,
        settings: Settings | None = None,
    ) -> List[BottleneckFinding]:
        """Walk the full plan tree and return all bottleneck findings.

        Parameters
        ----------
        root_node:
            The root PlanNode returned by :meth:`PlanAnalyzer.analyze`.
        settings:
            Optional Settings override.  Defaults to the process-level singleton.

        Returns
        -------
        List of BottleneckFinding, ordered by traversal order (pre-order).
        Findings within the same node follow rule-declaration order.
        """
        cfg = settings or get_settings()
        findings: List[BottleneckFinding] = []

        for node in flatten_nodes(root_node):
            for rule in ALL_RULES:
                findings.extend(rule(node, cfg))

        return findings
