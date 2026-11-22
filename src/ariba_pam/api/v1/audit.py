"""Audit evidence query, WORM integrity verification, and export routes."""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from sqlalchemy import select
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, AuditOutbox, EvidenceExport
from ariba_pam.services.auth import get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.core.errors import ForbiddenException, NotFoundException
from ariba_pam.db.base import ensure_utc
from ariba_pam.api.schemas import (
    CreateAuditExportInput,
    AuditExportResponse,
    VerifyIntegrityInput,
    VerifyIntegrityResponse,
)

router = APIRouter(prefix="/audit-events", tags=["Audit & Evidence"])


@router.get("", response_model=List[Dict[str, Any]])
def query_audit_events(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Query audit evidence within caller's scope.
    Restricted to auditors, operators, and administrators.
    """
    user_roles = ScopeChecker.get_user_roles(current_user)
    if not any(r in user_roles for r in ("auditor", "evidence_custodian", "operator", "admin")):
        raise ForbiddenException("Auditor or operator role required to query audit evidence", code="FORBIDDEN")

    stmt = (
        select(AuditOutbox)
        .order_by(AuditOutbox.occurred_at.desc())
        .limit(min(limit, 200))
    )
    events = list(db.scalars(stmt).all())

    return [
        {
            "id": ev.id,
            "event_type": ev.event_type,
            "correlation_id": ev.correlation_id,
            "actor_id": ev.actor_id,
            "payload": ev.payload,
            "payload_digest": ev.payload_digest,
            "occurred_at": ensure_utc(ev.occurred_at).isoformat(),
            "delivery_state": ev.delivery_state,
        }
        for ev in events
    ]


@router.post("/verify-integrity", response_model=VerifyIntegrityResponse)
def verify_audit_integrity(
    payload: VerifyIntegrityInput,
    x_correlation_id: str = Header(default="corr_audit_verify"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Verify tamper-free WORM status of audit outbox records.
    Custody boundary: Restricted strictly to Evidence Custodian or Auditor roles.
    Routine PAM Administrators cannot verify or attest evidence custody.
    """
    user_roles = ScopeChecker.get_user_roles(current_user)
    if not any(r in user_roles for r in ("evidence_custodian", "auditor")):
        raise ForbiddenException(
            "Evidence custodian or auditor role required for WORM integrity verification",
            code="FORBIDDEN",
        )

    result = AuditService.verify_integrity(db=db, batch_limit=payload.batch_limit)

    # Log integrity audit check into outbox
    AuditService.record_event(
        db=db,
        event_type="AUDIT_INTEGRITY_VERIFIED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "verified": result["verified"],
            "events_checked": result["events_checked"],
            "tampered_count": len(result["tampered_event_ids"]),
            "hash_algorithm": result["hash_algorithm"],
        },
    )
    db.commit()

    return VerifyIntegrityResponse(
        verified=result["verified"],
        events_checked=result["events_checked"],
        tampered_event_ids=result["tampered_event_ids"],
        hash_algorithm=result["hash_algorithm"],
        verified_at=ensure_utc(result["verified_at"]),
        message=result["message"],
    )


@router.post("/exports", response_model=AuditExportResponse, status_code=202)
def create_audit_export(
    payload: CreateAuditExportInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a sealed audit trail export bundle with SHA-256 manifest.
    Restricted strictly to Evidence Custodian or Auditor roles.
    """
    user_roles = ScopeChecker.get_user_roles(current_user)
    if not any(r in user_roles for r in ("evidence_custodian", "auditor")):
        raise ForbiddenException(
            "Evidence custodian or auditor role required to export audit evidence",
            code="FORBIDDEN",
        )

    export = AuditService.create_audit_export(
        db=db,
        requester_id=current_user.id,
        justification=payload.justification,
        scope_filter=payload.scope_filter,
        limit=payload.limit,
    )

    return AuditExportResponse(
        export_id=export.id,
        export_type=export.export_type,
        status=export.status,
        record_count=export.record_count,
        manifest_sha256=export.manifest_sha256,
        storage_uri=export.storage_uri,
        download_url=f"/api/v1/audit-events/exports/{export.id}/download",
        justification=export.justification,
        expires_at=ensure_utc(export.expires_at),
        created_at=ensure_utc(export.created_at),
        requester_id=export.requester_id,
    )


@router.get("/exports/{export_id}", response_model=AuditExportResponse)
def get_audit_export(
    export_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve export status and download reference.
    Enforces identifier concealment (HTTP 404 for out-of-scope/unauthorized requests).
    """
    user_roles = ScopeChecker.get_user_roles(current_user)
    if not any(r in user_roles for r in ("evidence_custodian", "auditor")):
        # Identifier concealment
        raise NotFoundException("Export not found", code="EXPORT_NOT_FOUND")

    export = db.get(EvidenceExport, export_id)
    if not export or export.export_type != "audit_trail":
        raise NotFoundException("Export not found", code="EXPORT_NOT_FOUND")

    return AuditExportResponse(
        export_id=export.id,
        export_type=export.export_type,
        status=export.status,
        record_count=export.record_count,
        manifest_sha256=export.manifest_sha256,
        storage_uri=export.storage_uri,
        download_url=f"/api/v1/audit-events/exports/{export.id}/download",
        justification=export.justification,
        expires_at=ensure_utc(export.expires_at),
        created_at=ensure_utc(export.created_at),
        requester_id=export.requester_id,
    )

