from unittest.mock import patch
from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "AutoDBA"
    assert data["status"] == "running"


def test_health_endpoint_healthy(client: TestClient):
    with patch("app.api.health.check_db_connection") as mock_check:
        mock_check.return_value = {
            "connected": True,
            "version": "PostgreSQL 17.0",
            "extensions": ["pg_stat_statements", "hypopg"],
        }
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "pg_stat_statements" in data["extensions"]
        assert "hypopg" in data["extensions"]


def test_health_endpoint_degraded(client: TestClient):
    with patch("app.api.health.check_db_connection") as mock_check:
        mock_check.return_value = {
            "connected": False,
            "error": "Connection refused",
            "extensions": [],
        }
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"
