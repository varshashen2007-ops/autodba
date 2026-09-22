from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.schemas.optimization import RemediationResult
from app.services.remediation_service import (
    RemediationBlockedError,
    RemediationError,
    RemediationExecutionError,
    RemediationService,
    RemediationVerificationError,
)

router = APIRouter(prefix="/remediations", tags=["remediation"])


class ApplyRemediationPayload(BaseModel):
    approval_id: str = Field(..., description="ID of the approved request to remediate")


@router.post("/apply", response_model=RemediationResult, summary="Apply approved physical remediation")
def apply_remediation(payload: ApplyRemediationPayload):
    try:
        return RemediationService.remediate(approval_id=payload.approval_id)
    except RemediationBlockedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (RemediationExecutionError, RemediationVerificationError) as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except RemediationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
