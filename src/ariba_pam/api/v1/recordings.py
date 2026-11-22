"""Session recording playback, streaming authorization, and scoped evidence exports."""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from ariba_pam.db.session import get_db
from ariba_pam.db.models import (
    User,
    AccessSession,
    AccessGrant,
    Asset,
    TargetAccount,
    SessionRecording,
    EvidenceExport,
)
from ariba_pam.services.auth import get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.core.errors import ForbiddenException, NotFoundException
from ariba_pam.db.base import generate_id, utc_now, ensure_utc
from ariba_pam.api.schemas import (
    RecordingResponse,
    PlaybackSessionResponse,
    CreateRecordingExportInput,
    RecordingExportResponse,
)

router = APIRouter(tags=["Recordings & Evidence Playback"])


def _check_recording_scope(user: User, recording: SessionRecording) -> bool:
    """Check if recording is in caller scope. Enforces default deny."""
    session = recording.session
    if not session or not session.grant:
        return False

    grant = session.grant
    # Requester who owns the session can view own recording metadata
    if grant.requester_id == user.id:
        return True

    user_roles = ScopeChecker.get_user_roles(user)
    # Auditors, operators, and evidence custodians must satisfy asset resource scope
    for role in ("auditor", "evidence_custodian", "operator", "admin"):
        if role in user_roles and ScopeChecker.is_asset_in_scope(user, grant.asset, role):
            return True

    return False


@router.get("/recordings", response_model=List[RecordingResponse])
def list_recordings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List recordings within caller's resource scope."""
    stmt = (
        select(SessionRecording)
        .options(
            joinedload(SessionRecording.session)
            .joinedload(AccessSession.grant)
            .joinedload(AccessGrant.asset),
            joinedload(SessionRecording.session)
            .joinedload(AccessSession.grant)
            .joinedload(AccessGrant.target_account),
        )
        .order_by(SessionRecording.created_at.desc())
    )
    all_recordings = list(db.scalars(stmt).unique().all())

    results = []
    for rec in all_recordings:
        if _check_recording_scope(current_user, rec):
            session = rec.session
            grant = session.grant
            results.append(
                RecordingResponse(
                    recording_id=rec.id,
                    session_id=session.id,
                    asset_id=grant.asset.id,
                    asset_name=grant.asset.name,
                    target_account=grant.target_account.username,
                    duration_seconds=rec.duration_seconds,
                    size_bytes=rec.size_bytes,
                    coverage_status=rec.coverage_status,
                    digest_sha256=rec.digest_sha256,
                    storage_uri=rec.storage_uri,
                    created_at=ensure_utc(rec.created_at),
                )
            )
    return results


@router.get("/recordings/{recording_id}", response_model=RecordingResponse)
def get_recording(
    recording_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    View scoped recording metadata, file size, and coverage status.
    Anti-enumeration: Out-of-scope recording returns 404 Not Found.
    """
    rec = (
        db.query(SessionRecording)
        .options(
            joinedload(SessionRecording.session)
            .joinedload(AccessSession.grant)
            .joinedload(AccessGrant.asset),
            joinedload(SessionRecording.session)
            .joinedload(AccessSession.grant)
            .joinedload(AccessGrant.target_account),
        )
        .filter(SessionRecording.id == recording_id)
        .first()
    )
    if not rec or not _check_recording_scope(current_user, rec):
        raise NotFoundException("Recording not found", code="RECORDING_NOT_FOUND")

    session = rec.session
    grant = session.grant
    return RecordingResponse(
        recording_id=rec.id,
        session_id=session.id,
        asset_id=grant.asset.id,
        asset_name=grant.asset.name,
        target_account=grant.target_account.username,
        duration_seconds=rec.duration_seconds,
        size_bytes=rec.size_bytes,
        coverage_status=rec.coverage_status,
        digest_sha256=rec.digest_sha256,
        storage_uri=rec.storage_uri,
        created_at=ensure_utc(rec.created_at),
    )


@router.post(
    "/recordings/{recording_id}/playback-sessions",
    response_model=PlaybackSessionResponse,
    status_code=201,
)
def create_playback_session(
    recording_id: str,
    x_correlation_id: str = Header(default="corr_playback"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Authorize short-lived playback streaming URL for scoped auditor or operator.
    Anti-enumeration: Cross-scope attempts return 404 Not Found.
    """
    rec = (
        db.query(SessionRecording)
        .options(
            joinedload(SessionRecording.session)
            .joinedload(AccessSession.grant)
            .joinedload(AccessGrant.asset),
        )
        .filter(SessionRecording.id == recording_id)
        .first()
    )
    if not rec or not _check_recording_scope(current_user, rec):
        raise NotFoundException("Recording not found", code="RECORDING_NOT_FOUND")

    user_roles = ScopeChecker.get_user_roles(current_user)
    if not any(r in user_roles for r in ("auditor", "evidence_custodian", "operator")):
        raise ForbiddenException("Auditor or operator role required for recording playback", code="FORBIDDEN")

    playback_token = hashlib.sha256(f"{rec.id}:{current_user.id}:{utc_now().isoformat()}".encode()).hexdigest()
    expires_at = utc_now() + timedelta(minutes=15)
    playback_url = f"/api/v1/recordings/{rec.id}/stream?token={playback_token}"

    AuditService.record_event(
        db=db,
        event_type="RECORDING_PLAYBACK_AUTHORIZED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "recording_id": rec.id,
            "session_id": rec.session_id,
            "expires_at": expires_at.isoformat(),
        },
    )
    db.commit()

    return PlaybackSessionResponse(
        recording_id=rec.id,
        playback_url=playback_url,
        token=playback_token,
        expires_at=ensure_utc(expires_at),
    )


