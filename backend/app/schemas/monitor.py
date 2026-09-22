from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SlowQuery(BaseModel):
    """Normalized performance metrics for a PostgreSQL query from pg_stat_statements."""

    query: str = Field(..., description="Normalized SQL statement text")
    calls: int = Field(..., description="Number of times executed")
    total_time_ms: float = Field(..., description="Total execution time spent in milliseconds")
    mean_time_ms: float = Field(..., description="Mean execution time in milliseconds")
    rows: int = Field(..., description="Total number of rows retrieved or affected")
    shared_blks_hit: int = Field(..., description="Total number of shared block cache hits")
    shared_blks_read: int = Field(..., description="Total number of shared blocks read from disk")


class SlowQueryResponse(BaseModel):
    """Response envelope containing top slow queries."""

    queries: List[SlowQuery] = Field(default_factory=list, description="List of slow query metrics")
    count: int = Field(..., description="Total number of returned queries")


class ExplainRequest(BaseModel):
    """Request payload for executing PostgreSQL query plan analysis."""

    query: str = Field(
        ...,
        min_length=6,
        description="Read-only SQL query to analyze (e.g. SELECT ...)",
        examples=["SELECT * FROM orders WHERE customer_id = 42"],
    )
    analyze: bool = Field(
        default=False,
        description="Whether to execute with EXPLAIN ANALYZE (runs query inside a read-only transaction)",
    )


class ExplainResponse(BaseModel):
    """Structured response containing PostgreSQL execution plan tree."""

    query: str = Field(..., description="The analyzed SQL statement")
    plan: List[Dict[str, Any]] = Field(..., description="PostgreSQL JSON execution plan output")
    planning_time_ms: Optional[float] = Field(None, description="Planning time in milliseconds")
    execution_time_ms: Optional[float] = Field(None, description="Execution time in milliseconds if analyze was enabled")


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(..., description="Overall service status (healthy/degraded)")
    database: str = Field(..., description="Database connection status (connected/disconnected)")
    version: Optional[str] = Field(None, description="PostgreSQL server version string")
    extensions: List[str] = Field(default_factory=list, description="List of enabled PostgreSQL extensions")


class ErrorResponse(BaseModel):
    """Standardized API error schema."""

    error: str = Field(..., description="Machine-readable error classification code")
    message: str = Field(..., description="Human-readable error explanation")
