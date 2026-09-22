"""
Phase 4.1: Intelligence Service

Coordinates the deterministic AutoDBA diagnosis engine, recommendation engine,
historical RAG retrieval, and advisory LLM explanation layer.

The deterministic engine remains authoritative.
The LLM cannot execute SQL, approve remediation, or bypass safety controls.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.schemas.optimization import (
    DiagnoseRequest,
    DiagnoseResponse,
    DiagnosisResult,
)
from app.services.bottleneck_detector import BottleneckDetector
from app.services.database_monitor import DatabaseMonitorService
from app.services.llm_service import LLMService
from app.services.plan_analyzer import PlanAnalyzer
from app.services.rag_service import RAGService
from app.services.recommendation_engine import RecommendationEngine


class IntelligenceService:
    def __init__(
        self,
        db: Session,
        rag_service: Optional[RAGService] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        self.db = db
        self.rag_service = rag_service or RAGService(db)
        self.llm_service = llm_service or LLMService()

    def diagnose(
        self,
        *,
        request: DiagnoseRequest,
        analysis: Optional[Dict[str, Any]] = None,
        findings: Optional[list[Dict[str, Any]]] = None,
        recommendation: Optional[Dict[str, Any]] = None,
        incident_type: Optional[str] = None,
    ) -> DiagnoseResponse:
        explain_result = DatabaseMonitorService.explain_query(
            db=self.db,
            query=request.query,
        )

        raw_plan = explain_result.plan

        root_node, nodes_analyzed, summary = PlanAnalyzer.analyze(
            raw_plan=raw_plan,
            query=explain_result.query,
        )

        detected_findings = BottleneckDetector.detect(
            root_node=root_node,
        )

        summary.findings_count = len(detected_findings)

        deterministic_analysis: Dict[str, Any] = {
            "nodes_analyzed": nodes_analyzed,
            "summary": summary.model_dump(mode="json"),
            "root_node": root_node.model_dump(mode="json"),
            "raw_plan": raw_plan,
        }

        deterministic_findings = [
            finding.model_dump(mode="json")
            for finding in detected_findings
        ]

        # Recommendation generation remains fully deterministic.
        # HypoPG validation/safety/remediation remain separate authoritative
        # stages and are never delegated to the LLM.
        generated_recommendations = RecommendationEngine.recommend_all(
            findings=detected_findings,
        )

        generated_recommendation = None
        if generated_recommendations:
            generated_recommendation = generated_recommendations[0].model_dump(
                mode="json"
            )

        resolved_recommendation = recommendation or generated_recommendation

        resolved_incident_type = (
            incident_type
            or request.incident_type
            or self._infer_incident_type(deterministic_findings)
        )

        rag_context = None

        if request.include_rag:
            rag_context = self.rag_service.retrieve(
                query=request.query,
                incident_type=resolved_incident_type,
                limit=request.max_similar_cases,
            )

        diagnosis = DiagnosisResult(
            query=explain_result.query,
            incident_type=resolved_incident_type,
            analysis=deterministic_analysis,
            findings=deterministic_findings,
            recommendation=resolved_recommendation,
            rag_context=rag_context,
        )

        similar_cases: list[Dict[str, Any]] = []
        if rag_context:
            similar_cases = [
                case.model_dump(mode="json")
                for case in rag_context.similar_cases
            ]

        llm_explanation = self.llm_service.explain_diagnosis(
            query=explain_result.query,
            diagnosis=diagnosis.model_dump(
                mode="json",
                exclude={"rag_context"},
            ),
            recommendation=resolved_recommendation,
            similar_cases=similar_cases,
        )

        return DiagnoseResponse(
            diagnosis=diagnosis,
            llm_explanation=llm_explanation,
            llm_provider="groq",
        )

    @staticmethod
    def _infer_incident_type(findings: list[Dict[str, Any]]) -> str:
        priority = [
            "missing_index",
            "filtered_seq_scan",
            "expensive_sort",
            "expensive_nested_loop",
            "large_row_estimate",
        ]

        finding_types = {
            str(
                finding.get("finding_type")
                or finding.get("type")
                or ""
            ).lower()
            for finding in findings
        }

        for incident_type in priority:
            if incident_type in finding_types:
                return incident_type

        return "unknown"


def get_intelligence_service(db: Session) -> IntelligenceService:
    return IntelligenceService(db)

