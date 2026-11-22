"""Session visibility and user/operator termination endpoints."""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, AccessSession, AccessGrant, Asset
from ariba_pam.services.auth import get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.core.errors import ForbiddenException, NotFoundException
from ariba_pam.db.base import utc_now

router = APIRouter(prefix="/sessions", tags=["Session Operations"])


@router.get("", response_model=List[Dict[str, Any]])
def list_sessions(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List visible sessions within caller's scope."""
    stmt = (
        select(AccessSession)
        .options(
            joinedload(AccessSession.grant).joinedload(AccessGrant.asset),
            joinedload(AccessSession.grant).joinedload(AccessGrant.target_account),
        )
        .order_by(AccessSession.started_at.desc())
    )
    if status:
        stmt = stmt.where(AccessSession.status == status)

    all_sessions = list(db.scalars(stmt).unique().all())
    user_roles = ScopeChecker.get_user_roles(current_user)
    is_operator = "operator" in user_roles or "admin" in user_roles

    results = []
    for s in all_sessions:
        grant = s.grant
        if grant.requester_id == current_user.id or (is_operator and ScopeChecker.is_asset_in_scope(current_user, grant.asset, "operator")):
            results.append({
                "session_id": s.id,
                "grant_id": s.grant_id,
                "asset_name": grant.asset.name,
                "target_account": grant.target_account.username,
                "gateway_id": s.gateway_id,
                "status": s.status,
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "termination_reason": s.termination_reason,
            })
    return results


@router.post("/{session_id}/terminate", response_model=Dict[str, Any], status_code=202)
def terminate_session(
    session_id: str,
    x_correlation_id: str = Header(default="corr_session_terminate"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Terminate own session or one in operator scope."""
    session = (
        db.query(AccessSession)
        .options(joinedload(AccessSession.grant).joinedload(AccessGrant.asset))
        .filter(AccessSession.id == session_id)
        .first()
    )
    if not session:
        raise NotFoundException("Session not found", code="SESSION_NOT_FOUND")

    user_roles = ScopeChecker.get_user_roles(current_user)
    is_owner = session.grant.requester_id == current_user.id
    is_operator = "operator" in user_roles or "admin" in user_roles

    if not is_owner and not is_operator:
        raise ForbiddenException("Not authorized to terminate this session", code="FORBIDDEN")

    session.status = "terminating"
    session.termination_reason = f"Termination requested by user {current_user.id}"

    AuditService.record_event(
        db=db,
        event_type="SESSION_TERMINATION_REQUESTED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={"session_id": session.id, "grant_id": session.grant_id},
    )
    db.commit()

    return {"session_id": session.id, "status": session.status}
