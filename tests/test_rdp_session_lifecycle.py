"""RDP Authorization, Scoped Access, Revocation, and Evidence Validation Tests (P6-02, ADR-012).

Verifies the complete RDP lab milestone:
1. Scoped Access & Anti-Enumeration Concealment:
   - Requester in scope can request and launch RDP sessions.
   - Out-of-scope operators/users receive HTTP 404 Not Found on assets, requests, grants, and sessions.
   - Cross-tenant / unauthorized launch attempts fail-closed.
2. Operator Revocation & Confirmed Termination (< 60s):
   - Operator revokes grant or terminates session.
   - Gateway lease renewal is rejected with 409 Conflict.
   - Gateway terminates RDP stream and confirms termination to control plane.
   - Confirmed termination verified within 60s latency budget.
   - Target Windows account vault credential automatically rotates on session end.
3. Recording Failure Handling:
   - Stream/frame capture loss triggers fail-closed session termination at gateway.
   - Gateway reports coverage gap ("gap") to control plane.
   - Control plane logs CRITICAL CAPTURE_FAILURE SOC alert and rotates target credential.
"""

from datetime import timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from ariba_pam.config import settings
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.db.models import (
    User,
    Role,
    RoleAssignment,
    Asset,
    TargetAccount,
    AccessGrant,
    AccessSession,
    SessionLaunch,
    SessionRecording,
    SOCAlert,
    AuditOutbox,
    AccessRequest,
    RequestRevision,
    ApprovalStep,
    ApprovalDecision,
    AccessPolicyVersion,
    VaultSecretStore,
)
from ariba_pam.services.vault import VaultCredentialService
from ariba_pam.services.rdp import RDPGatewayService
from ariba_pam.core.security import decrypt_vault_payload
from tests.conftest import auth_headers


def _setup_rdp_test_environment(db: Session, fixtures: dict):
    """Setup a dedicated Windows RDP asset, vault target account, and stored credential."""
    zone = fixtures["zone_lab"]
    alice = fixtures["alice"]
    bob = fixtures["bob"]
    charlie = fixtures["charlie"]
    dave = fixtures["dave"]

    # 1. Assign operator role to Dave globally
    operator_role = db.query(Role).filter(Role.name == "operator").first()
    if not operator_role:
        operator_role = Role(id="rol_operator", name="operator", description="Operator role")
        db.add(operator_role)
        db.flush()

    dave_operator = RoleAssignment(
        id=generate_id("ras"),
        user_id=dave.id,
        role_id=operator_role.id,
        scope_type="global",
        scope_value="*",
    )
    db.add(dave_operator)

    # 2. Create RDP Asset scoped to payments team
    win_asset = Asset(
        id=generate_id("ast"),
        name="windows-prod-dc01",
        environment="lab",
        team="payments",
        host="10.0.2.150",
        port=3389,
        protocol="rdp",
        zone_id=zone.id,
        is_active=True,
    )
    db.add(win_asset)
    db.flush()

    # 3. Target Account with vault_secret credential type and auto-rotation
    win_account = TargetAccount(
        id=generate_id("act"),
        asset_id=win_asset.id,
        username="DomainAdmin",
        credential_type="vault_secret",
        vault_secret_path="/secret/data/pam/windows-prod-dc01/DomainAdmin",
        auto_rotate_on_session_end=True,
        rotation_status="initialized",
        is_active=True,
    )
    db.add(win_account)
    db.flush()

    # 4. Store initial vault password
    VaultCredentialService.store_target_credential(
        db=db,
        account_id=win_account.id,
        secret_value="InitialP@ssword2026!WinServer",
        actor_id=dave.id,
    )

    # 5. Create reviewed access policy authorizing the target account
    policy = AccessPolicyVersion(
        id=generate_id("pol"),
        asset_id=win_asset.id,
        version=1,
        rules={
            "allowed_target_account_ids": [win_account.id],
            "max_duration_seconds": 7200,
            "required_approvals": 1,
            "requires_ticket": False,
        },
        proposal_id="prp_initial_windows",
    )
    db.add(policy)
    db.commit()

    return {
        "alice": alice,
        "bob": bob,
        "charlie": charlie,
        "dave": dave,
        "win_asset": win_asset,
        "win_account": win_account,
        "zone": zone,
        "policy": policy,
    }


