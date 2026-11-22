"""Access request workflows and immutable revision management."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, Asset, TargetAccount, AccessRequest, RequestRevision, ApprovalStep
from ariba_pam.services.auth import get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.core.errors import ForbiddenException, NotFoundException, ConflictException, ValidationException
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.api.schemas import CreateRequestInput

router = APIRouter(prefix="/requests", tags=["Access Requests"])


@router.post("", response_model=Dict[str, Any], status_code=201)
def submit_access_request(
    payload: CreateRequestInput,
    x_correlation_id: str = Header(default="corr_request_submit"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit an access request with an immutable first revision.
    Validates asset availability, account existence, and time window.
    """
    if payload.requested_end_at <= payload.requested_start_at:
        raise ValidationException("requested_end_at must follow requested_start_at", code="INVALID_TIME_WINDOW")

    # Asset check
    asset = db.get(Asset, payload.asset_id)
    ScopeChecker.assert_asset_scope(current_user, asset)
    if not asset.is_active:
        raise ValidationException("Target asset is inactive", code="ASSET_INACTIVE")

    # Account check
    account = db.get(TargetAccount, payload.target_account_id)
    if not account or account.asset_id != asset.id or not account.is_active:
        raise NotFoundException("Target account not found or inactive on target asset", code="ACCOUNT_NOT_FOUND")

    if account.requires_ticket and not payload.ticket_ref:
        raise ValidationException("Target account requires a valid ticket reference", code="TICKET_REQUIRED")

    # Create Request
    req = AccessRequest(
        id=generate_id("req"),
        requester_id=current_user.id,
        status="pending",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(req)
    db.flush()

    # Create immutable Revision 1
    rev = RequestRevision(
        id=generate_id("rev"),
        request_id=req.id,
        revision_number=1,
        asset_id=asset.id,
        target_account_id=account.id,
        requested_start_at=payload.requested_start_at,
        requested_end_at=payload.requested_end_at,
        justification=payload.justification,
        ticket_ref=payload.ticket_ref,
        policy_version_id="pol_v1",
        is_frozen=True,
        created_at=utc_now(),
    )
    db.add(rev)
    db.flush()

    # Set current revision ID
    req.current_revision_id = rev.id

    # Create required approval step
    step = ApprovalStep(
        id=generate_id("stp"),
        revision_id=rev.id,
        step_order=1,
        status="pending",
        required_role="approver",
    )
    db.add(step)
    db.flush()

    # Record outbox audit event atomically
    AuditService.record_event(
        db=db,
        event_type="ACCESS_REQUEST_SUBMITTED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "request_id": req.id,
            "revision_id": rev.id,
            "asset_id": asset.id,
            "target_account": account.username,
            "start_at": payload.requested_start_at.isoformat(),
            "end_at": payload.requested_end_at.isoformat(),
        },
    )
    db.commit()

    return {
        "request_id": req.id,
        "revision_id": rev.id,
        "step_id": step.id,
        "status": req.status,
    }


@router.get("", response_model=List[Dict[str, Any]])
def list_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List requests visible to requester or scoped reviewer."""
    stmt = (
        select(AccessRequest)
        .options(
            joinedload(AccessRequest.revisions).joinedload(RequestRevision.asset),
            joinedload(AccessRequest.revisions).joinedload(RequestRevision.target_account),
        )
        .order_by(AccessRequest.created_at.desc())
    )
    all_reqs = list(db.scalars(stmt).unique().all())

    user_roles = ScopeChecker.get_user_roles(current_user)
    is_admin = "admin" in user_roles
    is_approver = "approver" in user_roles

    results = []
    for req in all_reqs:
        # User can view own requests
        if req.requester_id == current_user.id or is_admin:
            current_rev = next((r for r in req.revisions if r.id == req.current_revision_id), None)
            results.append({
                "id": req.id,
                "requester_id": req.requester_id,
                "status": req.status,
                "current_revision_id": req.current_revision_id,
                "asset_name": current_rev.asset.name if current_rev else None,
                "target_account": current_rev.target_account.username if current_rev else None,
                "created_at": req.created_at.isoformat(),
            })
        elif is_approver:
            # Check if asset is in approver's scope
            current_rev = next((r for r in req.revisions if r.id == req.current_revision_id), None)
            if current_rev and ScopeChecker.is_asset_in_scope(current_user, current_rev.asset, "approver"):
                results.append({
                    "id": req.id,
                    "requester_id": req.requester_id,
                    "status": req.status,
                    "current_revision_id": req.current_revision_id,
                    "asset_name": current_rev.asset.name,
                    "target_account": current_rev.target_account.username,
                    "created_at": req.created_at.isoformat(),
                })
    return results


@router.post("/{request_id}/cancel", response_model=Dict[str, Any])
def cancel_request(
    request_id: str,
    x_correlation_id: str = Header(default="corr_request_cancel"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a pending request as the requester."""
    req = db.get(AccessRequest, request_id)
    if not req:
        raise NotFoundException("Request not found", code="REQUEST_NOT_FOUND")

    if req.requester_id != current_user.id:
        raise ForbiddenException("Only the requester can cancel their request", code="NOT_PERMITTED")

    if req.status != "pending":
        raise ConflictException(f"Cannot cancel request in {req.status} state", code="INVALID_STATE")

    req.status = "cancelled"
    req.updated_at = utc_now()

    AuditService.record_event(
        db=db,
        event_type="ACCESS_REQUEST_CANCELLED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={"request_id": req.id},
    )
    db.commit()

    return {"request_id": req.id, "status": req.status}
