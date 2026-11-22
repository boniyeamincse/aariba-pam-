"""Out-of-band Emergency Break-Glass API endpoints (FR-11, SOD-04, T-09)."""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, desc

from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, EmergencyRequest, EmergencyApproval
from ariba_pam.services.auth import get_current_user
from ariba_pam.core.errors import ForbiddenException, NotFoundException, ConflictException
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.db.base import ensure_utc
from ariba_pam.api.schemas import (
    CreateEmergencyRequestInput,
    EmergencyDecisionInput,
    ActivateEmergencyInput,
    RevokeEmergencyInput,
    ReviewEmergencyInput,
    EmergencyRequestResponse,
    EmergencyApprovalResponse,
)
from ariba_pam.services.emergency import EmergencyAccessService

router = APIRouter(prefix="/emergency-requests", tags=["Emergency Break-Glass Access"])


def _format_emergency_response(req: EmergencyRequest) -> EmergencyRequestResponse:
    approvals = [
        EmergencyApprovalResponse(
            id=appr.id,
            custodian_id=appr.custodian_id,
            decision=appr.decision,
            reason=appr.reason,
            created_at=ensure_utc(appr.created_at),
        )
        for appr in req.approvals
    ]
    return EmergencyRequestResponse(
        id=req.id,
        asset_id=req.asset_id,
        target_account_id=req.target_account_id,
        requester_id=req.requester_id,
        justification=req.justification,
        status=req.status,
        required_approvals=req.required_approvals,
        approval_count=req.approval_count,
        requested_end_at=ensure_utc(req.requested_end_at),
        activated_at=ensure_utc(req.activated_at) if req.activated_at else None,
        revoked_at=ensure_utc(req.revoked_at) if req.revoked_at else None,
        revocation_reason=req.revocation_reason,
        reviewed_at=ensure_utc(req.reviewed_at) if req.reviewed_at else None,
        reviewer_id=req.reviewer_id,
        review_notes=req.review_notes,
        grant_id=req.grant_id,
        created_at=ensure_utc(req.created_at),
        approvals=approvals,
    )


