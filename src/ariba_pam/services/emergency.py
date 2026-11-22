"""Out-of-Band Emergency Break-Glass Access Service (FR-11, SOD-04, T-09)."""

import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from ariba_pam.db.base import generate_id, utc_now, ensure_utc
from ariba_pam.db.models import (
    User,
    Asset,
    TargetAccount,
    AccessGrant,
    SessionLaunch,
    AccessSession,
    EmergencyRequest,
    EmergencyApproval,
    RequestRevision,
    AccessRequest,
)
from ariba_pam.core.errors import (
    ForbiddenException,
    NotFoundException,
    ConflictException,
    ValidationException,
)
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.services.audit import AuditService
from ariba_pam.services.alerts import soc_alerts_service


class EmergencyAccessService:
    """Manages multi-custodian emergency break-glass requests, approvals, activation, revocation, and review."""

    @staticmethod
    def create_emergency_request(
        db: Session,
        requester: User,
        asset_id: str,
        target_account_id: str,
        justification: str,
        requested_end_at: datetime,
        required_approvals: int = 2,
    ) -> EmergencyRequest:
        """Submit an out-of-band break-glass emergency request."""
        now = utc_now()
        end_at = ensure_utc(requested_end_at)
        if end_at <= now:
            raise ValidationException("Requested end time must be in the future", code="INVALID_WINDOW")

        max_emergency_window = timedelta(hours=4)
        if (end_at - now) > max_emergency_window:
            raise ValidationException("Emergency access duration cannot exceed 4 hours", code="WINDOW_EXCEEDED")

        asset = db.get(Asset, asset_id)
        if not asset or not asset.is_active:
            raise NotFoundException("Asset not found or inactive", code="ASSET_NOT_FOUND")

        target_account = db.get(TargetAccount, target_account_id)
        if not target_account or not target_account.is_active or target_account.asset_id != asset.id:
            raise NotFoundException("Target account not found or inactive", code="TARGET_ACCOUNT_NOT_FOUND")

        emergency_req = EmergencyRequest(
            id=generate_id("emg"),
            asset_id=asset.id,
            target_account_id=target_account.id,
            requester_id=requester.id,
            justification=justification,
            status="pending",
            required_approvals=max(1, required_approvals),
            approval_count=0,
            requested_end_at=end_at,
            created_at=now,
        )
        db.add(emergency_req)
        db.flush()

        AuditService.record_event(
            db=db,
            event_type="EMERGENCY_REQUEST_SUBMITTED",
            correlation_id=f"corr_emg_{emergency_req.id}",
            actor_id=requester.id,
            payload={
                "emergency_id": emergency_req.id,
                "asset_id": asset.id,
                "asset_name": asset.name,
                "target_account": target_account.username,
                "justification": justification,
                "required_approvals": emergency_req.required_approvals,
                "requested_end_at": end_at.isoformat(),
            },
        )
        db.commit()
        db.refresh(emergency_req)

        return emergency_req

    @staticmethod
    def record_decision(
        db: Session,
        emergency_id: str,
        custodian: User,
        decision: str,
        reason: str,
    ) -> EmergencyRequest:
        """
        Record independent custodian decision for break-glass emergency access (SOD-04).
        Requester cannot approve their own emergency request.
        """
        emergency_req = (
            db.query(EmergencyRequest)
            .options(joinedload(EmergencyRequest.approvals))
            .filter(EmergencyRequest.id == emergency_id)
            .first()
        )
        if not emergency_req:
            raise NotFoundException("Emergency request not found", code="EMERGENCY_REQUEST_NOT_FOUND")

        if emergency_req.status != "pending":
            raise ConflictException(f"Emergency request is already {emergency_req.status}", code="INVALID_STATUS")

        # SOD-04: Separation of Duties - Requester cannot approve their own emergency access!
        if emergency_req.requester_id == custodian.id:
            raise ForbiddenException(
                "Requester cannot approve their own emergency request (SOD-04)",
                code="SELF_APPROVAL_DENIED",
            )

        # Authorized roles: emergency_custodian, admin, or security_operator
        user_roles = ScopeChecker.get_user_roles(custodian)
        if not (user_roles & {"emergency_custodian", "admin", "security_operator"}):
            raise ForbiddenException("Only emergency custodians can vote on emergency requests", code="NOT_PERMITTED")

        # Prevent duplicate voting by the same custodian
        if any(appr.custodian_id == custodian.id for appr in emergency_req.approvals):
            raise ConflictException("Custodian has already voted on this emergency request", code="DUPLICATE_APPROVAL")

        now = utc_now()
        approval = EmergencyApproval(
            id=generate_id("ema"),
            emergency_request_id=emergency_req.id,
            custodian_id=custodian.id,
            decision=decision,
            reason=reason,
            created_at=now,
        )
        db.add(approval)
        db.flush()

        if decision == "reject":
            emergency_req.status = "rejected"
            event_type = "EMERGENCY_REQUEST_REJECTED"
        elif decision == "approve":
            emergency_req.approval_count += 1
            if emergency_req.approval_count >= emergency_req.required_approvals:
                emergency_req.status = "approved"
            event_type = "EMERGENCY_REQUEST_APPROVED"
        else:
            raise ValidationException(f"Invalid decision: {decision}", code="INVALID_DECISION")

        AuditService.record_event(
            db=db,
            event_type=event_type,
            correlation_id=f"corr_emg_{emergency_req.id}",
            actor_id=custodian.id,
            payload={
                "emergency_id": emergency_req.id,
                "decision": decision,
                "reason": reason,
                "approval_count": emergency_req.approval_count,
                "required_approvals": emergency_req.required_approvals,
                "status": emergency_req.status,
            },
        )
        db.commit()
        db.refresh(emergency_req)

        return emergency_req

    @staticmethod
    def activate_emergency_access(
        db: Session,
        emergency_id: str,
        activator: User,
        step_up_token: str,
    ) -> Dict[str, Any]:
        """
        Activate break-glass emergency access upon reaching approved threshold.
        Issues emergency grant, generates launch token, and immediately triggers CRITICAL SOC alert.
        """
        emergency_req = (
            db.query(EmergencyRequest)
            .options(
                joinedload(EmergencyRequest.asset),
                joinedload(EmergencyRequest.target_account),
                joinedload(EmergencyRequest.approvals),
            )
            .filter(EmergencyRequest.id == emergency_id)
            .first()
        )
        if not emergency_req:
            raise NotFoundException("Emergency request not found", code="EMERGENCY_REQUEST_NOT_FOUND")

        if emergency_req.status != "approved":
            raise ConflictException(
                f"Emergency request cannot be activated in status '{emergency_req.status}'",
                code="NOT_APPROVED",
            )

        now = utc_now()
        grant_end = ensure_utc(emergency_req.requested_end_at)
        if now >= grant_end:
            raise ConflictException("Emergency window has already expired", code="WINDOW_EXPIRED")

        # Create backing request and revision for emergency access to maintain relational integrity
        access_req = AccessRequest(
            id=generate_id("req"),
            requester_id=emergency_req.requester_id,
            status="approved",
            created_at=now,
            updated_at=now,
        )
        db.add(access_req)
        db.flush()

        rev = RequestRevision(
            id=generate_id("rev"),
            request_id=access_req.id,
            revision_number=1,
            asset_id=emergency_req.asset_id,
            target_account_id=emergency_req.target_account_id,
            requested_start_at=now,
            requested_end_at=grant_end,
            justification=f"[EMERGENCY BREAK-GLASS] {emergency_req.justification}",
            ticket_ref=None,
            policy_version_id="emergency_override",
            is_frozen=True,
            created_at=now,
        )
        db.add(rev)
        db.flush()
        access_req.current_revision_id = rev.id

        grant = AccessGrant(
            id=generate_id("grn"),
            revision_id=rev.id,
            requester_id=emergency_req.requester_id,
            asset_id=emergency_req.asset_id,
            target_account_id=emergency_req.target_account_id,
            effective_start_at=now,
            effective_end_at=grant_end,
            status="active",
        )
        db.add(grant)
        db.flush()

        raw_launch_token = f"lnc_emg_{secrets.token_urlsafe(32)}"
        token_digest = hashlib.sha256(raw_launch_token.encode("ascii")).hexdigest()

        launch = SessionLaunch(
            id=generate_id("lau"),
            grant_id=grant.id,
            launch_token_digest=token_digest,
            expires_at=now + timedelta(minutes=5),  # 5-minute launch window
            is_consumed=False,
        )
        db.add(launch)
        db.flush()

        emergency_req.status = "active"
        emergency_req.activated_at = now
        emergency_req.grant_id = grant.id
        db.flush()

        # Emit High-Priority SOC Security Alert (FR-11, NFR-08)
        soc_alerts_service.record_alert(
            db=db,
            alert_type="EMERGENCY_ACCESS_ACTIVATED",
            severity="CRITICAL",
            title="Emergency break-glass access activated",
            description=(
                f"Emergency break-glass access activated for target account "
                f"'{emergency_req.target_account.username}' on asset '{emergency_req.asset.name}' "
                f"by requester '{emergency_req.requester_id}'."
            ),
            correlation_id=f"corr_emg_{emergency_req.id}",
            details={
                "emergency_id": emergency_req.id,
                "asset_id": emergency_req.asset_id,
                "target_account": emergency_req.target_account.username,
                "grant_id": grant.id,
                "effective_end_at": grant_end.isoformat(),
                "approver_count": len(emergency_req.approvals),
                "justification": emergency_req.justification,
            },
            asset_id=emergency_req.asset_id,
        )

        AuditService.record_event(
            db=db,
            event_type="EMERGENCY_ACCESS_ACTIVATED",
            correlation_id=f"corr_emg_{emergency_req.id}",
            actor_id=activator.id,
            payload={
                "emergency_id": emergency_req.id,
                "grant_id": grant.id,
                "launch_id": launch.id,
                "effective_end_at": grant_end.isoformat(),
            },
        )
        db.commit()

        return {
            "emergency_id": emergency_req.id,
            "status": "active",
            "grant_id": grant.id,
            "launch_token": raw_launch_token,
            "effective_end_at": grant_end.isoformat(),
            "target_host": emergency_req.asset.host,
            "target_port": emergency_req.asset.port,
            "target_username": emergency_req.target_account.username,
        }

    @staticmethod
    def revoke_emergency_access(
        db: Session,
        emergency_id: str,
        revoker: User,
        reason: str,
    ) -> EmergencyRequest:
        """Revoke emergency access immediately fail-closed and terminate active sessions."""
        emergency_req = (
            db.query(EmergencyRequest)
            .options(joinedload(EmergencyRequest.grant))
            .filter(EmergencyRequest.id == emergency_id)
            .first()
        )
        if not emergency_req:
            raise NotFoundException("Emergency request not found", code="EMERGENCY_REQUEST_NOT_FOUND")

        now = utc_now()
        emergency_req.status = "revoked"
        emergency_req.revoked_at = now
        emergency_req.revocation_reason = reason

        terminated_sessions_count = 0
        if emergency_req.grant:
            grant = emergency_req.grant
            grant.status = "revoked"
            grant.revoked_at = now
            grant.revoked_by_id = revoker.id
            grant.revocation_reason = reason

            # Terminate any active sessions
            active_sessions = db.scalars(
                select(AccessSession).where(
                    AccessSession.grant_id == grant.id,
                    AccessSession.status == "active",
                )
            ).all()
            for s in active_sessions:
                s.status = "ended"
                s.ended_at = now
                s.termination_reason = f"Emergency access revoked: {reason}"
                terminated_sessions_count += 1

        AuditService.record_event(
            db=db,
            event_type="EMERGENCY_ACCESS_REVOKED",
            correlation_id=f"corr_emg_{emergency_req.id}",
            actor_id=revoker.id,
            payload={
                "emergency_id": emergency_req.id,
                "reason": reason,
                "terminated_sessions_count": terminated_sessions_count,
            },
        )
        db.commit()
        db.refresh(emergency_req)

        return emergency_req

    @staticmethod
    def review_emergency_access(
        db: Session,
        emergency_id: str,
        reviewer: User,
        review_notes: str,
    ) -> EmergencyRequest:
        """
        Independent post-incident review (specifications/modules/audit-and-recovery.md).
        Reviewer cannot be the requester.
        """
        emergency_req = db.get(EmergencyRequest, emergency_id)
        if not emergency_req:
            raise NotFoundException("Emergency request not found", code="EMERGENCY_REQUEST_NOT_FOUND")

        if emergency_req.status not in ("revoked", "active", "approved"):
            raise ConflictException(f"Cannot review emergency request in '{emergency_req.status}'", code="INVALID_STATUS")

        # Independent review: reviewer cannot be the requester
        if emergency_req.requester_id == reviewer.id:
            raise ForbiddenException("Reviewer cannot be the emergency requester", code="INDEPENDENT_REVIEW_REQUIRED")

        now = utc_now()
        emergency_req.status = "reviewed"
        emergency_req.reviewed_at = now
        emergency_req.reviewer_id = reviewer.id
        emergency_req.review_notes = review_notes

        AuditService.record_event(
            db=db,
            event_type="EMERGENCY_ACCESS_REVIEWED",
            correlation_id=f"corr_emg_{emergency_req.id}",
            actor_id=reviewer.id,
            payload={
                "emergency_id": emergency_req.id,
                "reviewer_id": reviewer.id,
                "review_notes": review_notes,
            },
        )
        db.commit()
        db.refresh(emergency_req)

        return emergency_req
