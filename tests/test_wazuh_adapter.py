"""Wazuh SIEM Event Adapter Integration Tests (P7-01, ADR-013).

Verifies:
1. Event Filtering: Thresholds based on severity and event type allowlists.
2. Authenticated Delivery: Bearer token and API key headers with Wazuh OSSEC schema formatting.
3. Cryptographic Deduplication: Sliding window deduplication suppressing duplicate alerts.
4. Observable Retry with Exponential Backoff: Transient failure recovery and dead-letter handling.
5. Outbox Dispatch & SOC Alert Escalation: Batch dispatch from AuditOutbox and alert emission on terminal delivery failure.
6. Admin API Visibility: Status inspection, test event generation, and RBAC enforcement.
"""

import json
from datetime import timedelta
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from ariba_pam.config import settings
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.db.models import (
    User,
    AuditOutbox,
    SOCAlert,
)
from ariba_pam.services.audit import AuditService
from ariba_pam.services.wazuh import (
    WazuhAdapter,
    WazuhDeliveryResult,
    WAZUH_RULES,
    wazuh_adapter,
)
from tests.conftest import auth_headers


def test_wazuh_event_filtering_by_severity():
    """
    P7-01: Verify event filtering by minimum severity threshold.
    Events below threshold are filtered out; events meeting threshold are passed.
    """
    delivered_payloads: List[bytes] = []

    def mock_transport(url: str, headers: Dict[str, str], body: bytes) -> Tuple[int, bytes]:
        delivered_payloads.append(body)
        return 200, b'{"status": "ok"}'

    # Adapter configured with min_severity="HIGH"
    adapter = WazuhAdapter(
        min_severity="HIGH",
        http_transport=mock_transport,
    )

    # 1. Low severity event -> Filtered
    low_event = {
        "id": "aud_low_01",
        "event_type": "SESSION_LAUNCH_CONSUMED",
        "severity": "LOW",
        "correlation_id": "corr_01",
        "payload": {"info": "normal launch"},
    }
    res_low = adapter.deliver(low_event)
    assert res_low.status == "filtered"
    assert "below minimum threshold" in (res_low.filtered_reason or "")
    assert len(delivered_payloads) == 0

    # 2. Medium severity event -> Filtered
    med_event = {
        "id": "aud_med_01",
        "event_type": "SESSION_TERMINATION_REQUESTED",
        "severity": "MEDIUM",
        "correlation_id": "corr_02",
        "payload": {"reason": "routine exit"},
    }
    res_med = adapter.deliver(med_event)
    assert res_med.status == "filtered"
    assert len(delivered_payloads) == 0

    # 3. High severity event -> Delivered
    high_event = {
        "id": "aud_high_01",
        "event_type": "ACCESS_GRANT_REVOKED",
        "severity": "HIGH",
        "correlation_id": "corr_03",
        "payload": {"reason": "unauthorized access"},
    }
    res_high = adapter.deliver(high_event)
    assert res_high.status == "delivered"
    assert len(delivered_payloads) == 1

    # 4. Critical severity event -> Delivered
    crit_event = {
        "id": "aud_crit_01",
        "event_type": "CAPTURE_FAILURE",
        "severity": "CRITICAL",
        "correlation_id": "corr_04",
        "payload": {"gap": True},
    }
    res_crit = adapter.deliver(crit_event)
    assert res_crit.status == "delivered"
    assert len(delivered_payloads) == 2


