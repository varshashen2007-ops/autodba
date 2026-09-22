"""
Real Runtime Benchmarking Service (Phase 3 Step 3)
==================================================
Conducts controlled before-and-after query performance benchmarking on PostgreSQL.

Guarantees:
  - Strictly read-only: executes only validated read-only queries with EXPLAIN (ANALYZE, BUFFERS).
  - Zero state mutation: does not insert, update, delete, or modify database objects.
  - Discarded warm-up runs: accounts for buffer pool and engine cache effects.
  - Statistical rigor: calculates mean, median, min, max, stddev, and coefficient of variation.
  - Controlled baseline: simulates pre-remediation baseline within session-local transaction
    (SET LOCAL enable_indexscan=off; SET LOCAL enable_bitmapscan=off) without dropping indexes.
  - Clear separation of metrics: keeps planner cost improvement strictly separate from
    actual measured runtime improvement.
  - Auditability: produces a structured, JSON-serializable BenchmarkResult.
"""

from __future__ import annotations

from datetime import datetime, timezone
import statistics
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import Settings, get_settings
from app.core.logging import log_operation, logger
from app.core.exceptions import InvalidSQLError, MultiStatementSQLError, UnsafeSQLError
from app.db.database import engine as default_engine
from app.schemas.optimization import (
    BenchmarkResult,
    BenchmarkStatus,
    ExecutionMeasurement,
    RemediationResult,
    RemediationStatus,
)
from app.services.sql_validator import validate_read_only_query


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BenchmarkError(Exception):
    """Base exception for benchmarking errors."""
    pass


class BenchmarkSafetyError(BenchmarkError):
    """Raised when a query fails read-only safety checks."""
    pass


class BenchmarkAuthorizationError(BenchmarkError):
    """Raised when attempting to benchmark an unverified or invalid remediation."""
    pass


class BenchmarkExecutionError(BenchmarkError):
    """Raised when database EXPLAIN ANALYZE execution fails."""
    pass


# ---------------------------------------------------------------------------
# Service Implementation
# ---------------------------------------------------------------------------

