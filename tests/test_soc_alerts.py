"""Integration tests for Pilot SOC Alerts & Component Health Monitoring (Phase 5 / P5-06, FR-10, NFR-08, T-07, T-10)."""

from datetime import timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from ariba_pam.config import settings
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.db.models import (
    AccessSession,
    AccessGrant,
    SessionLaunch,
    AuditOutbox,
    SOCAlert,
)
from ariba_pam.services.alerts import soc_alerts_service
from ariba_pam.services.notifications import NotificationDispatcher
from tests.conftest import auth_headers


def _create_active_grant_and_session(db: Session, fixtures: dict):
    """Helper to provision active grant and session for test scenarios."""
    alice = fixtures["alice"]
    asset = fixtures["asset_payment"]
    account = fixtures["acc_pay_admin"]
    now = utc_now()

    grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=alice.id,
        asset_id=asset.id,
        target_account_id=account.id,
        effective_start_at=now - timedelta(minutes=5),
        effective_end_at=now + timedelta(minutes=55),
        status="active",
    )
    db.add(grant)
    db.flush()

    launch = SessionLaunch(
        id=generate_id("lau"),
        grant_id=grant.id,
        launch_token_digest="digest_soc_test_launch",
        expires_at=now + timedelta(minutes=1),
        is_consumed=True,
    )
    db.add(launch)
    db.flush()

    session = AccessSession(
        id=generate_id("ses"),
        grant_id=grant.id,
        launch_id=launch.id,
        gateway_id="gw_zone_internal",
        status="active",
        started_at=now,
    )
    db.add(session)
    db.commit()
    return grant, session


