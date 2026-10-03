"""Advisory LLM layer regression tests.

The LLM explanation layer is strictly advisory: the deterministic engine is
authoritative and must keep working when the provider is unavailable,
rate-limited, or rejects an oversized request.  Previously any provider error
propagated out of ``IntelligenceService.diagnose`` and broke the entire
deterministic pipeline.
"""

import pytest
from sqlalchemy import text

from app.db.database import SessionLocal, engine
from app.schemas.optimization import DiagnoseRequest, SimilarCase
from app.services.intelligence_service import IntelligenceService
from app.services.llm_service import LLMProvider, LLMService

QUERY = "SELECT * FROM orders WHERE total_amount >= 450.00"


class _RaisingProvider(LLMProvider):
    def explain(self, *, query, diagnosis, recommendation, similar_cases):
        raise RuntimeError("provider unavailable")


class _StubProvider(LLMProvider):
    def explain(self, *, query, diagnosis, recommendation, similar_cases):
        return "deterministic explanation"


def test_llm_explanation_returns_none_on_provider_failure():
    service = LLMService(provider=_RaisingProvider())
    assert service.explain_diagnosis(
        query=QUERY, diagnosis={}, recommendation=None, similar_cases=[]
    ) is None


def test_llm_explanation_passes_through_provider_text():
    service = LLMService(provider=_StubProvider())
    assert service.explain_diagnosis(
        query=QUERY, diagnosis={}, recommendation=None, similar_cases=[]
    ) == "deterministic explanation"


def test_diagnose_survives_llm_provider_failure():
    """A broken LLM provider must not break the deterministic diagnosis."""
    with SessionLocal() as db:
        service = IntelligenceService(
            db, llm_service=LLMService(provider=_RaisingProvider())
        )
        response = service.diagnose(
            request=DiagnoseRequest(query=QUERY, include_rag=False)
        )

    assert response.diagnosis.query == QUERY
    assert response.diagnosis.analysis["summary"] is not None
    assert response.diagnosis.analysis["root_node"]["node_type"]
    assert response.diagnosis.analysis["raw_plan"]
    assert response.llm_explanation is None


def test_llm_historical_case_payload_excludes_heavy_evidence():
    """Historical cases sent to the LLM stay compact.

    Embedding the raw EXPLAIN plan and full benchmark evidence of real
    measured cases overflows the provider request-size limit.
    """
    case = SimilarCase(
        memory_id=1,
        incident_type="missing_index",
        query_text=QUERY,
        outcome="success",
        outcome_summary="Measured runtime improved by 82.38%.",
        provenance="measured",
        is_verified=True,
        verification_state="verified_measured",
        similarity=0.9,
        diagnosis={"raw_plan": [{"Plan": {"Node Type": "Seq Scan"}}]},
        recommendation={"relation": "orders", "columns": ["total_amount"]},
        benchmark={"before": {"mean_execution_time_ms": 1.0}},
    )

    projected = IntelligenceService._to_llm_historical_case(case)

    assert "diagnosis" not in projected
    assert "benchmark" not in projected
    assert projected["memory_id"] == 1
    assert projected["outcome"] == "success"
    assert projected["provenance"] == "measured"
    assert projected["is_verified"] is True
    assert projected["verification_state"] == "verified_measured"
    assert projected["recommendation"]["columns"] == ["total_amount"]


def test_llm_historical_case_projection_shrinks_real_payload():
    """The projected payload must be dramatically smaller than the full case."""
    with SessionLocal() as db:
        rows = db.execute(
            text(
                "SELECT id FROM optimization_memories "
                "WHERE provenance = 'measured' ORDER BY id DESC LIMIT 1"
            )
        ).fetchall()

    if not rows:
        pytest.skip("No verified measured memory available")

    from app.services.memory_service import MemoryService

    with SessionLocal() as db:
        service = MemoryService(db)
        found = service.search_similar(query=QUERY, limit=5)

    full_sizes, projected_sizes = [], []
    for case in found:
        full_sizes.append(len(str(case.model_dump(mode="json"))))
        projected_sizes.append(len(str(IntelligenceService._to_llm_historical_case(case))))

    assert sum(projected_sizes) < sum(full_sizes)