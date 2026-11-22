"""Authentication and identity routes."""

from typing import Dict, Any
from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from ariba_pam.config import settings
from ariba_pam.core.errors import NotFoundException, ConflictException
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, AccessGrant, AccessSession
from ariba_pam.services.auth import AuthService, get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.idempotency import IdempotencyService
from ariba_pam.db.base import utc_now
from ariba_pam.api.schemas import UserProfileResponse

router = APIRouter(tags=["Authentication & Identity"])


class IdPLifecycleEventInput(BaseModel):
    event_id: str
    event_type: str
    idp_issuer: str | None = None
    idp_subject: str | None = None
    email: str | None = None
    timestamp: str | None = None



class SyntheticLoginInput(BaseModel):
    email: str
    idp_issuer: str | None = None
    idp_subject: str
    amr: list[str] = Field(default_factory=lambda: ["pwd", "fido2"])


@router.post("/auth/login", response_model=Dict[str, Any])
def synthetic_login(
    payload: SyntheticLoginInput,
    response: Response,
    x_correlation_id: str = Header(default="corr_synthetic_login"),
    db: Session = Depends(get_db),
):
    """Synthetic IdP login endpoint for the lab environment."""
    if settings.environment != "lab":
        raise NotFoundException("Login endpoint not found")

    result = AuthService.authenticate_lab_identity(
        db=db,
        idp_issuer=settings.idp_issuer if payload.idp_issuer is None else payload.idp_issuer,
        idp_subject=payload.idp_subject,
        email=payload.email,
        amr=payload.amr,
        correlation_id=x_correlation_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "access_token": result["token"],
        "token_type": "bearer",
        "user_id": result["user"].id,
    }


@router.get("/me", response_model=UserProfileResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """GET /api/v1/me - Returns caller principal, active roles, and resource scopes."""
    roles = []
    scopes = []
    for ra in current_user.role_assignments:
        roles.append({
            "role": ra.role.name,
            "scope_type": ra.scope_type,
            "scope_value": ra.scope_value,
        })
        scopes.append({
            "scope_type": ra.scope_type,
            "scope_value": ra.scope_value,
        })

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        roles=roles,
        permitted_scopes=scopes,
    )


@router.post("/auth/idp-events", response_model=Dict[str, Any])
def idp_lifecycle_event(
    payload: IdPLifecycleEventInput,
    response: Response,
    x_correlation_id: str = Header(default="corr_idp_event"),
    db: Session = Depends(get_db),
):
    """
    Ingest IdP lifecycle events (e.g. user.disabled, user.deprovisioned).
    Deduplicates events, invalidates identity, immediately revokes active grants,
    and terminates associated sessions within the 60s NFR-01 propagation window.
    """
    cached = IdempotencyService.check_idempotency(
        db=db,
        actor_id="idp",
        operation="idp_lifecycle_event",
        idempotency_key=payload.event_id,
        payload=payload.model_dump(),
    )
    if cached:
        status_code, cached_payload = cached
        response.status_code = status_code
        return cached_payload

    # Look up user by issuer+subject or email
    user = None
    if payload.idp_subject:
        issuer = payload.idp_issuer or settings.idp_issuer
        user = db.query(User).filter(User.idp_issuer == issuer, User.idp_subject == payload.idp_subject).first()
    if not user and payload.email:
        user = db.query(User).filter(User.email == payload.email).first()

    if not user:
        raise NotFoundException("User not found for IdP event", code="UNKNOWN_IDENTITY")

    now = utc_now()
    revoked_count = 0
    terminating_count = 0

    if payload.event_type in ("user.disabled", "user.deprovisioned"):
        user.is_active = False

        # Revoke active and scheduled grants
        active_grants = (
            db.query(AccessGrant)
            .filter(AccessGrant.requester_id == user.id, AccessGrant.status.in_(["active", "scheduled"]))
            .all()
        )
        revoked_count = len(active_grants)
        for grant in active_grants:
            grant.status = "revoked"
            grant.revocation_reason = f"IdP identity disablement ({payload.event_type})"
            grant.revoked_at = now

            # Mark active sessions under these grants as terminating
            active_sessions = (
                db.query(AccessSession)
                .filter(AccessSession.grant_id == grant.id, AccessSession.status.in_(["starting", "active"]))
                .all()
            )
            for s in active_sessions:
                s.status = "terminating"
                s.termination_reason = f"IdP identity disablement ({payload.event_type})"
                terminating_count += 1

        AuditService.record_event(
            db=db,
            event_type="IDP_USER_DISABLED",
            correlation_id=x_correlation_id,
            actor_id=user.id,
            payload={
                "event_id": payload.event_id,
                "event_type": payload.event_type,
                "user_id": user.id,
                "email": user.email,
                "revoked_grants_count": revoked_count,
                "terminating_sessions_count": terminating_count,
                "source_timestamp": payload.timestamp,
            },
        )

    result = {
        "status": "processed",
        "event_id": payload.event_id,
        "event_type": payload.event_type,
        "user_id": user.id,
        "is_active": user.is_active,
        "revoked_grants_count": revoked_count,
        "terminating_sessions_count": terminating_count,
    }

    IdempotencyService.save_idempotency(
        db=db,
        actor_id="idp",
        operation="idp_lifecycle_event",
        idempotency_key=payload.event_id,
        payload=payload.model_dump(),
        response_code=200,
        response_payload=result,
    )
    db.commit()

    return result