@router.post("", response_model=EmergencyRequestResponse, status_code=201)
def submit_emergency_request(
    payload: CreateEmergencyRequestInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit an out-of-band emergency break-glass access request."""
    user_roles = ScopeChecker.get_user_roles(current_user)
    if not (user_roles & {"admin", "operator", "emergency_custodian", "security_operator"}):
        raise ForbiddenException("Only operators, administrators, or custodians can initiate emergency access", code="NOT_PERMITTED")

    req = EmergencyAccessService.create_emergency_request(
        db=db,
        requester=current_user,
        asset_id=payload.asset_id,
        target_account_id=payload.target_account_id,
        justification=payload.justification,
        requested_end_at=payload.requested_end_at,
        required_approvals=payload.required_approvals,
    )
    return _format_emergency_response(req)


@router.get("", response_model=List[EmergencyRequestResponse])
def list_emergency_requests(
    status: Optional[str] = Query(None, description="Filter by status (pending, approved, active, revoked, reviewed)"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List visible emergency break-glass requests."""
    user_roles = ScopeChecker.get_user_roles(current_user)
    is_custodian = bool(user_roles & {"admin", "emergency_custodian", "security_operator", "auditor"})

    stmt = (
        select(EmergencyRequest)
        .options(joinedload(EmergencyRequest.approvals))
        .order_by(desc(EmergencyRequest.created_at))
        .limit(limit)
    )

    if not is_custodian:
        # Non-custodians can only see their own requests
        stmt = stmt.where(EmergencyRequest.requester_id == current_user.id)

    if status:
        stmt = stmt.where(EmergencyRequest.status == status)

    requests = list(db.scalars(stmt).unique().all())
    return [_format_emergency_response(r) for r in requests]


@router.get("/{emergency_id}", response_model=EmergencyRequestResponse)
def get_emergency_request(
    emergency_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve details for a specific emergency break-glass request."""
    req = (
        db.query(EmergencyRequest)
        .options(joinedload(EmergencyRequest.approvals))
        .filter(EmergencyRequest.id == emergency_id)
        .first()
    )
    if not req:
        raise NotFoundException("Emergency request not found", code="EMERGENCY_REQUEST_NOT_FOUND")

    user_roles = ScopeChecker.get_user_roles(current_user)
    is_custodian = bool(user_roles & {"admin", "emergency_custodian", "security_operator", "auditor"})
    if not is_custodian and req.requester_id != current_user.id:
        # Anti-enumeration identifier concealment
        raise NotFoundException("Emergency request not found", code="EMERGENCY_REQUEST_NOT_FOUND")

    return _format_emergency_response(req)


@router.post("/{emergency_id}/approve", response_model=EmergencyRequestResponse, status_code=201)
def approve_emergency_request(
    emergency_id: str,
    payload: EmergencyDecisionInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record custodian approval or rejection for emergency break-glass access (SOD-04)."""
    req = EmergencyAccessService.record_decision(
        db=db,
        emergency_id=emergency_id,
        custodian=current_user,
        decision=payload.decision,
        reason=payload.reason,
    )
    return _format_emergency_response(req)


@router.post("/{emergency_id}/activate", response_model=Dict[str, Any])
def activate_emergency_access(
    emergency_id: str,
    payload: ActivateEmergencyInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activate approved emergency access, issue launch credentials, and trigger CRITICAL SOC alert."""
    return EmergencyAccessService.activate_emergency_access(
        db=db,
        emergency_id=emergency_id,
        activator=current_user,
        step_up_token=payload.step_up_token or "mfa_valid",
    )


@router.post("/{emergency_id}/revoke", response_model=EmergencyRequestResponse, status_code=202)
def revoke_emergency_access(
    emergency_id: str,
    payload: RevokeEmergencyInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke emergency access fail-closed and terminate active sessions."""
    req = EmergencyAccessService.revoke_emergency_access(
        db=db,
        emergency_id=emergency_id,
        revoker=current_user,
        reason=payload.reason,
    )
    return _format_emergency_response(req)


@router.post("/{emergency_id}/review", response_model=EmergencyRequestResponse)
def review_emergency_access(
    emergency_id: str,
    payload: ReviewEmergencyInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Post-access review and exercise sign-off by independent reviewer."""
    user_roles = ScopeChecker.get_user_roles(current_user)
    if not (user_roles & {"admin", "auditor", "security_operator"}):
        raise ForbiddenException("Only auditors, security operators, or administrators can review emergency access", code="NOT_PERMITTED")

    req = EmergencyAccessService.review_emergency_access(
        db=db,
        emergency_id=emergency_id,
        reviewer=current_user,
        review_notes=payload.review_notes,
    )
    return _format_emergency_response(req)


@router.get("/{emergency_id}/review", response_model=Dict[str, Any])
def get_emergency_review(
    emergency_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve post-incident review report and evidence references."""
    req = db.get(EmergencyRequest, emergency_id)
    if not req:
        raise NotFoundException("Emergency request not found", code="EMERGENCY_REQUEST_NOT_FOUND")

    user_roles = ScopeChecker.get_user_roles(current_user)
    is_custodian = bool(user_roles & {"admin", "emergency_custodian", "security_operator", "auditor"})
    if not is_custodian and req.requester_id != current_user.id:
        raise NotFoundException("Emergency request not found", code="EMERGENCY_REQUEST_NOT_FOUND")

    return {
        "emergency_id": req.id,
        "status": req.status,
        "reviewed": req.reviewed_at is not None,
        "reviewed_at": ensure_utc(req.reviewed_at).isoformat() if req.reviewed_at else None,
        "reviewer_id": req.reviewer_id,
        "review_notes": req.review_notes,
        "revoked_at": ensure_utc(req.revoked_at).isoformat() if req.revoked_at else None,
        "revocation_reason": req.revocation_reason,
    }
