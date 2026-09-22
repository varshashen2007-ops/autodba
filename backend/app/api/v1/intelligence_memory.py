from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.optimization import (
    MemoryListItem,
    MemorySearchRequest,
    MemorySearchResponse,
    OptimizationMemory,
    OptimizationOutcomeRecord,
)
from app.services.memory_service import MemoryService

router = APIRouter(tags=["intelligence"])


def record_optimization_outcome(
    request: OptimizationOutcomeRecord,
    db: Session = Depends(get_db),
):
    service = MemoryService(db)

    benchmark = {
        "benchmark_id": request.benchmark_id,
        "remediation_id": request.remediation_id,
        "planner_cost_improvement_percent": request.planner_cost_improvement_percent,
        "runtime_improvement_percent": request.runtime_improvement_percent,
        "plan_changed": request.plan_changed,
        "index_usage_changed": request.index_usage_changed,
    }

    memory = service.create_memory(
        incident_type=request.incident_type,
        query_text=request.query_text,
        diagnosis=request.diagnosis,
        recommendation=request.recommendation,
        validation=request.validation,
        benchmark=benchmark,
        outcome=request.outcome,
        outcome_summary=request.outcome_summary,
    )

    return memory


@router.get(
    "/intelligence/memories",
    response_model=List[MemoryListItem],
    summary="List stored optimization memories",
)
def list_memories(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    service = MemoryService(db)
    return service.list_memories(limit=limit, offset=offset)


@router.get(
    "/intelligence/memories/{memory_id}",
    response_model=OptimizationMemory,
    summary="Get optimization memory by ID",
)
def get_memory(
    memory_id: int,
    db: Session = Depends(get_db),
):
    service = MemoryService(db)
    memory = service.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Memory '{memory_id}' not found")
    return memory


@router.post(
    "/intelligence/search",
    response_model=MemorySearchResponse,
    summary="Search optimization memories using semantic similarity",
)
def search_memories(
    request: MemorySearchRequest,
    db: Session = Depends(get_db),
):
    service = MemoryService(db)
    return service.search(request)
