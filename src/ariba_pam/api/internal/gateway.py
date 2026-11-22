"""Internal gateway interfaces for launch consumption, lease renewal, and session events."""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, joinedload
from ariba_pam.config import settings
from ariba_pam.db.session import get_db
from ariba_pam.db.models import SessionLaunch, AccessGrant, AccessSession, Asset, TargetAccount, SessionRecording
from ariba_pam.services.audit import AuditService
from ariba_pam.core.errors import ForbiddenException, NotFoundException, ConflictException, UnauthorizedException, ValidationException
from ariba_pam.db.base import generate_id, utc_now, ensure_utc
from ariba_pam.api.schemas import LaunchConsumeInput, CertificateSignInput, CertificateSignOutput, GatewayHeartbeatInput
from ariba_pam.services.policies import authorize_revision
from ariba_pam.services.ca import ca_service
from ariba_pam.services.alerts import soc_alerts_service
from ariba_pam.services.vault import VaultCredentialService
from ariba_pam.services.rdp import RDPGatewayService

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
            joinedload(SessionLaunch.grant).joinedload(AccessGrant.revision),
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

    if grant.revision is not None and grant.revision.policy_version_id != "emergency_override":
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
        "target_account_id": grant.target_account.id,
        "credential_type": getattr(grant.target_account, "credential_type", "ssh_certificate"),
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
        soc_alerts_service.record_alert(
            db=db,
            alert_type="LEASE_RENEWAL_FAILURE",
            severity="HIGH",
            title="Session lease renewal failed",
            description=f"Lease renewal rejected: session is {session.status}, grant is {grant.status}",
            correlation_id=x_correlation_id,
            details={"session_id": session.id, "session_status": session.status, "grant_status": grant.status},
            session_id=session.id,
            gateway_id=session.gateway_id,
            asset_id=grant.asset_id,
        )
        raise ConflictException(f"Cannot renew: session is {session.status}, grant is {grant.status}", code="SESSION_TERMINATING")

    if now >= grant_end:
        session.status = "ended"
        session.ended_at = now
        session.termination_reason = "Grant window expired"
        db.commit()
        soc_alerts_service.record_alert(
            db=db,
            alert_type="LEASE_RENEWAL_FAILURE",
            severity="HIGH",
            title="Session lease renewal failed: grant expired",
            description=f"Lease renewal rejected: grant window expired for session {session.id}",
            correlation_id=x_correlation_id,
            details={"session_id": session.id, "grant_end": grant_end.isoformat()},
            session_id=session.id,
            gateway_id=session.gateway_id,
            asset_id=grant.asset_id,
        )
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
        if event_state in ("ended", "closed"):
            session.status = "ended"
            session.ended_at = utc_now()
            session.termination_reason = payload.get("reason", "Gateway closed session")

            # Post-session automated credential rotation (P4-03)
            if session.grant and session.grant.target_account:
                account = session.grant.target_account
                if getattr(account, "credential_type", "ssh_certificate") == "vault_secret" and getattr(account, "auto_rotate_on_session_end", True):
                    try:
                        VaultCredentialService.rotate_target_credential(
                            db=db,
                            account_id=account.id,
                            trigger_reason="session_ended",
                            actor_id=session.gateway_id,
                        )
                    except Exception as e:
                        soc_alerts_service.record_alert(
                            db=db,
                            alert_type="ROTATION_FAILURE",
                            severity="HIGH",
                            title="Target credential rotation failed",
                            description=f"Automated post-session rotation failed for account {account.id}: {str(e)}",
                            correlation_id=x_correlation_id,
                            details={"account_id": account.id, "error": str(e)},
                            session_id=session.id,
                            gateway_id=session.gateway_id,
                            asset_id=session.grant.asset_id if session.grant else None,
                        )
        elif event_state == "failed":
            session.status = "failed"
            session.ended_at = utc_now()
            session.termination_reason = payload.get("reason", "Gateway session failure")

    # Ingest and persist session recording metadata if delivered
    if payload.get("recording"):
        rec_data = payload["recording"]
        recording = db.query(SessionRecording).filter(SessionRecording.session_id == session.id).first()
        if not recording:
            recording = SessionRecording(
                id=rec_data.get("recording_id") or generate_id("rec"),
                session_id=session.id,
                digest_sha256=rec_data.get("digest_sha256", ""),
                storage_uri=rec_data.get("storage_uri", f"s3://ariba-pam-evidence-worm/recordings/{session.id}.cast"),
                size_bytes=rec_data.get("size_bytes", 0),
                duration_seconds=rec_data.get("duration_seconds", 0),
                coverage_status=rec_data.get("coverage_status", "complete"),
                created_at=utc_now(),
            )
            db.add(recording)
        else:
            if "digest_sha256" in rec_data:
                recording.digest_sha256 = rec_data["digest_sha256"]
            if "size_bytes" in rec_data:
                recording.size_bytes = rec_data["size_bytes"]
            if "duration_seconds" in rec_data:
                recording.duration_seconds = rec_data["duration_seconds"]
            if "coverage_status" in rec_data:
                recording.coverage_status = rec_data["coverage_status"]

        if rec_data.get("coverage_status") == "gap":
            soc_alerts_service.record_alert(
                db=db,
                alert_type="CAPTURE_FAILURE",
                severity="CRITICAL",
                title="Session recording coverage gap",
                description=f"Gateway {session.gateway_id} reported a recording coverage gap for session {session.id}",
                correlation_id=x_correlation_id,
                details={"session_id": session.id, "size_bytes": rec_data.get("size_bytes", 0), "reason": session.termination_reason},
                session_id=session.id,
                gateway_id=session.gateway_id,
                asset_id=session.grant.asset_id if session.grant else None,
            )

    if event_state == "failed" and "Unsafe launch" in str(payload.get("reason", "")):
        soc_alerts_service.record_alert(
            db=db,
            alert_type="UNSAFE_LAUNCH_BLOCKED",
            severity="CRITICAL",
            title="Unsafe session launch blocked",
            description=f"Gateway {session.gateway_id} blocked unsafe session launch: {payload.get('reason')}",
            correlation_id=x_correlation_id,
            details={"session_id": session.id, "reason": payload.get("reason")},
            session_id=session.id,
            gateway_id=session.gateway_id,
            asset_id=session.grant.asset_id if session.grant else None,
        )

    AuditService.record_event(
        db=db,
        event_type="GATEWAY_SESSION_EVENT",
        correlation_id=x_correlation_id,
        actor_id=session.gateway_id,
        payload=payload,
    )
    db.commit()

    return {"session_id": session.id, "status": session.status}


