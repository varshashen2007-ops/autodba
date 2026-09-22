import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Provides a FastAPI test client instance."""
    with TestClient(app) as test_client:
        yield test_client


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test against live database")


def pytest_sessionstart(session):
    """Ensure baseline clean database state before executing the test session."""
    try:
        from app.db.database import engine
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text("DROP INDEX IF EXISTS idx_autodba_orders_customer_id;"))
    except Exception:
        pass


