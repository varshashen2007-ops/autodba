import pytest
from app.core.exceptions import (
    InvalidSQLError,
    MultiStatementSQLError,
    UnsafeSQLError,
)
from app.services.sql_validator import validate_read_only_query


def test_allowed_select_queries():
    # Basic SELECT
    assert validate_read_only_query("SELECT 1") == "SELECT 1"
    assert validate_read_only_query("SELECT * FROM orders") == "SELECT * FROM orders"
    assert (
        validate_read_only_query("SELECT * FROM orders WHERE customer_id = 42")
        == "SELECT * FROM orders WHERE customer_id = 42"
    )

    # Trailing semicolon stripped cleanly
    assert (
        validate_read_only_query("SELECT * FROM orders WHERE customer_id = 42;")
        == "SELECT * FROM orders WHERE customer_id = 42"
    )

    # Comments and line breaks
    query_with_comment = """
    -- Fetch active customers
    SELECT id, name
    FROM customers
    WHERE id > 10;
    """
    assert "SELECT id, name" in validate_read_only_query(query_with_comment)


def test_allowed_string_containing_destructive_word():
    # The word DROP is inside a single-quoted string literal, not a keyword
    query = "SELECT id, name FROM customers WHERE name = 'DROP TABLE orders'"
    assert validate_read_only_query(query) == query

    # The word update in identifier or string
    query2 = "SELECT id, updated_at FROM orders WHERE status = 'needs_update'"
    assert validate_read_only_query(query2) == query2


def test_allowed_read_only_cte():
    query = "WITH active AS (SELECT id FROM orders WHERE status = 'completed') SELECT count(*) FROM active"
    assert validate_read_only_query(query) == query


@pytest.mark.parametrize(
    "destructive_query",
    [
        "DROP TABLE orders",
        "DROP TABLE orders;",
        "DELETE FROM orders WHERE id = 1",
        "UPDATE orders SET status = 'cancelled' WHERE id = 1",
        "INSERT INTO orders (customer_id, total_amount) VALUES (1, 10.0)",
        "ALTER TABLE orders ADD COLUMN notes TEXT",
        "TRUNCATE orders",
        "TRUNCATE TABLE orders",
        "CREATE TABLE test_table (id INT)",
        "GRANT ALL PRIVILEGES ON orders TO public",
        "REVOKE SELECT ON orders FROM public",
        "VACUUM FULL orders",
        "CALL cleanup_old_orders()",
        "DO $$ BEGIN NULL; END $$",
        "COPY orders TO '/tmp/orders.csv'",
    ],
)
def test_rejected_destructive_queries(destructive_query: str):
    with pytest.raises(UnsafeSQLError):
        validate_read_only_query(destructive_query)


def test_rejected_multi_statements():
    with pytest.raises(MultiStatementSQLError):
        validate_read_only_query("SELECT 1; DROP TABLE orders;")

    with pytest.raises(MultiStatementSQLError):
        validate_read_only_query("SELECT * FROM orders; SELECT * FROM customers;")

    with pytest.raises(MultiStatementSQLError):
        validate_read_only_query("SELECT 1; ;")


def test_rejected_empty_and_comments_only():
    with pytest.raises(InvalidSQLError):
        validate_read_only_query("")

    with pytest.raises(InvalidSQLError):
        validate_read_only_query("   \n\t  ")

    with pytest.raises(InvalidSQLError):
        validate_read_only_query("-- just a comment\n-- another comment")

    with pytest.raises(InvalidSQLError):
        validate_read_only_query("/* block comment only */")


def test_rejected_data_modifying_cte():
    with pytest.raises(UnsafeSQLError):
        validate_read_only_query(
            "WITH del AS (DELETE FROM orders RETURNING id) SELECT count(*) FROM del"
        )