def test_wazuh_event_filtering_by_event_type_and_noise():
    """
    P7-01: Verify event filtering by event type allowlist and automatic noise suppression.
    """
    delivered_payloads: List[bytes] = []

    def mock_transport(url: str, headers: Dict[str, str], body: bytes) -> Tuple[int, bytes]:
        delivered_payloads.append(body)
        return 200, b'{"status": "ok"}'

    # Allowlist restricted to specific security alert types
    adapter = WazuhAdapter(
        min_severity="LOW",
        allowed_event_types=["ACCESS_GRANT_REVOKED", "EMERGENCY_ACCESS_ACTIVATED"],
        http_transport=mock_transport,
    )

    # 1. Allowed event type -> Delivered
    allowed_event = {
        "id": "aud_allow_01",
        "event_type": "ACCESS_GRANT_REVOKED",
        "correlation_id": "corr_allow_01",
        "payload": {"reason": "operator revocation"},
    }
    res_allowed = adapter.deliver(allowed_event)
    assert res_allowed.status == "delivered"
    assert len(delivered_payloads) == 1

    # 2. Non-allowed event type -> Filtered
    disallowed_event = {
        "id": "aud_disallow_01",
        "event_type": "RDP_TUNNEL_COMPILED",
        "correlation_id": "corr_disallow_01",
        "payload": {"protocol": "rdp"},
    }
    res_disallowed = adapter.deliver(disallowed_event)
    assert res_disallowed.status == "filtered"
    assert "not in allowed event types" in (res_disallowed.filtered_reason or "")
    assert len(delivered_payloads) == 1

    # 3. Heartbeat noise -> Filtered even if in allowed list
    heartbeat_event = {
        "id": "aud_hb_01",
        "event_type": "gateway_heartbeat",
        "correlation_id": "corr_hb_01",
        "payload": {"status": "healthy"},
    }
    res_hb = adapter.deliver(heartbeat_event)
    assert res_hb.status == "filtered"
    assert "noise dropped" in (res_hb.filtered_reason or "")


def test_wazuh_authenticated_delivery_and_ossec_transformation():
    """
    P7-01: Verify authenticated delivery with Bearer token / API key,
    and confirm OSSEC JSON schema conformity (rule level, agent info, data payload).
    """
    recorded_requests: List[Dict[str, Any]] = []

    def mock_transport(url: str, headers: Dict[str, str], body: bytes) -> Tuple[int, bytes]:
        recorded_requests.append({
            "url": url,
            "headers": headers,
            "body": json.loads(body.decode("utf-8")),
        })
        return 200, b'{"status": "received"}'

    # 1. Test Bearer Token Authentication
    adapter_bearer = WazuhAdapter(
        api_url="https://wazuh.corp.internal:55000",
        api_key="jwt-secret-wazuh-token-987",
        auth_type="bearer",
        http_transport=mock_transport,
    )

    event = {
        "id": "aud_auth_01",
        "event_type": "ACCESS_GRANT_REVOKED",
        "correlation_id": "corr_rev_01",
        "actor_id": "usr_operator_01",
        "payload": {
            "grant_id": "grn_999",
            "reason": "Host security compromise detected",
            "terminated_sessions_count": 1,
        },
        "occurred_at": utc_now().isoformat(),
    }

    res = adapter_bearer.deliver(event)
    assert res.status == "delivered"
    assert res.wazuh_rule_id == "100201"
    assert res.wazuh_rule_level == 10

    assert len(recorded_requests) == 1
    req = recorded_requests[0]
    assert req["url"] == "https://wazuh.corp.internal:55000/events"
    assert req["headers"]["Authorization"] == "Bearer jwt-secret-wazuh-token-987"
    assert req["headers"]["Content-Type"] == "application/json"

    # Verify native OSSEC/Wazuh schema
    body = req["body"]
    assert "timestamp" in body
    assert body["agent"]["name"] == "ariba-pam-control-plane"
    assert body["rule"]["id"] == "100201"
    assert body["rule"]["level"] == 10
    assert "pam" in body["rule"]["groups"]
    assert body["data"]["ariba_pam"]["event_type"] == "ACCESS_GRANT_REVOKED"
    assert body["data"]["ariba_pam"]["actor_id"] == "usr_operator_01"
    assert body["data"]["ariba_pam"]["payload"]["grant_id"] == "grn_999"

    # 2. Test Custom Header API Key Authentication
    recorded_requests.clear()
    adapter_apikey = WazuhAdapter(
        api_url="https://wazuh.corp.internal:55000",
        api_key="apikey_custom_xyz_123",
        auth_type="api_key",
        http_transport=mock_transport,
    )
    res_api = adapter_apikey.deliver(event)
    assert res_api.status == "delivered"
    assert recorded_requests[0]["headers"]["X-Wazuh-Key"] == "apikey_custom_xyz_123"