def _create_approved_rdp_grant(db: Session, env: dict) -> AccessGrant:
    """Helper to create an approved AccessGrant for Alice targeting the Windows RDP asset."""
    alice = env["alice"]
    bob = env["bob"]
    win_asset = env["win_asset"]
    win_account = env["win_account"]
    policy = env["policy"]

    now = utc_now()

    # Create Request
    req = AccessRequest(
        id=generate_id("req"),
        requester_id=alice.id,
        status="approved",
    )
    db.add(req)
    db.flush()

    # Revision
    rev = RequestRevision(
        id=generate_id("rev"),
        request_id=req.id,
        revision_number=1,
        asset_id=win_asset.id,
        target_account_id=win_account.id,
        requested_start_at=now - timedelta(minutes=5),
        requested_end_at=now + timedelta(minutes=55),
        justification="Emergency maintenance on Windows Domain Controller",
        policy_version_id=policy.id,
        is_frozen=True,
    )
    db.add(rev)
    db.flush()

    # Approval Step & Decision
    step = ApprovalStep(
        id=generate_id("stp"),
        revision_id=rev.id,
        step_order=1,
        status="approved",
        required_role="approver",
    )
    db.add(step)
    db.flush()

    decision = ApprovalDecision(
        id=generate_id("dcs"),
        step_id=step.id,
        approver_id=bob.id,
        decision="approved",
        reason="Verified change window ticket",
    )
    db.add(decision)
    db.flush()

    # Active Grant
    grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=rev.id,
        requester_id=alice.id,
        asset_id=win_asset.id,
        target_account_id=win_account.id,
        status="active",
        effective_start_at=now - timedelta(minutes=5),
        effective_end_at=now + timedelta(minutes=55),
    )
    db.add(grant)
    db.commit()
    return grant


