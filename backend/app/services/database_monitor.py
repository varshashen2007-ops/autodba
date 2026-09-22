import json
from typing import Any, Dict, List
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.exceptions import DatabaseExecutionError
from app.core.logging import log_operation, logger
from app.schemas.monitor import ExplainResponse, SlowQuery, SlowQueryResponse
from app.services.sql_validator import validate_read_only_query


class DatabaseMonitorService:
    """Service providing PostgreSQL performance monitoring and execution plan analysis."""

    @staticmethod
    def get_slow_queries(
        db: Session,
        limit: int = 10,
        min_exec_time_ms: float = 0.0,
    ) -> SlowQueryResponse:
        """Retrieves and normalizes top slow queries from pg_stat_statements."""
        sql = text("""
            SELECT
                query,
                calls,
                total_exec_time,
                mean_exec_time,
                rows,
                shared_blks_hit,
                shared_blks_read
            FROM pg_stat_statements
            WHERE query NOT LIKE '%pg_stat_statements%'
              AND mean_exec_time >= :min_exec_time
            ORDER BY total_exec_time DESC
            LIMIT :limit;
        """)

        with log_operation("get_slow_queries") as op_context:
            try:
                result = db.execute(sql, {"limit": limit, "min_exec_time": min_exec_time_ms})
                rows = result.fetchall()

                queries: List[SlowQuery] = []
                for row in rows:
                    queries.append(
                        SlowQuery(
                            query=row[0] or "",
                            calls=int(row[1] or 0),
                            total_time_ms=round(float(row[2] or 0.0), 2),
                            mean_time_ms=round(float(row[3] or 0.0), 2),
                            rows=int(row[4] or 0),
                            shared_blks_hit=int(row[5] or 0),
                            shared_blks_read=int(row[6] or 0),
                        )
                    )

                op_context["returned_count"] = len(queries)
                return SlowQueryResponse(queries=queries, count=len(queries))

            except Exception as exc:
                logger.error(f"Failed to query pg_stat_statements: {exc}")
                raise DatabaseExecutionError(
                    f"Unable to retrieve query statistics: {str(exc)}"
                ) from exc

    @staticmethod
    def explain_query(db: Session, query: str) -> ExplainResponse:
        """Validates that a query is read-only and executes EXPLAIN (FORMAT JSON)."""
        # Step 1: Strict read-only SQL validation
        validated_sql = validate_read_only_query(query)

        # Step 2: Execute EXPLAIN (FORMAT JSON) without executing the user statement
        with log_operation("explain_query") as op_context:
            try:
                explain_sql = text(f"EXPLAIN (FORMAT JSON) {validated_sql}")
                result = db.execute(explain_sql)
                row = result.fetchone()

                if not row or row[0] is None:
                    raise DatabaseExecutionError("PostgreSQL returned empty execution plan.")

                raw_plan = row[0]
                plan_json: List[Dict[str, Any]]
                if isinstance(raw_plan, str):
                    plan_json = json.loads(raw_plan)
                elif isinstance(raw_plan, list):
                    plan_json = raw_plan
                else:
                    plan_json = [raw_plan]

                planning_time: float | None = None
                execution_time: float | None = None
                if isinstance(plan_json, list) and len(plan_json) > 0 and isinstance(plan_json[0], dict):
                    planning_time = plan_json[0].get("Planning Time")
                    execution_time = plan_json[0].get("Execution Time")

                op_context["has_plan"] = True
                return ExplainResponse(
                    query=validated_sql,
                    plan=plan_json,
                    planning_time_ms=planning_time,
                    execution_time_ms=execution_time,
                )

            except DatabaseExecutionError:
                raise
            except Exception as exc:
                logger.error(f"Failed to generate query plan: {exc}")
                raise DatabaseExecutionError(f"PostgreSQL EXPLAIN failed: {str(exc)}") from exc