@router.post(
    "/sessions/{session_id}/sign-certificate",
    response_model=CertificateSignOutput,
    status_code=201,
)
def sign_session_certificate(
    session_id: str,
    payload: CertificateSignInput,
    x_correlation_id: str = Header(default="corr_gw_cert_sign"),
    db: Session = Depends(get_db),
    _gw_auth: None = Depends(verify_gateway_identity),
):
    """
    Gateway requests an ephemeral OpenSSH User Certificate for an active session.
    Signs certificate restricted strictly to the approved target account and remaining grant time.
    """
    session = (
        db.query(AccessSession)
        .options(
            joinedload(AccessSession.grant).joinedload(AccessGrant.target_account),
        )
        .filter(AccessSession.id == session_id)
        .first()
    )
    if not session:
        raise NotFoundException("Session not found", code="SESSION_NOT_FOUND")

    if session.status != "active":
        soc_alerts_service.record_alert(
            db=db,
            alert_type="SIGNING_FAILURE",
            severity="HIGH",
            title="SSH certificate signing failed: session not active",
            description=f"Signing rejected: session {session.id} is {session.status}",
            correlation_id=x_correlation_id,
            details={"session_id": session.id, "session_status": session.status},
            session_id=session.id,
            gateway_id=session.gateway_id,
        )
        raise ConflictException(f"Cannot sign certificate: session is {session.status}", code="SESSION_NOT_ACTIVE")

    grant = session.grant
    if grant.status != "active":
        soc_alerts_service.record_alert(
            db=db,
            alert_type="SIGNING_FAILURE",
            severity="HIGH",
            title="SSH certificate signing failed: grant not active",
            description=f"Signing rejected: grant {grant.id} is {grant.status}",
            correlation_id=x_correlation_id,
            details={"session_id": session.id, "grant_status": grant.status},
            session_id=session.id,
            gateway_id=session.gateway_id,
            asset_id=grant.asset_id,
        )
        raise ConflictException(f"Cannot sign certificate: grant is {grant.status}", code="GRANT_NOT_ACTIVE")

    now = utc_now()
    grant_end = ensure_utc(grant.effective_end_at)
    if now >= grant_end:
        soc_alerts_service.record_alert(
            db=db,
            alert_type="SIGNING_FAILURE",
            severity="HIGH",
            title="SSH certificate signing failed: grant expired",
            description=f"Signing rejected: grant {grant.id} expired at {grant_end.isoformat()}",
            correlation_id=x_correlation_id,
            details={"session_id": session.id, "grant_end": grant_end.isoformat()},
            session_id=session.id,
            gateway_id=session.gateway_id,
            asset_id=grant.asset_id,
        )
        raise ConflictException("Grant validity window has expired", code="GRANT_EXPIRED")

    target_username = grant.target_account.username

    cert_str, valid_before, serial_int, ca_fp = ca_service.sign_grant_certificate(
        client_public_key_openssh=payload.client_public_key,
        principal=target_username,
        grant_id=grant.id,
        grant_end_at=grant_end,
    )

    AuditService.record_event(
        db=db,
        event_type="SSH_CERTIFICATE_ISSUED",
        correlation_id=x_correlation_id,
        actor_id=session.gateway_id,
        payload={
            "session_id": session.id,
            "grant_id": grant.id,
            "principal": target_username,
            "serial": serial_int,
            "valid_before": valid_before.isoformat(),
            "ca_fingerprint": ca_fp,
        },
    )
    db.commit()

    return CertificateSignOutput(
        certificate=cert_str,
        expires_at=valid_before,
        principal=target_username,
        serial=serial_int,
        ca_fingerprint=ca_fp,
    )


