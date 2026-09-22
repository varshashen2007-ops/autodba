from fastapi import APIRouter
from app.api.health import router as health_router
from app.api.v1.monitor import router as monitor_router

api_v1_router = APIRouter()

# Register health check and monitoring endpoints under /api/v1
api_v1_router.include_router(health_router)
api_v1_router.include_router(monitor_router)
