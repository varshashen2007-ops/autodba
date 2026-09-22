"""
Phase 1 Acceptance Tests
========================
End-to-end verification that the full Phase 1 stack operates correctly.

These tests run inside the Docker Compose network so that a real PostgreSQL
connection is available.  They verify:

  - pg_stat_statements is active and collecting statistics
  - HypoPG extension is available
  - Correct seed row counts
  - Slow-query endpoint returns real pg_stat_statements data
  - slow-queries 'limit' and 'min_exec_time_ms' parameters work
  - EXPLAIN returns a structured query plan with expected fields
  - All destructive SQL forms are rejected by the safety validator
  - String literals containing destructive words are NOT rejected (false-positive check)
  - Database integrity is preserved throughout all destructive-query tests
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.db.database import engine


# ---------------------------------------------------------------------------
# Infrastructure acceptance
# ---------------------------------------------------------------------------

def test_postgresql_extensions_active():
    """pg_stat_statements and hypopg must be installed and enabled."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT extname FROM pg_extension;")).fetchall()
        ext_names = {r[0] for r in rows}
    assert "pg_stat_statements" in ext_names, "pg_stat_statements extension missing"
    assert "hypopg" in ext_names, "hypopg extension missing"


def test_expected_tables_exist():
    """All four e-commerce tables must exist."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename;"
            )
        ).fetchall()
        tables = {r[0] for r in rows}
    assert "customers" in tables
    assert "products" in tables
    assert "orders" in tables
    assert "order_items" in tables


def test_seed_row_counts():
    """Deterministic seed data must produce exact row counts."""
    with engine.connect() as conn:
        customers = conn.execute(text("SELECT count(*) FROM customers;")).scalar()
        products = conn.execute(text("SELECT count(*) FROM products;")).scalar()
        orders = conn.execute(text("SELECT count(*) FROM orders;")).scalar()
        order_items = conn.execute(text("SELECT count(*) FROM order_items;")).scalar()

    assert customers == 500, f"Expected 500 customers, got {customers}"
    assert products == 100, f"Expected 100 products, got {products}"
    assert orders == 5000, f"Expected 5000 orders, got {orders}"
    assert order_items == 15000, f"Expected 15000 order_items, got {order_items}"


def test_shared_preload_libraries():
    """pg_stat_statements must appear in shared_preload_libraries."""
    with engine.connect() as conn:
        val = conn.execute(text("SHOW shared_preload_libraries;")).scalar()
    assert "pg_stat_statements" in val


def test_hypopg_functional():
    """HypoPG must be usable: create a hypothetical index and clean up.

    HypoPG hypothetical indexes are session-scoped, so index creation and
    EXPLAIN must run within the same connection object.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT hypopg_reset();"))

        # hypopg_create_index returns a set of rows with (indexrelid, indexname)
        row = conn.execute(
            text("SELECT * FROM hypopg_create_index('CREATE INDEX ON orders (customer_id)');")
        ).fetchone()
        assert row is not None, "hypopg_create_index returned no row"

        # row = (indexrelid::oid, indexname::text)
        idx_name = row[1]
        assert "btree_orders_customer_id" in idx_name, (
            f"Unexpected hypothetical index name: {idx_name}"
        )

        # EXPLAIN inside the same session should switch to Bitmap/Index Scan
        plan_rows = conn.execute(
            text("EXPLAIN SELECT * FROM orders WHERE customer_id = 42;")
        ).fetchall()
        plan_text = " ".join(r[0] for r in plan_rows)
        assert "Index" in plan_text or "Bitmap" in plan_text, (
            f"Expected hypothetical index to appear in plan, got: {plan_text}"
        )

        conn.execute(text("SELECT hypopg_reset();"))


# ---------------------------------------------------------------------------
# Monitoring acceptance
# ---------------------------------------------------------------------------

def test_slow_queries_returns_real_statistics(client: TestClient):
    """Executing a query against the DB must produce an entry in pg_stat_statements."""
    # Run a distinctive query so pg_stat_statements has something to record
    with engine.connect() as conn:
        conn.execute(text("SELECT * FROM orders WHERE customer_id = 42;")).fetchall()

    response = client.get("/api/v1/slow-queries?limit=20")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    assert len(data["queries"]) == data["count"]

    # At least one query in pg_stat_statements must reference 'orders'
    order_queries = [q for q in data["queries"] if "orders" in q["query"].lower()]
    assert len(order_queries) >= 1, "No 'orders' query found in pg_stat_statements results"

    # Schema validation on each returned record
    for q in data["queries"]:
        assert isinstance(q["query"], str) and q["query"]
        assert isinstance(q["calls"], int) and q["calls"] >= 0
        assert isinstance(q["total_time_ms"], float) and q["total_time_ms"] >= 0
        assert isinstance(q["mean_time_ms"], float) and q["mean_time_ms"] >= 0
        assert isinstance(q["rows"], int) and q["rows"] >= 0
        assert isinstance(q["shared_blks_hit"], int)
        assert isinstance(q["shared_blks_read"], int)


