"""
HypoPG Counterfactual Validator Service
========================================
Validates optimization candidates by creating hypothetical indexes with HypoPG,
re-evaluating query execution plans, and determining if PostgreSQL's planner
produces a meaningful cost improvement.

Guarantees:
  - NEVER creates physical indexes (only HypoPG in-memory simulation).
  - Strictly validates table and column identifiers against SQL injection before formatting.
  - Reuses Phase 1 SQL safety validation for all analyzed queries.
  - Reuses Phase 2 PlanAnalyzer for all plan parsing and normalization.
  - Session-scoped: creation, EXPLAIN, and cleanup all execute on the same connection.
  - Guaranteed cleanup via hypopg_reset() in a finally block even on errors.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import DatabaseExecutionError, SQLValidationError
from app.core.logging import log_operation, logger
from app.db.database import engine
from app.schemas.optimization import (
    HypoPGValidationResult,
    HypotheticalIndexRequest,
    IndexMethod,
    PlanComparison,
    PlanNode,
    ValidationVerdict,
)
from app.services.plan_analyzer import PlanAnalyzer, flatten_nodes
from app.services.sql_validator import validate_read_only_query

# Valid PostgreSQL unquoted identifier pattern: starts with letter/underscore, followed by alphanumeric/underscore
# Standard PostgreSQL identifiers have a maximum length of 63 bytes (NAMEDATALEN - 1)
_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")

# Disallowed tokens in identifiers even if matching regex (defensive guard)
_FORBIDDEN_IDENTIFIER_TOKENS = frozenset(
    {
        "SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
        "CREATE", "GRANT", "REVOKE", "VACUUM", "CALL", "DO", "COPY",
    }
)


class InvalidCandidateError(ValueError):
    """Raised when a candidate index definition is structurally invalid or unsafe."""
    pass


class HypoPGValidatorService:
    """Deterministic counterfactual index validation service using HypoPG."""

    @staticmethod
    def validate_identifier(ident: str, name_type: str = "identifier") -> str:
        """Validates that a string is a safe, single PostgreSQL identifier.

        Rejects SQL injection fragments, semicolons, comments, quotes, spaces,
        and dangerous keywords.
        """
        if not ident or not isinstance(ident, str):
            raise InvalidCandidateError(f"Candidate {name_type} cannot be empty or non-string.")

        cleaned = ident.strip()
        if not _IDENTIFIER_REGEX.match(cleaned):
            raise InvalidCandidateError(
                f"Invalid {name_type} '{ident}'. Must be a standard alphanumeric identifier "
                "starting with a letter or underscore (1-63 chars) with no special characters."
            )

        if cleaned.upper() in _FORBIDDEN_IDENTIFIER_TOKENS:
            raise InvalidCandidateError(
                f"Forbidden SQL keyword '{cleaned}' cannot be used as a candidate {name_type}."
            )

        return cleaned

    @classmethod
    def build_candidate_index_sql(
        cls,
        table: str,
        columns: List[str],
        index_method: IndexMethod = IndexMethod.BTREE,
    ) -> Tuple[str, str, List[str]]:
        """Validates identifiers and safely constructs the internal CREATE INDEX SQL for HypoPG.

        Returns:
            Tuple of (index_sql, safe_table, safe_columns)
        """
        safe_table = cls.validate_identifier(table, "table name")

        if not columns or not isinstance(columns, list):
            raise InvalidCandidateError("Candidate index must specify at least one column.")

        safe_columns: List[str] = []
        for col in columns:
            safe_columns.append(cls.validate_identifier(col, "column name"))

        cols_str = ", ".join(safe_columns)

        if index_method == IndexMethod.BTREE:
            index_sql = f"CREATE INDEX ON {safe_table} ({cols_str})"
        else:
            index_sql = f"CREATE INDEX ON {safe_table} USING {index_method.value} ({cols_str})"

        return index_sql, safe_table, safe_columns

    @classmethod
    def validate_candidate(
        cls,
        request: HypotheticalIndexRequest,
        db: Optional[Session] = None,
        settings: Optional[Settings] = None,
    ) -> HypoPGValidationResult:
        """Executes full counterfactual validation of a candidate index against a query.

        Steps:
          1. Validates candidate structure and read-only query safety.
          2. Connects to PostgreSQL and resets any prior HypoPG state on the connection.
          3. Captures original execution plan via EXPLAIN (FORMAT JSON).
          4. Creates hypothetical index with hypopg_create_index().
          5. Captures hypothetical execution plan via EXPLAIN (FORMAT JSON).
          6. Compares original vs. hypothetical plans and computes cost improvement.
          7. Assigns deterministic ValidationVerdict based on configured threshold.
          8. Resets HypoPG state in a finally block (guaranteed cleanup).

        Parameters:
            request: The hypothetical index candidate request.
            db: Optional SQLAlchemy Session (uses its connection).
            settings: Optional configuration override.

        Returns:
            HypoPGValidationResult containing comparison, plans, and verdict.
        """
        cfg = settings or get_settings()
        min_improvement = (
            request.min_cost_improvement_percent
            if request.min_cost_improvement_percent is not None
            else cfg.HYPOPG_MIN_COST_IMPROVEMENT_PERCENT
        )

        # Step 1: Validate candidate definition
        try:
            index_sql, safe_table, safe_columns = cls.build_candidate_index_sql(
                table=request.table,
                columns=request.columns,
                index_method=request.index_method,
            )
        except InvalidCandidateError as exc:
            logger.warning(f"Invalid hypothetical index candidate: {exc}")
            return HypoPGValidationResult(
                verdict=ValidationVerdict.INVALID_CANDIDATE,
                candidate_index="",
                original_query=request.query,
                error_message=str(exc),
            )

        # Step 2: Validate read-only query using Phase 1 validator
        try:
            validated_query = validate_read_only_query(request.query)
        except SQLValidationError as exc:
            logger.warning(f"Unsafe or invalid query submitted for HypoPG validation: {exc}")
            return HypoPGValidationResult(
                verdict=ValidationVerdict.INVALID_CANDIDATE,
                candidate_index=index_sql,
                original_query=request.query,
                error_message=f"Query failed read-only safety validation: {exc.message}",
            )

        # Step 3: Run execution on a single connection to preserve session-scoped HypoPG state
        with log_operation("hypopg_validate_candidate") as op_context:
            op_context["table"] = safe_table
            op_context["columns"] = safe_columns

            if db is not None:
                # Use the connection associated with the session
                connection = db.connection()
                return cls._execute_session_validation(
                    conn=connection,
                    original_query=validated_query,
                    index_sql=index_sql,
                    table=safe_table,
                    min_improvement_percent=min_improvement,
                )
            else:
                # Open a dedicated connection with guaranteed closure
                with engine.connect() as connection:
                    return cls._execute_session_validation(
                        conn=connection,
                        original_query=validated_query,
                        index_sql=index_sql,
                        table=safe_table,
                        min_improvement_percent=min_improvement,
                    )

    @classmethod
    def _execute_session_validation(
        cls,
        conn: Connection,
        original_query: str,
        index_sql: str,
        table: str,
        min_improvement_percent: float,
    ) -> HypoPGValidationResult:
        """Runs the before-explain, hypopg creation, after-explain, and cleanup on a single connection."""
        hypo_oid: Optional[int] = None
        hypo_name: Optional[str] = None
        warnings: List[str] = []

        try:
            # 1. Clean slate before starting
            conn.execute(text("SELECT hypopg_reset();"))

            # 2. Capture original plan
            raw_orig = cls._run_explain(conn, original_query)
            orig_plan, _, _ = PlanAnalyzer.analyze(raw_orig, query=original_query)

            # 3. Create hypothetical index
            create_stmt = text("SELECT * FROM hypopg_create_index(:idx_sql);")
            result = conn.execute(create_stmt, {"idx_sql": index_sql})
            row = result.fetchone()

            if not row:
                raise DatabaseExecutionError("hypopg_create_index returned no rows.")

            hypo_oid = int(row[0])
            hypo_name = str(row[1])

            # 4. Capture hypothetical plan
            raw_hypo = cls._run_explain(conn, original_query)
            hypo_plan, _, _ = PlanAnalyzer.analyze(raw_hypo, query=original_query)

            # 5. Build comparison
            comparison = cls._compare_plans(
                orig_plan=orig_plan,
                hypo_plan=hypo_plan,
                table=table,
                hypo_index_name=hypo_name,
            )

            # 6. Determine verdict
            verdict = cls._determine_verdict(
                comparison=comparison,
                min_improvement_percent=min_improvement_percent,
            )

            evidence = {
                "original_cost": comparison.original_cost,
                "hypothetical_cost": comparison.hypothetical_cost,
                "cost_difference": comparison.cost_difference,
                "cost_improvement_percent": comparison.cost_improvement_percent,
                "min_improvement_threshold_percent": min_improvement_percent,
                "plan_changed": comparison.plan_changed,
                "hypothetical_index_used": (
                    hypo_name in json.dumps(raw_hypo) if hypo_name else False
                ),
            }

            return HypoPGValidationResult(
                verdict=verdict,
                candidate_index=index_sql,
                hypothetical_index_name=hypo_name,
                hypothetical_index_oid=hypo_oid,
                original_query=original_query,
                comparison=comparison,
                original_plan=orig_plan,
                hypothetical_plan=hypo_plan,
                evidence=evidence,
                warnings=warnings,
            )

        except DatabaseExecutionError as exc:
            logger.error(f"HypoPG database execution error: {exc}")
            return HypoPGValidationResult(
                verdict=ValidationVerdict.ERROR,
                candidate_index=index_sql,
                original_query=original_query,
                error_message=str(exc),
            )
        except Exception as exc:
            logger.error(f"HypoPG validation failed with unexpected error: {exc}")
            return HypoPGValidationResult(
                verdict=ValidationVerdict.ERROR,
                candidate_index=index_sql,
                original_query=original_query,
                error_message=f"HypoPG validation error: {str(exc)}",
            )
        finally:
            # 7. Guaranteed cleanup: always reset HypoPG state on this session
            try:
                # If an error aborted the transaction, rollback so subsequent commands succeed
                if conn.in_transaction():
                    conn.rollback()
            except Exception:
                pass

            try:
                conn.execute(text("SELECT hypopg_reset();"))
            except Exception as reset_err:
                logger.error(f"Failed to reset HypoPG state during cleanup: {reset_err}")

    @staticmethod
    def _run_explain(conn: Connection, query: str) -> List[Dict[str, Any]]:
        """Runs EXPLAIN (FORMAT JSON) on a connection and parses the JSON result."""
        explain_sql = text(f"EXPLAIN (FORMAT JSON) {query}")
        result = conn.execute(explain_sql)
        row = result.fetchone()
        if not row or row[0] is None:
            raise DatabaseExecutionError("PostgreSQL EXPLAIN returned an empty result.")

        raw_plan = row[0]
        if isinstance(raw_plan, str):
            return json.loads(raw_plan)
        elif isinstance(raw_plan, list):
            return raw_plan
        return [raw_plan]

    @classmethod
    def _compare_plans(
        cls,
        orig_plan: PlanNode,
        hypo_plan: PlanNode,
        table: str,
        hypo_index_name: Optional[str] = None,
    ) -> PlanComparison:
        """Deterministically computes cost differences, percentage improvements, and plan shape changes."""
        orig_cost = orig_plan.total_cost if orig_plan.total_cost is not None else 0.0
        hypo_cost = hypo_plan.total_cost if hypo_plan.total_cost is not None else 0.0

        cost_diff = round(orig_cost - hypo_cost, 4)

        if orig_cost > 0.0:
            improvement_pct = round(((orig_cost - hypo_cost) / orig_cost) * 100.0, 2)
        else:
            improvement_pct = 0.0

        # Scan node detection for target table
        orig_scan = cls._find_scan_for_table(orig_plan, table)
        hypo_scan = cls._find_scan_for_table(hypo_plan, table)

        # Determine if plan changed shape
        plan_changed = (
            orig_plan.node_type != hypo_plan.node_type
            or orig_scan != hypo_scan
            or cost_diff != 0.0
        )

        # Construct concise human-readable summary of plan change
        summary_parts = []
        if orig_scan and hypo_scan and orig_scan != hypo_scan:
            summary_parts.append(f"{orig_scan} on {table} → {hypo_scan} on {table}")
        elif orig_plan.node_type != hypo_plan.node_type:
            summary_parts.append(f"{orig_plan.node_type} → {hypo_plan.node_type}")
        elif cost_diff > 0:
            summary_parts.append(f"Cost reduced from {orig_cost:.2f} to {hypo_cost:.2f} ({improvement_pct:.1f}%)")
        else:
            summary_parts.append("No structural plan or cost change observed")

        return PlanComparison(
            original_cost=orig_cost,
            hypothetical_cost=hypo_cost,
            cost_difference=cost_diff,
            cost_improvement_percent=improvement_pct,
            original_root_node_type=orig_plan.node_type,
            hypothetical_root_node_type=hypo_plan.node_type,
            original_scan_type=orig_scan,
            hypothetical_scan_type=hypo_scan,
            plan_changed=plan_changed,
            plan_change_summary="; ".join(summary_parts),
        )

    @staticmethod
    def _find_scan_for_table(root: PlanNode, table: str) -> Optional[str]:
        """Traverses a plan tree and finds the node type of the scan operating on a specific relation."""
        for node in flatten_nodes(root):
            if node.relation_name == table and "Scan" in node.node_type:
                return node.node_type
        return None

    @staticmethod
    def _determine_verdict(
        comparison: PlanComparison,
        min_improvement_percent: float,
    ) -> ValidationVerdict:
        """Determines the validation verdict based on cost metrics and configured threshold."""
        # Regression: hypothetical cost is strictly higher than original cost
        if comparison.cost_difference < -0.0001:
            return ValidationVerdict.REGRESSION

        # Meaningful improvement: exceeds or meets threshold
        if comparison.cost_improvement_percent >= min_improvement_percent:
            return ValidationVerdict.VALIDATED

        # No meaningful improvement (equal cost or below threshold)
        return ValidationVerdict.NO_IMPROVEMENT
