"""Tests for access request revision replacement, reads, and stale conflict protection (Task P2-03)."""

from datetime import timedelta
from ariba_pam.db.base import utc_now
from tests.conftest import auth_headers


def test_request_revision_replacement_and_stale_rejection(client, seeded_fixtures, policy_admin):
    """
    1. Publish policy on payments asset.
    2. Alice submits access request (revision 1).
    3. Alice replaces revision with new justification and adjusted time window (revision 2).
    4. Stale replacement with old expected_revision_id is rejected with 409 Conflict.
    5. GET /api/v1/requests/{request_id} returns all revisions and step history.
    """
    fixtures = seeded_fixtures
    alice = fixtures["alice"]
    bob = fixtures["bob"]
    asset = fixtures["asset_payment"]
    account = fixtures["acc_pay_admin"]

    # 1. Publish policy
    policy_admin.publish(policy_admin.propose())

    # 2. Alice submits request
    now = utc_now()
    resp_submit = client.post(
        "/api/v1/requests",
        headers=auth_headers(alice.id, alice.email),
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "requested_start_at": (now - timedelta(minutes=1)).isoformat(),
            "requested_end_at": (now + timedelta(minutes=30)).isoformat(),
            "justification": "Initial maintenance window proposal",
        },
    )
    assert resp_submit.status_code == 201
    submit_data = resp_submit.json()
    req_id = submit_data["request_id"]
    rev1_id = submit_data["revision_id"]

    # 3. Alice replaces revision (updating justification and extending window to 45 mins)
    resp_replace = client.post(
        f"/api/v1/requests/{req_id}/revisions",
        headers=auth_headers(alice.id, alice.email),
        json={
            "expected_revision_id": rev1_id,
            "requested_end_at": (now + timedelta(minutes=45)).isoformat(),
            "justification": "Extended maintenance window after initial review",
        },
    )
    assert resp_replace.status_code == 201
    replace_data = resp_replace.json()
    assert replace_data["request_id"] == req_id
    assert replace_data["revision_number"] == 2
    rev2_id = replace_data["revision_id"]
    assert rev2_id != rev1_id

    # 4. Attempting to replace using stale revision ID (rev1_id) fails with 409 Conflict
    resp_stale = client.post(
        f"/api/v1/requests/{req_id}/revisions",
        headers=auth_headers(alice.id, alice.email),
        json={
            "expected_revision_id": rev1_id,
            "justification": "Stale concurrent edit",
        },
    )
    assert resp_stale.status_code == 409
    assert resp_stale.json()["code"] == "STALE_REVISION"

    # 5. Non-owner (Bob) attempts revision replacement -> 403 Forbidden
    resp_unauth = client.post(
        f"/api/v1/requests/{req_id}/revisions",
        headers=auth_headers(bob.id, bob.email),
        json={
            "expected_revision_id": rev2_id,
            "justification": "Unauthorized revision attempt",
        },
    )
    assert resp_unauth.status_code == 403
    assert resp_unauth.json()["code"] == "NOT_PERMITTED"

    # 6. GET /api/v1/requests/{request_id} reads both revisions
    resp_get = client.get(
        f"/api/v1/requests/{req_id}",
        headers=auth_headers(alice.id, alice.email),
    )
    assert resp_get.status_code == 200
    get_data = resp_get.json()
    assert get_data["current_revision_id"] == rev2_id
    assert len(get_data["revisions"]) == 2
    assert get_data["revisions"][0]["revision_number"] == 1
    assert get_data["revisions"][1]["revision_number"] == 2
    assert get_data["revisions"][1]["justification"] == "Extended maintenance window after initial review"
