"""Ariba SOC Event Adapter (P7-02, ADR-014).

Provides:
1. Priority Routing: Multi-tier routing to designated channels (Critical, Triage, Stream).
2. Correlation Tracking & Propagation: Enforces trace_id and correlation_id across all incident payloads.
3. Runbook Enrichment: Maps alert classifications to documented SOC operational runbooks.
4. Delivery Failure Monitoring & Circuit Breaker: Tracks consecutive delivery failures, triggers degraded health state, and logs local delivery failure alerts.
5. Observable Metrics: In-depth metrics for routed channels, delivery rates, and circuit breaker status.
"""

import json
import time
import uuid
import threading
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ariba_pam.config import settings
from ariba_pam.db.base import generate_id, utc_now, ensure_utc
from ariba_pam.services.audit import AuditService


# Priority Routing Channels
CHANNEL_CRITICAL = "critical_channel"
CHANNEL_TRIAGE = "triage_channel"
CHANNEL_STREAM = "audit_stream_channel"

# Runbook Mapping Catalog
RUNBOOK_CATALOG: Dict[str, str] = {
    "CAPTURE_FAILURE": "RB-SEC-01: Terminal Recording Capture Pipeline Degradation / Buffer Overflow",
    "EMERGENCY_ACCESS_ACTIVATED": "RB-SEC-02: Out-of-Band Emergency Break-Glass Quorum Authorization Review",
    "UNPINNED_HOST_KEY": "RB-SEC-03: Gateway Target Host Key Mismatch / Potential Man-in-the-Middle Attack",
    "UNSAFE_LAUNCH_BLOCKED": "RB-SEC-04: Host Key Verification Blocked Launch Investigation",
    "ACCESS_GRANT_REVOKED": "RB-SEC-05: Immediate Revocation Execution and Active Session Termination Verification",
    "LEASE_RENEWAL_FAILURE": "RB-SEC-06: Session Lease Invalidation or Premature Termination Investigation",
    "ROTATION_FAILURE": "RB-SEC-07: Vault Credential Auto-Rotation Failure Remediation",
    "IDP_USER_DISABLED": "RB-SEC-08: Workforce Disablement Propagation and Session Teardown Validation",
    "SOC_DELIVERY_FAILURE": "RB-SEC-09: SOC / SIEM Egress Delivery Failure and Evidence Queue Degradation",
    "EVIDENCE_DELIVERY_FAILURE": "RB-SEC-09: SOC / SIEM Egress Delivery Failure and Evidence Queue Degradation",
}
DEFAULT_RUNBOOK = "RB-SEC-99: General Privileged Access Incident Triage"


class SOCIncidentPayload(BaseModel):
    """Structured SOC incident contract with correlation tracking and runbook context."""
    incident_id: str
    correlation_id: str
    trace_id: str
    timestamp: str
    severity: str
    channel: str
    alert_type: str
    title: str
    description: str
    suggested_runbook: str
    source_component: str = "ariba-pam-control-plane"
    actor_id: Optional[str] = None
    asset_id: Optional[str] = None
    session_id: Optional[str] = None
    gateway_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class SOCDeliveryResult(BaseModel):
    """Result of SOC incident delivery."""
    incident_id: str
    correlation_id: str
    channel: str
    destination_url: str
    status: str  # "delivered", "failed", "simulated", "circuit_broken"
    attempts: int
    duration_ms: float
    error: Optional[str] = None


