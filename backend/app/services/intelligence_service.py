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
    BottleneckFinding,
    BottleneckType,
    CandidateEvaluation,
    DiagnoseRequest,
    DiagnoseResponse,
    DiagnosisResult,
    HypotheticalIndexRequest,
    IndexMethod,
)
from app.services.bottleneck_detector import BottleneckDetector
from app.services.database_monitor import DatabaseMonitorService
from app.services.hypopg_validator import HypoPGValidatorService
from app.services.llm_service import LLMService
from app.services.plan_analyzer import PlanAnalyzer
from app.services.rag_service import RAGService
from app.services.recommendation_engine import RecommendationEngine
from app.services.safety_assessor import SafetyAssessor


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

        # Deterministic candidate evaluation for MISSING_INDEX findings
        candidate_evaluations = self._evaluate_candidates(
            query=explain_result.query,
            findings=detected_findings,
        )

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
            candidate_evaluations=candidate_evaluations,
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

    def _evaluate_candidates(
        self,
        *,
        query: str,
        findings: list[BottleneckFinding],
    ) -> list[CandidateEvaluation]:
        """
        Deterministically evaluates index optimization candidates for MISSING_INDEX findings.

        1. Generates baseline and single-column candidate definitions strictly from
           columns extractable by RecommendationEngine.extract_candidate_columns.
        2. Deduplicates candidates deterministically using canonical keys.
        3. Independently validates each candidate via HypoPGValidatorService.
        4. Generates an OptimizationRecommendation for each candidate.
        5. Evaluates each candidate through SafetyAssessor to determine approval eligibility.
        """
        evaluations: list[CandidateEvaluation] = []
        seen_canonical_keys: set[tuple[str, str, tuple[str, ...]]] = set()

        for finding in findings:
            if finding.finding_type != BottleneckType.MISSING_INDEX:
                continue

            table = finding.relation or finding.evidence.get("relation")
            if not table or table == "<unknown>":
                continue

            extracted_cols = RecommendationEngine.extract_candidate_columns(finding)
            if not extracted_cols:
                continue

            # 1. Baseline candidate definition (all extracted columns)
            # 2. Single-column candidate definitions (each individual extracted column)
            candidate_definitions: list[tuple[list[str], bool]] = [
                (extracted_cols, True),
            ]
            for col in extracted_cols:
                candidate_definitions.append(([col], False))

            for cols, is_baseline in candidate_definitions:
                canonical_key = (
                    table.strip().lower(),
                    IndexMethod.BTREE.value.lower(),
                    tuple(c.strip().lower() for c in cols if c and c.strip()),
                )

                if not canonical_key[2] or canonical_key in seen_canonical_keys:
                    continue

                seen_canonical_keys.add(canonical_key)

                # Step A: Validate candidate via HypoPG
                val_req = HypotheticalIndexRequest(
                    query=query,
                    table=table,
                    columns=cols,
                    index_method=IndexMethod.BTREE,
                )
                validation_result = HypoPGValidatorService.validate_candidate(
                    request=val_req,
                    db=self.db,
                )

                # Step B: Generate deterministic recommendation for this candidate
                cand_rec = RecommendationEngine.recommend(
                    finding=finding,
                    validation=validation_result,
                )

                # Step C: Assess safety and approval eligibility
                safety_assessment = SafetyAssessor.assess(
                    recommendation=cand_rec,
                )

                col_suffix = "_".join(canonical_key[2])
                candidate_id = f"cand_{canonical_key[0]}_{col_suffix}"

                evaluations.append(
                    CandidateEvaluation(
                        candidate_id=candidate_id,
                        recommendation=cand_rec,
                        validation=validation_result,
                        safety_assessment=safety_assessment,
                        is_baseline=is_baseline,
                    )
                )

        return evaluations

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

