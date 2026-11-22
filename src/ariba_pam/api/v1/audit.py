"""Audit evidence query routes."""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, AuditOutbox
from ariba_pam.services.auth import get_current_user
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.core.errors import ForbiddenException

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
    if not any(r in user_roles for r in ("auditor", "operator", "admin")):
        raise ForbiddenException("Auditor or operator role required to query audit evidence", code="FORBIDDEN")

    stmt = (
        select(AuditOutbox)
        .order_by(AuditOutbox.occurred_at.desc())
        .limit(min(limit, 200))
    )
    events = db.scalars(stmt).all()

    return [
        {
            "id": ev.id,
            "event_type": ev.event_type,
            "correlation_id": ev.correlation_id,
            "actor_id": ev.actor_id,
            "payload": ev.payload,
            "occurred_at": ev.occurred_at.isoformat(),
            "delivery_state": ev.delivery_state,
        }
        for ev in events
    ]
