from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.optimization import DiagnoseRequest, DiagnoseResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter(tags=["intelligence"])


@router.post(
    "/intelligence/diagnose",
    response_model=DiagnoseResponse,
    summary="Diagnose Database Performance Issue",
    description=(
        "Runs deterministic database diagnosis, retrieves similar historical "
        "optimization cases, and generates an advisory LLM explanation."
    ),
)
def diagnose(
    request: DiagnoseRequest,
    db: Session = Depends(get_db),
):
    """
    Phase 4.1 intelligence endpoint.

    The endpoint is advisory only:
    - no SQL remediation is executed
    - no recommendation is automatically approved
    - deterministic evidence remains authoritative
    """

    service = IntelligenceService(db)

    # Phase 4.1 currently accepts deterministic evidence from the
    # intelligence orchestration layer. Full automatic connection to
    # PlanAnalyzer/BottleneckDetector will be wired in the next integration step.
    analysis = {}
    findings = []
    recommendation = None

    return service.diagnose(
        request=request,
        analysis=analysis,
        findings=findings,
        recommendation=recommendation,
    )
