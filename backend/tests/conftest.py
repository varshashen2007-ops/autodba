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
    """Ensure baseline clean database state before executing the test session.

    Any physical index previously created by AutoDBA remediation is removed so
    the suite-wide "no new physical indexes" invariants start from a clean,
    deterministic state regardless of what ran before (closed loop, manual
    remediation, or a previous test session).
    """
    try:
        from app.db.database import engine
        from sqlalchemy import text
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE indexname LIKE 'idx_autodba_%'"
                )
            ).fetchall()
            for (indexname,) in rows:
                conn.execute(text(f'DROP INDEX IF EXISTS "{indexname}";'))
    except Exception:
        pass


