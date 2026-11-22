"""Access request workflows, immutable revision management, and idempotency."""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, update
from ariba_pam.db.session import get_db
from ariba_pam.db.models import (
    User,
    Asset,
    TargetAccount,
    AccessRequest,
    RequestRevision,
    ApprovalStep,
)
from ariba_pam.services.auth import get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.core.idempotency import IdempotencyService
from ariba_pam.core.errors import (
    ForbiddenException,
    NotFoundException,
    ConflictException,
    ValidationException,
)
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.api.schemas import CreateRequestInput, ReplaceRevisionInput
from ariba_pam.services.policies import authorize_request

router = APIRouter(prefix="/requests", tags=["Access Requests"])


@router.post("", response_model=Dict[str, Any], status_code=201)
def submit_access_request(
    payload: CreateRequestInput,
    x_correlation_id: str = Header(default="corr_request_submit"),
    x_idempotency_key: Optional[str] = Header(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit an access request with an immutable first revision (P2-02).
    Evaluates policy against requested window and account.
    Replay with same idempotency key returns the same request without repeating state change.
    """
    cached = IdempotencyService.check_idempotency(
        db=db,
        actor_id=current_user.id,
        operation="SUBMIT_ACCESS_REQUEST",
        idempotency_key=x_idempotency_key,
        payload=payload.model_dump(),
    )
    if cached:
        return cached[1]

    # Asset check
    asset = db.get(Asset, payload.asset_id)
    ScopeChecker.assert_asset_scope(current_user, asset)
    if not asset.is_active:
        raise ValidationException("Target asset is inactive", code="ASSET_INACTIVE")

    # Account check
    account = db.get(TargetAccount, payload.target_account_id)
    if not account or account.asset_id != asset.id or not account.is_active:
        raise NotFoundException("Target account not found or inactive on target asset", code="ACCOUNT_NOT_FOUND")

    version, rules = authorize_request(
        db, asset, account, payload.requested_start_at, payload.requested_end_at, payload.ticket_ref
    )

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
        policy_version_id=version.id,
        is_frozen=True,
        created_at=utc_now(),
    )
    db.add(rev)
    db.flush()

    # Set current revision ID
    req.current_revision_id = rev.id

    # Create required approval steps from policy
    steps = [
        ApprovalStep(
            id=generate_id("stp"),
            revision_id=rev.id,
            step_order=idx + 1,
            status="pending" if idx == 0 else "waiting",
            required_role="approver",
        )
        for idx in range(rules.required_approvals)
    ]
    db.add_all(steps)
    db.flush()

    response_data = {
        "request_id": req.id,
        "revision_id": rev.id,
        "step_id": steps[0].id,
        "policy_version_id": version.id,
        "status": req.status,
    }

    # Record outbox audit event atomically
    AuditService.record_event(
        db=db,
        event_type="ACCESS_REQUEST_SUBMITTED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "request_id": req.id,
            "revision_id": rev.id,
            "policy_version_id": version.id,
            "asset_id": asset.id,
            "target_account": account.username,
            "start_at": payload.requested_start_at.isoformat(),
            "end_at": payload.requested_end_at.isoformat(),
        },
    )

    # Record idempotency
    IdempotencyService.save_idempotency(
        db=db,
        actor_id=current_user.id,
        operation="SUBMIT_ACCESS_REQUEST",
        idempotency_key=x_idempotency_key,
        payload=payload.model_dump(),
        response_code=201,
        response_payload=response_data,
    )

    db.commit()
    return response_data


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


@router.get("/{request_id}", response_model=Dict[str, Any])
def get_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """View a scoped request, its current revision, and revision history (P2-03)."""
    req = (
        db.query(AccessRequest)
        .options(
            joinedload(AccessRequest.revisions).joinedload(RequestRevision.asset),
            joinedload(AccessRequest.revisions).joinedload(RequestRevision.target_account),
            joinedload(AccessRequest.revisions).joinedload(RequestRevision.steps).joinedload(ApprovalStep.decisions),
        )
        .filter(AccessRequest.id == request_id)
        .first()
    )
    if not req:
        raise NotFoundException("Request not found", code="REQUEST_NOT_FOUND")

    user_roles = ScopeChecker.get_user_roles(current_user)
    is_owner = req.requester_id == current_user.id
    is_admin = "admin" in user_roles

    current_rev = next((r for r in req.revisions if r.id == req.current_revision_id), None)
    if not is_owner and not is_admin:
        if not current_rev or not ScopeChecker.is_asset_in_scope(current_user, current_rev.asset, "approver"):
            raise NotFoundException("Request not found", code="REQUEST_NOT_FOUND")

    revisions_data = []
    for r in sorted(req.revisions, key=lambda x: x.revision_number):
        steps_data = []
        for s in sorted(r.steps, key=lambda x: x.step_order):
            decisions_data = [
                {
                    "decision_id": d.id,
                    "approver_id": d.approver_id,
                    "decision": d.decision,
                    "reason": d.reason,
                    "decided_at": d.decided_at.isoformat(),
                }
                for d in s.decisions
            ]
            steps_data.append({
                "step_id": s.id,
                "step_order": s.step_order,
                "status": s.status,
                "required_role": s.required_role,
                "decisions": decisions_data,
            })
        revisions_data.append({
            "revision_id": r.id,
            "revision_number": r.revision_number,
            "asset_id": r.asset_id,
            "asset_name": r.asset.name,
            "target_account_id": r.target_account_id,
            "target_account": r.target_account.username,
            "requested_start_at": r.requested_start_at.isoformat(),
            "requested_end_at": r.requested_end_at.isoformat(),
            "justification": r.justification,
            "ticket_ref": r.ticket_ref,
            "policy_version_id": r.policy_version_id,
            "is_frozen": r.is_frozen,
            "created_at": r.created_at.isoformat(),
            "steps": steps_data,
        })

    return {
        "request_id": req.id,
        "requester_id": req.requester_id,
        "status": req.status,
        "current_revision_id": req.current_revision_id,
        "created_at": req.created_at.isoformat(),
        "updated_at": req.updated_at.isoformat(),
        "revisions": revisions_data,
    }


@router.post("/{request_id}/revisions", response_model=Dict[str, Any], status_code=201)
def replace_request_revision(
    request_id: str,
    payload: ReplaceRevisionInput,
    x_correlation_id: str = Header(default="corr_request_revision_replace"),
    x_idempotency_key: Optional[str] = Header(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Replace a pending revision with changed fields and expected revision ID (P2-03).
    A stale change fails with 409 Conflict. Historical fields remain unchanged.
    """
    cached = IdempotencyService.check_idempotency(
        db=db,
        actor_id=current_user.id,
        operation="REPLACE_REQUEST_REVISION",
        idempotency_key=x_idempotency_key,
        payload=payload.model_dump(),
    )
    if cached:
        return cached[1]

    req = db.get(AccessRequest, request_id)
    if not req:
        raise NotFoundException("Request not found", code="REQUEST_NOT_FOUND")

    if req.requester_id != current_user.id:
        raise ForbiddenException("Only the requester can replace pending revisions", code="NOT_PERMITTED")

    if req.status != "pending":
        raise ConflictException("Only pending requests can have their revisions replaced", code="INVALID_STATE")

    if req.current_revision_id != payload.expected_revision_id:
        raise ConflictException("The request revision has changed", code="STALE_REVISION")

    current_rev = db.get(RequestRevision, req.current_revision_id)
    if not current_rev:
        raise NotFoundException("Current revision not found", code="REVISION_NOT_FOUND")

    new_account_id = payload.target_account_id or current_rev.target_account_id
    new_start_at = payload.requested_start_at or current_rev.requested_start_at
    new_end_at = payload.requested_end_at or current_rev.requested_end_at
    new_justification = payload.justification or current_rev.justification
    new_ticket_ref = payload.ticket_ref if payload.ticket_ref is not None else current_rev.ticket_ref

    asset = db.get(Asset, current_rev.asset_id)
    account = db.get(TargetAccount, new_account_id)
    if not account or account.asset_id != asset.id or not account.is_active:
        raise NotFoundException("Target account not found or inactive", code="ACCOUNT_NOT_FOUND")

    policy_ver, rules = authorize_request(
        db,
        asset,
        account,
        new_start_at,
        new_end_at,
        new_ticket_ref,
    )

    # Invalidate previous pending steps
    prev_steps = db.scalars(
        select(ApprovalStep).where(ApprovalStep.revision_id == current_rev.id, ApprovalStep.status == "pending")
    ).all()
    for s in prev_steps:
        s.status = "superseded"

    new_rev = RequestRevision(
        id=generate_id("rev"),
        request_id=req.id,
        revision_number=current_rev.revision_number + 1,
        asset_id=asset.id,
        target_account_id=account.id,
        requested_start_at=new_start_at,
        requested_end_at=new_end_at,
        justification=new_justification,
        ticket_ref=new_ticket_ref,
        policy_version_id=policy_ver.id,
        is_frozen=True,
        created_at=utc_now(),
    )
    db.add(new_rev)
    db.flush()

    new_steps = [
        ApprovalStep(
            id=generate_id("stp"),
            revision_id=new_rev.id,
            step_order=idx + 1,
            status="pending" if idx == 0 else "waiting",
            required_role="approver",
        )
        for idx in range(rules.required_approvals)
    ]
    db.add_all(new_steps)
    db.flush()

    req.current_revision_id = new_rev.id
    req.updated_at = utc_now()

    response_data = {
        "request_id": req.id,
        "revision_id": new_rev.id,
        "revision_number": new_rev.revision_number,
        "policy_version_id": policy_ver.id,
        "step_id": new_steps[0].id,
        "status": req.status,
    }

    AuditService.record_event(
        db=db,
        event_type="ACCESS_REQUEST_REVISION_REPLACED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "request_id": req.id,
            "previous_revision_id": current_rev.id,
            "new_revision_id": new_rev.id,
            "revision_number": new_rev.revision_number,
            "asset_id": asset.id,
            "target_account": account.username,
        },
    )

    IdempotencyService.save_idempotency(
        db=db,
        actor_id=current_user.id,
        operation="REPLACE_REQUEST_REVISION",
        idempotency_key=x_idempotency_key,
        payload=payload.model_dump(),
        response_code=201,
        response_payload=response_data,
    )

    db.commit()
    return response_data


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

    cancelled = db.execute(
        update(AccessRequest)
        .where(AccessRequest.id == req.id, AccessRequest.status == "pending")
        .values(status="cancelled", updated_at=utc_now())
    )
    if not cancelled.rowcount:
        raise ConflictException("Only pending requests can be cancelled", code="INVALID_STATE")

    AuditService.record_event(
        db=db,
        event_type="ACCESS_REQUEST_CANCELLED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={"request_id": req.id},
    )
    db.commit()

    return {"request_id": req.id, "status": req.status}