def test_wazuh_cryptographic_deduplication():
    """
    P7-01: Verify cryptographic deduplication sliding window:
    - Identical event re-emissions are suppressed.
    - Network transport is called once.
    - Distinct events with different payloads or correlation IDs are delivered.
    """
    delivery_count = 0

    def mock_transport(url: str, headers: Dict[str, str], body: bytes) -> Tuple[int, bytes]:
        nonlocal delivery_count
        delivery_count += 1
        return 200, b'{"status": "ok"}'

    adapter = WazuhAdapter(
        dedup_window_seconds=10,
        http_transport=mock_transport,
    )

    event_original = {
        "id": "aud_dedup_01",
        "event_type": "ACCESS_GRANT_REVOKED",
        "correlation_id": "corr_dedup_100",
        "actor_id": "usr_operator",
        "payload": {"grant_id": "grn_01", "reason": "Revoked due to policy violation"},
    }

    # 1. First emission: unique -> Delivered
    res1 = adapter.deliver(event_original)
    assert res1.status == "delivered"
    assert res1.is_duplicate is False
    assert delivery_count == 1

    # 2. Duplicate emission with same semantic identity -> Deduplicated
    res2 = adapter.deliver(event_original)
    assert res2.status == "deduplicated"
    assert res2.is_duplicate is True
    # Transport was NOT invoked a second time
    assert delivery_count == 1

    # Metrics verify suppression
    metrics = adapter.get_metrics()
    assert metrics["metrics"]["total_duplicates_suppressed"] == 1
    assert metrics["metrics"]["total_delivered"] == 1

    # 3. Different event (different correlation_id) -> Delivered
    event_different = dict(event_original)
    event_different["correlation_id"] = "corr_dedup_200"
    res3 = adapter.deliver(event_different)
    assert res3.status == "delivered"
    assert res3.is_duplicate is False
    assert delivery_count == 2


def test_wazuh_observable_retry_with_transient_failure_recovery():
    """
    P7-01: Verify observable exponential retry recovers from transient failures (e.g. 503, connection drops).
    """
    attempt_count = 0

    def transient_failing_transport(url: str, headers: Dict[str, str], body: bytes) -> Tuple[int, bytes]:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            # Simulate 503 Service Unavailable on attempts 1 and 2
            return 503, b'{"error": "Wazuh cluster indexer queue busy"}'
        # Succeed on attempt 3
        return 200, b'{"status": "accepted"}'

    adapter = WazuhAdapter(
        max_retries=4,
        backoff_base_seconds=0.01,  # Fast backoff for tests
        http_transport=transient_failing_transport,
    )

    event = {
        "id": "aud_retry_01",
        "event_type": "EMERGENCY_ACCESS_ACTIVATED",
        "correlation_id": "corr_retry_01",
        "payload": {"emergency_id": "emg_123"},
    }

    res = adapter.deliver(event)
    assert res.status == "delivered"
    assert res.attempts == 3
    assert attempt_count == 3

    metrics = adapter.get_metrics()
    assert metrics["metrics"]["total_retries"] == 2
    assert metrics["metrics"]["total_delivered"] == 1
    assert metrics["metrics"]["total_failed"] == 0


def test_wazuh_dead_letter_and_terminal_failure_handling():
    """
    P7-01: Verify dead-letter state when retries are exhausted without successful delivery.
    """
    attempt_count = 0

    def permanently_failing_transport(url: str, headers: Dict[str, str], body: bytes) -> Tuple[int, bytes]:
        nonlocal attempt_count
        attempt_count += 1
        raise ConnectionResetError("Connection refused by Wazuh manager")

    adapter = WazuhAdapter(
        max_retries=3,
        backoff_base_seconds=0.01,
        http_transport=permanently_failing_transport,
    )

    event = {
        "id": "aud_fail_01",
        "event_type": "ROTATION_FAILURE",
        "correlation_id": "corr_fail_01",
        "payload": {"account_id": "act_win_01", "error": "RPC timeout"},
    }

    res = adapter.deliver(event)
    assert res.status == "dead_letter"
    assert res.attempts == 3
    assert "Connection refused" in (res.error or "")

    metrics = adapter.get_metrics()
    assert metrics["metrics"]["total_failed"] == 1
    assert metrics["metrics"]["total_retries"] == 3
    assert "Connection refused" in metrics["last_error"]