def test_capture_failure_alert_on_recording_gap(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    FR-10, T-07: When a gateway reports a session recording coverage gap,
    a CRITICAL CAPTURE_FAILURE alert is created and logged to the audit outbox.
    """
    _, session = _create_active_grant_and_session(db_session, seeded_fixtures)

    # Gateway delivers session event with gap coverage
    resp = client.post(
        f"/internal/v1/sessions/{session.id}/events",
        headers={"X-Gateway-Secret": settings.gateway_api_secret, "X-Correlation-ID": "corr_gap_test"},
        json={
            "state": "ended",
            "reason": "Recording buffer exhausted during upstream outage",
            "recording": {
                "recording_id": generate_id("rec"),
                "digest_sha256": "abcdef1234567890" * 4,
                "size_bytes": 10485760,
                "duration_seconds": 45,
                "coverage_status": "gap",
            },
        },
    )
    assert resp.status_code == 202

    # Verify SOCAlert record in database
    alert = db_session.query(SOCAlert).filter(
        SOCAlert.session_id == session.id,
        SOCAlert.alert_type == "CAPTURE_FAILURE",
    ).first()
    assert alert is not None
    assert alert.severity == "CRITICAL"
    assert alert.status == "open"
    assert "coverage gap" in alert.title.lower()

    # Verify audit outbox event
    outbox_entry = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "SOC_SECURITY_ALERT",
        AuditOutbox.correlation_id == "corr_gap_test",
    ).first()
    assert outbox_entry is not None
    assert outbox_entry.payload["alert_type"] == "CAPTURE_FAILURE"


def test_unsafe_launch_blocked_alert(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    T-10: When a gateway blocks an unsafe session launch fail-closed,
    an UNSAFE_LAUNCH_BLOCKED alert is created.
    """
    _, session = _create_active_grant_and_session(db_session, seeded_fixtures)

    resp = client.post(
        f"/internal/v1/sessions/{session.id}/events",
        headers={"X-Gateway-Secret": settings.gateway_api_secret, "X-Correlation-ID": "corr_unsafe_launch"},
        json={
            "state": "failed",
            "reason": "Unsafe launch: recording pipeline degraded before target connection",
        },
    )
    assert resp.status_code == 202

    alert = db_session.query(SOCAlert).filter(
        SOCAlert.session_id == session.id,
        SOCAlert.alert_type == "UNSAFE_LAUNCH_BLOCKED",
    ).first()
    assert alert is not None
    assert alert.severity == "CRITICAL"
    assert "Unsafe session launch blocked" in alert.title


def test_lease_renewal_failure_alert_on_revoked_grant(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    T-04, FR-10: When gateway attempts to renew lease on a revoked grant,
    renewal fails and generates LEASE_RENEWAL_FAILURE alert.
    """
    grant, session = _create_active_grant_and_session(db_session, seeded_fixtures)

    # Revoke grant (simulate security revocation)
    grant.status = "revoked"
    db_session.commit()

    resp = client.post(
        f"/internal/v1/sessions/{session.id}/renew",
        headers={"X-Gateway-Secret": settings.gateway_api_secret, "X-Correlation-ID": "corr_renew_fail"},
    )
    assert resp.status_code == 409

    alert = db_session.query(SOCAlert).filter(
        SOCAlert.session_id == session.id,
        SOCAlert.alert_type == "LEASE_RENEWAL_FAILURE",
    ).first()
    assert alert is not None
    assert alert.severity == "HIGH"
    assert "lease renewal failed" in alert.title.lower()


def test_signing_failure_alert_on_ended_session(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    T-10: When certificate signing is attempted on an ended session,
    signing is rejected and generates SIGNING_FAILURE alert.
    """
    _, session = _create_active_grant_and_session(db_session, seeded_fixtures)

    # End session
    session.status = "ended"
    db_session.commit()

    resp = client.post(
        f"/internal/v1/sessions/{session.id}/sign-certificate",
        headers={"X-Gateway-Secret": settings.gateway_api_secret, "X-Correlation-ID": "corr_sign_fail"},
        json={"client_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGatewayEphemeralKeyTest"},
    )
    assert resp.status_code == 409

    alert = db_session.query(SOCAlert).filter(
        SOCAlert.session_id == session.id,
        SOCAlert.alert_type == "SIGNING_FAILURE",
    ).first()
    assert alert is not None
    assert alert.severity == "HIGH"
    assert "session not active" in alert.title.lower()


def test_repeated_evidence_delivery_failure_alert(client: TestClient, db_session: Session):
    """
    FR-10, NFR-08: When notification dispatcher encounters repeated delivery failures (>=3),
    an EVIDENCE_DELIVERY_FAILURE alert is created.
    """
    # Create an outbox event
    event = AuditOutbox(
        id=generate_id("aud"),
        event_type="ACCESS_REQUEST_SUBMITTED",
        correlation_id="corr_evidence_deliv_test",
        actor_id="usr_test",
        payload={"request_id": "req_123"},
        payload_digest="digest123",
        occurred_at=utc_now(),
        delivery_state="pending",
        delivery_attempts=2,  # already 2 failed attempts
    )
    db_session.add(event)
    db_session.commit()

    def failing_sink(msg):
        return False

    dispatcher = NotificationDispatcher(delivery_sink=failing_sink)
    dispatcher.process_outbox_event(db_session, event)

    # Verify alert created
    alert = db_session.query(SOCAlert).filter(
        SOCAlert.correlation_id == "corr_evidence_deliv_test",
        SOCAlert.alert_type == "EVIDENCE_DELIVERY_FAILURE",
    ).first()
    assert alert is not None
    assert alert.severity == "CRITICAL"
    assert "Repeated evidence delivery failure" in alert.title


def test_gateway_heartbeat_and_degraded_capture(client: TestClient, db_session: Session):
    """
    NFR-08: Gateway 15-second heartbeat reports degraded capture, triggering alert
    and updating component health status to degraded.
    """
    # 1. Gateway sends degraded heartbeat
    resp = client.post(
        "/internal/v1/gateways/gw_pilot_01/heartbeat",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
        json={
            "zone_id": "zone_dmz",
            "status": "healthy",
            "active_sessions_count": 3,
            "capture_status": "degraded",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["healthy"] is False

    # Check alert was created
    alert = db_session.query(SOCAlert).filter(
        SOCAlert.gateway_id == "gw_pilot_01",
        SOCAlert.alert_type == "CAPTURE_FAILURE",
    ).first()
    assert alert is not None
    assert alert.severity == "CRITICAL"

    # 2. Check system component health probe
    health_resp = client.get("/health/components")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["status"] == "degraded"
    assert health_data["components"]["open_critical_alerts"] >= 1

    # 3. Gateway recovers and sends healthy heartbeat
    resp_healthy = client.post(
        "/internal/v1/gateways/gw_pilot_01/heartbeat",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
        json={
            "zone_id": "zone_dmz",
            "status": "healthy",
            "active_sessions_count": 3,
            "capture_status": "healthy",
        },
    )
    assert resp_healthy.status_code == 200
    assert resp_healthy.json()["healthy"] is True


def test_soc_alerts_list_and_acknowledge_lifecycle(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Authorized security operator lists alerts and acknowledges an open alert.
    """
    dave = seeded_fixtures["dave"]  # admin/operator
    _, session = _create_active_grant_and_session(db_session, seeded_fixtures)

    # Generate an alert
    alert = soc_alerts_service.record_alert(
        db=db_session,
        alert_type="SOD_VIOLATION",
        severity="HIGH",
        title="Unauthorized role conflict attempt",
        description="Requester attempted self-approval",
        correlation_id="corr_sod_test",
        details={"attempted_by": "usr_test"},
        session_id=session.id,
    )

    # Dave lists alerts
    list_resp = client.get(
        "/api/v1/alerts?status=open&severity=HIGH",
        headers=auth_headers(dave.id, dave.email),
    )
    assert list_resp.status_code == 200
    alerts = list_resp.json()
    assert any(a["id"] == alert.id for a in alerts)

    # Dave gets single alert
    get_resp = client.get(
        f"/api/v1/alerts/{alert.id}",
        headers=auth_headers(dave.id, dave.email),
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == alert.id
    assert get_resp.json()["status"] == "open"

    # Dave acknowledges the alert
    ack_resp = client.post(
        f"/api/v1/alerts/{alert.id}/acknowledge",
        headers=auth_headers(dave.id, dave.email),
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["status"] == "acknowledged"
    assert ack_resp.json()["acknowledged_by_id"] == dave.id
    assert ack_resp.json()["acknowledged_at"] is not None

    # Verify audit event for acknowledgement
    ack_audit = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "SOC_ALERT_ACKNOWLEDGED",
        AuditOutbox.actor_id == dave.id,
    ).first()
    assert ack_audit is not None
    assert ack_audit.payload["alert_id"] == alert.id


def test_soc_alerts_access_control_and_anti_enumeration(client: TestClient, seeded_fixtures: dict):
    """
    Security invariants:
    - Routine non-security users (e.g. Alice / requester) denied with 403 Forbidden.
    - Authorized users querying non-existent alert receive 404 Not Found.
    """
    alice = seeded_fixtures["alice"]  # regular requester
    dave = seeded_fixtures["dave"]    # admin

    # Alice denied listing alerts
    resp = client.get(
        "/api/v1/alerts",
        headers=auth_headers(alice.id, alice.email),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "NOT_PERMITTED"

    # Dave queries non-existent alert -> 404
    resp_404 = client.get(
        "/api/v1/alerts/alt_non_existent_123",
        headers=auth_headers(dave.id, dave.email),
    )
    assert resp_404.status_code == 404
    assert resp_404.json()["code"] == "ALERT_NOT_FOUND"


def test_siem_custom_receiver_dispatch(db_session: Session):
    """
    Verifies that registered custom SIEM receivers (e.g. Wazuh / Splunk)
    receive the structured security alert payload immediately upon creation.
    """
    received_payloads = []

    def mock_siem_receiver(payload):
        received_payloads.append(payload)
        return True

    soc_alerts_service.set_receiver(mock_siem_receiver)
    try:
        soc_alerts_service.record_alert(
            db=db_session,
            alert_type="UNPINNED_HOST_KEY",
            severity="CRITICAL",
            title="SSH host key mismatch detected",
            description="Target host presented unpinned public key fingerprint",
            correlation_id="corr_hostkey_test",
            details={"host": "payment-db.internal", "fingerprint": "SHA256:unknown"},
        )
        assert len(received_payloads) == 1
        assert received_payloads[0]["alert_type"] == "UNPINNED_HOST_KEY"
        assert received_payloads[0]["severity"] == "CRITICAL"
        assert received_payloads[0]["correlation_id"] == "corr_hostkey_test"
    finally:
        soc_alerts_service.set_receiver(None)
