from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.schemas.optimization import BenchmarkResult
from app.services.benchmark_service import (
    BenchmarkAuthorizationError,
    BenchmarkExecutionError,
    BenchmarkSafetyError,
    BenchmarkService,
)

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


class RunBenchmarkPayload(BaseModel):
    query: str = Field(..., min_length=1, description="Read-only query to benchmark")
    runs: Optional[int] = Field(default=10, ge=1, le=50, description="Measurement runs")
    warmup_runs: Optional[int] = Field(default=2, ge=0, le=10, description="Warmup runs to discard")


@router.post("/run", response_model=BenchmarkResult, summary="Execute controlled before/after benchmark")
def run_benchmark(payload: RunBenchmarkPayload):
    try:
        return BenchmarkService.benchmark(
            query=payload.query,
            runs=payload.runs,
            warmup_runs=payload.warmup_runs,
        )
    except BenchmarkSafetyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except BenchmarkAuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except BenchmarkExecutionError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