@router.post("/gateways/{gateway_id}/heartbeat", response_model=Dict[str, Any])
def record_gateway_heartbeat(
    gateway_id: str,
    payload: GatewayHeartbeatInput,
    db: Session = Depends(get_db),
    _gw_auth: None = Depends(verify_gateway_identity),
):
    """
    Gateway transmits 15-second health heartbeat and capture pipeline status (FR-10, NFR-08).
    """
    hb = soc_alerts_service.record_heartbeat(
        gateway_id=gateway_id,
        zone_id=payload.zone_id,
        status=payload.status,
        active_sessions_count=payload.active_sessions_count,
        capture_status=payload.capture_status,
        db=db,
    )
    return {
        "gateway_id": gateway_id,
        "status": "acknowledged",
        "capture_status": hb["capture_status"],
        "healthy": hb["status"] == "healthy" and hb["capture_status"] == "healthy",
    }


@router.post("/credentials/vault-secret", response_model=Dict[str, Any])
def retrieve_vault_secret(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _gw_auth: None = Depends(verify_gateway_identity),
):
    """
    Internal Gateway endpoint to retrieve target credentials for vault-backed targets (P4-03).
    Strictly verifies active grant and session, non-disclosure to client.
    """
    grant_id = payload.get("grant_id")
    session_id = payload.get("session_id")
    account_id = payload.get("target_account_id")
    if not grant_id or not session_id or not account_id:
        raise ValidationException("grant_id, session_id, and target_account_id are required")

    res = VaultCredentialService.retrieve_secret_for_gateway(
        db=db,
        grant_id=grant_id,
        session_id=session_id,
        account_id=account_id,
    )
    db.commit()
    return res


@router.post("/rdp/tunnel-parameters", response_model=Dict[str, Any])
def compile_rdp_tunnel_parameters(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _gw_auth: None = Depends(verify_gateway_identity),
):
    """
    Gateway retrieves compiled RDP connection parameters (P6-01, ADR-012).
    Injects vault password, validates grant and session, and enforces clipboard/drive restrictions.
    """
    grant_id = payload.get("grant_id")
    session_id = payload.get("session_id")
    if not grant_id or not session_id:
        raise ValidationException("grant_id and session_id are required")

    res = RDPGatewayService.compile_rdp_connection_parameters(
        db=db,
        grant_id=grant_id,
        session_id=session_id,
    )
    db.commit()
    return res




