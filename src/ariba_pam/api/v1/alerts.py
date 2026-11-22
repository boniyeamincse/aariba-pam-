"""Enterprise SOC security alerts and health monitoring endpoints (Task P5-06 / FR-10, NFR-08, T-07, T-10)."""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, SOCAlert
from ariba_pam.services.auth import get_current_user
from ariba_pam.services.audit import AuditService
from ariba_pam.core.errors import ForbiddenException, NotFoundException
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.db.base import ensure_utc, utc_now
from ariba_pam.api.schemas import SOCAlertResponse
from ariba_pam.services.alerts import soc_alerts_service

router = APIRouter(prefix="/alerts", tags=["SOC Security Alerts & Health"])


def _verify_alert_viewer(user: User) -> None:
    roles = ScopeChecker.get_user_roles(user)
    authorized_roles = {"admin", "operator", "security_operator", "auditor"}
    if not (roles & authorized_roles):
        raise ForbiddenException("Access to SOC alerts is restricted to security personnel", code="NOT_PERMITTED")


@router.get("", response_model=List[SOCAlertResponse])
def list_alerts(
    status: Optional[str] = Query(None, description="Filter by status (open, acknowledged, resolved)"),
    severity: Optional[str] = Query(None, description="Filter by severity (CRITICAL, HIGH, WARNING)"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List enterprise SOC alerts with optional status, severity, and type filters."""
    _verify_alert_viewer(current_user)

    stmt = select(SOCAlert).order_by(desc(SOCAlert.created_at)).limit(limit)
    if status:
        stmt = stmt.where(SOCAlert.status == status)
    if severity:
        stmt = stmt.where(SOCAlert.severity == severity)
    if alert_type:
        stmt = stmt.where(SOCAlert.alert_type == alert_type)

    alerts = list(db.scalars(stmt).all())
    return [
        SOCAlertResponse(
            id=a.id,
            alert_type=a.alert_type,
            severity=a.severity,
            title=a.title,
            description=a.description,
            correlation_id=a.correlation_id,
            session_id=a.session_id,
            gateway_id=a.gateway_id,
            asset_id=a.asset_id,
            details=a.details or {},
            status=a.status,
            acknowledged_by_id=a.acknowledged_by_id,
            acknowledged_at=ensure_utc(a.acknowledged_at) if a.acknowledged_at else None,
            created_at=ensure_utc(a.created_at),
        )
        for a in alerts
    ]


@router.get("/health/components", response_model=Dict[str, Any])
def get_component_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate health monitoring probe across database, outbox, CA, and gateways."""
    _verify_alert_viewer(current_user)
    return soc_alerts_service.get_system_health(db)


@router.get("/{alert_id}", response_model=SOCAlertResponse)
def get_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve detailed SOC alert metadata."""
    _verify_alert_viewer(current_user)

    alert = db.get(SOCAlert, alert_id)
    if not alert:
        raise NotFoundException("Security alert not found", code="ALERT_NOT_FOUND")

    return SOCAlertResponse(
        id=alert.id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        title=alert.title,
        description=alert.description,
        correlation_id=alert.correlation_id,
        session_id=alert.session_id,
        gateway_id=alert.gateway_id,
        asset_id=alert.asset_id,
        details=alert.details or {},
        status=alert.status,
        acknowledged_by_id=alert.acknowledged_by_id,
        acknowledged_at=ensure_utc(alert.acknowledged_at) if alert.acknowledged_at else None,
        created_at=ensure_utc(alert.created_at),
    )


@router.post("/{alert_id}/acknowledge", response_model=SOCAlertResponse)
def acknowledge_alert(
    alert_id: str,
    x_correlation_id: str = Header(default="corr_ack_alert"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Acknowledge an open security alert by an authorized security operator or admin."""
    _verify_alert_viewer(current_user)

    alert = db.get(SOCAlert, alert_id)
    if not alert:
        raise NotFoundException("Security alert not found", code="ALERT_NOT_FOUND")

    now = utc_now()
    alert.status = "acknowledged"
    alert.acknowledged_by_id = current_user.id
    alert.acknowledged_at = now

    AuditService.record_event(
        db=db,
        event_type="SOC_ALERT_ACKNOWLEDGED",
        correlation_id=x_correlation_id,
        actor_id=current_user.id,
        payload={
            "alert_id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "acknowledged_by": current_user.id,
        },
    )
    db.commit()
    db.refresh(alert)

    return SOCAlertResponse(
        id=alert.id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        title=alert.title,
        description=alert.description,
        correlation_id=alert.correlation_id,
        session_id=alert.session_id,
        gateway_id=alert.gateway_id,
        asset_id=alert.asset_id,
        details=alert.details or {},
        status=alert.status,
        acknowledged_by_id=alert.acknowledged_by_id,
        acknowledged_at=ensure_utc(alert.acknowledged_at) if alert.acknowledged_at else None,
        created_at=ensure_utc(alert.created_at),
    )
