"""RDP Gateway Policy and Windows Infrastructure Integration Tests (P6-01, P6-02, ADR-012).

Verifies:
1. RDP Protocol Support & Scoped Discovery: Windows assets with protocol="rdp" on port 3389.
2. Anti-Enumeration Concealment: Out-of-scope RDP assets return HTTP 404.
3. RDP Security Policy: Enforces default-deny for clipboard and drive redirection.
4. JIT Credential Injection: RDP tunnel parameters incorporate decrypted vault secrets.
5. Protocol Validation: SSH assets reject RDP tunnel parameter compilation (fail-closed).
6. Post-Session Invalidation: Terminating an RDP session triggers automated credential rotation.
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
    VaultSecretStore,
    AccessPolicyVersion,
    AdminChangeProposal,
    AuditOutbox,
)
from ariba_pam.services.vault import VaultCredentialService
from ariba_pam.services.rdp import RDPGatewayService, RDPSecurityPolicy
from ariba_pam.core.security import decrypt_vault_payload
from tests.conftest import auth_headers


def _assign_role(db: Session, user: User, role_name: str, scope_type: str = "global", scope_value: str = "*"):
    """Helper to assign a role to a test user."""
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        role = Role(id=f"rol_{role_name}", name=role_name, description=f"{role_name} role")
        db.add(role)
        db.flush()

    assignment = RoleAssignment(
        id=generate_id("ras"),
        user_id=user.id,
        role_id=role.id,
        scope_type=scope_type,
        scope_value=scope_value,
    )
    db.add(assignment)
    db.commit()


def test_rdp_asset_onboarding_and_scoped_discovery(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    FR-02, P6-01: Maintain scoped Windows infrastructure assets with protocol='rdp'.
    Conceals out-of-scope Windows assets with HTTP 404.
    """
    zone = seeded_fixtures["zone_lab"]
    alice_requester = seeded_fixtures["alice"]  # scoped to payments
    charlie_approver = seeded_fixtures["charlie"]  # scoped to analytics

    # Onboard Windows Domain Controller into payments team
    win_dc = Asset(
        id="ast_win_dc01",
        name="win-dc01.corp",
        environment="lab",
        team="payments",
        zone_id=zone.id,
        host="10.0.1.200",
        port=3389,
        protocol="rdp",
        host_trust_ref="SHA256:win_dc_cert_thumbprint",
        is_active=True,
    )
    db_session.add(win_dc)
    db_session.commit()

    # 1. Alice (payments scope) queries assets -> sees Windows DC with protocol='rdp'
    resp = client.get("/api/v1/assets", headers=auth_headers(alice_requester.id, alice_requester.email))
    assert resp.status_code == 200
    assets = resp.json()
    win_asset = next((a for a in assets if a["id"] == win_dc.id), None)
    assert win_asset is not None
    assert win_asset["port"] == 3389

    # 2. Charlie (analytics scope) queries Windows DC directly -> 404 ASSET_NOT_FOUND
    resp = client.get(f"/api/v1/assets/{win_dc.id}", headers=auth_headers(charlie_approver.id, charlie_approver.email))
    assert resp.status_code == 404
    assert resp.json()["code"] == "ASSET_NOT_FOUND"


def test_rdp_security_policy_enforcement_default_deny(seeded_fixtures: dict, db_session: Session):
    """
    ADR-012, P6-01: Default-deny RDP security policy.
    Clipboard, drive redirection, audio, and printing must be disabled by default.
    """
    zone = seeded_fixtures["zone_lab"]
    win_asset = Asset(
        id=generate_id("ast"),
        name="win-fs01.corp",
        environment="lab",
        team="payments",
        zone_id=zone.id,
        host="10.0.1.201",
        port=3389,
        protocol="rdp",
        is_active=True,
    )
    db_session.add(win_asset)
    db_session.commit()

    policy = RDPGatewayService.get_effective_policy(db_session, win_asset)
    assert policy.disable_clipboard is True
    assert policy.disable_drive_redirection is True
    assert policy.disable_audio is True
    assert policy.disable_printing is True
    assert policy.enable_recording is True
    assert policy.security_mode == "nla"


def test_rdp_policy_override_via_published_policy(seeded_fixtures: dict, db_session: Session):
    """
    P6-01: Asset policy versions can configure explicit RDP restrictions.
    """
    zone = seeded_fixtures["zone_lab"]
    dave_admin = seeded_fixtures["dave"]

    win_asset = Asset(
        id=generate_id("ast"),
        name="win-app01.corp",
        environment="lab",
        team="payments",
        zone_id=zone.id,
        host="10.0.1.202",
        port=3389,
        protocol="rdp",
        is_active=True,
    )
    db_session.add(win_asset)
    db_session.flush()

    proposal = AdminChangeProposal(
        id=generate_id("prp"),
        resource_type="policy",
        resource_id=win_asset.id,
        change_payload={"rdp": {"disable_clipboard": False, "enable_recording": True}},
        expected_version=1,
        author_id=dave_admin.id,
        status="applied",
    )
    db_session.add(proposal)
    db_session.flush()

    policy_ver = AccessPolicyVersion(
        id=generate_id("pol"),
        asset_id=win_asset.id,
        version=1,
        rules={"rdp": {"disable_clipboard": False, "enable_recording": True}},
        proposal_id=proposal.id,
    )
    db_session.add(policy_ver)
    db_session.commit()

    policy = RDPGatewayService.get_effective_policy(db_session, win_asset)
    assert policy.disable_clipboard is False  # Explicitly permitted by published policy
    assert policy.disable_drive_redirection is True  # Unspecified remains default deny


