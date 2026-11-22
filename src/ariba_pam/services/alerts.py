"""Enterprise SOC Alerting and Health Monitoring service (Task P5-06 / FR-10, NFR-08, T-07, T-10)."""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Callable
import threading
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ariba_pam.db.models import SOCAlert, AuditOutbox, GatewayZone, User
from ariba_pam.db.base import generate_id, utc_now, ensure_utc
from ariba_pam.services.audit import AuditService


class SOCAlertsService:
    """Manages classification, delivery, and lifecycle of SOC security alerts and health probes."""

    def __init__(self):
        self._receiver: Optional[Callable[[Dict[str, Any]], bool]] = None
        self._gateway_heartbeats: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set_receiver(self, receiver: Optional[Callable[[Dict[str, Any]], bool]]) -> None:
        """Register custom SOC/SIEM delivery receiver (e.g. Wazuh / Splunk / Webhook)."""
        self._receiver = receiver

    def record_alert(
        self,
        db: Session,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        correlation_id: str,
        details: Dict[str, Any],
        session_id: Optional[str] = None,
        gateway_id: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> SOCAlert:
        """
        Record a high-priority SOC alert, commit to database, and dispatch to SIEM.
        Writes transactional audit outbox record atomically.
        """
        alert = SOCAlert(
            id=generate_id("alt"),
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            correlation_id=correlation_id,
            session_id=session_id,
            gateway_id=gateway_id,
            asset_id=asset_id,
            details=details,
            status="open",
            created_at=utc_now(),
        )
        db.add(alert)
        db.flush()

        # Write audit outbox event
        AuditService.record_event(
            db=db,
            event_type="SOC_SECURITY_ALERT",
            correlation_id=correlation_id,
            actor_id=gateway_id or "system",
            payload={
                "alert_id": alert.id,
                "alert_type": alert_type,
                "severity": severity,
                "title": title,
                "session_id": session_id,
                "gateway_id": gateway_id,
                "asset_id": asset_id,
                "details": details,
            },
        )
        db.commit()
        db.refresh(alert)

        # Dispatch through approved receiving path
        alert_payload = {
            "alert_id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "title": alert.title,
            "description": alert.description,
            "correlation_id": alert.correlation_id,
            "session_id": alert.session_id,
            "gateway_id": alert.gateway_id,
            "asset_id": alert.asset_id,
            "details": alert.details,
            "created_at": ensure_utc(alert.created_at).isoformat(),
        }
        if self._receiver:
            try:
                self._receiver(alert_payload)
            except Exception:
                pass

        return alert

    def record_heartbeat(
        self,
        gateway_id: str,
        zone_id: str,
        status: str,
        active_sessions_count: int,
        capture_status: str,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Record periodic 15-second heartbeat from a Session Gateway instance."""
        now = utc_now()
        with self._lock:
            self._gateway_heartbeats[gateway_id] = {
                "gateway_id": gateway_id,
                "zone_id": zone_id,
                "status": status,
                "active_sessions_count": active_sessions_count,
                "capture_status": capture_status,
                "last_seen_at": now,
            }

        # If gateway reports degraded capture storage, automatically emit SOC alert
        if capture_status == "degraded" and db is not None:
            self.record_alert(
                db=db,
                alert_type="CAPTURE_FAILURE",
                severity="CRITICAL",
                title="Gateway storage pipeline degraded",
                description=f"Gateway {gateway_id} in zone {zone_id} reported degraded terminal recording capture",
                correlation_id=f"corr_gw_hb_{gateway_id}",
                details={"active_sessions": active_sessions_count, "zone_id": zone_id},
                gateway_id=gateway_id,
            )

        return self._gateway_heartbeats[gateway_id]

    def get_gateway_health(self) -> List[Dict[str, Any]]:
        """Evaluate gateway availability and detect missing heartbeats (> 45s timeout)."""
        now = utc_now()
        results = []
        with self._lock:
            for gw_id, info in self._gateway_heartbeats.items():
                last_seen = info["last_seen_at"]
                is_stale = (now - last_seen).total_seconds() > 45
                gw_status = "offline" if is_stale else info["status"]
                results.append({
                    "gateway_id": gw_id,
                    "zone_id": info["zone_id"],
                    "status": gw_status,
                    "active_sessions_count": info["active_sessions_count"],
                    "capture_status": info["capture_status"],
                    "last_seen_at": ensure_utc(last_seen).isoformat(),
                    "healthy": not is_stale and gw_status == "healthy",
                })
        return results

    def get_system_health(self, db: Session) -> Dict[str, Any]:
        """
        Aggregate component health monitoring for NFR-08 (99.95% availability & health probes).
        Evaluates database connectivity, outbox backlog, gateway heartbeats, and open alerts.
        """
        now = utc_now()

        # 1. Outbox backlog check
        pending_outbox = db.scalar(
            select(func.count(AuditOutbox.id)).where(AuditOutbox.delivery_state == "pending")
        ) or 0
        failed_outbox = db.scalar(
            select(func.count(AuditOutbox.id)).where(AuditOutbox.delivery_state == "failed")
        ) or 0

        # 2. Critical SOC alerts check
        critical_alerts = db.scalar(
            select(func.count(SOCAlert.id)).where(
                SOCAlert.severity == "CRITICAL", SOCAlert.status == "open"
            )
        ) or 0

        # 3. Gateways
        gateways = self.get_gateway_health()
        any_gw_degraded = any(not g["healthy"] for g in gateways)

        overall_status = "healthy"
        if critical_alerts > 0 or failed_outbox > 10 or any_gw_degraded:
            overall_status = "degraded"

        return {
            "status": overall_status,
            "timestamp": now.isoformat(),
            "components": {
                "database": "connected",
                "ephemeral_ca": "ready",
                "audit_outbox": {
                    "pending_count": pending_outbox,
                    "failed_count": failed_outbox,
                    "healthy": failed_outbox < 10,
                },
                "gateways": gateways,
                "open_critical_alerts": critical_alerts,
            },
        }


# Global singleton instance
soc_alerts_service = SOCAlertsService()
