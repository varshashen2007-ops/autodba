from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.schemas.optimization import (
    ApprovalRequest,
    OptimizationRecommendation,
)
from app.services.approval_service import (
    ApprovalNotFoundError,
    ApprovalStateError,
    IneligibleForApprovalError,
    default_approval_service,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


class CreateApprovalPayload(BaseModel):
    recommendation: OptimizationRecommendation


class ApprovePayload(BaseModel):
    approved_by: str = Field(..., min_length=1, description="Name or ID of human approver")


class RejectPayload(BaseModel):
    rejection_reason: str = Field(..., min_length=1, description="Reason for rejection")


@router.get("", response_model=List[ApprovalRequest], summary="List approval requests")
def list_approvals():
    return default_approval_service.list_requests()


@router.post("", response_model=ApprovalRequest, status_code=status.HTTP_201_CREATED, summary="Create an approval request")
def create_approval(payload: CreateApprovalPayload):
    try:
        return default_approval_service.create_approval_request(payload.recommendation)
    except IneligibleForApprovalError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{approval_id}", response_model=ApprovalRequest, summary="Get approval request by ID")
def get_approval(approval_id: str):
    req = default_approval_service.get_approval_request(approval_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Approval request '{approval_id}' not found")
    return req


@router.post("/{approval_id}/approve", response_model=ApprovalRequest, summary="Approve an approval request")
def approve_request(approval_id: str, payload: ApprovePayload):
    try:
        return default_approval_service.approve(approval_id, approved_by=payload.approved_by)
    except ApprovalNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ApprovalStateError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{approval_id}/reject", response_model=ApprovalRequest, summary="Reject an approval request")
def reject_request(approval_id: str, payload: RejectPayload):
    try:
        return default_approval_service.reject(approval_id, rejection_reason=payload.rejection_reason)
    except ApprovalNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ApprovalStateError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