def test_wazuh_outbox_batch_dispatch_and_soc_alert_escalation(db_session: Session):
    """
    P7-01: Verify transactional outbox dispatch to Wazuh:
    - Successfully delivered events transition to 'delivered'.
    - Repeated delivery failures trigger critical SOC alert and transition to 'failed'.
    """
    attempt_count = 0

    def failing_transport(url: str, headers: Dict[str, str], body: bytes) -> Tuple[int, bytes]:
        nonlocal attempt_count
        attempt_count += 1
        return 500, b'{"error": "Internal Wazuh Elasticsearch indexing error"}'

    # 1. Create a pending audit event in the database
    event = AuditService.record_event(
        db=db_session,
        event_type="UNSAFE_LAUNCH_BLOCKED",
        correlation_id="corr_outbox_wazuh_01",
        actor_id="gw_lab_01",
        payload={"host": "10.0.1.50", "reason": "Host key fingerprint unpinned"},
    )
    # Simulate prior attempts reaching max failure threshold
    event.delivery_attempts = 4
    db_session.commit()

    adapter = WazuhAdapter(
        max_retries=2,
        backoff_base_seconds=0.01,
        http_transport=failing_transport,
    )

    # 2. Dispatch outbox
    results = adapter.dispatch_outbox_events(db_session, batch_limit=10)
    assert len(results) == 1
    res = results[0]
    assert res.status == "dead_letter"

    # Refresh DB session
    db_session.refresh(event)
    assert event.delivery_state == "failed"
    assert event.delivery_attempts >= 3

    # 3. Verify critical SOC alert emitted due to repeated evidence delivery failure
    alert = (
        db_session.query(SOCAlert)
        .filter(SOCAlert.alert_type == "EVIDENCE_DELIVERY_FAILURE")
        .first()
    )
    assert alert is not None
    assert alert.severity == "CRITICAL"
    assert "Wazuh SIEM delivery failure" in alert.title
    assert event.id in alert.description


def test_wazuh_admin_status_and_test_event_endpoints(client: TestClient, seeded_fixtures: dict):
    """
    P7-01: Verify Admin API endpoints for Wazuh SIEM status inspection and synthetic event testing.
    """
    dave = seeded_fixtures["dave"]
    alice = seeded_fixtures["alice"]

    # 1. Non-admin (Alice) denied access
    resp = client.get("/api/v1/admin/integrations/wazuh/status", headers=auth_headers(alice.id, alice.email))
    assert resp.status_code == 403

    # 2. Admin (Dave) retrieves status and metrics
    resp = client.get("/api/v1/admin/integrations/wazuh/status", headers=auth_headers(dave.id, dave.email))
    assert resp.status_code == 200
    status_data = resp.json()
    assert "api_url" in status_data
    assert "metrics" in status_data
    assert "dedup_window_seconds" in status_data

    # 3. Admin triggers synthetic test event
    # Set mock transport on global singleton to avoid network dependency in test
    delivered_bodies = []
    wazuh_adapter.http_transport = lambda url, headers, body: (delivered_bodies.append(body) or (200, b'{"status":"ok"}'))

    test_resp = client.post(
        "/api/v1/admin/integrations/wazuh/test-event?event_type=ACCESS_GRANT_REVOKED&severity=HIGH",
        headers=auth_headers(dave.id, dave.email),
    )
    assert test_resp.status_code == 200
    test_data = test_resp.json()
    assert test_data["delivery_result"]["status"] == "delivered"
    assert test_data["delivery_result"]["wazuh_rule_id"] == "100201"
    assert len(delivered_bodies) == 1
