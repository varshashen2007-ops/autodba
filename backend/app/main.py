from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request, status
from app.db.database import get_db
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.exceptions import DatabaseExecutionError, SQLValidationError
from app.core.logging import logger
from app.api.health import router as health_router
from app.api.v1.router import api_v1_router
from app.api.v1.intelligence import diagnose
from app.schemas.optimization import OptimizationMemory
from app.api.v1.intelligence_memory import record_optimization_outcome
from app.schemas.monitor import ErrorResponse
from app.schemas.optimization import DiagnoseRequest, DiagnoseResponse
from app.schemas.optimization import ClosedLoopRequest, ClosedLoopResponse
from app.services.closed_loop_service import get_closed_loop_service

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


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title=f"{settings.PROJECT_NAME} API",
    version="0.1.0",
    description="AutoDBA backend foundation and performance engineering API",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SQLValidationError)
async def sql_validation_exception_handler(request: Request, exc: SQLValidationError):
    logger.warning(
        f"SQL validation error on {request.method} {request.url.path}: {exc.message}",
        extra={
            "operation": "sql_validation",
            "error_code": exc.error_code,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            error=exc.error_code,
            message=exc.message,
        ).model_dump(),
    )


@app.exception_handler(DatabaseExecutionError)
async def database_execution_exception_handler(
    request: Request,
    exc: DatabaseExecutionError,
):
    logger.error(
        f"Database execution error on {request.method} {request.url.path}: {exc.message}",
        extra={
            "operation": "db_execution",
            "error_code": exc.error_code,
            "path": request.url.path,
        },
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
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        extra={
            "operation": "unhandled_exception",
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
        ).model_dump(),
    )


# Existing API
app.include_router(
    api_v1_router,
    prefix=settings.API_V1_PREFIX,
)

# Phase 4.1 intelligence endpoint.
# Register directly because this FastAPI environment retains nested
# APIRouter objects instead of flattening them.
app.add_api_route(
    f"{settings.API_V1_PREFIX}/intelligence/diagnose",
    diagnose,
    methods=["POST"],
    response_model=DiagnoseResponse,
    tags=["intelligence"],
    summary="Diagnose Database Performance Issue",
)


# Phase 4.1 optimization memory endpoint.
app.add_api_route(
    f"{settings.API_V1_PREFIX}/intelligence/memories",
    record_optimization_outcome,
    methods=["POST"],
    response_model=OptimizationMemory,
    tags=["intelligence"],
    summary="Record an optimization outcome for future RAG retrieval",
)

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




# Phase 4.2 closed-loop self-improvement endpoint.
def execute_closed_loop(
    request: ClosedLoopRequest,
    db=Depends(get_db),
):
    service = get_closed_loop_service(db)
    return service.execute(
        approval_id=request.approval_id,
        query_text=request.query_text,
        incident_type=request.incident_type,
        diagnosis=request.diagnosis,
        recommendation=request.recommendation,
    )


app.add_api_route(
    f"{settings.API_V1_PREFIX}/intelligence/closed-loop",
    execute_closed_loop,
    methods=["POST"],
    response_model=ClosedLoopResponse,
    tags=["intelligence"],
    summary="Execute approved remediation, benchmark it, and store the outcome",
)