class BenchmarkService:
    """Service governing controlled before/after runtime query benchmarking."""

    @classmethod
    def validate_query(cls, query: str) -> str:
        """Validates that the benchmark query is strictly read-only and safe."""
        if not query or not query.strip():
            raise BenchmarkSafetyError("Benchmark query cannot be empty.")

        try:
            # Use existing Phase 1 SQL validator
            cleaned = validate_read_only_query(query)
        except (InvalidSQLError, MultiStatementSQLError, UnsafeSQLError) as e:
            raise BenchmarkSafetyError(f"Benchmark query rejected by SQL safety validator: {str(e)}") from e

        return cleaned

    @classmethod
    def verify_remediation_authorization(
        cls, remediation: Optional[RemediationResult]
    ) -> None:
        """Verifies that the associated remediation was verified and applied successfully."""
        if remediation is None:
            return

        if remediation.status not in (RemediationStatus.APPLIED, RemediationStatus.ALREADY_APPLIED):
            raise BenchmarkAuthorizationError(
                f"Cannot benchmark remediation with status '{remediation.status.value}'. "
                "Only APPLIED or ALREADY_APPLIED remediations can be benchmarked."
            )

        if not remediation.verification_passed:
            raise BenchmarkAuthorizationError(
                "Cannot benchmark an unverified remediation."
            )

    @classmethod
    def parse_explain_analyze_json(
        cls, raw_explain: Any
    ) -> Dict[str, Any]:
        """Parses PostgreSQL EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) output.

        Extracts planning time, execution time, total cost, rows returned,
        primary scan node type, index used (if any), and buffer hit/read blocks.
        """
        if not raw_explain or not isinstance(raw_explain, list) or len(raw_explain) == 0:
            raise BenchmarkExecutionError("Malformed EXPLAIN output: expected non-empty list.")

        top = raw_explain[0]
        if not isinstance(top, dict) or "Plan" not in top:
            raise BenchmarkExecutionError("Malformed EXPLAIN output: missing 'Plan' key.")

        planning_time_ms = float(top.get("Planning Time", 0.0))
        execution_time_ms = float(top.get("Execution Time", 0.0))
        plan_root = top["Plan"]

        planner_cost = float(plan_root.get("Total Cost", 0.0))
        actual_rows = int(plan_root.get("Actual Rows", plan_root.get("Plan Rows", 0)))

        # Extract scan type, index used, and buffer counts recursively
        scan_type, index_used, hits, reads = cls._traverse_plan_tree(plan_root)

        return {
            "planning_time_ms": planning_time_ms,
            "execution_time_ms": execution_time_ms,
            "planner_cost": planner_cost,
            "rows_returned": actual_rows,
            "scan_type": scan_type,
            "index_used": index_used,
            "shared_hit_blocks": hits,
            "shared_read_blocks": reads,
            "plan_tree": plan_root,
        }

    @classmethod
    def _traverse_plan_tree(
        cls, plan_node: Dict[str, Any]
    ) -> Tuple[str, Optional[str], int, int]:
        """Recursively traverses a plan tree to extract primary scan type, index used, and buffer blocks."""
        node_type = plan_node.get("Node Type", "Unknown")
        index_name = plan_node.get("Index Name")
        hits = int(plan_node.get("Shared Hit Blocks", 0))
        reads = int(plan_node.get("Shared Read Blocks", 0))

        found_scan = node_type if "Scan" in node_type else None
        found_index = index_name

        # Recurse through child plans
        for child in plan_node.get("Plans", []):
            c_scan, c_idx, c_hits, c_reads = cls._traverse_plan_tree(child)
            hits += c_hits
            reads += c_reads
            if not found_scan and c_scan:
                found_scan = c_scan
            if not found_index and c_idx:
                found_index = c_idx

        primary_scan = found_scan or node_type
        return primary_scan, found_index, hits, reads

    @classmethod
    def measure_query(
        cls,
        conn: Any,
        query: str,
        runs: int,
        warmup_runs: int,
        disable_indexes: bool = False,
    ) -> ExecutionMeasurement:
        """Executes repeated EXPLAIN ANALYZE runs under controlled transaction settings.

        Args:
            conn: Active SQLAlchemy connection.
            query: Validated read-only SQL query.
            runs: Number of measurement runs to record.
            warmup_runs: Number of warm-up runs to discard.
            disable_indexes: When True, locally disables index/bitmap scans to simulate baseline.
        """
        if runs < 1:
            raise BenchmarkError("Benchmark runs must be at least 1.")

        # Configure session-local scan switches within current transaction block
        if disable_indexes:
            conn.execute(text("SET LOCAL enable_indexscan = off;"))
            conn.execute(text("SET LOCAL enable_bitmapscan = off;"))
        else:
            conn.execute(text("SET LOCAL enable_indexscan = on;"))
            conn.execute(text("SET LOCAL enable_bitmapscan = on;"))

        explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query};"

        # 1. Warm-up runs (discarded to stabilize cache/buffer pool)
        for _ in range(warmup_runs):
            conn.execute(text(explain_sql))

        # 2. Measurement runs
        exec_times: List[float] = []
        plan_times: List[float] = []
        last_metadata: Optional[Dict[str, Any]] = None

        for _ in range(runs):
            result = conn.execute(text(explain_sql))
            raw_json = result.scalar()
            parsed = cls.parse_explain_analyze_json(raw_json)

            exec_times.append(parsed["execution_time_ms"])
            plan_times.append(parsed["planning_time_ms"])
            last_metadata = parsed

        if not last_metadata or len(exec_times) == 0:
            raise BenchmarkExecutionError("Failed to collect benchmark measurements.")

        mean_ms = statistics.mean(exec_times)
        median_ms = statistics.median(exec_times)
        min_ms = min(exec_times)
        max_ms = max(exec_times)
        stddev_ms = statistics.stdev(exec_times) if len(exec_times) > 1 else 0.0
        cov = (stddev_ms / mean_ms) if mean_ms > 0 else 0.0

        return ExecutionMeasurement(
            runs=runs,
            warmup_runs=warmup_runs,
            execution_times_ms=exec_times,
            planning_times_ms=plan_times,
            mean_execution_time_ms=round(mean_ms, 4),
            median_execution_time_ms=round(median_ms, 4),
            min_execution_time_ms=round(min_ms, 4),
            max_execution_time_ms=round(max_ms, 4),
            stddev_execution_time_ms=round(stddev_ms, 4),
            coefficient_of_variation=round(cov, 4),
            rows_returned=last_metadata["rows_returned"],
            planner_cost=last_metadata["planner_cost"],
            scan_type=last_metadata["scan_type"],
            index_used=last_metadata["index_used"],
            shared_hit_blocks=last_metadata["shared_hit_blocks"],
            shared_read_blocks=last_metadata["shared_read_blocks"],
            plan_tree=last_metadata["plan_tree"],
        )

    @classmethod
    def benchmark(
        cls,
        query: str,
        remediation: Optional[RemediationResult] = None,
        settings: Optional[Settings] = None,
        db_engine: Optional[Engine] = None,
        runs: Optional[int] = None,
        warmup_runs: Optional[int] = None,
    ) -> BenchmarkResult:
        """Conducts a complete, controlled before-and-after query performance benchmark.

        Returns:
            BenchmarkResult containing detailed before/after timing distributions,
            percentage improvements, and execution plan changes.
        """
        cfg = settings or get_settings()
        engine = db_engine or default_engine
        num_runs = runs if runs is not None else cfg.BENCHMARK_RUNS
        num_warmups = warmup_runs if warmup_runs is not None else cfg.BENCHMARK_WARMUP_RUNS

        benchmark_id = f"bench_{uuid4().hex[:12]}"
        remediation_id = remediation.remediation_id if remediation else None
        started_at = datetime.now(timezone.utc)
        warnings: List[str] = []

        with log_operation("benchmark_query"):
            # Step 1: Validate Query Safety
            safe_query = cls.validate_query(query)

            # Step 2: Validate Remediation Authorization
            cls.verify_remediation_authorization(remediation)

            # Step 3: Execute Controlled Measurements
            try:
                with engine.connect() as conn:
                    # Before: session-local disabled indexes (clean baseline approximation)
                    with conn.begin():
                        before = cls.measure_query(
                            conn, safe_query, runs=num_runs, warmup_runs=num_warmups, disable_indexes=True
                        )

                    # After: physical indexes active
                    with conn.begin():
                        after = cls.measure_query(
                            conn, safe_query, runs=num_runs, warmup_runs=num_warmups, disable_indexes=False
                        )
            except Exception as e:
                completed_at = datetime.now(timezone.utc)
                err_msg = f"Benchmark execution failed: {str(e)}"
                logger.error("Benchmark failed", extra={"error": err_msg})
                raise BenchmarkExecutionError(err_msg) from e

            # Step 4: Calculate Improvements
            planner_improvement: Optional[float] = None
            if before.planner_cost is not None and after.planner_cost is not None:
                if before.planner_cost > 0:
                    planner_improvement = round(
                        ((before.planner_cost - after.planner_cost) / before.planner_cost) * 100, 2
                    )
                else:
                    warnings.append("Baseline planner cost was 0.0; planner improvement cannot be calculated.")

            runtime_improvement: Optional[float] = None
            if before.mean_execution_time_ms > 0:
                runtime_improvement = round(
                    (
                        (before.mean_execution_time_ms - after.mean_execution_time_ms)
                        / before.mean_execution_time_ms
                    )
                    * 100,
                    2,
                )
            else:
                warnings.append("Baseline execution time was 0.0 ms; runtime improvement cannot be calculated.")

            plan_changed = (
                before.scan_type != after.scan_type
                or before.index_used != after.index_used
                or before.planner_cost != after.planner_cost
            )
            index_usage_changed = (before.index_used != after.index_used)

            completed_at = datetime.now(timezone.utc)

            logger.info(
                "Benchmark completed",
                extra={
                    "benchmark_id": benchmark_id,
                    "runtime_improvement_percent": runtime_improvement,
                    "planner_improvement_percent": planner_improvement,
                },
            )

            return BenchmarkResult(
                benchmark_id=benchmark_id,
                remediation_id=remediation_id,
                status=BenchmarkStatus.COMPLETED,
                query=safe_query,
                before=before,
                after=after,
                planner_cost_improvement_percent=planner_improvement,
                runtime_improvement_percent=runtime_improvement,
                plan_changed=plan_changed,
                index_usage_changed=index_usage_changed,
                started_at=started_at,
                completed_at=completed_at,
                warnings=warnings,
                error=None,
            )
