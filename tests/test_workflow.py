"""End-to-end access request, approval, grant, launch, and gateway lifecycle tests."""

from datetime import datetime, timezone, timedelta
from tests.conftest import auth_headers
from ariba_pam.config import settings


def test_full_pam_access_lifecycle(client, seeded_fixtures):
    """
    Complete lifecycle verification:
    1. Alice submits access request.
    2. Alice attempts self-approval (fails with 403).
    3. Charlie (out-of-scope approver) attempts approval (fails with 403).
    4. Bob (scoped approver) approves request -> Atomic grant issuance.
    5. Alice creates a single-use session launch.
    6. Non-owner attempts to launch (fails with 403).
    7. Gateway consumes launch token -> session starts.
    8. Gateway replay of same launch token fails (fails with 409).
    9. Security operator revokes grant -> session marked terminating.
    10. Gateway renewal on revoked session fails.
    """
    alice = seeded_fixtures["alice"]
    bob = seeded_fixtures["bob"]
    charlie = seeded_fixtures["charlie"]
    dave = seeded_fixtures["dave"]
    asset_payment = seeded_fixtures["asset_payment"]
    acc_pay_admin = seeded_fixtures["acc_pay_admin"]

    now = datetime.now(timezone.utc)
    start_at = now - timedelta(minutes=5)
    end_at = now + timedelta(hours=1)

    # 1. Alice submits access request
    req_payload = {
        "asset_id": asset_payment.id,
        "target_account_id": acc_pay_admin.id,
        "requested_start_at": start_at.isoformat(),
        "requested_end_at": end_at.isoformat(),
        "justification": "Investigating high payment latency on lab cluster",
    }
    submit_resp = client.post(
        "/api/v1/requests",
        json=req_payload,
        headers=auth_headers(alice.id, alice.email),
    )
    assert submit_resp.status_code == 201
    req_data = submit_resp.json()
    req_id = req_data["request_id"]
    rev_id = req_data["revision_id"]
    step_id = req_data["step_id"]

    # 2. Self-approval attempt by Alice
    self_approve_resp = client.post(
        f"/api/v1/approval-steps/{step_id}/decisions",
        json={"expected_revision_id": rev_id, "decision": "approved"},
        headers=auth_headers(alice.id, alice.email),
    )
    assert self_approve_resp.status_code == 403
    assert self_approve_resp.json()["code"] == "SELF_APPROVAL_FORBIDDEN"

    # 3. Out-of-scope approver attempt by Charlie (analytics team)
    cross_scope_resp = client.post(
        f"/api/v1/approval-steps/{step_id}/decisions",
        json={"expected_revision_id": rev_id, "decision": "approved"},
        headers=auth_headers(charlie.id, charlie.email),
    )
    assert cross_scope_resp.status_code == 403
    assert cross_scope_resp.json()["code"] == "OUT_OF_SCOPE"

    # 4. Valid scoped approver Bob approves -> Atomic grant issuance
    bob_approve_resp = client.post(
        f"/api/v1/approval-steps/{step_id}/decisions",
        json={"expected_revision_id": rev_id, "decision": "approved"},
        headers=auth_headers(bob.id, bob.email),
    )
    assert bob_approve_resp.status_code == 201
    decision_data = bob_approve_resp.json()
    assert decision_data["decision"] == "approved"
    assert decision_data["request_status"] == "approved"
    grant_id = decision_data["grant_id"]
    assert grant_id is not None

    # Verify Grant status
    grant_resp = client.get(
        f"/api/v1/grants/{grant_id}",
        headers=auth_headers(alice.id, alice.email),
    )
    assert grant_resp.status_code == 200
    assert grant_resp.json()["status"] == "active"
    assert grant_resp.json()["is_active_window"] is True

    # 5. Non-owner (Bob) attempts to create a launch -> 403 Forbidden
    unauth_launch = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(bob.id, bob.email),
    )
    assert unauth_launch.status_code == 403
    assert unauth_launch.json()["code"] == "NOT_GRANT_OWNER"

    # 6. Alice creates a session launch
    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    assert launch_resp.status_code == 201
    launch_data = launch_resp.json()
    launch_token = launch_data["launch_token"]
    assert launch_token.startswith("launch_")

    # 7. Gateway consumes the launch token (T-04)
    consume_resp = client.post(
        "/internal/v1/launches/consume",
        json={
            "launch_token": launch_token,
            "gateway_id": "gw_lab_01",
        },
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert consume_resp.status_code == 201
    session_data = consume_resp.json()
    session_id = session_data["session_id"]
    assert session_data["target_host"] == "10.0.1.50"
    assert session_data["target_username"] == "dbadmin"

    # 8. Replay of same launch token fails (T-04 replay prevention)
    replay_resp = client.post(
        "/internal/v1/launches/consume",
        json={
            "launch_token": launch_token,
            "gateway_id": "gw_lab_01",
        },
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert replay_resp.status_code == 409
    assert replay_resp.json()["code"] == "LAUNCH_REPLAY_DENIED"

    # 9. Security Operator Dave revokes the grant
    revoke_resp = client.post(
        f"/api/v1/grants/{grant_id}/revoke",
        json={"reason": "Emergency incident response containment"},
        headers=auth_headers(dave.id, dave.email),
    )
    assert revoke_resp.status_code == 202
    assert revoke_resp.json()["status"] == "revoked"
    assert revoke_resp.json()["terminating_sessions_count"] == 1

    # 10. Gateway renewal on revoked session is rejected
    renew_resp = client.post(
        f"/internal/v1/sessions/{session_id}/renew",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert renew_resp.status_code == 409
    assert renew_resp.json()["code"] == "SESSION_TERMINATING"