def test_rdp_tunnel_parameters_compilation_with_vault_credentials(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    FR-06, ADR-012: Compile RDP gateway tunnel parameters with injected vault secrets.
    """
    zone = seeded_fixtures["zone_lab"]
    bob_requester = seeded_fixtures["bob"]

    win_asset = Asset(
        id=generate_id("ast"),
        name="win-sql01.corp",
        environment="lab",
        team="payments",
        zone_id=zone.id,
        host="10.0.1.205",
        port=3389,
        protocol="rdp",
        is_active=True,
    )
    db_session.add(win_asset)
    db_session.flush()

    win_account = TargetAccount(
        id=generate_id("act"),
        asset_id=win_asset.id,
        username="sql_admin",
        is_active=True,
        credential_type="vault_secret",
        auto_rotate_on_session_end=True,
    )
    db_session.add(win_account)
    db_session.flush()

    VaultCredentialService.store_target_credential(
        db=db_session,
        account_id=win_account.id,
        secret_value="WindowsComplexSecret#2026",
        secret_type="password",
    )
    db_session.commit()

    now = utc_now()
    grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=bob_requester.id,
        asset_id=win_asset.id,
        target_account_id=win_account.id,
        status="active",
        effective_start_at=now - timedelta(minutes=5),
        effective_end_at=now + timedelta(minutes=55),
    )
    db_session.add(grant)
    db_session.flush()

    session = AccessSession(
        id=generate_id("ses"),
        grant_id=grant.id,
        launch_id=generate_id("lnc"),
        gateway_id="gw_zone_lab_01",
        status="active",
        started_at=now,
    )
    db_session.add(session)
    db_session.commit()

    # Gateway requests compiled RDP tunnel parameters
    resp = client.post(
        "/internal/v1/rdp/tunnel-parameters",
        json={"grant_id": grant.id, "session_id": session.id},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert resp.status_code == 200
    params = resp.json()
    assert params["protocol"] == "rdp"
    assert params["hostname"] == "10.0.1.205"
    assert params["port"] == 3389
    assert params["username"] == "sql_admin"
    assert params["password"] == "WindowsComplexSecret#2026"
    assert params["security"] == "nla"
    assert params["disable_clipboard"] is True
    assert params["disable_drive_redirection"] is True
    assert params["enable_recording"] is True


def test_rdp_tunnel_parameters_rejected_on_ssh_asset(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Fail-closed: Compiling RDP parameters for an SSH asset must be rejected.
    """
    ssh_asset = seeded_fixtures["asset_payment"]  # protocol="ssh"
    account = seeded_fixtures["acc_pay_admin"]
    bob_requester = seeded_fixtures["bob"]

    now = utc_now()
    grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=bob_requester.id,
        asset_id=ssh_asset.id,
        target_account_id=account.id,
        status="active",
        effective_start_at=now - timedelta(minutes=5),
        effective_end_at=now + timedelta(minutes=55),
    )
    db_session.add(grant)
    db_session.flush()

    session = AccessSession(
        id=generate_id("ses"),
        grant_id=grant.id,
        launch_id=generate_id("lnc"),
        gateway_id="gw_zone_lab_01",
        status="active",
        started_at=now,
    )
    db_session.add(session)
    db_session.commit()

    resp = client.post(
        "/internal/v1/rdp/tunnel-parameters",
        json={"grant_id": grant.id, "session_id": session.id},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "NOT_RDP_ASSET"


def test_rdp_post_session_vault_rotation(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    FR-06, SEC-05: Closing an RDP session triggers automated password rotation.
    """
    zone = seeded_fixtures["zone_lab"]
    bob_requester = seeded_fixtures["bob"]

    win_asset = Asset(
        id=generate_id("ast"),
        name="win-iis01.corp",
        environment="lab",
        team="payments",
        zone_id=zone.id,
        host="10.0.1.206",
        port=3389,
        protocol="rdp",
        is_active=True,
    )
    db_session.add(win_asset)
    db_session.flush()

    win_account = TargetAccount(
        id=generate_id("act"),
        asset_id=win_asset.id,
        username="web_admin",
        is_active=True,
        credential_type="vault_secret",
        auto_rotate_on_session_end=True,
    )
    db_session.add(win_account)
    db_session.flush()

    initial_password = "WinPasswordPreRDP#01"
    VaultCredentialService.store_target_credential(
        db=db_session,
        account_id=win_account.id,
        secret_value=initial_password,
        secret_type="password",
    )
    db_session.commit()

    now = utc_now()
    grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=bob_requester.id,
        asset_id=win_asset.id,
        target_account_id=win_account.id,
        status="active",
        effective_start_at=now - timedelta(minutes=5),
        effective_end_at=now + timedelta(minutes=55),
    )
    db_session.add(grant)
    db_session.flush()

    session = AccessSession(
        id=generate_id("ses"),
        grant_id=grant.id,
        launch_id=generate_id("lnc"),
        gateway_id="gw_zone_lab_01",
        status="active",
        started_at=now,
    )
    db_session.add(session)
    db_session.commit()

    # Gateway delivers session 'ended' event
    resp = client.post(
        f"/internal/v1/sessions/{session.id}/events",
        json={"state": "ended", "reason": "RDP connection closed by user"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert resp.status_code == 202

    # Verify password rotated in Vault
    db_session.expire_all()
    vault_rec = db_session.query(VaultSecretStore).filter(VaultSecretStore.account_id == win_account.id).first()
    assert vault_rec.key_version == 2
    new_password = decrypt_vault_payload(vault_rec.encrypted_payload)
    assert new_password != initial_password