class AribaSOCAdapter:
    """Enterprise SOC Event Adapter with priority routing and delivery failure monitoring."""

    def __init__(
        self,
        enabled: Optional[bool] = None,
        webhook_url: Optional[str] = None,
        critical_webhook_url: Optional[str] = None,
        api_key: Optional[str] = None,
        max_retries: Optional[int] = None,
        backoff_base_seconds: Optional[float] = None,
        failure_threshold: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        verify_ssl: Optional[bool] = None,
    ):
        self.enabled = enabled if enabled is not None else settings.soc_adapter_enabled
        self.webhook_url = webhook_url or settings.soc_webhook_url
        self.critical_webhook_url = critical_webhook_url or settings.soc_critical_webhook_url
        self.api_key = api_key or settings.soc_api_key
        self.max_retries = max_retries if max_retries is not None else settings.soc_max_retries
        self.backoff_base_seconds = (
            backoff_base_seconds if backoff_base_seconds is not None else settings.soc_backoff_base_seconds
        )
        self.failure_threshold = (
            failure_threshold if failure_threshold is not None else settings.soc_failure_threshold_for_alert
        )
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.soc_timeout_seconds
        self.verify_ssl = verify_ssl if verify_ssl is not None else settings.soc_verify_ssl

        # Concurrency & Circuit Breaker State
        self._lock = threading.Lock()
        self.consecutive_failures = 0
        self.circuit_state = "HEALTHY"  # "HEALTHY" or "DEGRADED"
        self._in_escalation = False

        # Observable Metrics
        self.total_routed = 0
        self.routed_critical = 0
        self.routed_triage = 0
        self.routed_stream = 0
        self.total_delivered = 0
        self.total_delivery_failures = 0
        self.last_delivery_at: Optional[datetime] = None
        self.last_failure_at: Optional[datetime] = None
        self.last_failure_error: Optional[str] = None

        # Custom mock sender for testing / synthetic simulation
        self._mock_sender: Optional[Callable[[str, Dict[str, Any], Dict[str, str]], bool]] = None

    def set_mock_sender(
        self, sender: Optional[Callable[[str, Dict[str, Any], Dict[str, str]], bool]]
    ) -> None:
        """Inject synthetic sender for unit and isolation testing."""
        self._mock_sender = sender

    def classify_channel(self, severity: str, alert_type: str) -> str:
        """
        Multi-tier priority classification:
        - Critical: CAPTURE_FAILURE, EMERGENCY_ACCESS_ACTIVATED, UNPINNED_HOST_KEY, UNSAFE_LAUNCH_BLOCKED, or severity CRITICAL
        - Triage: ACCESS_GRANT_REVOKED, LEASE_RENEWAL_FAILURE, ROTATION_FAILURE, IDP_USER_DISABLED, or severity HIGH/MEDIUM
        - Stream: Routine and LOW severity events
        """
        sev_upper = (severity or "MEDIUM").upper()
        alert_upper = (alert_type or "").upper()

        critical_events = {
            "CAPTURE_FAILURE",
            "EMERGENCY_ACCESS_ACTIVATED",
            "UNPINNED_HOST_KEY",
            "UNSAFE_LAUNCH_BLOCKED",
            "SOC_DELIVERY_FAILURE",
        }
        if sev_upper == "CRITICAL" or alert_upper in critical_events:
            return CHANNEL_CRITICAL

        triage_events = {
            "ACCESS_GRANT_REVOKED",
            "LEASE_RENEWAL_FAILURE",
            "ROTATION_FAILURE",
            "IDP_USER_DISABLED",
            "EVIDENCE_DELIVERY_FAILURE",
            "POLICY_VIOLATION",
            "UNAUTHORIZED_ACCESS_ATTEMPT",
        }
        if sev_upper in {"HIGH", "MEDIUM"} or alert_upper in triage_events:
            return CHANNEL_TRIAGE

        return CHANNEL_STREAM

    def get_destination_url(self, channel: str) -> str:
        """Resolve channel target endpoint."""
        if channel == CHANNEL_CRITICAL:
            return self.critical_webhook_url or self.webhook_url
        return self.webhook_url

    def build_incident_payload(self, raw_event: Dict[str, Any]) -> SOCIncidentPayload:
        """Transform raw alert or outbox payload into structured SOC incident contract."""
        alert_type = raw_event.get("alert_type") or raw_event.get("event_type") or "SECURITY_ALERT"
        severity = (raw_event.get("severity") or "MEDIUM").upper()
        channel = self.classify_channel(severity, alert_type)

        # Enforce Correlation Tracking
        raw_corr = raw_event.get("correlation_id")
        if raw_corr and str(raw_corr).strip():
            correlation_id = str(raw_corr).strip()
        else:
            correlation_id = f"corr_soc_{uuid.uuid4().hex[:12]}"

        # Tracing identifiers
        trace_id = raw_event.get("trace_id") or f"trc_{uuid.uuid4().hex[:12]}"
        incident_id = raw_event.get("incident_id") or raw_event.get("alert_id") or f"inc_{generate_id('soc')}"

        title = raw_event.get("title") or f"Ariba PAM Security Alert: {alert_type}"
        description = raw_event.get("description") or f"Security event {alert_type} triggered with severity {severity}"
        suggested_runbook = RUNBOOK_CATALOG.get(alert_type.upper(), DEFAULT_RUNBOOK)

        details = dict(raw_event.get("details") or raw_event.get("payload") or {})

        return SOCIncidentPayload(
            incident_id=incident_id,
            correlation_id=correlation_id,
            trace_id=trace_id,
            timestamp=raw_event.get("created_at") or raw_event.get("occurred_at") or utc_now().isoformat(),
            severity=severity,
            channel=channel,
            alert_type=alert_type,
            title=title,
            description=description,
            suggested_runbook=suggested_runbook,
            source_component="ariba-pam-control-plane",
            actor_id=raw_event.get("actor_id"),
            asset_id=raw_event.get("asset_id"),
            session_id=raw_event.get("session_id"),
            gateway_id=raw_event.get("gateway_id"),
            details=details,
        )

    def route_and_deliver(
        self,
        raw_event: Dict[str, Any],
        db: Optional[Session] = None,
    ) -> SOCDeliveryResult:
        """
        Enforce priority routing, build incident payload with correlation identifiers,
        and deliver with observable retry and failure monitoring.
        """
        start_time = time.monotonic()
        incident = self.build_incident_payload(raw_event)
        destination_url = self.get_destination_url(incident.channel)

        with self._lock:
            self.total_routed += 1
            if incident.channel == CHANNEL_CRITICAL:
                self.routed_critical += 1
            elif incident.channel == CHANNEL_TRIAGE:
                self.routed_triage += 1
            else:
                self.routed_stream += 1

        payload_dict = incident.model_dump()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Correlation-ID": incident.correlation_id,
            "X-Trace-ID": incident.trace_id,
            "X-Incident-ID": incident.incident_id,
            "X-Channel": incident.channel,
        }

        attempts = 0
        last_error: Optional[str] = None
        delivered = False

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            try:
                if self._mock_sender is not None:
                    # Injected test / simulation sender
                    success = self._mock_sender(destination_url, payload_dict, headers)
                    if success:
                        delivered = True
                        break
                    else:
                        raise RuntimeError(f"Mock SOC receiver rejected delivery to {destination_url}")
                else:
                    # Production HTTP POST
                    if not self.enabled:
                        # Simulated lab run when adapter is disabled
                        delivered = True
                        break

                    req_data = json.dumps(payload_dict).encode("utf-8")
                    req = urllib.request.Request(
                        destination_url,
                        data=req_data,
                        headers=headers,
                        method="POST",
                    )
                    ctx = ssl.create_default_context()
                    if not self.verify_ssl:
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE

                    with urllib.request.urlopen(req, timeout=self.timeout_seconds, context=ctx) as resp:
                        if 200 <= resp.status < 300:
                            delivered = True
                            break
                        else:
                            raise RuntimeError(f"SOC endpoint responded with HTTP {resp.status}")

            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    delay = min(2.0, self.backoff_base_seconds * (2 ** (attempt - 1)))
                    time.sleep(delay)

        duration_ms = (time.monotonic() - start_time) * 1000

        with self._lock:
            if delivered:
                self.total_delivered += 1
                self.last_delivery_at = utc_now()
                self.consecutive_failures = 0
                self.circuit_state = "HEALTHY"
            else:
                self.total_delivery_failures += 1
                self.consecutive_failures += 1
                self.last_failure_at = utc_now()
                self.last_failure_error = last_error

                # Evaluate Failure Monitoring Threshold
                if self.consecutive_failures >= self.failure_threshold:
                    self.circuit_state = "DEGRADED"
                    if db is not None and not self._in_escalation:
                        self._escalate_delivery_failure(db, incident, last_error)

        status_str = "delivered" if delivered else "failed"
        if not self.enabled and self._mock_sender is None:
            status_str = "simulated"

        return SOCDeliveryResult(
            incident_id=incident.incident_id,
            correlation_id=incident.correlation_id,
            channel=incident.channel,
            destination_url=destination_url,
            status=status_str,
            attempts=attempts,
            duration_ms=round(duration_ms, 2),
            error=last_error if not delivered else None,
        )

    def _escalate_delivery_failure(
        self,
        db: Session,
        incident: SOCIncidentPayload,
        error_msg: Optional[str],
    ) -> None:
        """Escalate consecutive delivery failures by writing an emergency SOC alert and outbox record."""
        self._in_escalation = True
        try:
            from ariba_pam.db.models import SOCAlert

            alert = SOCAlert(
                id=generate_id("alt"),
                alert_type="SOC_DELIVERY_FAILURE",
                severity="CRITICAL",
                title="SOC delivery failure threshold exceeded",
                description=(
                    f"Ariba SOC adapter exceeded consecutive failure threshold ({self.failure_threshold}). "
                    f"Circuit breaker degraded. Last error: {error_msg}"
                ),
                correlation_id=f"corr_esc_{incident.correlation_id}",
                details={
                    "consecutive_failures": self.consecutive_failures,
                    "target_channel": incident.channel,
                    "failed_incident_id": incident.incident_id,
                    "error": error_msg,
                },
                status="open",
                created_at=utc_now(),
            )
            db.add(alert)

            AuditService.record_event(
                db=db,
                event_type="SOC_DELIVERY_FAILURE",
                correlation_id=alert.correlation_id,
                actor_id="ariba_soc_adapter",
                payload={
                    "alert_id": alert.id,
                    "consecutive_failures": self.consecutive_failures,
                    "circuit_state": "DEGRADED",
                    "error": error_msg,
                },
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            self._in_escalation = False

    def handle_alert(self, alert_payload: Dict[str, Any]) -> bool:
        """Callback handler matching SOCAlertsService receiver interface."""
        # Avoid recursion if this alert is about delivery failure escalation
        if alert_payload.get("alert_type") == "SOC_DELIVERY_FAILURE":
            return True

        result = self.route_and_deliver(alert_payload)
        return result.status in {"delivered", "simulated"}

    def reset_failure_counter(self) -> None:
        """Operator manual reset of failure counter and circuit breaker."""
        with self._lock:
            self.consecutive_failures = 0
            self.circuit_state = "HEALTHY"
            self.last_failure_error = None

    def get_metrics(self) -> Dict[str, Any]:
        """Observable adapter status and metrics."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "circuit_state": self.circuit_state,
                "consecutive_failures": self.consecutive_failures,
                "failure_threshold": self.failure_threshold,
                "total_routed": self.total_routed,
                "routed_critical": self.routed_critical,
                "routed_triage": self.routed_triage,
                "routed_stream": self.routed_stream,
                "total_delivered": self.total_delivered,
                "total_delivery_failures": self.total_delivery_failures,
                "last_delivery_at": ensure_utc(self.last_delivery_at).isoformat() if self.last_delivery_at else None,
                "last_failure_at": ensure_utc(self.last_failure_at).isoformat() if self.last_failure_at else None,
                "last_failure_error": self.last_failure_error,
                "channels": {
                    "critical": {
                        "url": self.critical_webhook_url,
                        "count": self.routed_critical,
                    },
                    "triage": {
                        "url": self.webhook_url,
                        "count": self.routed_triage,
                    },
                    "stream": {
                        "count": self.routed_stream,
                    },
                },
            }


# Global singleton instance
soc_adapter = AribaSOCAdapter()
