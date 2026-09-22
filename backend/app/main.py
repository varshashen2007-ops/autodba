from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.core.exceptions import DatabaseExecutionError, SQLValidationError
from app.core.logging import logger
from app.api.health import router as health_router
from app.api.v1.router import api_v1_router
from app.schemas.monitor import ErrorResponse

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Starting {settings.PROJECT_NAME} in {settings.ENVIRONMENT} mode",
        extra={"operation": "startup", "environment": settings.ENVIRONMENT},
    )
    yield
    logger.info(
        f"Shutting down {settings.PROJECT_NAME}",
        extra={"operation": "shutdown"},
    )


app = FastAPI(
    title=f"{settings.PROJECT_NAME} API",
    version="0.1.0",
    description="AutoDBA backend foundation and performance engineering API",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)


@app.exception_handler(SQLValidationError)
async def sql_validation_exception_handler(request: Request, exc: SQLValidationError):
    """Handles query safety and validation rejections, returning 400 Bad Request."""
    logger.warning(
        f"SQL validation error on {request.method} {request.url.path}: {exc.message}",
        extra={"operation": "sql_validation", "error_code": exc.error_code, "path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            error=exc.error_code,
            message=exc.message,
        ).model_dump(),
    )


@app.exception_handler(DatabaseExecutionError)
async def database_execution_exception_handler(request: Request, exc: DatabaseExecutionError):
    """Handles database execution failures cleanly without exposing sensitive internals."""
    logger.error(
        f"Database execution error on {request.method} {request.url.path}: {exc.message}",
        extra={"operation": "db_execution", "error_code": exc.error_code, "path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            error=exc.error_code,
            message=exc.message,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Safely catches unhandled exceptions without leaking credentials or stack traces."""
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        extra={"operation": "unhandled_exception", "path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
        ).model_dump(),
    )


# Mount main v1 API router (/api/v1/health, /api/v1/slow-queries, /api/v1/explain)
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

# Top-level backwards compatibility mounts
app.include_router(health_router, prefix="/api")
app.include_router(health_router)


@app.get("/", tags=["root"])
def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT,
        "status": "running",
    }
