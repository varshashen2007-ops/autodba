from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.db.database import check_db_connection
from app.schemas.monitor import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health():
    """Returns application and PostgreSQL database connectivity status."""
    db_info = check_db_connection()
    if db_info.get("connected"):
        return HealthResponse(
            status="healthy",
            database="connected",
            version=db_info.get("version"),
            extensions=db_info.get("extensions", []),
        )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=HealthResponse(
            status="degraded",
            database="disconnected",
            version=None,
            extensions=[],
        ).model_dump(),
    )
