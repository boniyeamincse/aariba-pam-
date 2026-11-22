"""P3-09: Gateway Lab Milestone Verification Test Suite.

Verifies the complete gateway lifecycle:
1. Allowed SSH path (Request -> Approval -> Grant -> Launch -> Session reservation -> Lease renewal -> Termination).
2. Anti-replay enforcement (T-04): consuming a launch token twice produces 409 Conflict.
3. Expired launch authorization rejection (T-04).
4. Revocation propagation: revoking an active grant halts lease renewal.
5. Mutual-secret authentication enforcement (unauthorized gateway calls return 401).
6. Terminal state immutability: late gateway events cannot reopen ended sessions.
7. Transactional audit outbox evidence verification for all lifecycle transitions.
"""

from datetime import datetime, timezone, timedelta
from tests.conftest import auth_headers
from ariba_pam.config import settings
from ariba_pam.db.models import AuditOutbox, SessionLaunch, AccessSession
from ariba_pam.db.base import utc_now


def _gateway_headers(correlation_id: str = "corr_gw_test") -> dict:
    return {
        "X-Gateway-Secret": settings.gateway_api_secret,
        "X-Correlation-Id": correlation_id,
    }


def _create_approved_grant(client, seeded_fixtures, policy_admin):
    alice = seeded_fixtures["alice"]
    bob = seeded_fixtures["bob"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    assert policy_admin.publish(policy_admin.propose()).status_code == 200

    now = datetime.now(timezone.utc)
    submit_resp = client.post(
        "/api/v1/requests",
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "requested_start_at": (now - timedelta(minutes=2)).isoformat(),
            "requested_end_at": (now + timedelta(minutes=45)).isoformat(),
            "justification": "Gateway lab milestone verification",
        },
        headers=auth_headers(alice.id, alice.email),
    )
    assert submit_resp.status_code == 201
    req_data = submit_resp.json()

    # Bob approves
    approve_resp = client.post(
        f"/api/v1/approval-steps/{req_data['step_id']}/decisions",
        json={"expected_revision_id": req_data["revision_id"], "decision": "approved"},
        headers=auth_headers(bob.id, bob.email),
    )
    assert approve_resp.status_code == 201
    grant_id = approve_resp.json()["grant_id"]
    return alice, grant_id


def test_gateway_milestone_allowed_path_and_lifecycle(client, seeded_fixtures, policy_admin, db_session):
    """Verify standard end-to-end flow from launch token issuance to session termination and audit."""
    alice, grant_id = _create_approved_grant(client, seeded_fixtures, policy_admin)

    # 1. Requester issues a one-time launch token
    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    assert launch_resp.status_code == 201
    launch_data = launch_resp.json()
    launch_token = launch_data["launch_token"]
    assert launch_token

    # 2. Gateway consumes launch token
    consume_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_zone_lab_01"},
        headers=_gateway_headers("corr_gw_consume_valid"),
    )
    assert consume_resp.status_code == 201
    session_data = consume_resp.json()
    session_id = session_data["session_id"]
    assert session_data["target_host"] == "10.0.1.50"
    assert session_data["target_username"] == "dbadmin"
    assert "lease_deadline" in session_data

    # 3. Gateway renews session lease
    renew_resp = client.post(
        f"/internal/v1/sessions/{session_id}/renew",
        headers=_gateway_headers("corr_gw_renew_valid"),
    )
    assert renew_resp.status_code == 200
    renew_data = renew_resp.json()
    assert "lease_deadline" in renew_data

    # 4. Gateway delivers session terminated event
    term_resp = client.post(
        f"/internal/v1/sessions/{session_id}/events",
        json={"state": "ended", "reason": "Operator closed SSH terminal normally"},
        headers=_gateway_headers("corr_gw_event_term"),
    )
    assert term_resp.status_code == 202
    assert term_resp.json()["status"] == "ended"

    # 5. Verify database session state
    session_db = db_session.get(AccessSession, session_id)
    assert session_db.status == "ended"
    assert session_db.termination_reason == "Operator closed SSH terminal normally"

    # 6. Verify transactional audit outbox records
    outbox_events = (
        db_session.query(AuditOutbox)
        .filter(AuditOutbox.correlation_id.in_(["corr_gw_consume_valid", "corr_gw_event_term"]))
        .all()
    )
    event_types = {e.event_type for e in outbox_events}
    assert "SESSION_LAUNCH_CONSUMED" in event_types
    assert "GATEWAY_SESSION_EVENT" in event_types


def test_gateway_milestone_launch_replay_protection(client, seeded_fixtures, policy_admin):
    """Enforce T-04: single-use launch token cannot be re-consumed."""
    alice, grant_id = _create_approved_grant(client, seeded_fixtures, policy_admin)

    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    launch_token = launch_resp.json()["launch_token"]

    # First consumption succeeds
    first_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_zone_lab_01"},
        headers=_gateway_headers(),
    )
    assert first_resp.status_code == 201

    # Second consumption must be denied with 409 Conflict
    replay_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_zone_lab_01"},
        headers=_gateway_headers(),
    )
    assert replay_resp.status_code == 409
    assert replay_resp.json()["code"] == "LAUNCH_REPLAY_DENIED"