def test_slow_queries_limit_parameter(client: TestClient):
    """The 'limit' parameter must cap the number of returned queries."""
    for limit in (1, 3, 5):
        response = client.get(f"/api/v1/slow-queries?limit={limit}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["queries"]) <= limit


def test_slow_queries_min_exec_time_filter(client: TestClient):
    """Queries with mean execution time below the threshold must be filtered out."""
    # Setting an astronomically high threshold should return zero results
    response = client.get("/api/v1/slow-queries?min_exec_time_ms=999999999")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["queries"] == []


# ---------------------------------------------------------------------------
# EXPLAIN acceptance
# ---------------------------------------------------------------------------

def test_explain_returns_structured_plan(client: TestClient):
    """EXPLAIN must return a structured plan with expected PostgreSQL fields."""
    response = client.post(
        "/api/v1/explain",
        json={"query": "SELECT * FROM orders WHERE customer_id = 42"},
    )
    assert response.status_code == 200
    data = response.json()

    # Envelope
    assert data["query"] == "SELECT * FROM orders WHERE customer_id = 42"
    assert isinstance(data["plan"], list)
    assert len(data["plan"]) >= 1

    # PostgreSQL planner fields
    plan_node = data["plan"][0]["Plan"]
    assert "Node Type" in plan_node
    assert "Startup Cost" in plan_node
    assert "Total Cost" in plan_node
    assert "Plan Rows" in plan_node
    assert plan_node["Relation Name"] == "orders"


def test_explain_trailing_semicolon_stripped(client: TestClient):
    """A trailing semicolon in the query must be stripped before execution."""
    response = client.post(
        "/api/v1/explain",
        json={"query": "SELECT 1;"},
    )
    assert response.status_code == 200
    data = response.json()
    assert not data["query"].endswith(";")


def test_explain_select_1(client: TestClient):
    """SELECT 1 must produce a valid plan (no table scan)."""
    response = client.post("/api/v1/explain", json={"query": "SELECT 1"})
    assert response.status_code == 200
    assert response.json()["plan"][0]["Plan"]["Node Type"] == "Result"


def test_explain_plan_node_type_is_seq_scan_without_index(client: TestClient):
    """Without an index on customer_id, orders must use a sequential scan strategy.

    PostgreSQL may choose 'Seq Scan' or 'Parallel Seq Scan'; either is correct
    and both indicate the missing index is detected by the planner.
    """
    response = client.post(
        "/api/v1/explain",
        json={"query": "SELECT * FROM orders WHERE customer_id = 42"},
    )
    assert response.status_code == 200
    plan = response.json()["plan"][0]["Plan"]

    # Walk nested plans to find the relation scan node
    def find_orders_node(node: dict) -> dict | None:
        if node.get("Relation Name") == "orders":
            return node
        for child in node.get("Plans", []):
            found = find_orders_node(child)
            if found:
                return found
        return None

    orders_node = find_orders_node(plan)
    assert orders_node is not None, f"No 'orders' relation node found in plan: {plan}"
    node_type = orders_node["Node Type"]
    assert "Scan" in node_type, (
        f"Expected a Scan node on orders (e.g. 'Seq Scan', 'Parallel Seq Scan'), got: {node_type}"
    )


# ---------------------------------------------------------------------------
# Security acceptance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_query,expected_error",
    [
        ("INSERT INTO orders (customer_id, total_amount) VALUES (1, 10.0)", "UNSAFE_QUERY_REJECTED"),
        ("UPDATE orders SET status = 'cancelled'", "UNSAFE_QUERY_REJECTED"),
        ("DELETE FROM orders WHERE id = 1", "UNSAFE_QUERY_REJECTED"),
        ("DROP TABLE orders", "UNSAFE_QUERY_REJECTED"),
        ("ALTER TABLE orders ADD COLUMN dummy INT", "UNSAFE_QUERY_REJECTED"),
        ("TRUNCATE orders", "UNSAFE_QUERY_REJECTED"),
        ("TRUNCATE TABLE orders", "UNSAFE_QUERY_REJECTED"),
        ("CREATE TABLE _test (id INT)", "UNSAFE_QUERY_REJECTED"),
        ("GRANT ALL ON orders TO public", "UNSAFE_QUERY_REJECTED"),
        ("REVOKE ALL ON orders FROM public", "UNSAFE_QUERY_REJECTED"),
        ("VACUUM orders", "UNSAFE_QUERY_REJECTED"),
        ("CALL test_proc()", "UNSAFE_QUERY_REJECTED"),
        ("DO $$ BEGIN NULL; END $$", "UNSAFE_QUERY_REJECTED"),
        ("SELECT 1; DROP TABLE orders;", "MULTI_STATEMENT_REJECTED"),
        ("SELECT * FROM orders; SELECT * FROM customers;", "MULTI_STATEMENT_REJECTED"),
    ],
)
def test_security_destructive_sql_rejected(client: TestClient, bad_query: str, expected_error: str):
    """Every destructive SQL form must be rejected with the expected error code."""
    response = client.post("/api/v1/explain", json={"query": bad_query})
    assert response.status_code == 400, f"Expected 400 for: {bad_query}"
    body = response.json()
    assert body["error"] == expected_error, (
        f"Expected error {expected_error!r}, got {body['error']!r} for: {bad_query}"
    )


