"""Internal gateway interfaces for launch consumption, lease renewal, and session events."""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, joinedload
from ariba_pam.config import settings
from ariba_pam.db.session import get_db
from ariba_pam.db.models import SessionLaunch, AccessGrant, AccessSession, Asset, TargetAccount
from ariba_pam.services.audit import AuditService
from ariba_pam.core.errors import ForbiddenException, NotFoundException, ConflictException, UnauthorizedException
from ariba_pam.db.base import generate_id, utc_now, ensure_utc
from ariba_pam.api.schemas import LaunchConsumeInput
from ariba_pam.services.policies import authorize_revision

router = APIRouter(prefix="/internal/v1", tags=["Internal Gateway Interfaces"])


def verify_gateway_identity(
    x_gateway_secret: str = Header(default=""),
) -> None:
    """Validate internal gateway authentication."""
    if not x_gateway_secret or x_gateway_secret != settings.gateway_api_secret:
        raise UnauthorizedException("Invalid or missing gateway authentication credentials", code="GATEWAY_UNAUTHORIZED")


@router.post("/launches/consume", response_model=Dict[str, Any], status_code=201)
def consume_launch(
    payload: LaunchConsumeInput,
    x_correlation_id: str = Header(default="corr_gateway_consume"),
    db: Session = Depends(get_db),
    _gw_auth: None = Depends(verify_gateway_identity),
):
    """
    Gateway consumes a single-use launch capability.
    Enforces atomic consumption, non-replay, expiry, and active grant status (T-04).
    """
    token_digest = hashlib.sha256(payload.launch_token.encode("ascii")).hexdigest()

    # Query launch with lock to prevent race conditions
    launch = (
        db.query(SessionLaunch)
        .options(
            joinedload(SessionLaunch.grant).joinedload(AccessGrant.asset),
            joinedload(SessionLaunch.grant).joinedload(AccessGrant.target_account),
        )
        .filter(SessionLaunch.launch_token_digest == token_digest)
        .with_for_update(of=SessionLaunch)
        .first()
    )
    if not launch:
        raise NotFoundException("Launch authorization not found", code="LAUNCH_NOT_FOUND")

    # Race condition / replay check (T-04)
    if launch.is_consumed:
        raise ConflictException("Launch authorization has already been consumed", code="LAUNCH_REPLAY_DENIED")

    now = utc_now()
    launch_expiry = ensure_utc(launch.expires_at)
    if now >= launch_expiry:
        raise ConflictException("Launch authorization has expired", code="LAUNCH_EXPIRED")

    grant = launch.grant
    if grant.status != "active":
        raise ConflictException(f"Associated grant is {grant.status}", code="GRANT_NOT_ACTIVE")

    grant_end = ensure_utc(grant.effective_end_at)
    if now >= grant_end:
        raise ConflictException("Grant validity window has expired", code="GRANT_EXPIRED")

    authorize_revision(db, grant.revision)
    now = utc_now()
    if now >= launch_expiry:
        raise ConflictException("Launch authorization has expired", code="LAUNCH_EXPIRED")

    # Mark consumed atomically
    launch.is_consumed = True
    launch.consumed_at = now
    launch.consumed_by_gateway_id = payload.gateway_id

    # Compute lease deadline bounded by grant expiry
    lease_seconds = min(
        settings.gateway_lease_duration_seconds,
        int((grant_end - now).total_seconds()),
    )
    lease_deadline = now + timedelta(seconds=max(0, lease_seconds))

    # Reserve starting session
    session = AccessSession(
        id=generate_id("ses"),
        grant_id=grant.id,
        launch_id=launch.id,
        gateway_id=payload.gateway_id,
        status="active",
        started_at=now,
    )
    db.add(session)
    db.flush()

    AuditService.record_event(
        db=db,
        event_type="SESSION_LAUNCH_CONSUMED",
        correlation_id=x_correlation_id,
        actor_id=grant.requester_id,
        payload={
            "session_id": session.id,
            "grant_id": grant.id,
            "launch_id": launch.id,
            "gateway_id": payload.gateway_id,
            "target_host": grant.asset.host,
            "target_user": grant.target_account.username,
        },
    )
    db.commit()

    return {
        "session_id": session.id,
        "grant_id": grant.id,
        "target_host": grant.asset.host,
        "target_port": grant.asset.port,
        "target_username": grant.target_account.username,
        "lease_deadline": lease_deadline.isoformat(),
        "grant_expiry": grant.effective_end_at.isoformat(),
    }


@router.post("/sessions/{session_id}/renew", response_model=Dict[str, Any])
def renew_session_lease(
    session_id: str,
    x_correlation_id: str = Header(default="corr_gateway_renew"),
    db: Session = Depends(get_db),
    _gw_auth: None = Depends(verify_gateway_identity),
):
    """
    Gateway renews session lease.
    Returns deadline strictly bounded by grant expiry. Fails if grant was revoked.
    """
    session = (
        db.query(AccessSession)
        .options(joinedload(AccessSession.grant))
        .filter(AccessSession.id == session_id)
        .first()
    )
    if not session:
        raise NotFoundException("Session not found", code="SESSION_NOT_FOUND")

    grant = session.grant
    now = utc_now()
    grant_end = ensure_utc(grant.effective_end_at)

    if grant.status != "active" or session.status != "active":
        raise ConflictException(f"Cannot renew: session is {session.status}, grant is {grant.status}", code="SESSION_TERMINATING")

    if now >= grant_end:
        session.status = "ended"
        session.ended_at = now
        session.termination_reason = "Grant window expired"
        db.commit()
        raise ConflictException("Grant validity window has expired", code="GRANT_EXPIRED")

    # Compute lease deadline bounded by grant expiry
    lease_seconds = min(
        settings.gateway_lease_duration_seconds,
        int((grant_end - now).total_seconds()),
    )
    lease_deadline = now + timedelta(seconds=max(0, lease_seconds))

    return {
        "session_id": session.id,
        "lease_deadline": lease_deadline.isoformat(),
        "grant_expiry": grant_end.isoformat(),
    }


@router.post("/sessions/{session_id}/events", response_model=Dict[str, Any], status_code=202)
def record_gateway_event(
    session_id: str,
    payload: Dict[str, Any],
    x_correlation_id: str = Header(default="corr_gateway_event"),
    db: Session = Depends(get_db),
    _gw_auth: None = Depends(verify_gateway_identity),
):
    """
    Gateway delivers session lifecycle evidence (e.g. terminated, recording_saved).
    Deduplicates and commits state changes.
    """
    session = db.get(AccessSession, session_id)
    if not session:
        raise NotFoundException("Session not found", code="SESSION_NOT_FOUND")

    event_state = payload.get("state")
    if session.status not in ("ended", "failed"):
        if event_state == "ended":
            session.status = "ended"
            session.ended_at = utc_now()
            session.termination_reason = payload.get("reason", "Gateway closed session")
        elif event_state == "failed":
            session.status = "failed"
            session.ended_at = utc_now()
            session.termination_reason = payload.get("reason", "Gateway session failure")

    AuditService.record_event(
        db=db,
        event_type="GATEWAY_SESSION_EVENT",
        correlation_id=x_correlation_id,
        actor_id=session.gateway_id,
        payload=payload,
    )
    db.commit()

    return {"session_id": session.id, "status": session.status}