def test_gateway_milestone_expired_launch_rejection(client, seeded_fixtures, policy_admin, db_session):
    """Consuming an expired launch authorization fails closed."""
    alice, grant_id = _create_approved_grant(client, seeded_fixtures, policy_admin)

    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    launch_token = launch_resp.json()["launch_token"]

    # Artificially expire the launch in DB
    launch_row = db_session.query(SessionLaunch).first()
    launch_row.expires_at = utc_now() - timedelta(minutes=5)
    db_session.commit()

    consume_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_zone_lab_01"},
        headers=_gateway_headers(),
    )
    assert consume_resp.status_code == 409
    assert consume_resp.json()["code"] == "LAUNCH_EXPIRED"


def test_gateway_milestone_revoked_grant_denies_launch(client, seeded_fixtures, policy_admin):
    """Security revocation of grant stops launch consumption."""
    alice, grant_id = _create_approved_grant(client, seeded_fixtures, policy_admin)
    dave = seeded_fixtures["dave"]  # SecOps

    # Issue launch
    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    launch_token = launch_resp.json()["launch_token"]

    # SecOps revokes the grant
    revoke_resp = client.post(
        f"/api/v1/grants/{grant_id}/revoke",
        json={"reason": "Compromised host reported by IDS"},
        headers=auth_headers(dave.id, dave.email),
    )
    assert revoke_resp.status_code == 202

    # Gateway tries to consume launch on revoked grant
    consume_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_zone_lab_01"},
        headers=_gateway_headers(),
    )
    assert consume_resp.status_code == 409
    assert consume_resp.json()["code"] == "GRANT_NOT_ACTIVE"


def test_gateway_milestone_revocation_breaks_lease_renewal(client, seeded_fixtures, policy_admin):
    """When grant is revoked during active session, gateway lease renewal is denied."""
    alice, grant_id = _create_approved_grant(client, seeded_fixtures, policy_admin)
    dave = seeded_fixtures["dave"]

    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    launch_token = launch_resp.json()["launch_token"]

    # Session started
    consume_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_zone_lab_01"},
        headers=_gateway_headers(),
    )
    session_id = consume_resp.json()["session_id"]

    # Revoke grant
    client.post(
        f"/api/v1/grants/{grant_id}/revoke",
        json={"reason": "Emergency security revocation"},
        headers=auth_headers(dave.id, dave.email),
    )

    # Next gateway renewal attempt must fail
    renew_resp = client.post(
        f"/internal/v1/sessions/{session_id}/renew",
        headers=_gateway_headers(),
    )
    assert renew_resp.status_code == 409
    assert renew_resp.json()["code"] == "SESSION_TERMINATING"


def test_gateway_milestone_unauthorized_gateway_rejected(client, seeded_fixtures, policy_admin):
    """Internal gateway endpoints reject requests missing or invalid X-Gateway-Secret."""
    alice, grant_id = _create_approved_grant(client, seeded_fixtures, policy_admin)

    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    launch_token = launch_resp.json()["launch_token"]

    # Missing secret
    missing_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_zone_lab_01"},
        headers={},
    )
    assert missing_resp.status_code == 401
    assert missing_resp.json()["code"] == "GATEWAY_UNAUTHORIZED"

    # Wrong secret
    wrong_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_zone_lab_01"},
        headers={"X-Gateway-Secret": "invalid_bogus_secret"},
    )
    assert wrong_resp.status_code == 401
    assert wrong_resp.json()["code"] == "GATEWAY_UNAUTHORIZED"


def test_gateway_milestone_late_events_cannot_reopen_ended_session(client, seeded_fixtures, policy_admin, db_session):
    """Ensure state machine transition: once a session is ended, late events cannot alter terminal state."""
    alice, grant_id = _create_approved_grant(client, seeded_fixtures, policy_admin)

    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    launch_token = launch_resp.json()["launch_token"]

    consume_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_zone_lab_01"},
        headers=_gateway_headers(),
    )
    session_id = consume_resp.json()["session_id"]

    # Terminate session normally
    client.post(
        f"/internal/v1/sessions/{session_id}/events",
        json={"state": "ended", "reason": "First clean termination"},
        headers=_gateway_headers(),
    )

    # Late / delayed event arrives
    late_resp = client.post(
        f"/internal/v1/sessions/{session_id}/events",
        json={"state": "failed", "reason": "Late packet arrival"},
        headers=_gateway_headers(),
    )
    assert late_resp.status_code == 202

    # Verify session remains 'ended' with original termination reason
    session_db = db_session.get(AccessSession, session_id)
    assert session_db.status == "ended"
    assert session_db.termination_reason == "First clean termination"
