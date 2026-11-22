"""Tests for IdP account disablement propagation and session termination reconciliation (P3-06, P3-07, P3-08, T-01)."""

from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from ariba_pam.db.models import (
    User, Role, RoleAssignment, GatewayZone, Asset, TargetAccount,
    AccessGrant, AccessSession, SessionLaunch, RequestRevision, AccessRequest
)
from ariba_pam.core.security import create_session_token


def test_idp_disablement_revokes_grants_and_terminates_sessions(client: TestClient, db_session: Session):
    # 1. Setup User and Role
    user = User(
        id="usr_pilot_target",
        email="operator_target@example.com",
        full_name="Target Operator",
        idp_issuer="https://idp.pilot.example.com",
        idp_subject="sub_target_operator",
        is_active=True,
    )
    role = Role(id="role_engineer", name="engineer", description="Engineer")
    zone = GatewayZone(id="zone_lab", name="Lab Zone")
    asset = Asset(
        id="ast_server_1",
        name="Server 1",
        environment="lab",
        team="platform",
        host="10.0.0.5",
        port=22,
        zone=zone,
        host_trust_ref="trust_1",
    )
    account = TargetAccount(id="acc_root", asset=asset, username="root")

    db_session.add_all([user, role, zone, asset, account])
    db_session.flush()

    role_assign = RoleAssignment(user=user, role=role, scope_type="global", scope_value="*")
    db_session.add(role_assign)

    req = AccessRequest(id="req_test_idp", requester=user)
    rev = RequestRevision(
        id="rev_test_idp",
        request=req,
        revision_number=1,
        asset=asset,
        target_account=account,
        requested_start_at=datetime.now(timezone.utc),
        requested_end_at=datetime.now(timezone.utc) + timedelta(hours=1),
        justification="Lab debugging",
        policy_version_id="pol_1",
    )
    grant = AccessGrant(
        id="grn_test_idp",
        revision=rev,
        requester=user,
        asset=asset,
        target_account=account,
        effective_start_at=datetime.now(timezone.utc),
        effective_end_at=datetime.now(timezone.utc) + timedelta(hours=1),
        status="active",
    )
    launch = SessionLaunch(
        id="lnc_test_idp",
        grant=grant,
        launch_token_digest="digest_dummy",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        is_consumed=True,
        consumed_by_gateway_id="gw_zone_lab",
    )
    session = AccessSession(
        id="ses_test_idp",
        grant=grant,
        launch=launch,
        gateway_id="gw_zone_lab",
        status="active",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add_all([req, rev, grant, launch, session])
    db_session.commit()

    token = create_session_token(user_id=user.id, email=user.email, auth_methods=["pwd", "fido2"])

    # Verify session is visible and active
    resp = client.get("/api/v1/sessions/ses_test_idp", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # 2. Ingest IdP account disablement signal
    idp_payload = {
        "event_id": "evt_idp_disable_001",
        "event_type": "user.disabled",
        "idp_issuer": "https://idp.pilot.example.com",
        "idp_subject": "sub_target_operator",
        "email": "operator_target@example.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    idp_resp = client.post("/api/v1/auth/idp-events", json=idp_payload)
    assert idp_resp.status_code == 200
    data = idp_resp.json()
    assert data["status"] == "processed"
    assert data["is_active"] is False
    assert data["revoked_grants_count"] == 1
    assert data["terminating_sessions_count"] == 1

    # 3. Verify user is now rejected at authentication endpoints
    me_resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 401
    assert me_resp.json()["code"] == "ACCOUNT_DISABLED"

    # 4. Verify gateway renewal immediately fails and returns conflict to close SSH session
    from ariba_pam.config import settings
    gw_renew_resp = client.post(
        "/internal/v1/sessions/ses_test_idp/renew",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert gw_renew_resp.status_code == 409
    assert gw_renew_resp.json()["code"] == "SESSION_TERMINATING"

    # 5. Gateway delivers termination confirmation
    gw_event_resp = client.post(
        "/internal/v1/sessions/ses_test_idp/events",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
        json={"state": "ended", "reason": "IdP account disabled"},
    )
    assert gw_event_resp.status_code == 202
    assert gw_event_resp.json()["status"] == "ended"

    # 6. Verify late event cannot reopen ended session
    gw_late_event = client.post(
        "/internal/v1/sessions/ses_test_idp/events",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
        json={"state": "active", "reason": "delayed packet"},
    )
    assert gw_late_event.status_code == 202
    assert gw_late_event.json()["status"] == "ended"


def test_idp_event_deduplication(client: TestClient, db_session: Session):
    user = User(
        id="usr_dedup_test",
        email="dedup@example.com",
        full_name="Dedup User",
        idp_issuer="https://idp.pilot.example.com",
        idp_subject="sub_dedup_001",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    payload = {
        "event_id": "evt_dedup_999",
        "event_type": "user.disabled",
        "idp_issuer": "https://idp.pilot.example.com",
        "idp_subject": "sub_dedup_001",
        "email": "dedup@example.com",
    }

    # First call
    r1 = client.post("/api/v1/auth/idp-events", json=payload)
    assert r1.status_code == 200
    assert r1.json()["status"] == "processed"

    # Replay identical event
    r2 = client.post("/api/v1/auth/idp-events", json=payload)
    assert r2.status_code == 200
    assert r2.json() == r1.json()

    # Conflicting payload under same event ID -> 409
    conflict_payload = dict(payload)
    conflict_payload["email"] = "other@example.com"
    r3 = client.post("/api/v1/auth/idp-events", json=conflict_payload)
    assert r3.status_code == 409
    assert r3.json()["code"] == "IDEMPOTENCY_CONFLICT"
