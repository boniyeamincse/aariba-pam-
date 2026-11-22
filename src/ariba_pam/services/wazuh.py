"""Wazuh SIEM Event Adapter (P7-01, ADR-013).

Provides:
1. Event Filtering: Configurable minimum severity threshold and event type allowlist.
2. Authenticated Delivery: Structured JSON over HTTPS using Bearer token, API Key, or Basic auth.
3. Cryptographic Deduplication: SHA-256 sliding window cache suppressing redundant alerts.
4. Observable Retry: Exponential backoff with retry counters, dead-letter state, and SOC alert escalation.
5. OSSEC Rule Mapping: Standard Wazuh decoders, rule IDs, and alert levels.
"""

import hashlib
import json
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable, Tuple
from pydantic import BaseModel, Field

from ariba_pam.config import settings
from ariba_pam.db.base import utc_now, ensure_utc
from ariba_pam.services.audit import AuditService


# Severity rank hierarchy
SEVERITY_LEVELS: Dict[str, int] = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}

# Pre-mapped Wazuh OSSEC rule catalog
WAZUH_RULES: Dict[str, Dict[str, Any]] = {
    "CAPTURE_FAILURE": {
        "id": "100202",
        "level": 15,
        "description": "Ariba PAM Terminal Recording Capture Failure or Gap Detected",
        "groups": ["pam", "evidence", "critical"],
        "default_severity": "CRITICAL",
    },
    "EMERGENCY_ACCESS_ACTIVATED": {
        "id": "100205",
        "level": 14,
        "description": "Ariba PAM Emergency Break-Glass Access Activated via Multi-Custodian Quorum",
        "groups": ["pam", "emergency", "break_glass"],
        "default_severity": "CRITICAL",
    },
    "UNSAFE_LAUNCH_BLOCKED": {
        "id": "100203",
        "level": 12,
        "description": "Ariba PAM Gateway Blocked Unsafe Launch Due to Target Host Key Mismatch",
        "groups": ["pam", "gateway", "mitm_defense"],
        "default_severity": "HIGH",
    },
    "ROTATION_FAILURE": {
        "id": "100206",
        "level": 11,
        "description": "Ariba PAM Target Credential Rotation Failed",
        "groups": ["pam", "vault", "credentials"],
        "default_severity": "HIGH",
    },
    "ACCESS_GRANT_REVOKED": {
        "id": "100201",
        "level": 10,
        "description": "Ariba PAM Access Grant Revoked by Security Operator",
        "groups": ["pam", "access_control", "revocation"],
        "default_severity": "HIGH",
    },
    "LEASE_RENEWAL_FAILURE": {
        "id": "100204",
        "level": 9,
        "description": "Ariba PAM Gateway Session Lease Renewal Failed",
        "groups": ["pam", "gateway", "lease"],
        "default_severity": "MEDIUM",
    },
    "IDP_USER_DISABLED": {
        "id": "100207",
        "level": 8,
        "description": "Ariba PAM User Disabled at IdP and Active Sessions Terminated",
        "groups": ["pam", "identity", "lifecycle"],
        "default_severity": "MEDIUM",
    },
    "SESSION_TERMINATION_REQUESTED": {
        "id": "100209",
        "level": 7,
        "description": "Ariba PAM Session Termination Requested by User or Operator",
        "groups": ["pam", "session", "operator"],
        "default_severity": "MEDIUM",
    },
    "RDP_TUNNEL_COMPILED": {
        "id": "100208",
        "level": 6,
        "description": "Ariba PAM RDP Proxy Tunnel Parameters Compiled",
        "groups": ["pam", "rdp", "session"],
        "default_severity": "LOW",
    },
    "SESSION_LAUNCH_CONSUMED": {
        "id": "100210",
        "level": 5,
        "description": "Ariba PAM Session Launch Token Consumed by Gateway",
        "groups": ["pam", "session", "gateway"],
        "default_severity": "LOW",
    },
    "AUDIT_EXPORT_CREATED": {
        "id": "100211",
        "level": 4,
        "description": "Ariba PAM Tamper-Evident Audit Evidence Export Created",
        "groups": ["pam", "audit", "compliance"],
        "default_severity": "LOW",
    },
}