def test_scoped_rdp_access_authorization_and_anti_enumeration(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    P6-02: Demonstrate scoped access and anti-enumeration concealment:
    - In-scope requester launches RDP session and gateway compiles tunnel parameters.
    - Out-of-scope user (Charlie) querying asset, grant, or session receives HTTP 404 Not Found.
    - Gateway injects vault password and enforces default-deny clipboard/drive redirection.
    """
    env = _setup_rdp_test_environment(db_session, seeded_fixtures)
    grant = _create_approved_rdp_grant(db_session, env)
    alice = env["alice"]
    charlie = env["charlie"]
    win_asset = env["win_asset"]

    # 1. Anti-enumeration: Charlie (scoped to /analytics) queries Alice's grant -> returns 404
    resp = client.get(f"/api/v1/grants/{grant.id}", headers=auth_headers(charlie.id, charlie.email))
    assert resp.status_code == 404, f"Expected 404 concealment, got {resp.status_code}"

    # 2. Charlie attempts to request launch token on Alice's grant -> returns 403 / 404
    resp = client.post(f"/api/v1/grants/{grant.id}/launches", headers=auth_headers(charlie.id, charlie.email))
    assert resp.status_code in (403, 404)

    # 3. Alice (owner) generates launch token
    resp = client.post(f"/api/v1/grants/{grant.id}/launches", headers=auth_headers(alice.id, alice.email))
    assert resp.status_code == 201
    launch_token = resp.json()["launch_token"]
    assert launch_token.startswith("launch_")

    # 4. Gateway consumes launch token
    resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_lab_windows_01"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert resp.status_code == 201
    session_data = resp.json()
    session_id = session_data["session_id"]
    assert session_data["credential_type"] == "vault_secret"
    assert session_data["target_port"] == 3389

    # 5. Gateway compiles RDP tunnel parameters
    resp = client.post(
        "/internal/v1/rdp/tunnel-parameters",
        json={"grant_id": grant.id, "session_id": session_id},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert resp.status_code == 200
    tunnel_params = resp.json()
    assert tunnel_params["protocol"] == "rdp"
    assert tunnel_params["security"] == "nla"
    assert tunnel_params["username"] == "DomainAdmin"
    assert tunnel_params["password"] == "InitialP@ssword2026!WinServer"
    assert tunnel_params["disable_clipboard"] is True
    assert tunnel_params["disable_drive_redirection"] is True
    assert tunnel_params["disable_audio"] is True
    assert tunnel_params["disable_printing"] is True
    assert "tunnel_token" in tunnel_params

    # 6. Verify audit outbox captured tunnel compilation
    outbox = (
        db_session.query(AuditOutbox)
        .filter(AuditOutbox.event_type == "RDP_TUNNEL_COMPILED")
        .first()
    )
    assert outbox is not None
    assert outbox.payload["session_id"] == session_id
    assert outbox.payload["clipboard_disabled"] is True
    assert outbox.payload["drive_redirection_disabled"] is True


def test_operator_revocation_and_confirmed_termination_within_budget(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    P6-02: Demonstrate operator revocation and confirmed termination within 60s:
    - Operator revokes grant during active RDP session.
    - Gateway renewal rejected with 409 Conflict.
    - Gateway delivers session closure event.
    - Confirmed termination verified (< 60s latency).
    - Windows target credential automatically rotated.
    """
    env = _setup_rdp_test_environment(db_session, seeded_fixtures)
    grant = _create_approved_rdp_grant(db_session, env)
    alice = env["alice"]
    dave = env["dave"]
    win_account = env["win_account"]

    # 1. Launch active session
    resp = client.post(f"/api/v1/grants/{grant.id}/launches", headers=auth_headers(alice.id, alice.email))
    launch_token = resp.json()["launch_token"]

    resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_lab_windows_01"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    session_id = resp.json()["session_id"]

    # Session is active
    session = db_session.get(AccessSession, session_id)
    assert session.status == "active"

    # 2. Operator Dave revokes the grant
    revocation_payload = {"reason": "Security Alert: Suspicious lateral movement detected on workstation"}
    revoke_resp = client.post(
        f"/api/v1/grants/{grant.id}/revoke",
        json=revocation_payload,
        headers=auth_headers(dave.id, dave.email),
    )
    assert revoke_resp.status_code == 202
    assert revoke_resp.json()["status"] == "revoked"

    # Refresh DB session state
    db_session.expire_all()
    grant_after_revoke = db_session.get(AccessGrant, grant.id)
    session_after_revoke = db_session.get(AccessSession, session_id)
    assert grant_after_revoke.status == "revoked"
    assert session_after_revoke.status == "terminating"

    # 3. Gateway attempts lease renewal -> rejected with 409 Conflict
    renew_resp = client.post(
        f"/internal/v1/sessions/{session_id}/renew",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert renew_resp.status_code == 409
    assert "SESSION_TERMINATING" in renew_resp.text

    # 4. Gateway closes connection and delivers confirmation event to Control Plane
    closure_event = {
        "state": "ended",
        "reason": "Lease renewal failure or grant revocation",
        "recording": {
            "digest_sha256": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
            "size_bytes": 40960,
            "duration_seconds": 12,
            "coverage_status": "complete",
        },
    }
    event_resp = client.post(
        f"/internal/v1/sessions/{session_id}/events",
        json=closure_event,
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert event_resp.status_code == 202

    # 5. Verify confirmed termination in database
    db_session.expire_all()
    final_session = db_session.get(AccessSession, session_id)
    assert final_session.status == "ended"
    assert final_session.ended_at is not None
    assert final_session.termination_reason == "Lease renewal failure or grant revocation"

    # Confirmed termination latency budget (< 60 seconds)
    duration = (final_session.ended_at - grant_after_revoke.revoked_at).total_seconds()
    assert duration < 60, f"Expected termination in <60s, took {duration}s"

    # 6. Verify automated post-session credential rotation for Windows account
    db_session.refresh(win_account)
    assert win_account.rotation_status == "active"
    assert win_account.last_rotated_at is not None

    vault_entry = db_session.query(VaultSecretStore).filter(VaultSecretStore.account_id == win_account.id).first()
    assert vault_entry.key_version == 2
    new_password = decrypt_vault_payload(vault_entry.encrypted_payload)
    assert new_password != "InitialP@ssword2026!WinServer"
    assert len(new_password) == 32

    # Verify audit trail for rotation
    rotation_audit = (
        db_session.query(AuditOutbox)
        .filter(AuditOutbox.event_type == "vault_secret.rotated")
        .first()
    )
    assert rotation_audit is not None
    assert rotation_audit.payload["account_id"] == win_account.id
    assert rotation_audit.payload["trigger_reason"] == "session_ended"


def test_operator_session_termination_and_scoped_visibility(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    P6-02: Demonstrate operator session termination and anti-enumeration:
    - In-scope operator can view and terminate session.
    - Out-of-scope operator/user receives 404 on session query.
    """
    env = _setup_rdp_test_environment(db_session, seeded_fixtures)
    grant = _create_approved_rdp_grant(db_session, env)
    alice = env["alice"]
    charlie = env["charlie"]
    dave = env["dave"]

    resp = client.post(f"/api/v1/grants/{grant.id}/launches", headers=auth_headers(alice.id, alice.email))
    launch_token = resp.json()["launch_token"]

    resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_lab_windows_01"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    session_id = resp.json()["session_id"]

    # 1. Charlie (out of scope) queries session -> 404
    resp = client.get(f"/api/v1/sessions/{session_id}", headers=auth_headers(charlie.id, charlie.email))
    assert resp.status_code == 404

    # 2. Dave (operator in scope) queries session -> 200
    resp = client.get(f"/api/v1/sessions/{session_id}", headers=auth_headers(dave.id, dave.email))
    assert resp.status_code == 200
    assert resp.json()["session_id"] == session_id
    assert resp.json()["status"] == "active"

    # 3. Dave terminates session directly
    resp = client.post(
        f"/api/v1/sessions/{session_id}/terminate",
        headers=auth_headers(dave.id, dave.email),
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "terminating"

    # 4. Gateway renewal returns 409
    renew_resp = client.post(
        f"/internal/v1/sessions/{session_id}/renew",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert renew_resp.status_code == 409


def test_rdp_recording_failure_fail_closed_handling(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    P6-02: Demonstrate recording failure handling:
    - Gateway encounters visual recording pipeline failure.
    - Gateway terminates fail-closed and reports coverage_status: "gap".
    - Control plane records CAPTURE_FAILURE critical SOC alert.
    - Target Windows credentials automatically rotated to prevent unrecorded access.
    """
    env = _setup_rdp_test_environment(db_session, seeded_fixtures)
    grant = _create_approved_rdp_grant(db_session, env)
    alice = env["alice"]
    win_account = env["win_account"]

    resp = client.post(f"/api/v1/grants/{grant.id}/launches", headers=auth_headers(alice.id, alice.email))
    launch_token = resp.json()["launch_token"]

    resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_lab_windows_01"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    session_id = resp.json()["session_id"]

    # Gateway reports recording capture failure
    failure_payload = {
        "state": "ended",
        "reason": "RDP recording failure: evidence pipeline stalled",
        "recording": {
            "digest_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "size_bytes": 1024,
            "duration_seconds": 15,
            "coverage_status": "gap",
        },
    }
    resp = client.post(
        f"/internal/v1/sessions/{session_id}/events",
        json=failure_payload,
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert resp.status_code == 202

    # Verify SessionRecording stored with coverage gap
    rec = db_session.query(SessionRecording).filter(SessionRecording.session_id == session_id).first()
    assert rec is not None
    assert rec.coverage_status == "gap"

    # Verify CRITICAL SOC alert logged
    alert = (
        db_session.query(SOCAlert)
        .filter(SOCAlert.alert_type == "CAPTURE_FAILURE", SOCAlert.session_id == session_id)
        .first()
    )
    assert alert is not None
    assert alert.severity == "CRITICAL"
    assert "coverage gap" in alert.title.lower() or "gap" in alert.description.lower()

    # Verify Windows target account password was automatically rotated
    db_session.refresh(win_account)
    assert win_account.rotation_status == "active"
    assert win_account.last_rotated_at is not None


def test_rdp_expired_grant_fails_closed_and_auto_rotates(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    P6-02: Demonstrate expired grant window fails closed:
    - Grant passes effective_end_at.
    - Gateway renew attempt rejected with 409 GRANT_EXPIRED.
    - Session terminated and target credential rotated.
    """
    env = _setup_rdp_test_environment(db_session, seeded_fixtures)
    grant = _create_approved_rdp_grant(db_session, env)
    alice = env["alice"]
    win_account = env["win_account"]

    # Launch active session
    resp = client.post(f"/api/v1/grants/{grant.id}/launches", headers=auth_headers(alice.id, alice.email))
    launch_token = resp.json()["launch_token"]

    resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_lab_windows_01"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    session_id = resp.json()["session_id"]

    # Fast-forward grant expiry into the past
    grant.effective_end_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    # Gateway attempts renewal -> rejected with 409 GRANT_EXPIRED
    renew_resp = client.post(
        f"/internal/v1/sessions/{session_id}/renew",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert renew_resp.status_code == 409
    assert "GRANT_EXPIRED" in renew_resp.text

    # Verify session marked ended in db
    db_session.expire_all()
    session = db_session.get(AccessSession, session_id)
    assert session.status == "ended"
    assert session.termination_reason == "Grant window expired"

    # Gateway reports final ended event
    event_resp = client.post(
        f"/internal/v1/sessions/{session_id}/events",
        json={"state": "ended", "reason": "Grant window expired"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert event_resp.status_code == 202

    # Verify Windows target account password was automatically rotated
    db_session.refresh(win_account)
    assert win_account.rotation_status == "active"
    assert win_account.last_rotated_at is not None

