"""Admin change proposals and four-eyes review enforcement tests (Task P1-07 / FR-02 / FR-08 / T-02)."""

from tests.conftest import auth_headers


def test_admin_proposal_four_eyes_and_self_review_prevention(client, seeded_fixtures):
    """
    Verify independent review:
    1. Author submits change proposal.
    2. Author is rejected when attempting to approve their own proposal (403 Forbidden).
    3. Independent administrator successfully reviews and applies the proposal.
    4. Stale/duplicate decisions are rejected (409 Conflict).
    """
    dave = seeded_fixtures["dave"]
    bob = seeded_fixtures["bob"]
    zone_lab = seeded_fixtures["zone_lab"]

    # Dave (admin) submits a proposal to add a new server
    proposal_payload = {
        "resource_type": "asset",
        "change_payload": {
            "name": "ledger-db-01.lab",
            "environment": "lab",
            "team": "payments",
            "zone_id": zone_lab.id,
            "host": "10.0.1.60",
            "port": 22,
        },
        "reason": "Onboard new payments ledger database",
        "expected_version": 1,
    }

    create_resp = client.post(
        "/api/v1/admin/change-proposals",
        json=proposal_payload,
        headers=auth_headers(dave.id, dave.email),
    )
    assert create_resp.status_code == 201
    proposal_id = create_resp.json()["proposal_id"]

    # 1. Self-review attempt: Dave tries to approve his own proposal
    self_review_resp = client.post(
        f"/api/v1/admin/change-proposals/{proposal_id}/decisions",
        json={"decision": "applied"},
        headers=auth_headers(dave.id, dave.email),
    )
    assert self_review_resp.status_code == 403
    assert self_review_resp.json()["code"] == "SELF_REVIEW_DENIED"

    # 2. Unauthorized non-admin/reviewer (Bob is only team approver, not admin)
    unauth_resp = client.post(
        f"/api/v1/admin/change-proposals/{proposal_id}/decisions",
        json={"decision": "applied"},
        headers=auth_headers(bob.id, bob.email),
    )
    assert unauth_resp.status_code == 403
    assert unauth_resp.json()["code"] == "NOT_PERMITTED"

    # Add a second admin for independent review
    # Seed user 'frank' with admin role
    admin_token_headers = auth_headers("usr_frank_admin", "frank@example.com")

    # Let's seed Frank into db_session via client synthetic login or direct fixture
    from ariba_pam.db.models import User, RoleAssignment
    from tests.conftest import TestingSessionLocal
    with TestingSessionLocal() as s:
        frank = User(
            id="usr_frank_admin",
            email="frank@example.com",
            full_name="Frank Independent Admin",
            idp_issuer="https://idp.lab.ariba.internal",
            idp_subject="sub_frank_admin",
            is_active=True,
        )
        s.add(frank)
        s.flush()
        s.add(
            RoleAssignment(
                id="ras_frank_admin",
                user_id=frank.id,
                role_id="rol_admin",
                scope_type="global",
                scope_value="*",
            )
        )
        s.commit()

    # 3. Frank (independent admin) reviews and applies
    apply_resp = client.post(
        f"/api/v1/admin/change-proposals/{proposal_id}/decisions",
        json={"decision": "applied"},
        headers=admin_token_headers,
    )
    assert apply_resp.status_code == 200
    assert apply_resp.json()["status"] == "applied"
    assert apply_resp.json()["reviewer_id"] == "usr_frank_admin"

    # 4. Attempting to decide on an already applied proposal fails with 409 Conflict (Stale version)
    stale_resp = client.post(
        f"/api/v1/admin/change-proposals/{proposal_id}/decisions",
        json={"decision": "rejected", "reason": "Too late"},
        headers=admin_token_headers,
    )
    assert stale_resp.status_code == 409
    assert stale_resp.json()["code"] == "STALE_PROPOSAL"
