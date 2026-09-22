from fastapi.testclient import TestClient

from app.main import app


def test_intelligence_diagnose_endpoint_returns_rag_llm_and_recommendation():
    client = TestClient(app)

    response = client.post(
        "/api/v1/intelligence/diagnose",
        json={
            "query": "SELECT * FROM orders WHERE customer_id = 42",
            "include_rag": True,
            "max_similar_cases": 3,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert "diagnosis" in body
    assert "llm_explanation" in body
    assert body["llm_provider"] == "groq"

    diagnosis = body["diagnosis"]

    assert "customer_id" in diagnosis["query"]
    assert diagnosis["rag_context"] is not None
    assert diagnosis["rag_context"]["retrieval_count"] >= 1
    assert len(diagnosis["rag_context"]["similar_cases"]) >= 1

    recommendation = diagnosis["recommendation"]

    assert recommendation is not None
    assert recommendation["optimization_type"] == "missing_index"
    assert recommendation["relation"] == "orders"
    assert "customer_id" in recommendation["columns"]
    assert recommendation["requires_human_approval"] is True

