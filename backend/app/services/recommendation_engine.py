"""
Optimization Recommendation Engine Service
===========================================
Deterministic, rule-based recommendation engine for database query optimizations.

Grounded strictly in:
  1. PostgreSQL EXPLAIN execution plan evidence (Phase 2 Step 1).
  2. HypoPG counterfactual planner validation (Phase 2 Step 2).

Guarantees:
  - Completely deterministic; no LLM, RAG, or heuristic guesswork.
  - Never executes SQL against the database.
  - Never creates physical indexes.
  - Never hallucinates table columns (only safe identifier extraction from predicates).
  - All SQL generation is preview-only (never auto-executed).
  - requires_human_approval is True on all advisory database recommendations.

Confidence Rules (deterministic):
  HIGH   : HypoPG verdict VALIDATED + clear bottleneck + meaningful cost improvement.
  MEDIUM : Bottleneck evidence exists but HypoPG unavailable or inconclusive.
  LOW    : Weak evidence, ambiguous plan, or heuristic only.

Risk Rules (deterministic):
  LOW    : Single-column B-tree index validated by HypoPG.
  MEDIUM : Multi-column index, sort/join investigation (write-overhead uncertainty).
  HIGH   : Unvalidated candidate, regression detected, or unusual index method.

Status Rules (deterministic):
  VALIDATED      : HypoPG verdict == VALIDATED.
  REJECTED       : HypoPG shows NO_IMPROVEMENT or REGRESSION.
  UNVALIDATED    : No HypoPG result available.
  REQUIRES_REVIEW: Validation failed (ERROR / INVALID_CANDIDATE).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.core.config import Settings
from app.core.logging import log_operation
from app.schemas.optimization import (
    BottleneckFinding,
    BottleneckType,
    HypoPGValidationResult,
    IndexMethod,
    OptimizationRecommendation,
    OptimizationType,
    RecommendationConfidence,
    RecommendationRisk,
    RecommendationStatus,
    ValidationVerdict,
)
from app.services.hypopg_validator import HypoPGValidatorService, InvalidCandidateError


# SQL tokens excluded from filter column extraction
_EXCLUDED_FILTER_TOKENS = frozenset({
    "AND", "OR", "NOT", "NULL", "TRUE", "FALSE", "CASE", "WHEN", "THEN",
    "ELSE", "END", "SELECT", "FROM", "WHERE", "JOIN", "ON", "AS", "IN",
    "IS", "LIKE", "ILIKE", "BETWEEN", "EXISTS", "ANY", "ALL", "SOME",
    "CAST", "TEXT", "INTEGER", "BIGINT", "DATE", "TIMESTAMP", "BOOLEAN",
    "NUMERIC", "FLOAT", "VARCHAR", "CHAR",
})

# Identifier followed by a comparison operator (not a function call)
_FILTER_OPERAND_RE = re.compile(
    r"\b([a-zA-Z_][a-zA-Z0-9_]*)(?!\s*\()\s*(?:=|<=|>=|!=|<>|<|>)",
    re.IGNORECASE,
)


class RecommendationEngine:
    """Deterministic recommendation engine for database query optimizations."""

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    @classmethod
    def extract_candidate_columns(cls, finding: BottleneckFinding) -> List[str]:
        """Safely extract candidate columns from finding evidence without hallucination."""
        evidence = finding.evidence or {}

        # 1. Explicit list
        if isinstance(evidence.get("columns"), list):
            cols: List[str] = []
            for col in evidence["columns"]:
                try:
                    safe = HypoPGValidatorService.validate_identifier(str(col), "column name")
                    if safe not in cols:
                        cols.append(safe)
                except InvalidCandidateError:
                    pass
            if cols:
                return cols

        # 2. Single column key
        if isinstance(evidence.get("column"), str):
            try:
                return [HypoPGValidatorService.validate_identifier(evidence["column"], "column name")]
            except InvalidCandidateError:
                pass

        # 3. Parse filter predicate
        filter_str = evidence.get("filter")
        if not isinstance(filter_str, str):
            return []

        candidates: List[str] = []
        for token in _FILTER_OPERAND_RE.findall(filter_str):
            if token.upper() in _EXCLUDED_FILTER_TOKENS:
                continue
            try:
                safe = HypoPGValidatorService.validate_identifier(token, "column name")
                if safe not in candidates:
                    candidates.append(safe)
            except InvalidCandidateError:
                continue
        return candidates

    @classmethod
    def build_sql_preview(
        cls,
        table: str,
        columns: List[str],
        index_method: IndexMethod = IndexMethod.BTREE,
    ) -> str:
        """Build a safe, non-executable SQL preview for an index creation statement."""
        safe_table = HypoPGValidatorService.validate_identifier(table, "table name")
        if not columns:
            raise InvalidCandidateError("At least one column required for SQL preview.")
        safe_cols = [HypoPGValidatorService.validate_identifier(c, "column name") for c in columns]
        cols_str = ", ".join(safe_cols)
        if index_method == IndexMethod.BTREE:
            return f"CREATE INDEX ON {safe_table} ({cols_str});"
        return f"CREATE INDEX ON {safe_table} USING {index_method.value} ({cols_str});"

    @classmethod
    def recommend(
        cls,
        finding: BottleneckFinding,
        validation: Optional[HypoPGValidationResult] = None,
        settings: Optional[Settings] = None,
    ) -> OptimizationRecommendation:
        """Generate a deterministic OptimizationRecommendation from a BottleneckFinding."""
        with log_operation("generate_recommendation"):
            if finding.finding_type in (
                BottleneckType.MISSING_INDEX, BottleneckType.FILTERED_SEQ_SCAN
            ):
                return cls._recommend_index(finding, validation, settings)
            if finding.finding_type == BottleneckType.EXPENSIVE_SORT:
                return cls._recommend_sort(finding, settings)
            if finding.finding_type == BottleneckType.EXPENSIVE_NESTED_LOOP:
                return cls._recommend_nested_loop(finding, settings)
            if finding.finding_type == BottleneckType.LARGE_ROW_ESTIMATE:
                return cls._recommend_large_rows(finding, settings)
            return cls._recommend_generic(finding)

    @classmethod
    def recommend_all(
        cls,
        findings: List[BottleneckFinding],
        validations: Optional[Dict[str, HypoPGValidationResult]] = None,
        settings: Optional[Settings] = None,
    ) -> List[OptimizationRecommendation]:
        """Generate recommendations for a list of findings."""
        val_map = validations or {}
        return [
            cls.recommend(f, val_map.get(f.relation or ""), settings)
            for f in findings
        ]

    # -----------------------------------------------------------------------
    # Specialized Handlers
    # -----------------------------------------------------------------------

    @classmethod
    def _recommend_index(
        cls,
        finding: BottleneckFinding,
        validation: Optional[HypoPGValidationResult],
        settings: Optional[Settings],
    ) -> OptimizationRecommendation:
        """MISSING_INDEX / FILTERED_SEQ_SCAN recommendation handler."""
        table = finding.relation or finding.evidence.get("relation")

        # Prefer columns from validation candidate index definition
        columns: List[str] = []
        if validation and validation.candidate_index:
            m = re.search(
                r"CREATE INDEX ON\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+USING\s+\w+)?\s*\(([^)]+)\)",
                validation.candidate_index,
                re.IGNORECASE,
            )
            if m:
                if not table or table == "<unknown>":
                    table = m.group(1).strip()
                columns = [c.strip() for c in m.group(2).split(",") if c.strip()]

        if not columns:
            columns = cls.extract_candidate_columns(finding)

        # Defensive identifier validation
        has_violation = False
        safe_table: Optional[str] = None
        safe_cols: List[str] = []

        if table and table != "<unknown>":
            try:
                safe_table = HypoPGValidatorService.validate_identifier(table, "table name")
            except InvalidCandidateError:
                has_violation = True

        for col in columns:
            try:
                safe_cols.append(HypoPGValidatorService.validate_identifier(col, "column name"))
            except InvalidCandidateError:
                has_violation = True

        if has_violation:
            return OptimizationRecommendation(
                optimization_type=OptimizationType.MISSING_INDEX,
                title="Rejected: unsafe identifier in optimization candidate",
                summary="Candidate identifier failed SQL injection security validation.",
                description=cls._desc(
                    observed=f"Plan filter on \"{table}\": {finding.evidence.get('filter')}.",
                    candidate="Candidate identifier contained invalid SQL characters.",
                    validation_="Rejected before planner simulation for security.",
                    recommendation="Do not create this index candidate.",
                    caveats="Security: identifier rejected by defensive SQL injection validation.",
                ),
                relation=table,
                columns=[],
                recommended_action="Reject candidate: identifier failed safety validation.",
                sql_preview=None,
                status=RecommendationStatus.REJECTED,
                confidence=RecommendationConfidence.LOW,
                risk=RecommendationRisk.HIGH,
                evidence=[
                    f"Filter on \"{table}\" flagged.",
                    "Candidate column validation failed (SQL injection guard).",
                ],
                hypopg_validated=False,
                warnings=["Security: candidate identifier failed SQL injection validation."],
                requires_human_approval=True,
            )

        target = safe_table or table or "relation"
        col_repr = ", ".join(safe_cols) if safe_cols else "filtered column(s)"

        std_tradeoffs = [
            f"Storage: physical index on {target}({col_repr}) consumes disk space and buffer cache.",
            f"Write amplification: INSERT/UPDATE/DELETE on {target} must maintain index pages.",
            "Maintenance: autovacuum required to prevent index bloat over time.",
        ]

        # ---- HypoPG result present ----
        if validation is not None:
            comp = validation.comparison
            orig_cost = (comp.original_cost if comp else None) or finding.evidence.get("total_cost")
            hypo_cost = comp.hypothetical_cost if comp else None
            improvement = comp.cost_improvement_percent if comp else 0.0
            chain = cls._evidence_chain(finding, safe_table, safe_cols, validation)

            # Case A – VALIDATED
            if validation.verdict == ValidationVerdict.VALIDATED:
                sql_prev: Optional[str] = None
                if safe_table and safe_cols:
                    try:
                        sql_prev = cls.build_sql_preview(safe_table, safe_cols)
                    except InvalidCandidateError:
                        pass
                risk = RecommendationRisk.LOW if len(safe_cols) <= 1 else RecommendationRisk.MEDIUM
                plan_chg = (
                    comp.plan_change_summary
                    if comp and comp.plan_change_summary
                    else "sequential scan to index scan"
                )
                # Safe formatting with None guards
                _orig_fmt = f"{orig_cost:.1f}" if orig_cost is not None else "N/A"
                _hypo_fmt = f"{hypo_cost:.1f}" if hypo_cost is not None else "N/A"
                _orig_fmt2 = f"{orig_cost:.2f}" if orig_cost is not None else "N/A"
                _hypo_fmt2 = f"{hypo_cost:.2f}" if hypo_cost is not None else "N/A"
                return OptimizationRecommendation(
                    optimization_type=OptimizationType.MISSING_INDEX,
                    title=f"Create index on {target}({col_repr})",
                    summary=(
                        f"Validated: index on {target}({col_repr}) reduces estimated planner cost "
                        f"by {improvement:.1f}% ({_orig_fmt} -> {_hypo_fmt})."
                    ),
                    description=cls._desc(
                        observed=(
                            f"Query uses {finding.evidence.get('node_type', 'Seq Scan')} on \"{target}\" "
                            f"with filter \"{finding.evidence.get('filter')}\" (cost {_orig_fmt})."
                        ),
                        candidate=f"B-tree index on {target}({col_repr}) evaluated via HypoPG.",
                        validation_=(
                            f"HypoPG confirmed plan change ({plan_chg}), reducing cost "
                            f"from {_orig_fmt2} to {_hypo_fmt2} ({improvement:.1f}%)."
                        ),
                        recommendation=f"Consider creating index on {target}({col_repr}) — HypoPG-verified.",
                    ),
                    relation=safe_table,
                    columns=safe_cols,
                    recommended_action=(
                        f"CREATE INDEX ON {target} ({col_repr}): "
                        f"{improvement:.1f}% estimated planner cost reduction."
                    ),
                    sql_preview=sql_prev,
                    status=RecommendationStatus.VALIDATED,
                    confidence=RecommendationConfidence.HIGH,
                    risk=risk,
                    evidence=chain,
                    hypopg_validated=True,
                    original_cost=orig_cost,
                    hypothetical_cost=hypo_cost,
                    cost_improvement_percent=improvement,
                    plan_before=validation.original_plan,
                    plan_after=validation.hypothetical_plan,
                    tradeoffs=std_tradeoffs,
                    warnings=list(validation.warnings),
                    requires_human_approval=True,
                )

            # Case B – NO_IMPROVEMENT
            if validation.verdict == ValidationVerdict.NO_IMPROVEMENT:
                return OptimizationRecommendation(
                    optimization_type=OptimizationType.MISSING_INDEX,
                    title=f"Candidate index on {target}({col_repr}) — no improvement",
                    summary=f"HypoPG: no meaningful cost improvement ({improvement:.1f}%) for {target}({col_repr}).",
                    description=cls._desc(
                        observed=(
                            f"Query scans \"{target}\" with filter \"{finding.evidence.get('filter')}\" "
                            f"(cost {orig_cost:.1f})."
                        ),
                        candidate=f"Candidate index on {target}({col_repr}) evaluated via HypoPG.",
                        validation_=f"HypoPG showed no meaningful improvement ({improvement:.1f}% < threshold).",
                        recommendation=f"Do not create index on {target}({col_repr}): no planner benefit confirmed.",
                    ),
                    relation=safe_table,
                    columns=safe_cols,
                    recommended_action=(
                        f"Do not create index on {target} ({col_repr}): "
                        f"no planner improvement ({improvement:.1f}%)."
                    ),
                    sql_preview=None,
                    status=RecommendationStatus.REJECTED,
                    confidence=RecommendationConfidence.MEDIUM,
                    risk=RecommendationRisk.MEDIUM,
                    evidence=chain,
                    hypopg_validated=False,
                    original_cost=orig_cost,
                    hypothetical_cost=hypo_cost,
                    cost_improvement_percent=improvement,
                    plan_before=validation.original_plan,
                    plan_after=validation.hypothetical_plan,
                    tradeoffs=[],
                    warnings=["HypoPG showed no planner cost improvement; index not recommended."],
                    requires_human_approval=True,
                )

            # Case C – REGRESSION
            if validation.verdict == ValidationVerdict.REGRESSION:
                return OptimizationRecommendation(
                    optimization_type=OptimizationType.MISSING_INDEX,
                    title=f"Candidate index on {target}({col_repr}) — planner cost regression",
                    summary=f"HypoPG revealed cost regression: estimated cost increased ({improvement:.1f}%).",
                    description=cls._desc(
                        observed=f"Query scans \"{target}\" with filter \"{finding.evidence.get('filter')}\".",
                        candidate=f"Candidate index on {target}({col_repr}) simulated via HypoPG.",
                        validation_=(
                            f"HypoPG showed REGRESSION: {orig_cost:.2f} -> {hypo_cost:.2f} "
                            f"({improvement:.1f}%)."
                        ),
                        recommendation=f"Reject index on {target}({col_repr}): worsens execution plan cost.",
                    ),
                    relation=safe_table,
                    columns=safe_cols,
                    recommended_action=(
                        f"Do not create index on {target}({col_repr}): "
                        f"plan cost regressed {orig_cost:.2f} -> {hypo_cost:.2f}."
                    ),
                    sql_preview=None,
                    status=RecommendationStatus.REJECTED,
                    confidence=RecommendationConfidence.HIGH,
                    risk=RecommendationRisk.HIGH,
                    evidence=chain,
                    hypopg_validated=False,
                    original_cost=orig_cost,
                    hypothetical_cost=hypo_cost,
                    cost_improvement_percent=improvement,
                    plan_before=validation.original_plan,
                    plan_after=validation.hypothetical_plan,
                    tradeoffs=[],
                    warnings=["HypoPG revealed cost regression; creating this index degrades performance."],
                    requires_human_approval=True,
                )

            # Case – ERROR / INVALID_CANDIDATE
            return OptimizationRecommendation(
                optimization_type=OptimizationType.MISSING_INDEX,
                title=f"Candidate on {target} — validation error",
                summary=f"Validation error: {validation.error_message or 'unknown'}.",
                description=cls._desc(
                    observed=f"Finding flagged on \"{target}\".",
                    candidate="Candidate submitted for HypoPG validation.",
                    validation_=f"Validation error: {validation.error_message or 'unknown'}.",
                    recommendation="Requires manual review before any action.",
                ),
                relation=safe_table,
                columns=safe_cols,
                recommended_action=f"Review candidate: {validation.error_message or 'validation failed'}.",
                sql_preview=None,
                status=RecommendationStatus.REJECTED,
                confidence=RecommendationConfidence.LOW,
                risk=RecommendationRisk.HIGH,
                evidence=chain,
                hypopg_validated=False,
                warnings=[validation.error_message or "Validation error."],
                requires_human_approval=True,
            )

        # ---- Case D: No HypoPG result ----
        chain = cls._evidence_chain(finding, safe_table, safe_cols, None)
        cost = finding.evidence.get("total_cost")

        confidence = (
            RecommendationConfidence.MEDIUM
            if finding.confidence.value == "high"
            else RecommendationConfidence.LOW
        )

        if safe_table and safe_cols:
            sql_prev = None
            try:
                sql_prev = cls.build_sql_preview(safe_table, safe_cols)
            except InvalidCandidateError:
                pass
            return OptimizationRecommendation(
                optimization_type=OptimizationType.MISSING_INDEX,
                title=f"Candidate index on {target}({col_repr}) (unvalidated)",
                summary=f"Unvalidated candidate: {target}({col_repr}) from query filter predicate.",
                description=cls._desc(
                    observed=(
                        f"Query performs {finding.evidence.get('node_type', 'Seq Scan')} on \"{target}\" "
                        f"filter \"{finding.evidence.get('filter')}\" (cost {cost or 0:.1f})."
                    ),
                    candidate=f"Index candidate {target}({col_repr}) from filter predicate.",
                    validation_="HypoPG counterfactual validation has NOT been performed.",
                    recommendation=(
                        f"Evaluate {target}({col_repr}) with HypoPG before physical deployment. "
                        "This is unvalidated and must not be created without simulation."
                    ),
                ),
                relation=safe_table,
                columns=safe_cols,
                recommended_action=f"Evaluate {target}({col_repr}) with HypoPG simulation before deployment.",
                sql_preview=sql_prev,
                status=RecommendationStatus.UNVALIDATED,
                confidence=confidence,
                risk=RecommendationRisk.HIGH,
                evidence=chain,
                hypopg_validated=False,
                original_cost=cost,
                tradeoffs=std_tradeoffs,
                warnings=["Candidate not HypoPG-validated; planner benefit is unverified."],
                requires_human_approval=True,
            )

        # No identifiable columns
        return OptimizationRecommendation(
            optimization_type=OptimizationType.FILTERED_SEQ_SCAN,
            title=f"Review sequential scan on \"{target}\" (insufficient predicate info)",
            summary=f"Seq scan on \"{target}\": no safe index column candidate from plan evidence.",
            description=cls._desc(
                observed=(
                    f"Query performs {finding.evidence.get('node_type', 'Seq Scan')} on \"{target}\" "
                    f"(cost {cost or 0:.1f})."
                ),
                candidate="No specific column identifiable from plan evidence without hallucination.",
                validation_="HypoPG cannot be scheduled without candidate columns.",
                recommendation=(
                    f"Review filter predicates on \"{target}\". "
                    "Insufficient predicate detail in plan evidence."
                ),
            ),
            relation=table,
            columns=[],
            recommended_action=(
                f"Review filter predicates on \"{target}\"; "
                "insufficient predicate detail for index candidate identification."
            ),
            sql_preview=None,
            status=RecommendationStatus.UNVALIDATED,
            confidence=RecommendationConfidence.LOW,
            risk=RecommendationRisk.HIGH,
            evidence=chain,
            hypopg_validated=False,
            original_cost=cost,
            tradeoffs=[],
            warnings=["No candidate column extracted without hallucination."],
            requires_human_approval=True,
        )

    @classmethod
    def _recommend_sort(
        cls,
        finding: BottleneckFinding,
        settings: Optional[Settings],
    ) -> OptimizationRecommendation:
        """EXPENSIVE_SORT diagnostic handler."""
        cost = finding.evidence.get("total_cost", 0.0)
        rows = finding.evidence.get("estimated_rows", 0)
        thresh = finding.evidence.get("sort_cost_threshold", 100.0)
        node = finding.evidence.get("node_type", "Sort")
        return OptimizationRecommendation(
            optimization_type=OptimizationType.EXPENSIVE_SORT,
            title=f"Investigate expensive {node} (cost {cost:.1f})",
            summary=f"{node} cost {cost:.1f} exceeds threshold. Consider index-aligned sorting or work_mem review.",
            description=cls._desc(
                observed=f"{node} incurs cost {cost:.1f} on {rows:,} rows (threshold {thresh:.1f}).",
                candidate="Index aligned with ORDER BY clause, or work_mem increase to avoid on-disk sorting.",
                validation_="HypoPG cannot auto-schedule without specific sort key columns.",
                recommendation="Investigate index aligned with ORDER BY or tune work_mem to avoid on-disk sorting.",
            ),
            relation=finding.relation,
            columns=[],
            recommended_action="Investigate ORDER BY-aligned index or evaluate work_mem tuning.",
            sql_preview=None,
            status=RecommendationStatus.UNVALIDATED,
            confidence=(
                RecommendationConfidence.MEDIUM if finding.confidence.value == "high"
                else RecommendationConfidence.LOW
            ),
            risk=RecommendationRisk.MEDIUM,
            evidence=[
                f"PostgreSQL plan included {node} node.",
                f"Sort cost: {cost:.2f} (threshold {thresh:.2f}).",
                f"Estimated sorted rows: {rows:,}.",
                "Sort keys not exposed in parsed node; examine SQL ORDER BY clause.",
            ],
            hypopg_validated=False,
            original_cost=cost,
            tradeoffs=[
                "Covering index: ORDER BY-aligned index adds storage and write overhead.",
                "work_mem: increasing allocates more memory per sort across active connections.",
            ],
            warnings=["Examine SQL ORDER BY clause to identify candidate sort-key columns."],
            requires_human_approval=True,
        )

    @classmethod
    def _recommend_nested_loop(
        cls,
        finding: BottleneckFinding,
        settings: Optional[Settings],
    ) -> OptimizationRecommendation:
        """EXPENSIVE_NESTED_LOOP diagnostic handler."""
        cost = finding.evidence.get("total_cost", 0.0)
        rows = finding.evidence.get("estimated_rows", 0)
        return OptimizationRecommendation(
            optimization_type=OptimizationType.EXPENSIVE_NESTED_LOOP,
            title=f"Investigate expensive nested loop join (cost {cost:.1f})",
            summary=f"Nested loop join cost {cost:.1f} exceeds threshold. Inner relation indexing may reduce cost.",
            description=cls._desc(
                observed=f"Nested Loop join: cost {cost:.1f} on {rows:,} rows.",
                candidate="Index on inner relation join key, or alternative join strategy.",
                validation_="HypoPG cannot auto-schedule without the specific join key column.",
                recommendation="Investigate join condition and inner table indexing.",
            ),
            relation=finding.relation,
            columns=[],
            recommended_action="Investigate join condition and inner table indexing; check selectivity.",
            sql_preview=None,
            status=RecommendationStatus.UNVALIDATED,
            confidence=RecommendationConfidence.MEDIUM,
            risk=RecommendationRisk.MEDIUM,
            evidence=[
                f"PostgreSQL selected Nested Loop join (cost {cost:.2f}).",
                f"Estimated output rows: {rows:,}.",
                "High-cost nested loops may indicate missing inner-relation join key indexes.",
            ],
            hypopg_validated=False,
            original_cost=cost,
            tradeoffs=["Join path: nested loops optimal for small outer sets; verify outer cardinality."],
            warnings=["Examine JOIN condition before adding indexes to inner relation."],
            requires_human_approval=True,
        )

    @classmethod
    def _recommend_large_rows(
        cls,
        finding: BottleneckFinding,
        settings: Optional[Settings],
    ) -> OptimizationRecommendation:
        """LARGE_ROW_ESTIMATE diagnostic handler."""
        rows = finding.evidence.get("estimated_rows", 0)
        cost = finding.evidence.get("total_cost", 0.0)
        table = finding.relation
        tname = table or "relation"
        return OptimizationRecommendation(
            optimization_type=OptimizationType.LARGE_ROW_ESTIMATE,
            title=f"Investigate cardinality and statistics on \"{tname}\"",
            summary=f"Plan node estimated {rows:,} rows on \"{tname}\". Investigate statistics and cardinality.",
            description=cls._desc(
                observed=f"Plan node on \"{tname}\" estimated {rows:,} rows (cost {cost:.1f}).",
                candidate="Running ANALYZE to refresh planner statistics.",
                validation_="Statistics refresh cannot be evaluated via HypoPG simulation.",
                recommendation=f"Investigate statistics: consider ANALYZE on \"{tname}\" to refresh planner stats.",
            ),
            relation=table,
            columns=[],
            recommended_action=f"Investigate statistics: consider ANALYZE on \"{tname}\" to refresh planner stats.",
            sql_preview=None,
            status=RecommendationStatus.UNVALIDATED,
            confidence=RecommendationConfidence.LOW,
            risk=RecommendationRisk.LOW,
            evidence=[
                f"Plan node estimated {rows:,} rows.",
                f"Estimated cost: {cost:.2f}.",
                "Large estimates may reflect genuine result size or stale planner statistics.",
            ],
            hypopg_validated=False,
            original_cost=cost,
            tradeoffs=["ANALYZE overhead: brief read lock, I/O and CPU to sample data pages."],
            warnings=["Verify actual table row count before assuming stale statistics."],
            requires_human_approval=True,
        )

    @classmethod
    def _recommend_generic(cls, finding: BottleneckFinding) -> OptimizationRecommendation:
        """Fallback handler for unclassified findings."""
        cost = finding.evidence.get("total_cost")
        return OptimizationRecommendation(
            optimization_type=OptimizationType.FILTERED_SEQ_SCAN,
            title=finding.title,
            summary=finding.description[:200],
            description=finding.description,
            relation=finding.relation,
            columns=[],
            recommended_action="Review finding evidence with a database administrator.",
            sql_preview=None,
            status=RecommendationStatus.UNVALIDATED,
            confidence=RecommendationConfidence.LOW,
            risk=RecommendationRisk.HIGH,
            evidence=[f"Finding: {finding.title}."],
            hypopg_validated=False,
            original_cost=cost,
            tradeoffs=[],
            warnings=[],
            requires_human_approval=True,
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @classmethod
    def _evidence_chain(
        cls,
        finding: BottleneckFinding,
        table: Optional[str],
        columns: List[str],
        validation: Optional[HypoPGValidationResult],
    ) -> List[str]:
        """Build an ordered evidence chain from plan and HypoPG data."""
        chain: List[str] = []
        node_type = finding.evidence.get("node_type", "Seq Scan")
        if table:
            chain.append(f"PostgreSQL selected {node_type} on {table}.")
        else:
            chain.append(f"PostgreSQL plan included {node_type} node.")

        if isinstance(finding.evidence.get("filter"), str):
            chain.append(f"Filter predicate was {finding.evidence['filter']}.")

        cost = finding.evidence.get("total_cost")
        if cost is not None:
            chain.append(f"Estimated scan cost was {cost:.1f}.")

        rows = finding.evidence.get("estimated_rows")
        if rows is not None:
            chain.append(f"Estimated row count was {rows:,} rows.")

        if validation is not None:
            col_repr = ", ".join(columns) if columns else "candidate column(s)"
            if table:
                chain.append(f"HypoPG simulated {table}({col_repr}).")
            comp = validation.comparison
            if comp:
                if comp.plan_change_summary:
                    chain.append(f"PostgreSQL changed plan to {comp.plan_change_summary}.")
                if comp.original_cost is not None and comp.hypothetical_cost is not None:
                    chain.append(
                        f"Estimated cost decreased from {comp.original_cost:.2f} to "
                        f"{comp.hypothetical_cost:.2f}."
                    )
                if comp.cost_improvement_percent is not None:
                    chain.append(
                        f"Estimated planner cost improvement was "
                        f"{comp.cost_improvement_percent:.1f}%."
                    )
        elif finding.finding_type in (
            BottleneckType.MISSING_INDEX, BottleneckType.FILTERED_SEQ_SCAN
        ):
            chain.append("HypoPG counterfactual validation has not been performed.")

        return chain

    @classmethod
    def _desc(
        cls,
        observed: str,
        candidate: str,
        validation_: str,
        recommendation: str,
        caveats: Optional[str] = None,
    ) -> str:
        """Build a structured recommendation description."""
        note = caveats or (
            "Important:\n"
            "This recommendation is based on PostgreSQL planner cost estimates and "
            "hypothetical simulation. Actual runtime improvement must be measured "
            "after approved physical deployment."
        )
        return "\n\n".join([
            f"Observed:\n{observed}",
            f"Candidate:\n{candidate}",
            f"Validation:\n{validation_}",
            f"Recommendation:\n{recommendation}",
            note,
        ])
