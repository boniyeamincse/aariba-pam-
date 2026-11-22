"""Tests for outbox notification delivery, outage resilience, and deduplication (Task P2-07 / FR-10 / T-11)."""

from datetime import timedelta
from ariba_pam.db.base import utc_now
from ariba_pam.services.notifications import NotificationDispatcher
from ariba_pam.services.audit import AuditService
from tests.conftest import auth_headers


def test_notification_delivery_outage_preserves_decision_and_retries(client, seeded_fixtures, policy_admin, db_session):
    """
    1. Submit access request and approve it -> decisions and grants committed.
    2. Simulate notification delivery outage:
       - Delivery fails, error is logged, retry count increments.
       - Authoritative approval decision and grant remain preserved and active!
    3. Simulate network recovery:
       - Retrying dispatch succeeds and marks events delivered.
    4. Duplicate delivery attempt:
       - Deduplicated, prevents repeating state transition.
    """
    fixtures = seeded_fixtures
    alice = fixtures["alice"]
    bob = fixtures["bob"]
    asset = fixtures["asset_payment"]
    account = fixtures["acc_pay_admin"]

    policy_admin.publish(policy_admin.propose())

    # 1. Alice submits request
    now = utc_now()
    resp_req = client.post(
        "/api/v1/requests",
        headers=auth_headers(alice.id, alice.email),
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "requested_start_at": (now - timedelta(minutes=1)).isoformat(),
            "requested_end_at": (now + timedelta(minutes=30)).isoformat(),
            "justification": "Testing notification delivery resilience",
        },
    )
    assert resp_req.status_code == 201
    step_id = resp_req.json()["step_id"]
    rev_id = resp_req.json()["revision_id"]

    # Bob approves
    resp_app = client.post(
        f"/api/v1/approval-steps/{step_id}/decisions",
        headers=auth_headers(bob.id, bob.email),
        json={"expected_revision_id": rev_id, "decision": "approved"},
    )
    assert resp_app.status_code == 201
    grant_id = resp_app.json()["grant_id"]
    assert grant_id is not None

    # Verify pending outbox events exist
    pending = AuditService.get_pending_events(db_session)
    assert len(pending) >= 2  # ACCESS_REQUEST_SUBMITTED and ACCESS_GRANT_ISSUED

    # 2. Simulate notification delivery outage
    def failing_sink(msg):
        raise ConnectionError("Simulated upstream notification delivery outage")

    dispatcher = NotificationDispatcher(delivery_sink=failing_sink)
    result_outage = dispatcher.dispatch_pending(db_session)
    assert result_outage["failed"] >= 2
    assert result_outage["successful"] == 0

    # Crucial check: Despite notification failure, Grant and Request status remain intact!
    grant_resp = client.get(
        f"/api/v1/grants/{grant_id}",
        headers=auth_headers(alice.id, alice.email),
    )
    assert grant_resp.status_code == 200
    assert grant_resp.json()["status"] == "active"

    # Retry count is visible
    pending_after_fail = AuditService.get_pending_events(db_session)
    assert all(e.delivery_attempts >= 1 for e in pending_after_fail)

    # 3. Network recovery: dispatcher succeeds
    delivered_msgs = []
    def successful_sink(msg):
        delivered_msgs.append(msg)
        return True

    dispatcher.delivery_sink = successful_sink
    result_recovered = dispatcher.dispatch_pending(db_session)
    assert result_recovered["successful"] >= 2
    assert len(delivered_msgs) >= 2

    # All events are now marked delivered
    pending_now = AuditService.get_pending_events(db_session)
    assert len(pending_now) == 0

    # 4. Duplicate delivery cannot repeat a transition
    result_duplicate = dispatcher.dispatch_pending(db_session)
    assert result_duplicate["processed"] == 0
