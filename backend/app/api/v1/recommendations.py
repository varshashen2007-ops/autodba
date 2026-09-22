from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.db.database import engine
from app.schemas.optimization import (
    HypoPGValidationResult,
    OptimizationRecommendation,
)
from app.services.bottleneck_detector import BottleneckDetector
from app.services.database_monitor import DatabaseMonitorService
from app.services.hypopg_validator import HypoPGValidatorService, InvalidCandidateError
from app.services.plan_analyzer import PlanAnalyzer
from app.services.recommendation_engine import RecommendationEngine

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class ValidateCandidatePayload(BaseModel):
    query: str = Field(..., min_length=1, description="SQL query to evaluate")
    index_definition: str = Field(..., min_length=1, description="Candidate CREATE INDEX statement")
    table: str = Field(..., min_length=1, description="Target table name")
    min_improvement_percent: Optional[float] = Field(None, ge=0.0, description="Minimum cost improvement required")


class AnalyzeQueryPayload(BaseModel):
    query: str = Field(..., min_length=1, description="Read-only query to analyze")


class RecommendationsResponse(BaseModel):
    query: str
    recommendations: List[OptimizationRecommendation]


@router.post("/validate", response_model=HypoPGValidationResult, summary="HypoPG counterfactual validation")
def validate_candidate(payload: ValidateCandidatePayload):
    try:
        return HypoPGValidatorService.validate(
            query=payload.query,
            index_definition=payload.index_definition,
            table=payload.table,
            min_improvement_percent=payload.min_improvement_percent,
        )
    except InvalidCandidateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/generate", response_model=RecommendationsResponse, summary="Generate recommendations for query")
def generate_recommendations(payload: AnalyzeQueryPayload):
    try:
        with engine.connect() as conn:
            explain_result = DatabaseMonitorService.explain_query(db=None, query=payload.query)
            raw_plan = explain_result.plan
            root_node, _, _ = PlanAnalyzer.analyze(raw_plan=raw_plan, query=payload.query)
            findings = BottleneckDetector.detect(root_node=root_node)
            recs = RecommendationEngine.recommend_all(findings=findings)
            return RecommendationsResponse(query=payload.query, recommendations=recs)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
