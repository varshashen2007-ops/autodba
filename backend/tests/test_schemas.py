import pytest
from pydantic import ValidationError
from app.schemas.monitor import (
    SlowQuery,
    SlowQueryResponse,
    ExplainRequest,
    ExplainResponse,
    HealthResponse,
    ErrorResponse,
)


def test_slow_query_schema():
    sq = SlowQuery(
        query="SELECT * FROM orders WHERE customer_id = 42",
        calls=10,
        total_time_ms=125.4,
        mean_time_ms=12.54,
        rows=100,
        shared_blks_hit=500,
        shared_blks_read=20,
    )
    assert sq.calls == 10
    assert sq.mean_time_ms == 12.54

    resp = SlowQueryResponse(queries=[sq], count=1)
    assert resp.count == 1
    assert len(resp.queries) == 1


def test_explain_request_schema():
    req = ExplainRequest(query="SELECT * FROM orders", analyze=True)
    assert req.query == "SELECT * FROM orders"
    assert req.analyze is True

    # Too short query should fail validation
    with pytest.raises(ValidationError):
        ExplainRequest(query="SEL")


def test_explain_response_schema():
    resp = ExplainResponse(
        query="SELECT 1",
        plan=[{"Plan": {"Node Type": "Result", "Total Cost": 0.01}}],
        planning_time_ms=0.15,
        execution_time_ms=0.05,
    )
    assert resp.query == "SELECT 1"
    assert resp.planning_time_ms == 0.15
    assert len(resp.plan) == 1


def test_health_response_schema():
    resp = HealthResponse(
        status="healthy",
        database="connected",
        version="PostgreSQL 17.0",
        extensions=["pg_stat_statements", "hypopg"],
    )
    assert resp.status == "healthy"
    assert "hypopg" in resp.extensions


def test_error_response_schema():
    err = ErrorResponse(
        error="DATABASE_UNAVAILABLE",
        message="Unable to connect to PostgreSQL",
    )
    assert err.error == "DATABASE_UNAVAILABLE"
