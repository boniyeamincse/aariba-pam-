"""Tests for Requester and Approver Portal Flows (P2-08, FR-03, FR-04, T-02)."""

from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from ariba_pam.core.security import create_session_token


def test_requester_and_approver_portal_flows(client: TestClient, seeded_fixtures, policy_admin):
    fixtures = seeded_fixtures
    alice = fixtures["alice"]           # requester
    bob = fixtures["bob"]               # approver
    asset = fixtures["asset_payment"]
    account = fixtures["acc_pay_admin"]

    # Publish an approved policy for the payment asset
    proposal = policy_admin.propose(
        allowed_target_account_ids=[account.id],
        max_duration_seconds=3600,
        required_approvals=1,
        requires_ticket=False,
    )
    published = policy_admin.publish(proposal)
    assert published.status_code == 200

    alice_token = create_session_token(user_id=alice.id, email=alice.email, auth_methods=["pwd", "fido2"])
    bob_token = create_session_token(user_id=bob.id, email=bob.email, auth_methods=["pwd", "fido2"])

    # 1. Requester submits access request
    now = datetime.now(timezone.utc)
    req_payload = {
        "asset_id": asset.id,
        "target_account_id": account.id,
        "requested_start_at": now.isoformat(),
        "requested_end_at": (now + timedelta(minutes=45)).isoformat(),
        "justification": "Production database patch rehearsal",
    }
    resp = client.post(
        "/api/v1/requests",
        headers={"Authorization": f"Bearer {alice_token}", "X-Idempotency-Key": "idm_portal_req_1"},
        json=req_payload,
    )
    assert resp.status_code == 201
    req_data = resp.json()
    request_id = req_data["request_id"]
    rev1_id = req_data["revision_id"]

    # 2. Requester tracks requests list (GET /api/v1/requests)
    my_reqs = client.get("/api/v1/requests", headers={"Authorization": f"Bearer {alice_token}"})
    assert my_reqs.status_code == 200
    req_ids = [r["id"] for r in my_reqs.json()]
    assert request_id in req_ids

    # 3. Approver views pending queue (GET /api/v1/approvals)
    approvals_resp = client.get("/api/v1/approvals", headers={"Authorization": f"Bearer {bob_token}"})
    assert approvals_resp.status_code == 200
    pending_steps = approvals_resp.json()
    step1 = next((s for s in pending_steps if s["request_id"] == request_id), None)
    assert step1 is not None
    assert step1["revision_id"] == rev1_id
    assert step1["asset_name"] == asset.name
    assert step1["target_account"] == account.username

    # 4. Requester replaces revision in background (amendment)
    revise_payload = {
        "expected_revision_id": rev1_id,
        "requested_start_at": now.isoformat(),
        "requested_end_at": (now + timedelta(minutes=50)).isoformat(),
        "justification": "Production database patch rehearsal - extended 5m",
    }
    replace_resp = client.post(
        f"/api/v1/requests/{request_id}/revisions",
        headers={"Authorization": f"Bearer {alice_token}", "X-Idempotency-Key": "idm_portal_rev_2"},
        json=revise_payload,
    )
    assert replace_resp.status_code == 201
    rev2_id = replace_resp.json()["revision_id"]
    assert rev2_id != rev1_id

    # 5. Approver tries to decide on stale revision rev1 -> gets 409 Conflict (stale-decision feedback)
    stale_decision = client.post(
        f"/api/v1/approval-steps/{step1['step_id']}/decisions",
        headers={"Authorization": f"Bearer {bob_token}", "X-Idempotency-Key": "idm_stale_dec_1"},
        json={"expected_revision_id": rev1_id, "decision": "approved"},
    )
    assert stale_decision.status_code == 409
    assert stale_decision.json()["code"] in ("STALE_REVISION", "STEP_ALREADY_DECIDED")

    # 6. Approver reloads queue and sees updated revision rev2
    refreshed_approvals = client.get("/api/v1/approvals", headers={"Authorization": f"Bearer {bob_token}"})
    assert refreshed_approvals.status_code == 200
    step2 = next((s for s in refreshed_approvals.json() if s["request_id"] == request_id), None)
    assert step2 is not None
    assert step2["revision_id"] == rev2_id

    # 7. Bob approves revision rev2, finalizing approval and issuing grant
    bob_dec = client.post(
        f"/api/v1/approval-steps/{step2['step_id']}/decisions",
        headers={"Authorization": f"Bearer {bob_token}", "X-Idempotency-Key": "idm_bob_dec_2"},
        json={"expected_revision_id": rev2_id, "decision": "approved"},
    )
    assert bob_dec.status_code == 201
    grant_id = bob_dec.json().get("grant_id")
    assert grant_id is not None

    # 8. Requester views grant and issues single-use launch capability
    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert launch_resp.status_code == 201
    assert "launch_token" in launch_resp.json()
    assert "expires_at" in launch_resp.json()


def test_requester_cancellation_flow(client: TestClient, seeded_fixtures, policy_admin):
    fixtures = seeded_fixtures
    alice = fixtures["alice"]
    asset = fixtures["asset_payment"]
    account = fixtures["acc_pay_admin"]
    bob = fixtures["bob"]

    # Publish policy
    proposal = policy_admin.propose(
        allowed_target_account_ids=[account.id],
        max_duration_seconds=3600,
        required_approvals=1,
    )
    policy_admin.publish(proposal)

    alice_token = create_session_token(user_id=alice.id, email=alice.email, auth_methods=["pwd", "fido2"])
    bob_token = create_session_token(user_id=bob.id, email=bob.email, auth_methods=["pwd", "fido2"])

    now = datetime.now(timezone.utc)
    resp = client.post(
        "/api/v1/requests",
        headers={"Authorization": f"Bearer {alice_token}", "X-Idempotency-Key": "idm_cancel_flow_1"},
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "requested_start_at": now.isoformat(),
            "requested_end_at": (now + timedelta(minutes=30)).isoformat(),
            "justification": "Cancelling soon",
        },
    )
    request_id = resp.json()["request_id"]

    # Requester cancels request
    cancel_resp = client.post(
        f"/api/v1/requests/{request_id}/cancel",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Approver queue should no longer list steps for cancelled request
    approvals_resp = client.get("/api/v1/approvals", headers={"Authorization": f"Bearer {bob_token}"})
    assert not any(s["request_id"] == request_id for s in approvals_resp.json())
