"""Reviewed policy publication and fail-closed access checks."""

from datetime import timedelta

from sqlalchemy import select

from ariba_pam.config import settings
from ariba_pam.db.base import utc_now
from ariba_pam.db.models import AccessGrant, AccessPolicyVersion, AuditOutbox, RoleAssignment
from tests.conftest import auth_headers


def submit(client, fixtures, *, minutes=20, ticket_ref=None, account=None):
    requester = fixtures["alice"]
    now = utc_now()
    return client.post(
        "/api/v1/requests",
        headers=auth_headers(requester.id, requester.email),
        json={
            "asset_id": fixtures["asset_payment"].id,
            "target_account_id": (account or fixtures["acc_pay_admin"]).id,
            "requested_start_at": (now - timedelta(minutes=1)).isoformat(),
            "requested_end_at": (now + timedelta(minutes=minutes)).isoformat(),
            "justification": "Check approved policy on an isolated lab host",
            "ticket_ref": ticket_ref,
        },
    )


def approve(client, actor, step_id, revision_id):
    return client.post(
        f"/api/v1/approval-steps/{step_id}/decisions",
        headers=auth_headers(actor.id, actor.email),
        json={"expected_revision_id": revision_id, "decision": "approved"},
    )


def test_policy_publication_requires_independent_scoped_review(client, seeded_fixtures, policy_admin, db_session):
    fixtures = seeded_fixtures
    proposal = policy_admin.propose()
    duplicate = policy_admin.propose()
    assert policy_admin.publish(proposal, actor=fixtures["dave"]).json()["code"] == "SELF_REVIEW_DENIED"
    assert policy_admin.publish(proposal, actor=fixtures["charlie"]).status_code == 404
    proposal_id = proposal.json()["proposal_id"]
    assert client.get(
        f"{policy_admin.path}/{proposal_id}",
        headers=auth_headers(fixtures["charlie"].id, fixtures["charlie"].email),
    ).status_code == 404
    assert submit(client, fixtures).json()["code"] == "POLICY_REQUIRED"

    applied = policy_admin.publish(proposal)
    assert applied.status_code == 200
    assert applied.json()["policy_version"] == 1
    assert policy_admin.publish(duplicate).json()["code"] == "STALE_POLICY_VERSION"

    version = db_session.scalar(select(AccessPolicyVersion))
    assert version.id == applied.json()["policy_version_id"]
    assert version.proposal_id == proposal_id
    events = db_session.scalars(select(AuditOutbox).where(AuditOutbox.event_type == "ADMIN_PROPOSAL_APPLIED"))
    assert [event.payload["policy_version_id"] for event in events] == [version.id]


def test_policy_validation_and_request_constraints(client, seeded_fixtures, policy_admin):
    fixtures = seeded_fixtures
    invalid = policy_admin.propose(required_approvals=0)
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "INVALID_POLICY"
    assert policy_admin.propose(
        allowed_target_account_ids=[fixtures["acc_ana_readonly"].id]
    ).json()["code"] == "INVALID_POLICY_ACCOUNTS"
    rejected = policy_admin.publish(policy_admin.propose(), decision="rejected")
    assert rejected.json()["status"] == "rejected"
    assert submit(client, fixtures).json()["code"] == "POLICY_REQUIRED"

    assert policy_admin.publish(policy_admin.propose(max_duration_seconds=2400, requires_ticket=True)).status_code == 200
    assert submit(client, fixtures, minutes=45, ticket_ref="LAB-42").json()["code"] == "POLICY_DURATION_EXCEEDED"
    assert submit(client, fixtures, account=fixtures["acc_pay_root"]).json()["code"] == "POLICY_ACCOUNT_DENIED"
    assert submit(client, fixtures, ticket_ref=" ").json()["code"] == "TICKET_REQUIRED"
    assert submit(client, fixtures, ticket_ref="LAB-42").status_code == 201


def test_ordered_steps_require_distinct_approvers(client, seeded_fixtures, policy_admin, db_session):
    fixtures = seeded_fixtures
    dave = fixtures["dave"]
    bob = fixtures["bob"]
    db_session.add(RoleAssignment(
        user_id=dave.id, role_id="rol_approver",
        scope_type="asset", scope_value=fixtures["asset_payment"].id,
    ))
    db_session.commit()

    policy = policy_admin.publish(policy_admin.propose(required_approvals=2)).json()
    request = submit(client, fixtures).json()
    assert request["policy_version_id"] == policy["policy_version_id"]
    first = approve(client, bob, request["step_id"], request["revision_id"])
    assert first.status_code == 201
    assert first.json()["request_status"] == "pending"
    assert first.json()["grant_id"] is None
    assert client.get("/api/v1/approvals", headers=auth_headers(bob.id, bob.email)).json() == []
    queue = client.get("/api/v1/approvals", headers=auth_headers(dave.id, dave.email)).json()
    assert len(queue) == 1
    second = queue[0]["step_id"]
    assert second != request["step_id"]
    assert approve(client, bob, second, request["revision_id"]).json()["code"] == "DUPLICATE_VOTE"
    grant = approve(client, dave, second, request["revision_id"])
    assert grant.status_code == 201
    assert grant.json()["grant_id"] == db_session.scalar(select(AccessGrant)).id


def test_new_policy_blocks_old_revisions_and_outstanding_launches(client, seeded_fixtures, policy_admin, db_session):
    fixtures = seeded_fixtures
    alice = fixtures["alice"]
    bob = fixtures["bob"]
    assert policy_admin.publish(policy_admin.propose()).status_code == 200
    pending = submit(client, fixtures).json()
    approved = submit(client, fixtures).json()
    grant = approve(client, bob, approved["step_id"], approved["revision_id"]).json()["grant_id"]
    launch_path = f"/api/v1/grants/{grant}/launches"
    launch = client.post(launch_path, headers=auth_headers(alice.id, alice.email)).json()

    assert policy_admin.publish(policy_admin.propose(version=1, max_duration_seconds=1800)).status_code == 200
    assert approve(client, bob, pending["step_id"], pending["revision_id"]).json()["code"] == "POLICY_CHANGED"
    assert client.post(launch_path, headers=auth_headers(alice.id, alice.email)).json()["code"] == "POLICY_CHANGED"
    old_launch = client.post(
        "/internal/v1/launches/consume",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
        json={"launch_token": launch["launch_token"], "gateway_id": "gw_lab_01"},
    )
    assert old_launch.json()["code"] == "POLICY_CHANGED"
    assert [version.version for version in db_session.scalars(
        select(AccessPolicyVersion).order_by(AccessPolicyVersion.version)
    )] == [1, 2]
    assert submit(client, fixtures).status_code == 201


def test_unreadable_active_policy_fails_closed(client, seeded_fixtures, policy_admin, db_session):
    assert policy_admin.publish(policy_admin.propose()).status_code == 200
    version = db_session.scalar(select(AccessPolicyVersion))
    version.rules = {}
    db_session.commit()
    response = submit(client, seeded_fixtures)
    assert response.status_code == 503
    assert response.json()["code"] == "INVALID_ACTIVE_POLICY"
