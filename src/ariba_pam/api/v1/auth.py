"""Authentication and identity routes."""

from typing import Dict, Any, Optional, List
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
from ariba_pam.services.idp import MultiIdPService

router = APIRouter(tags=["Authentication & Identity"])


class IdPLifecycleEventInput(BaseModel):
    model_config = {"extra": "allow"}

    event_id: Optional[str] = None
    event_type: Optional[str] = None
    idp_issuer: Optional[str] = None
    idp_subject: Optional[str] = None
    email: Optional[str] = None
    timestamp: Optional[str] = None
    # Microsoft Graph change notification fields
    id: Optional[str] = None
    subscriptionId: Optional[str] = None
    resourceData: Optional[Dict[str, Any]] = None
    # SCIM 2.0 fields
    schemas: Optional[List[str]] = None
    Operations: Optional[List[Dict[str, Any]]] = None
    externalId: Optional[str] = None
    userName: Optional[str] = None



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
    raw_dict = payload.model_dump()
    norm_event = MultiIdPService.normalize_lifecycle_event(raw_dict)

    cached = IdempotencyService.check_idempotency(
        db=db,
        actor_id="idp",
        operation="idp_lifecycle_event",
        idempotency_key=norm_event.event_id,
        payload=raw_dict,
    )
    if cached:
        status_code, cached_payload = cached
        response.status_code = status_code
        return cached_payload

    result = MultiIdPService.execute_disablement(
        db=db,
        event=norm_event,
        correlation_id=x_correlation_id,
    )

    IdempotencyService.save_idempotency(
        db=db,
        actor_id="idp",
        operation="idp_lifecycle_event",
        idempotency_key=norm_event.event_id,
        payload=raw_dict,
        response_code=200,
        response_payload=result,
    )
    db.commit()

    return result

