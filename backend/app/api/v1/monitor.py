from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.monitor import (
    ErrorResponse,
    ExplainRequest,
    ExplainResponse,
    SlowQueryResponse,
)
from app.services.database_monitor import DatabaseMonitorService

router = APIRouter(tags=["monitoring"])


@router.get(
    "/slow-queries",
    response_model=SlowQueryResponse,
    summary="Get Top Slow Queries",
    description="Retrieves normalized query execution statistics from pg_stat_statements.",
    responses={500: {"model": ErrorResponse}},
)
@router.get(
    "/monitor/slow-queries",
    response_model=SlowQueryResponse,
    include_in_schema=False,
)
def get_slow_queries(
    limit: int = Query(default=10, ge=1, le=100, description="Maximum number of queries to return"),
    min_exec_time_ms: float = Query(
        default=0.0,
        ge=0.0,
        description="Filter for queries with mean execution time >= threshold in ms",
    ),
    db: Session = Depends(get_db),
):
    return DatabaseMonitorService.get_slow_queries(
        db=db,
        limit=limit,
        min_exec_time_ms=min_exec_time_ms,
    )


@router.post(
    "/explain",
    response_model=ExplainResponse,
    summary="Explain Query Plan",
    description="Conservatively validates read-only SQL and generates a structured PostgreSQL JSON execution plan.",
    responses={
        400: {"model": ErrorResponse, "description": "Unsafe, destructive, or invalid SQL query"},
        500: {"model": ErrorResponse, "description": "Database execution failure"},
    },
)
@router.post(
    "/monitor/explain",
    response_model=ExplainResponse,
    include_in_schema=False,
)
def explain_query(
    request: ExplainRequest,
    db: Session = Depends(get_db),
):
    return DatabaseMonitorService.explain_query(
        db=db,
        query=request.query,
    )
