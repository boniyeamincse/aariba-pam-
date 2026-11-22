"""Access grant lifecycle, launch issuance, and revocation."""

import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, joinedload
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, AccessGrant, SessionLaunch, AccessSession
from ariba_pam.services.auth import get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.core.errors import ForbiddenException, NotFoundException, ConflictException
from ariba_pam.db.base import generate_id, utc_now, ensure_utc
from ariba_pam.api.schemas import RevokeGrantInput

router = APIRouter(prefix="/grants", tags=["Grants & Session Launch"])


@router.get("/{grant_id}", response_model=Dict[str, Any])
def get_grant(
    grant_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """View grant details within caller's scope."""
    grant = (
        db.query(AccessGrant)
        .options(
            joinedload(AccessGrant.asset),
            joinedload(AccessGrant.target_account),
        )
        .filter(AccessGrant.id == grant_id)
        .first()
    )
    if not grant:
        raise NotFoundException("Grant not found", code="GRANT_NOT_FOUND")

    # Requester or scoped operator/admin
    user_roles = ScopeChecker.get_user_roles(current_user)
    is_owner = grant.requester_id == current_user.id
    is_operator = "operator" in user_roles or "admin" in user_roles

    if not is_owner and not is_operator:
        raise NotFoundException("Grant not found", code="GRANT_NOT_FOUND")

    # Time-window evaluation
    now = utc_now()
    effective_start = ensure_utc(grant.effective_start_at)
    effective_end = ensure_utc(grant.effective_end_at)
    effective_status = grant.status
    if grant.status == "active":
        if now > effective_end:
            effective_status = "expired"

    return {
        "id": grant.id,
        "requester_id": grant.requester_id,
        "asset_id": grant.asset_id,
        "asset_name": grant.asset.name,
        "target_account": grant.target_account.username,
        "effective_start_at": effective_start.isoformat(),
        "effective_end_at": effective_end.isoformat(),
        "status": effective_status,
        "is_active_window": effective_start <= now <= effective_end,
    }


@router.post("/{grant_id}/launches", response_model=Dict[str, Any], status_code=201)
def create_session_launch(
    grant_id: str,
    x_correlation_id: str = Header(default="corr_launch_create"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a single-use launch authorization for the grant owner.
    Launch token digest is stored; raw token is returned once to the caller.
    """
    grant = db.get(AccessGrant, grant_id)
    if not grant:
        raise NotFoundException("Grant not found", code="GRANT_NOT_FOUND")

    # Only grant owner can launch
    if grant.requester_id != current_user.id:
        raise ForbiddenException("Only the grant owner can launch a session", code="NOT_GRANT_OWNER")

    # Check active status
    if grant.status != "active":
        raise ConflictException(f"Cannot launch from a {grant.status} grant", code="GRANT_NOT_ACTIVE")

    # Check time window
    now = utc_now()
    effective_start = ensure_utc(grant.effective_start_at)
    effective_end = ensure_utc(grant.effective_end_at)
    if now < effective_start or now > effective_end:
        raise ConflictException("Current time is outside the authorized grant window", code="WINDOW_EXPIRED")

    # Generate single-use launch token (opaque, random)
    raw_token = f"launch_{secrets.token_urlsafe(32)}"
    token_digest = hashlib.sha256(raw_token.encode("ascii")).hexdigest()

    # Short-lived launch authorization (e.g. 60 seconds to consume)
    launch_expiry = min(now + timedelta(seconds=60), effective_end)

    launch = SessionLaunch(
        id=generate_id("lnc"),
        grant_id=grant.id,
        launch_token_digest=token_digest,
        expires_at=launch_expiry,
        is_consumed=False,
    )
    db.add(launch)
    db.flush()

    AuditService.record_event(
        db=db,
        event_type="SESSION_LAUNCH_ISSUED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "launch_id": launch.id,
            "grant_id": grant.id,
            "expires_at": launch_expiry.isoformat(),
        },
    )
    db.commit()

    return {
        "launch_id": launch.id,
        "launch_token": raw_token,
        "expires_at": launch_expiry.isoformat(),
    }


@router.post("/{grant_id}/revoke", response_model=Dict[str, Any], status_code=202)
def revoke_grant(
    grant_id: str,
    payload: RevokeGrantInput,
    x_correlation_id: str = Header(default="corr_grant_revoke"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Commit grant revocation as a scoped security operator.
    Blocks new launches and marks active sessions for termination.
    """
    grant = db.get(AccessGrant, grant_id)
    if not grant:
        raise NotFoundException("Grant not found", code="GRANT_NOT_FOUND")

    user_roles = ScopeChecker.get_user_roles(current_user)
    if "operator" not in user_roles and "admin" not in user_roles:
        raise ForbiddenException("Only security operators or administrators can revoke grants", code="NOT_PERMITTED")

    grant.status = "revoked"
    grant.revocation_reason = payload.reason
    grant.revoked_at = utc_now()
    grant.revoked_by_id = current_user.id

    # Mark active sessions as terminating
    active_sessions = (
        db.query(AccessSession)
        .filter(AccessSession.grant_id == grant.id, AccessSession.status == "active")
        .all()
    )
    for session in active_sessions:
        session.status = "terminating"
        session.termination_reason = f"Grant revoked: {payload.reason}"

    AuditService.record_event(
        db=db,
        event_type="ACCESS_GRANT_REVOKED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "grant_id": grant.id,
            "reason": payload.reason,
            "terminated_sessions_count": len(active_sessions),
        },
    )
    db.commit()

    return {
        "grant_id": grant.id,
        "status": grant.status,
        "revoked_at": grant.revoked_at.isoformat(),
        "terminating_sessions_count": len(active_sessions),
    }
