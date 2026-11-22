"""Unit and integration tests for Ariba SOC Event Adapter (P7-02, ADR-014).

Verifies:
1. Multi-tier priority routing (Critical, Triage, Stream).
2. Correlation identifier preservation and automatic generation.
3. Runbook enrichment from catalog.
4. Authenticated delivery with tracing headers.
5. Observable exponential backoff retry.
6. Delivery failure monitoring, circuit breaker degradation, and automated outbox escalation.
7. Circuit breaker recovery on successful delivery and operator manual reset.
8. Admin API endpoints and RBAC protection.
9. Integration with SOCAlertsService receiver broadcast.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from ariba_pam.config import settings
from ariba_pam.db.models import SOCAlert, AuditOutbox
from ariba_pam.services.soc_adapter import (
    AribaSOCAdapter,
    soc_adapter,
    CHANNEL_CRITICAL,
    CHANNEL_TRIAGE,
    CHANNEL_STREAM,
)
from ariba_pam.services.alerts import soc_alerts_service
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def reset_global_soc_adapter():
    """Ensure global soc_adapter state is clean before and after each test."""
    soc_adapter.reset_failure_counter()
    soc_adapter.set_mock_sender(None)
    yield
    soc_adapter.reset_failure_counter()
    soc_adapter.set_mock_sender(None)


def test_soc_priority_routing_channels():
    """
    P7-02: Verifies multi-tier priority routing correctly classifies events into
    critical_channel, triage_channel, and audit_stream_channel.
    """
    adapter = AribaSOCAdapter(
        webhook_url="https://soc.internal/triage",
        critical_webhook_url="https://soc.internal/critical",
        enabled=True,
    )

    # 1. Critical Events
    for alert_type in ["CAPTURE_FAILURE", "EMERGENCY_ACCESS_ACTIVATED", "UNPINNED_HOST_KEY", "UNSAFE_LAUNCH_BLOCKED"]:
        channel = adapter.classify_channel("HIGH", alert_type)
        assert channel == CHANNEL_CRITICAL
        assert adapter.get_destination_url(channel) == "https://soc.internal/critical"

    # Explicit CRITICAL severity
    channel_crit = adapter.classify_channel("CRITICAL", "CUSTOM_ANOMALY")
    assert channel_crit == CHANNEL_CRITICAL
    assert adapter.get_destination_url(channel_crit) == "https://soc.internal/critical"

    # 2. Triage Events
    for alert_type in ["ACCESS_GRANT_REVOKED", "LEASE_RENEWAL_FAILURE", "ROTATION_FAILURE", "IDP_USER_DISABLED"]:
        channel = adapter.classify_channel("MEDIUM", alert_type)
        assert channel == CHANNEL_TRIAGE
        assert adapter.get_destination_url(channel) == "https://soc.internal/triage"

    # Explicit HIGH/MEDIUM severity
    channel_high = adapter.classify_channel("HIGH", "CUSTOM_POLICY_CHECK")
    assert channel_high == CHANNEL_TRIAGE
    assert adapter.get_destination_url(channel_high) == "https://soc.internal/triage"

    # 3. Stream Events (LOW severity routine operations)
    channel_low = adapter.classify_channel("LOW", "RDP_TUNNEL_COMPILED")
    assert channel_low == CHANNEL_STREAM


def test_soc_correlation_tracking_and_generation():
    """
    P7-02: Verifies correlation identifier propagation.
    If provided, it must be preserved. If missing, a valid traced identifier must be generated.
    """
    adapter = AribaSOCAdapter()

    # Case A: Explicit correlation_id provided
    payload_a = adapter.build_incident_payload({
        "alert_type": "CAPTURE_FAILURE",
        "severity": "CRITICAL",
        "correlation_id": "corr_explicit_pipeline_99",
        "session_id": "ses_01H123",
    })
    assert payload_a.correlation_id == "corr_explicit_pipeline_99"
    assert payload_a.trace_id.startswith("trc_")
    assert payload_a.incident_id.startswith("inc_")
    assert payload_a.session_id == "ses_01H123"

    # Case B: Missing / empty correlation_id
    payload_b = adapter.build_incident_payload({
        "alert_type": "ACCESS_GRANT_REVOKED",
        "severity": "HIGH",
        "correlation_id": "",
    })
    assert payload_b.correlation_id.startswith("corr_soc_")
    assert len(payload_b.correlation_id) > len("corr_soc_")


def test_soc_runbook_enrichment():
    """
    P7-02: Verifies that incidents are enriched with actionable SOC runbooks.
    """
    adapter = AribaSOCAdapter()

    incident_rec = adapter.build_incident_payload({"alert_type": "CAPTURE_FAILURE", "severity": "CRITICAL"})
    assert "RB-SEC-01" in incident_rec.suggested_runbook

    incident_emg = adapter.build_incident_payload({"alert_type": "EMERGENCY_ACCESS_ACTIVATED", "severity": "CRITICAL"})
    assert "RB-SEC-02" in incident_emg.suggested_runbook

    incident_mitm = adapter.build_incident_payload({"alert_type": "UNPINNED_HOST_KEY", "severity": "CRITICAL"})
    assert "RB-SEC-03" in incident_mitm.suggested_runbook

    incident_rev = adapter.build_incident_payload({"alert_type": "ACCESS_GRANT_REVOKED", "severity": "HIGH"})
    assert "RB-SEC-05" in incident_rev.suggested_runbook

    incident_unknown = adapter.build_incident_payload({"alert_type": "UNKNOWN_ANOMALY", "severity": "MEDIUM"})
    assert "RB-SEC-99" in incident_unknown.suggested_runbook


def test_soc_delivery_payload_and_tracing_headers():
    """
    P7-02: Verifies structured JSON payload and tracing headers delivered to endpoint.
    """
    adapter = AribaSOCAdapter(
        webhook_url="https://soc.internal/triage",
        critical_webhook_url="https://soc.internal/critical",
        api_key="secret-soc-token-xyz",
        enabled=True,
    )

    captured_requests = []

    def mock_sender(url, payload, headers):
        captured_requests.append({"url": url, "payload": payload, "headers": headers})
        return True

    adapter.set_mock_sender(mock_sender)

    result = adapter.route_and_deliver({
        "alert_type": "CAPTURE_FAILURE",
        "severity": "CRITICAL",
        "correlation_id": "corr_delivery_hdr_test",
        "actor_id": "gw_01",
        "asset_id": "ast_payment_db",
        "details": {"recording_gap_bytes": 1048576},
    })

    assert result.status == "delivered"
    assert result.attempts == 1
    assert len(captured_requests) == 1

    req = captured_requests[0]
    assert req["url"] == "https://soc.internal/critical"
    assert req["headers"]["Authorization"] == "Bearer secret-soc-token-xyz"
    assert req["headers"]["X-Correlation-ID"] == "corr_delivery_hdr_test"
    assert req["headers"]["X-Channel"] == CHANNEL_CRITICAL
    assert req["payload"]["alert_type"] == "CAPTURE_FAILURE"
    assert req["payload"]["severity"] == "CRITICAL"
    assert req["payload"]["details"]["recording_gap_bytes"] == 1048576


def test_soc_observable_retry_transient_failure_recovery():
    """
    P7-02: Verifies bounded exponential retry on transient receiver failures,
    recovering successfully before reaching failure threshold.
    """
    adapter = AribaSOCAdapter(
        max_retries=3,
        backoff_base_seconds=0.01,
        enabled=True,
    )

    attempt_count = 0

    def mock_flaky_sender(url, payload, headers):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            return False  # Simulate transient HTTP 503 / network blip
        return True       # Succeed on 3rd attempt

    adapter.set_mock_sender(mock_flaky_sender)

    result = adapter.route_and_deliver({
        "alert_type": "ROTATION_FAILURE",
        "severity": "HIGH",
        "correlation_id": "corr_retry_test",
    })

    assert result.status == "delivered"
    assert result.attempts == 3
    assert attempt_count == 3
    assert adapter.consecutive_failures == 0
    assert adapter.circuit_state == "HEALTHY"


def test_soc_delivery_failure_monitoring_and_circuit_breaker(db_session: Session):
    """
    P7-02: Verifies delivery failure monitoring:
    Consecutive failures exceeding the threshold degrade circuit state to DEGRADED
    and escalate by creating a SOC_DELIVERY_FAILURE alert and audit record.
    """
    adapter = AribaSOCAdapter(
        max_retries=2,
        backoff_base_seconds=0.01,
        failure_threshold=3,
        enabled=True,
    )

    def mock_failing_sender(url, payload, headers):
        return False  # Complete downstream outage

    adapter.set_mock_sender(mock_failing_sender)

    # Deliver 1: Failure 1
    res1 = adapter.route_and_deliver({"alert_type": "ACCESS_GRANT_REVOKED", "severity": "HIGH"}, db=db_session)
    assert res1.status == "failed"
    assert adapter.consecutive_failures == 1
    assert adapter.circuit_state == "HEALTHY"

    # Deliver 2: Failure 2
    res2 = adapter.route_and_deliver({"alert_type": "LEASE_RENEWAL_FAILURE", "severity": "MEDIUM"}, db=db_session)
    assert res2.status == "failed"
    assert adapter.consecutive_failures == 2
    assert adapter.circuit_state == "HEALTHY"

    # Deliver 3: Failure 3 -> Hits threshold (3) -> Circuit DEGRADED + Outbox alert
    res3 = adapter.route_and_deliver({"alert_type": "ROTATION_FAILURE", "severity": "HIGH"}, db=db_session)
    assert res3.status == "failed"
    assert adapter.consecutive_failures == 3
    assert adapter.circuit_state == "DEGRADED"

    # Verify escalated alert in database
    failure_alert = db_session.query(SOCAlert).filter(
        SOCAlert.alert_type == "SOC_DELIVERY_FAILURE",
        SOCAlert.severity == "CRITICAL",
    ).first()
    assert failure_alert is not None
    assert "consecutive failure threshold" in failure_alert.description.lower()

    # Verify audit outbox event
    outbox_entry = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "SOC_DELIVERY_FAILURE",
    ).first()
    assert outbox_entry is not None
    assert outbox_entry.payload["circuit_state"] == "DEGRADED"


def test_soc_circuit_breaker_recovery_and_manual_reset():
    """
    P7-02: Verifies that circuit breaker automatically recovers to HEALTHY on successful delivery,
    and supports operator manual reset.
    """
    adapter = AribaSOCAdapter(failure_threshold=2, max_retries=1, backoff_base_seconds=0.01)

    # Force degraded state
    adapter.set_mock_sender(lambda u, p, h: False)
    adapter.route_and_deliver({"alert_type": "TEST_FAIL_1"})
    adapter.route_and_deliver({"alert_type": "TEST_FAIL_2"})
    assert adapter.circuit_state == "DEGRADED"
    assert adapter.consecutive_failures == 2

    # Operator manual reset
    adapter.reset_failure_counter()
    assert adapter.circuit_state == "HEALTHY"
    assert adapter.consecutive_failures == 0

    # Degrade again
    adapter.route_and_deliver({"alert_type": "TEST_FAIL_3"})
    adapter.route_and_deliver({"alert_type": "TEST_FAIL_4"})
    assert adapter.circuit_state == "DEGRADED"

    # Automatic recovery on next successful delivery
    adapter.set_mock_sender(lambda u, p, h: True)
    res_ok = adapter.route_and_deliver({"alert_type": "RECOVERY_TEST"})
    assert res_ok.status == "delivered"
    assert adapter.circuit_state == "HEALTHY"
    assert adapter.consecutive_failures == 0


def test_soc_admin_endpoints_and_anti_enumeration(client: TestClient, seeded_fixtures: dict):
    """
    P7-02: Verifies admin endpoints:
    - GET /api/v1/admin/integrations/soc/status
    - POST /api/v1/admin/integrations/soc/test-alert
    - POST /api/v1/admin/integrations/soc/reset-failures
    - RBAC enforcement (regular users denied with 403 Forbidden).
    """
    alice = seeded_fixtures["alice"]  # regular user
    dave = seeded_fixtures["dave"]    # admin

    # Alice denied
    resp_denied = client.get(
        "/api/v1/admin/integrations/soc/status",
        headers=auth_headers(alice.id, alice.email),
    )
    assert resp_denied.status_code == 403
    assert resp_denied.json()["code"] == "NOT_PERMITTED"

    # Dave gets status
    resp_status = client.get(
        "/api/v1/admin/integrations/soc/status",
        headers=auth_headers(dave.id, dave.email),
    )
    assert resp_status.status_code == 200
    metrics = resp_status.json()
    assert "circuit_state" in metrics
    assert "consecutive_failures" in metrics
    assert "channels" in metrics

    # Dave sends synthetic test alert
    resp_test = client.post(
        "/api/v1/admin/integrations/soc/test-alert",
        headers=auth_headers(dave.id, dave.email),
        params={"alert_type": "CAPTURE_FAILURE", "severity": "CRITICAL", "correlation_id": "corr_admin_test_123"},
    )
    assert resp_test.status_code == 200
    test_result = resp_test.json()
    assert test_result["test_alert"]["alert_type"] == "CAPTURE_FAILURE"
    assert test_result["delivery_result"]["channel"] == CHANNEL_CRITICAL
    assert test_result["delivery_result"]["correlation_id"] == "corr_admin_test_123"

    # Dave resets failures
    resp_reset = client.post(
        "/api/v1/admin/integrations/soc/reset-failures",
        headers=auth_headers(dave.id, dave.email),
    )
    assert resp_reset.status_code == 200
    assert resp_reset.json()["metrics"]["circuit_state"] == "HEALTHY"


def test_soc_integration_with_soc_alerts_service(db_session: Session):
    """
    P7-02: Verifies that registering soc_adapter with SOCAlertsService receiver broadcast
    automatically routes high-priority alerts with correlation tracking.
    """
    captured_payloads = []

    def mock_receiver_hook(url, payload, headers):
        captured_payloads.append(payload)
        return True

    soc_adapter.set_mock_sender(mock_receiver_hook)
    soc_alerts_service.add_receiver(soc_adapter.handle_alert)

    try:
        # Record alert via existing SOCAlertsService
        soc_alerts_service.record_alert(
            db=db_session,
            alert_type="UNPINNED_HOST_KEY",
            severity="CRITICAL",
            title="Host key mismatch on gateway bastion",
            description="Target server presented unrecognized SSH host key fingerprint",
            correlation_id="corr_live_soc_broadcast",
            details={"host": "core-db.internal"},
        )

        assert len(captured_payloads) == 1
        routed = captured_payloads[0]
        assert routed["alert_type"] == "UNPINNED_HOST_KEY"
        assert routed["severity"] == "CRITICAL"
        assert routed["channel"] == CHANNEL_CRITICAL
        assert routed["correlation_id"] == "corr_live_soc_broadcast"
        assert "RB-SEC-03" in routed["suggested_runbook"]
    finally:
        soc_alerts_service.remove_receiver(soc_adapter.handle_alert)
