"""Administrative change management enforcing independent four-eyes review."""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from sqlalchemy import select
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, AdminChangeProposal, Asset, TargetAccount
from ariba_pam.services.auth import get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.errors import ForbiddenException, NotFoundException, ConflictException
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.api.schemas import AdminProposalInput, AdminProposalDecisionInput

router = APIRouter(prefix="/admin", tags=["Administration & Change Control"])


@router.post("/change-proposals", response_model=Dict[str, Any], status_code=201)
def submit_change_proposal(
    payload: AdminProposalInput,
    x_correlation_id: str = Header(default="corr_admin_proposal"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a proposed change to inventory, roles, or policy for independent review."""
    user_roles = ScopeChecker.get_user_roles(current_user)
    if "admin" not in user_roles and "operator" not in user_roles:
        raise ForbiddenException("Only administrators or operators can submit change proposals", code="NOT_PERMITTED")

    proposal = AdminChangeProposal(
        id=generate_id("prp"),
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        change_payload=payload.change_payload,
        expected_version=payload.expected_version,
        author_id=current_user.id,
        status="pending",
        created_at=utc_now(),
    )
    db.add(proposal)
    db.flush()

    AuditService.record_event(
        db=db,
        event_type="ADMIN_PROPOSAL_SUBMITTED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "proposal_id": proposal.id,
            "resource_type": payload.resource_type,
            "reason": payload.reason,
        },
    )
    db.commit()

    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "resource_type": proposal.resource_type,
    }


@router.get("/change-proposals/{proposal_id}", response_model=Dict[str, Any])
def get_change_proposal(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """View a scoped change proposal."""
    proposal = db.get(AdminChangeProposal, proposal_id)
    if not proposal:
        raise NotFoundException("Proposal not found", code="PROPOSAL_NOT_FOUND")

    return {
        "id": proposal.id,
        "resource_type": proposal.resource_type,
        "resource_id": proposal.resource_id,
        "change_payload": proposal.change_payload,
        "status": proposal.status,
        "author_id": proposal.author_id,
        "reviewer_id": proposal.reviewer_id,
        "rejection_reason": proposal.rejection_reason,
        "created_at": proposal.created_at.isoformat(),
        "reviewed_at": proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
    }


@router.post("/change-proposals/{proposal_id}/decisions", response_model=Dict[str, Any])
def decide_change_proposal(
    proposal_id: str,
    payload: AdminProposalDecisionInput,
    x_correlation_id: str = Header(default="corr_admin_decision"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Apply or reject an independently reviewed change.
    Separation of duties: Author cannot review their own proposal.
    """
    proposal = db.get(AdminChangeProposal, proposal_id)
    if not proposal:
        raise NotFoundException("Proposal not found", code="PROPOSAL_NOT_FOUND")

    if proposal.status != "pending":
        raise ConflictException(f"Proposal is already {proposal.status}", code="STALE_PROPOSAL")

    # Enforce separation of duties (Self-review rejection)
    if proposal.author_id == current_user.id:
        raise ForbiddenException("Self-review is strictly forbidden. An independent reviewer is required.", code="SELF_REVIEW_DENIED")

    user_roles = ScopeChecker.get_user_roles(current_user)
    if "admin" not in user_roles and "reviewer" not in user_roles:
        raise ForbiddenException("Only designated reviewers or administrators can review proposals", code="NOT_PERMITTED")

    proposal.reviewer_id = current_user.id
    proposal.reviewed_at = utc_now()

    if payload.decision == "rejected":
        proposal.status = "rejected"
        proposal.rejection_reason = payload.reason or "Rejected by reviewer"
    elif payload.decision == "applied":
        proposal.status = "applied"
        # Apply the change if resource_type == "asset"
        if proposal.resource_type == "asset":
            cp = proposal.change_payload
            new_asset = Asset(
                id=proposal.resource_id or generate_id("ast"),
                name=cp["name"],
                environment=cp["environment"],
                team=cp["team"],
                zone_id=cp["zone_id"],
                host=cp["host"],
                port=cp.get("port", 22),
                is_active=cp.get("is_active", True),
            )
            db.add(new_asset)
            db.flush()
            if "accounts" in cp:
                for acc_data in cp["accounts"]:
                    db.add(
                        TargetAccount(
                            id=generate_id("act"),
                            asset_id=new_asset.id,
                            username=acc_data["username"],
                            is_active=acc_data.get("is_active", True),
                            requires_ticket=acc_data.get("requires_ticket", False),
                            max_duration_seconds=acc_data.get("max_duration_seconds", 3600),
                        )
                    )

    AuditService.record_event(
        db=db,
        event_type=f"ADMIN_PROPOSAL_{proposal.status.upper()}",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "proposal_id": proposal.id,
            "decision": payload.decision,
            "reason": payload.reason,
            "resource_type": proposal.resource_type,
        },
    )
    db.commit()

    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "reviewer_id": current_user.id,
    }
