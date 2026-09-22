from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1.monitor import router as monitor_router
from app.api.v1.intelligence_memory import router as memory_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.remediations import router as remediations_router
from app.api.v1.benchmarks import router as benchmarks_router
from app.api.v1.recommendations import router as recommendations_router

api_v1_router = APIRouter()

api_v1_router.include_router(health_router)
api_v1_router.include_router(monitor_router)
api_v1_router.include_router(memory_router)
api_v1_router.include_router(approvals_router)
api_v1_router.include_router(remediations_router)
api_v1_router.include_router(benchmarks_router)
api_v1_router.include_router(recommendations_router)
