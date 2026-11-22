"""Approval workflows with strict separation of duties and atomic grant issuance."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, aliased, joinedload
from sqlalchemy import select, update
from ariba_pam.db.session import get_db
from ariba_pam.db.models import (
    User,
    ApprovalStep,
    ApprovalDecision,
    AccessRequest,
    RequestRevision,
    AccessGrant,
)
from ariba_pam.services.auth import get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.core.errors import ForbiddenException, NotFoundException, ConflictException
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.api.schemas import DecisionInput
from ariba_pam.services.policies import authorize_revision

router = APIRouter(tags=["Approvals & Decision Control"])


@router.get("/approvals", response_model=List[Dict[str, Any]])
def list_pending_approvals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List pending approval steps within the caller's scoped authority."""
    user_roles = ScopeChecker.get_user_roles(current_user)
    if "approver" not in user_roles and "admin" not in user_roles:
        return []

    earlier_step = aliased(ApprovalStep)
    prior_vote = (
        select(ApprovalDecision.id)
        .join(earlier_step, earlier_step.id == ApprovalDecision.step_id)
        .where(earlier_step.revision_id == RequestRevision.id, ApprovalDecision.approver_id == current_user.id)
        .exists()
    )
    stmt = (
        select(ApprovalStep)
        .options(
            joinedload(ApprovalStep.revision).joinedload(RequestRevision.asset),
            joinedload(ApprovalStep.revision).joinedload(RequestRevision.target_account),
            joinedload(ApprovalStep.revision).joinedload(RequestRevision.request),
        )
        .join(ApprovalStep.revision)
        .join(RequestRevision.request)
        .where(
            ApprovalStep.status == "pending",
            AccessRequest.status == "pending",
            AccessRequest.current_revision_id == RequestRevision.id,
            ~prior_vote,
        )
    )
    steps = list(db.scalars(stmt).unique().all())

    results = []
    for step in steps:
        rev = step.revision
        if rev.request.requester_id != current_user.id and ScopeChecker.is_asset_in_scope(
            current_user, rev.asset, step.required_role
        ):
            results.append({
                "step_id": step.id,
                "request_id": rev.request_id,
                "revision_id": rev.id,
                "requester_id": rev.request.requester_id,
                "asset_id": rev.asset.id,
                "asset_name": rev.asset.name,
                "target_account": rev.target_account.username,
                "requested_start_at": rev.requested_start_at.isoformat(),
                "requested_end_at": rev.requested_end_at.isoformat(),
                "justification": rev.justification,
            })
    return results


@router.post("/approval-steps/{step_id}/decisions", response_model=Dict[str, Any], status_code=201)
def record_decision(
    step_id: str,
    payload: DecisionInput,
    x_correlation_id: str = Header(default="corr_approval_decision"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Record an approval or rejection.
    Enforces separation of duties (no self-approval), scope checks, and atomic grant issuance.
    """
    step = (
        db.query(ApprovalStep)
        .options(
            joinedload(ApprovalStep.revision).joinedload(RequestRevision.asset),
            joinedload(ApprovalStep.revision).joinedload(RequestRevision.target_account),
            joinedload(ApprovalStep.revision).joinedload(RequestRevision.request),
        )
        .filter(ApprovalStep.id == step_id)
        .first()
    )
    if not step:
        raise NotFoundException("Approval step not found", code="STEP_NOT_FOUND")

    if step.status != "pending":
        raise ConflictException("Approval step is no longer pending", code="STEP_ALREADY_DECIDED")

    rev = step.revision
    req = rev.request

    # Stale revision protection
    if rev.id != payload.expected_revision_id:
        raise ConflictException("Decision targeted a stale revision", code="STALE_REVISION")

    # Separation of duties: Self-approval rejection (T-02)
    if req.requester_id == current_user.id:
        raise ForbiddenException("Self-approval is forbidden. Requesters cannot approve their own requests.", code="SELF_APPROVAL_FORBIDDEN")

    # Scoped permission check
    if not ScopeChecker.is_asset_in_scope(current_user, rev.asset, step.required_role):
        raise ForbiddenException("Asset is outside caller's approver scope", code="OUT_OF_SCOPE")

    claimed = db.execute(
        update(AccessRequest)
        .where(
            AccessRequest.id == req.id,
            AccessRequest.current_revision_id == rev.id,
            AccessRequest.status == "pending",
        )
        .values(updated_at=utc_now())
    )
    if not claimed.rowcount:
        raise ConflictException("Request is no longer pending on this revision", code="STALE_REVISION")
    db.refresh(step)
    if step.status != "pending":
        raise ConflictException("Approval step is no longer pending", code="STEP_ALREADY_DECIDED")

    existing_vote = (
        db.query(ApprovalDecision)
        .join(ApprovalStep)
        .filter(ApprovalStep.revision_id == rev.id, ApprovalDecision.approver_id == current_user.id)
        .first()
    )
    if existing_vote:
        raise ConflictException("Each approval step requires a different principal", code="DUPLICATE_VOTE")

    if payload.decision == "approved":
        authorize_revision(db, rev)

    # Record decision
    decision_record = ApprovalDecision(
        id=generate_id("dcs"),
        step_id=step.id,
        approver_id=current_user.id,
        decision=payload.decision,
        reason=payload.reason,
        decided_at=utc_now(),
    )
    db.add(decision_record)
    step.status = payload.decision

    grant_id = None
    next_step = db.scalar(
        select(ApprovalStep)
        .where(ApprovalStep.revision_id == rev.id, ApprovalStep.status == "waiting")
        .order_by(ApprovalStep.step_order)
        .limit(1)
    )
    if payload.decision == "rejected":
        req.status = "rejected"
        req.updated_at = utc_now()
        AuditService.record_event(
            db=db,
            event_type="ACCESS_REQUEST_REJECTED",
            correlation_id=x_correlation_id,
            actor_id=current_user.id,
            payload={
                "request_id": req.id,
                "step_id": step.id,
                "reason": payload.reason,
            },
        )
    elif next_step is not None:
        next_step.status = "pending"
        AuditService.record_event(
            db=db,
            event_type="ACCESS_APPROVAL_STEP_APPROVED",
            correlation_id=x_correlation_id,
            actor_id=current_user.id,
            payload={"request_id": req.id, "step_id": step.id, "next_step_id": next_step.id},
        )
    else:
        req.status = "approved"
        req.updated_at = utc_now()

        # Atomic Grant Issuance in the exact same transaction
        grant = AccessGrant(
            id=generate_id("grn"),
            revision_id=rev.id,
            requester_id=req.requester_id,
            asset_id=rev.asset_id,
            target_account_id=rev.target_account_id,
            effective_start_at=rev.requested_start_at,
            effective_end_at=rev.requested_end_at,
            status="active",
        )
        db.add(grant)
        db.flush()
        grant_id = grant.id

        AuditService.record_event(
            db=db,
            event_type="ACCESS_GRANT_ISSUED",
            correlation_id=x_correlation_id,
            actor_id=current_user.id,
            payload={
                "grant_id": grant.id,
                "request_id": req.id,
                "revision_id": rev.id,
                "policy_version_id": rev.policy_version_id,
                "asset_id": rev.asset_id,
                "target_account_id": rev.target_account_id,
                "start_at": grant.effective_start_at.isoformat(),
                "end_at": grant.effective_end_at.isoformat(),
            },
        )

    db.commit()

    return {
        "step_id": step.id,
        "decision": payload.decision,
        "request_status": req.status,
        "grant_id": grant_id,
    }
