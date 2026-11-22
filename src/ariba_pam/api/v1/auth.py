"""Authentication and identity routes."""

from typing import Dict, Any
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User
from ariba_pam.services.auth import AuthService, get_current_user
from ariba_pam.api.schemas import UserProfileResponse

router = APIRouter(tags=["Authentication & Identity"])


class SyntheticLoginInput(BaseModel):
    email: str
    idp_issuer: str = "https://idp.lab.ariba.internal"
    idp_subject: str
    full_name: str = "Synthetic Lab User"
    amr: list = ["pwd", "fido2"]


@router.post("/auth/login", response_model=Dict[str, Any])
def synthetic_login(
    payload: SyntheticLoginInput,
    x_correlation_id: str = Header(default="corr_synthetic_login"),
    db: Session = Depends(get_db),
):
    """Synthetic IdP login endpoint for the lab environment."""
    result = AuthService.authenticate_assertion(
        db=db,
        idp_issuer=payload.idp_issuer,
        idp_subject=payload.idp_subject,
        email=payload.email,
        full_name=payload.full_name,
        amr=payload.amr,
        correlation_id=x_correlation_id,
    )
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
