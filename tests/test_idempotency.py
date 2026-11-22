"""Tests for idempotency key handling and conflict detection across API calls."""

from datetime import timedelta
from ariba_pam.db.base import utc_now
from tests.conftest import auth_headers


def test_idempotent_request_submission_and_conflict(client, seeded_fixtures, policy_admin):
    """
    1. Publish policy.
    2. Alice submits access request with X-Idempotency-Key.
    3. Replaying exact same payload with same idempotency key returns identical 201 response.
    4. Submitting a different payload with the same key returns 409 Conflict (IDEMPOTENCY_CONFLICT).
    """
    fixtures = seeded_fixtures
    alice = fixtures["alice"]
    asset = fixtures["asset_payment"]
    account = fixtures["acc_pay_admin"]

    policy_admin.publish(policy_admin.propose())

    now = utc_now()
    idem_key = "idem_test_req_key_12345"
    payload = {
        "asset_id": asset.id,
        "target_account_id": account.id,
        "requested_start_at": (now - timedelta(minutes=1)).isoformat(),
        "requested_end_at": (now + timedelta(minutes=30)).isoformat(),
        "justification": "Validate restart behavior in the pilot lab",
    }

    # 1. First submission
    resp1 = client.post(
        "/api/v1/requests",
        headers={
            **auth_headers(alice.id, alice.email),
            "X-Idempotency-Key": idem_key,
        },
        json=payload,
    )
    assert resp1.status_code == 201
    data1 = resp1.json()

    # 2. Replay with identical payload and key
    resp2 = client.post(
        "/api/v1/requests",
        headers={
            **auth_headers(alice.id, alice.email),
            "X-Idempotency-Key": idem_key,
        },
        json=payload,
    )
    assert resp2.status_code == 201
    data2 = resp2.json()
    assert data1 == data2  # Exact duplicate returns cached response

    # 3. Conflict: same key with modified payload (e.g. changed justification)
    conflicting_payload = {**payload, "justification": "Completely different reason"}
    resp3 = client.post(
        "/api/v1/requests",
        headers={
            **auth_headers(alice.id, alice.email),
            "X-Idempotency-Key": idem_key,
        },
        json=conflicting_payload,
    )
    assert resp3.status_code == 409
    assert resp3.json()["code"] == "IDEMPOTENCY_CONFLICT"