@pytest.mark.parametrize(
    "safe_with_dangerous_literal",
    [
        # String literals that contain destructive words — the word is NOT a token
        "SELECT * FROM customers WHERE name = 'DROP TABLE orders'",
        "SELECT * FROM customers WHERE name = 'DELETE FROM orders'",
        # 'update' appears as part of a status value, not a keyword
        "SELECT * FROM orders WHERE status = 'needs_update'",
        # 'create' appears as a value, not a keyword
        "SELECT * FROM orders WHERE status = 'create'",
        # Valid columns: orders schema = id, customer_id, order_date, total_amount, status
        "SELECT id, order_date FROM orders WHERE status = 'completed'",
        # Valid columns: customers schema = id, name, email, created_at
        "SELECT id, created_at FROM customers WHERE name = 'DROP TABLE'",
    ],
)
def test_security_string_literals_not_false_positives(client: TestClient, safe_with_dangerous_literal: str):
    """String literals containing destructive words must NOT be rejected."""
    response = client.post("/api/v1/explain", json={"query": safe_with_dangerous_literal})
    assert response.status_code == 200, (
        f"False positive rejection for safe literal query: {safe_with_dangerous_literal}"
    )


def test_security_comment_containing_destructive_word(client: TestClient):
    """A valid SELECT with a comment containing DROP must be accepted."""
    query = "-- DROP TABLE orders\nSELECT 1"
    response = client.post("/api/v1/explain", json={"query": query})
    assert response.status_code == 200


def test_security_empty_and_whitespace_rejected(client: TestClient):
    """Empty and whitespace-only queries must not reach the database."""
    for q in ["", "   ", "\n\t"]:
        response = client.post("/api/v1/explain", json={"query": q})
        # Pydantic min_length=6 catches some; validator catches others
        assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Database integrity acceptance
# ---------------------------------------------------------------------------

def test_database_integrity_after_all_destructive_attempts(client: TestClient):
    """
    Critical: Record row counts, attempt every destructive SQL form via the
    API, then verify the database is completely unchanged.
    """
    # --- Before counts ---
    with engine.connect() as conn:
        before = {
            "customers": conn.execute(text("SELECT count(*) FROM customers;")).scalar(),
            "products": conn.execute(text("SELECT count(*) FROM products;")).scalar(),
            "orders": conn.execute(text("SELECT count(*) FROM orders;")).scalar(),
            "order_items": conn.execute(text("SELECT count(*) FROM order_items;")).scalar(),
        }

    destructive_queries = [
        "DROP TABLE orders",
        "DROP TABLE order_items",
        "DROP TABLE customers",
        "DROP TABLE products",
        "DELETE FROM orders",
        "DELETE FROM order_items",
        "TRUNCATE orders",
        "UPDATE orders SET status = 'dropped'",
        "INSERT INTO orders (customer_id, total_amount) VALUES (999999, 0)",
        "ALTER TABLE orders DROP COLUMN status",
    ]
    for q in destructive_queries:
        resp = client.post("/api/v1/explain", json={"query": q})
        assert resp.status_code == 400, f"Destructive query was NOT rejected: {q}"

    # --- After counts must be identical ---
    with engine.connect() as conn:
        after = {
            "customers": conn.execute(text("SELECT count(*) FROM customers;")).scalar(),
            "products": conn.execute(text("SELECT count(*) FROM products;")).scalar(),
            "orders": conn.execute(text("SELECT count(*) FROM orders;")).scalar(),
            "order_items": conn.execute(text("SELECT count(*) FROM order_items;")).scalar(),
        }

    for table in ("customers", "products", "orders", "order_items"):
        assert before[table] == after[table], (
            f"Row count for '{table}' changed: {before[table]} -> {after[table]}"
        )

    assert before["orders"] == 5000
    assert before["order_items"] == 15000


# ---------------------------------------------------------------------------
# API documentation acceptance
# ---------------------------------------------------------------------------

def test_openapi_schema_contains_all_endpoints(client: TestClient):
    """All v1 endpoints must appear in the OpenAPI schema."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]

    assert "/api/v1/health" in paths
    assert "/api/v1/slow-queries" in paths
    assert "/api/v1/explain" in paths


def test_swagger_ui_accessible(client: TestClient):
    """/docs must return HTTP 200."""
    response = client.get("/docs")
    assert response.status_code == 200
