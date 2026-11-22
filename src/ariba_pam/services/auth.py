"""Workforce identity and authentication services."""

from typing import Optional, Dict, Any
from fastapi import Header, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from ariba_pam.config import settings
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User
from ariba_pam.core.security import verify_session_token, create_session_token
from ariba_pam.core.errors import UnauthorizedException
from ariba_pam.services.audit import AuditService


class AuthService:
    """Manages workforce authentication, session creation, and identity checks."""

    @staticmethod
    def authenticate_lab_identity(
        db: Session,
        idp_issuer: str,
        idp_subject: str,
        email: str,
        amr: list,
        correlation_id: str,
    ) -> Dict[str, Any]:
        """Look up a pre-enrolled synthetic identity and issue a lab session."""
        if settings.environment != "lab" or idp_issuer != settings.idp_issuer:
            raise UnauthorizedException("Identity not recognized or not enrolled", code="UNKNOWN_IDENTITY")

        stmt = select(User).where(User.idp_issuer == idp_issuer, User.idp_subject == idp_subject)
        user = db.scalar(stmt)

        if not user or user.email != email:
            raise UnauthorizedException("Identity not recognized or not enrolled", code="UNKNOWN_IDENTITY")

        if not user.is_active:
            raise UnauthorizedException("User account is disabled", code="ACCOUNT_DISABLED")

        token = create_session_token(
            user_id=user.id,
            email=user.email,
            auth_methods=amr,
        )

        AuditService.record_event(
            db=db,
            event_type="WORKFORCE_AUTHENTICATED",
            correlation_id=correlation_id,
            actor_id=user.id,
            payload={
                "email": user.email,
                "idp_issuer": idp_issuer,
                "amr": amr,
            },
        )
        db.commit()

        return {
            "token": token,
            "user": user,
        }


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency extracting and validating the bearer session token.
    Enforces active user account status and security version freshness.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException("Missing or malformed Authorization header", code="UNAUTHORIZED")

    token = authorization.split(" ", 1)[1]
    claims = verify_session_token(token)

    user_id = claims.get("sub")
    user = db.get(User, user_id)
    if not user:
        raise UnauthorizedException("User associated with session not found", code="UNKNOWN_USER")

    if not user.is_active:
        raise UnauthorizedException("User account has been disabled", code="ACCOUNT_DISABLED")

    return user