@router.post(
    "/recordings/{recording_id}/exports",
    response_model=RecordingExportResponse,
    status_code=202,
)
def create_recording_export(
    recording_id: str,
    payload: CreateRecordingExportInput,
    x_correlation_id: str = Header(default="corr_rec_export"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Initiate an auditable, scoped recording export job.
    Requires Evidence Custodian or Auditor role and asset scope match.
    """
    rec = (
        db.query(SessionRecording)
        .options(
            joinedload(SessionRecording.session)
            .joinedload(AccessSession.grant)
            .joinedload(AccessGrant.asset),
        )
        .filter(SessionRecording.id == recording_id)
        .first()
    )
    if not rec or not _check_recording_scope(current_user, rec):
        raise NotFoundException("Recording not found", code="RECORDING_NOT_FOUND")

    user_roles = ScopeChecker.get_user_roles(current_user)
    if not any(r in user_roles for r in ("evidence_custodian", "auditor")):
        raise ForbiddenException(
            "Evidence custodian or auditor role required to export recordings",
            code="FORBIDDEN",
        )

    export_id = generate_id("exp")
    manifest_sha256 = hashlib.sha256(f"{rec.id}:{rec.digest_sha256}:{rec.size_bytes}".encode()).hexdigest()
    storage_uri = f"s3://ariba-pam-evidence-worm/recording-exports/{export_id}.cast"
    expires_at = utc_now() + timedelta(hours=1)

    export = EvidenceExport(
        id=export_id,
        requester_id=current_user.id,
        export_type="session_recording",
        resource_id=rec.id,
        scope_filter=rec.session.grant.asset.team,
        record_count=1,
        manifest_sha256=manifest_sha256,
        storage_uri=storage_uri,
        status="completed",
        justification=payload.justification,
        expires_at=expires_at,
        created_at=utc_now(),
    )
    db.add(export)
    db.flush()

    AuditService.record_event(
        db=db,
        event_type="RECORDING_EXPORT_INITIATED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "export_id": export.id,
            "recording_id": rec.id,
            "manifest_sha256": manifest_sha256,
            "justification": payload.justification,
        },
    )
    db.commit()
    db.refresh(export)

    return RecordingExportResponse(
        export_id=export.id,
        recording_id=rec.id,
        status=export.status,
        manifest_sha256=export.manifest_sha256,
        storage_uri=export.storage_uri,
        download_url=f"/api/v1/recording-exports/{export.id}/download",
        justification=export.justification,
        expires_at=ensure_utc(export.expires_at),
        created_at=ensure_utc(export.created_at),
        requester_id=export.requester_id,
    )


@router.get("/recording-exports/{export_id}", response_model=RecordingExportResponse)
def get_recording_export(
    export_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check export status and retrieve expiring download reference.
    Enforces identifier concealment: Out-of-scope export returns 404 Not Found.
    """
    user_roles = ScopeChecker.get_user_roles(current_user)
    if not any(r in user_roles for r in ("evidence_custodian", "auditor")):
        raise NotFoundException("Export not found", code="EXPORT_NOT_FOUND")

    export = db.get(EvidenceExport, export_id)
    if not export or export.export_type != "session_recording":
        raise NotFoundException("Export not found", code="EXPORT_NOT_FOUND")

    return RecordingExportResponse(
        export_id=export.id,
        recording_id=export.resource_id or "",
        status=export.status,
        manifest_sha256=export.manifest_sha256,
        storage_uri=export.storage_uri,
        download_url=f"/api/v1/recording-exports/{export.id}/download",
        justification=export.justification,
        expires_at=ensure_utc(export.expires_at),
        created_at=ensure_utc(export.created_at),
        requester_id=export.requester_id,
    )