DEFAULT_RULE = {
    "id": "100200",
    "level": 3,
    "description": "Ariba PAM Generic Security Audit Event",
    "groups": ["pam", "audit"],
    "default_severity": "LOW",
}


class WazuhDeliveryResult(BaseModel):
    """Result of an event delivery attempt to Wazuh SIEM."""

    event_id: str
    status: str = Field(description="delivered, filtered, deduplicated, dead_letter")
    attempts: int = 0
    is_duplicate: bool = False
    filtered_reason: Optional[str] = None
    wazuh_rule_id: Optional[str] = None
    wazuh_rule_level: Optional[int] = None
    error: Optional[str] = None
    delivered_at: Optional[str] = None


class WazuhAdapter:
    """Enterprise Wazuh SIEM adapter with filtering, deduplication, and observable retry."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        auth_type: Optional[str] = None,
        min_severity: Optional[str] = None,
        allowed_event_types: Optional[List[str]] = None,
        max_retries: Optional[int] = None,
        backoff_base_seconds: Optional[float] = None,
        dedup_window_seconds: Optional[int] = None,
        http_transport: Optional[Callable[[str, Dict[str, str], bytes], Tuple[int, bytes]]] = None,
    ):
        self.api_url = api_url or getattr(settings, "wazuh_api_url", "https://wazuh.internal:55000")
        self.api_key = api_key or getattr(settings, "wazuh_api_key", "synthetic-wazuh-api-key")
        self.auth_type = auth_type or getattr(settings, "wazuh_auth_type", "bearer")
        self.min_severity = (min_severity or getattr(settings, "wazuh_min_severity", "LOW")).upper()
        self.allowed_event_types = allowed_event_types or []
        self.max_retries = max_retries if max_retries is not None else getattr(settings, "wazuh_max_retries", 3)
        self.backoff_base_seconds = (
            backoff_base_seconds if backoff_base_seconds is not None else getattr(settings, "wazuh_backoff_base_seconds", 0.1)
        )
        self.dedup_window_seconds = (
            dedup_window_seconds if dedup_window_seconds is not None else getattr(settings, "wazuh_dedup_window_seconds", 300)
        )
        self.http_transport = http_transport

        # Thread-safe sliding window deduplication cache: hash -> expiry_monotonic
        self._dedup_cache: Dict[str, float] = {}
        self._lock = threading.Lock()

        # Observable delivery metrics
        self._metrics = {
            "total_processed": 0,
            "total_delivered": 0,
            "total_filtered": 0,
            "total_duplicates_suppressed": 0,
            "total_retries": 0,
            "total_failed": 0,
        }
        self._last_error: Optional[str] = None
        self._last_delivery_at: Optional[datetime] = None

    def compute_dedup_key(self, event: Dict[str, Any]) -> str:
        """Compute SHA-256 deduplication fingerprint of event semantic identity."""
        event_type = str(event.get("event_type", ""))
        correlation_id = str(event.get("correlation_id", ""))
        actor_id = str(event.get("actor_id", ""))
        payload = event.get("payload", {})
        payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        raw = f"{event_type}|{correlation_id}|{actor_id}|{payload_str}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def check_and_record_dedup(self, dedup_key: str) -> bool:
        """
        Check if an event fingerprint exists in the sliding window.
        Returns True if duplicate (should suppress), False if unique (recorded).
        """
        now = time.monotonic()
        with self._lock:
            # Clean expired items
            expired = [k for k, exp in self._dedup_cache.items() if exp < now]
            for k in expired:
                del self._dedup_cache[k]

            if dedup_key in self._dedup_cache:
                return True

            self._dedup_cache[dedup_key] = now + self.dedup_window_seconds
            return False

    def should_emit(self, event: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Evaluate filtering policy:
        1. Drops internal health checks and noise.
        2. Enforces minimum severity threshold (LOW, MEDIUM, HIGH, CRITICAL).
        3. Enforces event type allowlist if specified.
        """
        event_type = event.get("event_type", "")

        # 1. Drop noise heartbeats
        if "heartbeat" in event_type.lower() or "ping" in event_type.lower():
            return False, "Internal heartbeat noise dropped"

        # 2. Check event type allowlist
        if self.allowed_event_types and event_type not in self.allowed_event_types:
            return False, f"Event type '{event_type}' not in allowed event types"

        # 3. Check severity threshold
        event_sev = (
            event.get("severity")
            or (event.get("payload", {}).get("severity") if isinstance(event.get("payload"), dict) else None)
            or WAZUH_RULES.get(event_type, {}).get("default_severity", "LOW")
        ).upper()

        event_rank = SEVERITY_LEVELS.get(event_sev, 1)
        min_rank = SEVERITY_LEVELS.get(self.min_severity, 1)

        if event_rank < min_rank:
            return False, f"Severity '{event_sev}' (rank {event_rank}) is below minimum threshold '{self.min_severity}' (rank {min_rank})"

        return True, None

    def transform_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Ariba PAM audit/alert record into native Wazuh JSON log format."""
        event_type = event.get("event_type", "UNKNOWN")
        rule_meta = WAZUH_RULES.get(event_type, DEFAULT_RULE)

        timestamp = event.get("occurred_at") or event.get("timestamp") or event.get("created_at")
        if isinstance(timestamp, datetime):
            timestamp_str = ensure_utc(timestamp).isoformat()
        elif isinstance(timestamp, str):
            timestamp_str = timestamp
        else:
            timestamp_str = utc_now().isoformat()

        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {"raw": payload}

        severity = (
            event.get("severity")
            or payload.get("severity")
            or rule_meta.get("default_severity", "LOW")
        ).upper()

        return {
            "timestamp": timestamp_str,
            "agent": {
                "id": getattr(settings, "wazuh_agent_id", "000"),
                "name": getattr(settings, "wazuh_agent_name", "ariba-pam-control-plane"),
            },
            "rule": {
                "id": rule_meta["id"],
                "level": rule_meta["level"],
                "description": rule_meta["description"],
                "groups": rule_meta["groups"],
            },
            "data": {
                "ariba_pam": {
                    "event_id": event.get("id") or event.get("event_id", ""),
                    "event_type": event_type,
                    "correlation_id": event.get("correlation_id", ""),
                    "severity": severity,
                    "actor_id": event.get("actor_id"),
                    "session_id": event.get("session_id") or payload.get("session_id"),
                    "asset_id": event.get("asset_id") or payload.get("asset_id"),
                    "payload": payload,
                }
            },
            "location": "ariba_pam.audit",
        }

    def _get_auth_headers(self) -> Dict[str, str]:
        """Compile authentication headers for Wazuh API."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Ariba-PAM-Wazuh-Adapter/1.0",
        }
        if self.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.auth_type == "api_key":
            headers["X-Wazuh-Key"] = self.api_key
        elif self.auth_type == "basic":
            headers["Authorization"] = f"Basic {self.api_key}"
        return headers

    def deliver(self, event: Dict[str, Any]) -> WazuhDeliveryResult:
        """
        Deliver a security event to Wazuh with filtering, deduplication, and observable retry.
        """
        event_id = str(event.get("id") or event.get("event_id") or "evt_unknown")
        with self._lock:
            self._metrics["total_processed"] += 1

        # 1. Event Filtering
        should_send, filter_reason = self.should_emit(event)
        if not should_send:
            with self._lock:
                self._metrics["total_filtered"] += 1
            return WazuhDeliveryResult(
                event_id=event_id,
                status="filtered",
                filtered_reason=filter_reason,
            )

        # 2. Cryptographic Deduplication
        dedup_key = self.compute_dedup_key(event)
        if self.check_and_record_dedup(dedup_key):
            with self._lock:
                self._metrics["total_duplicates_suppressed"] += 1
            return WazuhDeliveryResult(
                event_id=event_id,
                status="deduplicated",
                is_duplicate=True,
            )

        # 3. Transform to Wazuh OSSEC format
        wazuh_payload = self.transform_event(event)
        wazuh_rule_id = wazuh_payload["rule"]["id"]
        wazuh_rule_level = wazuh_payload["rule"]["level"]
        body_bytes = json.dumps(wazuh_payload).encode("utf-8")
        headers = self._get_auth_headers()
        target_url = f"{self.api_url}/events"

        # 4. Authenticated Delivery with Observable Retry & Exponential Backoff
        attempts = 0
        last_error = ""

        while attempts < self.max_retries:
            attempts += 1
            try:
                status_code, resp_bytes = self._execute_http(target_url, headers, body_bytes)
                if 200 <= status_code < 300:
                    with self._lock:
                        self._metrics["total_delivered"] += 1
                        self._last_delivery_at = utc_now()
                    return WazuhDeliveryResult(
                        event_id=event_id,
                        status="delivered",
                        attempts=attempts,
                        wazuh_rule_id=wazuh_rule_id,
                        wazuh_rule_level=wazuh_rule_level,
                        delivered_at=utc_now().isoformat(),
                    )
                else:
                    last_error = f"Wazuh server returned HTTP {status_code}: {resp_bytes.decode('utf-8', errors='ignore')[:200]}"
            except Exception as e:
                last_error = f"Network transport error: {str(e)}"

            with self._lock:
                self._metrics["total_retries"] += 1
                self._last_error = last_error

            # Bounded exponential backoff before retry
            if attempts < self.max_retries:
                backoff_delay = min(5.0, self.backoff_base_seconds * (2 ** (attempts - 1)))
                time.sleep(backoff_delay)

        # Retries exhausted -> Dead-Letter state
        with self._lock:
            self._metrics["total_failed"] += 1
            self._last_error = last_error

        return WazuhDeliveryResult(
            event_id=event_id,
            status="dead_letter",
            attempts=attempts,
            error=last_error,
            wazuh_rule_id=wazuh_rule_id,
            wazuh_rule_level=wazuh_rule_level,
        )

    def _execute_http(self, url: str, headers: Dict[str, str], body: bytes) -> Tuple[int, bytes]:
        """Internal HTTP executor dispatching via custom transport or urllib."""
        if self.http_transport:
            return self.http_transport(url, headers, body)

        import urllib.request
        import urllib.error
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def get_metrics(self) -> Dict[str, Any]:
        """Retrieve live observable delivery metrics and adapter state."""
        with self._lock:
            return {
                "api_url": self.api_url,
                "auth_type": self.auth_type,
                "min_severity": self.min_severity,
                "dedup_window_seconds": self.dedup_window_seconds,
                "max_retries": self.max_retries,
                "dedup_cache_size": len(self._dedup_cache),
                "metrics": dict(self._metrics),
                "last_error": self._last_error,
                "last_delivery_at": self._last_delivery_at.isoformat() if self._last_delivery_at else None,
            }

    def reset_metrics(self) -> None:
        """Reset internal delivery counters and deduplication cache."""
        with self._lock:
            for k in self._metrics:
                self._metrics[k] = 0
            self._dedup_cache.clear()
            self._last_error = None
            self._last_delivery_at = None

    def dispatch_outbox_events(self, db: Any, batch_limit: int = 50) -> List[WazuhDeliveryResult]:
        """
        Process pending events from the transactional AuditOutbox and forward to Wazuh.
        Updates outbox delivery states and raises alerts on terminal failures.
        """
        pending = AuditService.get_pending_events(db, limit=batch_limit)
        results = []

        for ev in pending:
            ev_dict = {
                "id": ev.id,
                "event_type": ev.event_type,
                "correlation_id": ev.correlation_id,
                "actor_id": ev.actor_id,
                "payload": ev.payload,
                "occurred_at": ev.occurred_at,
            }
            res = self.deliver(ev_dict)

            if res.status in ("delivered", "filtered", "deduplicated"):
                AuditService.mark_delivered(db, ev.id)
            elif res.status == "dead_letter":
                AuditService.mark_failed(db, ev.id)
                # Escalate to SOC alert on repeated terminal failures
                if ev.delivery_attempts >= 3 and ev.event_type != "SOC_SECURITY_ALERT":
                    from ariba_pam.services.alerts import soc_alerts_service
                    soc_alerts_service.record_alert(
                        db=db,
                        alert_type="EVIDENCE_DELIVERY_FAILURE",
                        severity="CRITICAL",
                        title="Wazuh SIEM delivery failure",
                        description=f"Outbox event {ev.id} ({ev.event_type}) failed delivery after {res.attempts} attempts: {res.error}",
                        correlation_id=ev.correlation_id,
                        details={"event_id": ev.id, "error": res.error, "attempts": ev.delivery_attempts},
                    )
            results.append(res)

        return results


# Global singleton instance
wazuh_adapter = WazuhAdapter()
