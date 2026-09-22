import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.db.database import engine


def test_get_slow_queries(client: TestClient):
    response = client.get("/api/v1/slow-queries?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "queries" in data
    assert "count" in data
    assert isinstance(data["queries"], list)
    assert data["count"] == len(data["queries"])
    assert len(data["queries"]) <= 5

    if data["queries"]:
        first = data["queries"][0]
        assert "query" in first
        assert "calls" in first
        assert "total_time_ms" in first
        assert "mean_time_ms" in first
        assert "rows" in first


@pytest.mark.parametrize(
    "safe_query",
    [
        "SELECT 1",
        "SELECT * FROM orders",
        "SELECT * FROM orders WHERE customer_id = 42",
        "SELECT id, name FROM customers WHERE name = 'DROP TABLE orders'",
    ],
)
def test_explain_safe_queries(client: TestClient, safe_query: str):
    response = client.post("/api/v1/explain", json={"query": safe_query})
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == safe_query.strip().rstrip(";")
    assert "plan" in data
    assert isinstance(data["plan"], list)
    assert len(data["plan"]) > 0
    assert "Plan" in data["plan"][0]


@pytest.mark.parametrize(
    "destructive_query",
    [
        "DROP TABLE orders",
        "DROP TABLE orders;",
        "DELETE FROM orders WHERE id = 1",
        "UPDATE orders SET status = 'cancelled'",
        "INSERT INTO orders (customer_id, total_amount) VALUES (1, 50.0)",
        "ALTER TABLE orders ADD COLUMN dummy INT",
        "TRUNCATE orders",
        "CREATE TABLE test_table (id INT)",
        "GRANT ALL ON orders TO public",
        "REVOKE ALL ON orders FROM public",
        "VACUUM orders",
        "CALL test_proc()",
        "DO $$ BEGIN NULL; END $$",
        "SELECT 1; DROP TABLE orders;",
    ],
)
def test_explain_rejects_destructive_queries(client: TestClient, destructive_query: str):
    response = client.post("/api/v1/explain", json={"query": destructive_query})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"] in ("UNSAFE_QUERY_REJECTED", "MULTI_STATEMENT_REJECTED")


def test_explain_rejects_empty_query(client: TestClient):
    # Empty string fails pydantic min_length validation (422) or validator (400)
    response = client.post("/api/v1/explain", json={"query": "   "})
    assert response.status_code in (400, 422)


def test_critical_safety_table_intact_after_drop_attempt(client: TestClient):
    """Critical safety test: verifies that after sending a DROP TABLE request,

    the orders table remains completely intact and undisturbed.
    """
    # 1. Verify orders table exists and has rows before
    with engine.connect() as conn:
        count_before = conn.execute(text("SELECT count(*) FROM orders;")).scalar()
        assert count_before == 5000

    # 2. Attempt DROP TABLE orders via EXPLAIN endpoint
    response = client.post("/api/v1/explain", json={"query": "DROP TABLE orders;"})
    assert response.status_code == 400
    assert response.json()["error"] == "UNSAFE_QUERY_REJECTED"

    # 3. Verify orders table STILL exists and row count is unchanged
    with engine.connect() as conn:
        count_after = conn.execute(text("SELECT count(*) FROM orders;")).scalar()
        assert count_after == 5000
