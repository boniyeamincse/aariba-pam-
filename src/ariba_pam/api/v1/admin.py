"""Administrative change management enforcing independent four-eyes review."""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from sqlalchemy import update
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, AdminChangeProposal, Asset, TargetAccount, BackupRehearsalRecord
from ariba_pam.services.auth import get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.errors import ForbiddenException, NotFoundException, ConflictException
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.db.base import generate_id, utc_now, ensure_utc
from ariba_pam.api.schemas import (
    AdminProposalInput,
    AdminProposalDecisionInput,
    CreateSnapshotInput,
    RestoreRehearsalInput,
    BackupRehearsalResponse,
)
from ariba_pam.services.backup import BackupRestoreService
from ariba_pam.services.policies import (
    check_expected_version,
    publish_policy,
    scoped_policy_asset,
    validate_proposed_policy,
)

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

    if payload.resource_type == "policy":
        asset = scoped_policy_asset(db, payload.resource_id, current_user, ("admin", "operator"))
        validate_proposed_policy(db, asset, payload.change_payload)
        check_expected_version(db, asset.id, payload.expected_version)

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
    if proposal.resource_type == "policy":
        roles = ("admin", "operator") if proposal.author_id == current_user.id else ("admin", "reviewer")
        scoped_policy_asset(db, proposal.resource_id, current_user, roles)

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

    asset = None
    if proposal.resource_type == "policy":
        asset = scoped_policy_asset(db, proposal.resource_id, current_user, ("admin", "reviewer"), lock=True)

    if proposal.status != "pending":
        raise ConflictException(f"Proposal is already {proposal.status}", code="STALE_PROPOSAL")

    # Enforce separation of duties (Self-review rejection)
    if proposal.author_id == current_user.id:
        raise ForbiddenException("Self-review is strictly forbidden. An independent reviewer is required.", code="SELF_REVIEW_DENIED")

    user_roles = ScopeChecker.get_user_roles(current_user)
    if "admin" not in user_roles and "reviewer" not in user_roles:
        raise ForbiddenException("Only designated reviewers or administrators can review proposals", code="NOT_PERMITTED")

    version = None
    if asset is not None:
        # Claim the pending decision in the transaction even on engines without row locks.
        claimed = db.execute(
            update(AdminChangeProposal)
            .where(AdminChangeProposal.id == proposal.id, AdminChangeProposal.status == "pending")
            .values(reviewed_at=utc_now())
        )
        if not claimed.rowcount:
            raise ConflictException("Proposal has already been reviewed", code="STALE_PROPOSAL")
        if payload.decision == "applied":
            version = publish_policy(db, asset, proposal)

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

    policy_details = {"policy_version_id": version.id, "policy_version": version.version} if version else {}
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
            **policy_details,
        },
    )
    db.commit()

    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "reviewer_id": current_user.id,
        **policy_details,
    }


@router.post("/backup/snapshots", response_model=Dict[str, Any], status_code=201)
def create_backup_snapshot(
    payload: CreateSnapshotInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a point-in-time snapshot across all PAM tables and compute manifest digest."""
    user_roles = ScopeChecker.get_user_roles(current_user)
    if "admin" not in user_roles and "operator" not in user_roles:
        raise ForbiddenException("Only administrators or operators can create backup snapshots", code="NOT_PERMITTED")

    snapshot = BackupRestoreService.create_snapshot(db, label=payload.label, operator_id=current_user.id)
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "label": snapshot["label"],
        "created_at": snapshot["created_at"],
        "manifest_sha256": snapshot["manifest_sha256"],
        "table_counts": snapshot["table_counts"],
    }


@router.post("/backup/restore-rehearsal", response_model=BackupRehearsalResponse, status_code=201)
def execute_restore_rehearsal(
    payload: RestoreRehearsalInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Execute disaster recovery restore rehearsal in isolated staging session (P5-07 / NFR-04, T-09).
    Measures RTO/RPO, verifies WORM evidence integrity, and reconciles stale grants fail-closed.
    """
    user_roles = ScopeChecker.get_user_roles(current_user)
    if "admin" not in user_roles and "operator" not in user_roles:
        raise ForbiddenException("Only administrators or operators can execute restore rehearsals", code="NOT_PERMITTED")

    snapshot = payload.snapshot
    if not snapshot:
        # Create a fresh snapshot of current state to restore against
        snapshot = BackupRestoreService.create_snapshot(db, label="rehearsal_auto_snap", operator_id=current_user.id)

    record = BackupRestoreService.execute_restore_rehearsal(
        snapshot=snapshot,
        target_db=db,
        exercise_ref=payload.exercise_ref,
        operator_id=current_user.id,
        simulated_data_loss_seconds=payload.simulated_data_loss_seconds,
    )

    return BackupRehearsalResponse(
        id=record.id,
        exercise_ref=record.exercise_ref,
        operator_id=record.operator_id,
        snapshot_id=record.snapshot_id,
        rto_seconds=record.rto_seconds,
        rpo_seconds=record.rpo_seconds,
        target_rto_seconds=record.target_rto_seconds,
        target_rpo_seconds=record.target_rpo_seconds,
        status=record.status,
        restored_counts=record.restored_counts,
        reconciled_grants_count=record.reconciled_grants_count,
        reconciled_sessions_count=record.reconciled_sessions_count,
        worm_verified=record.worm_verified,
        notes=record.notes,
        created_at=ensure_utc(record.created_at),
    )


@router.get("/backup/rehearsals", response_model=List[BackupRehearsalResponse])
def list_restore_rehearsals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List historical disaster recovery rehearsal reports."""
    user_roles = ScopeChecker.get_user_roles(current_user)
    if "admin" not in user_roles and "operator" not in user_roles and "auditor" not in user_roles:
        raise ForbiddenException("Access restricted to administrators and auditors", code="NOT_PERMITTED")

    rehearsals = db.query(BackupRehearsalRecord).order_by(BackupRehearsalRecord.created_at.desc()).all()
    return [
        BackupRehearsalResponse(
            id=r.id,
            exercise_ref=r.exercise_ref,
            operator_id=r.operator_id,
            snapshot_id=r.snapshot_id,
            rto_seconds=r.rto_seconds,
            rpo_seconds=r.rpo_seconds,
            target_rto_seconds=r.target_rto_seconds,
            target_rpo_seconds=r.target_rpo_seconds,
            status=r.status,
            restored_counts=r.restored_counts,
            reconciled_grants_count=r.reconciled_grants_count,
            reconciled_sessions_count=r.reconciled_sessions_count,
            worm_verified=r.worm_verified,
            notes=r.notes,
            created_at=ensure_utc(r.created_at),
        )
        for r in rehearsals
    ]

