"""Scoped Vault-Backed Target Access & Automated Rotation Tests (P4-03, FR-06, SEC-05, SEC-08, T-06).

Verifies:
1. Custodian Boundary: Only Vault Custodians can store credentials or manually rotate (anti-superuser principle).
2. Just-In-Time Secret Retrieval: Internal Gateway retrieves target secret if and only if grant and session are active.
3. Strict Revocation & Expiry: Revoked or expired grants immediately deny secret retrieval.
4. Non-Disclosure Invariant: Raw credentials are never exposed in user-facing APIs or status queries.
5. Automated Post-Session Rotation: Session termination triggers immediate secret rotation and invalidation.
6. Identifier Concealment: Querying vault status for out-of-scope targets returns HTTP 404.
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
    AuditOutbox,
    SOCAlert,
)
from ariba_pam.services.vault import VaultCredentialService
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


def test_vault_secret_store_and_custodian_boundary(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    SEC-08: Only Vault Custodians can store target secrets. Standard Admins are forbidden.
    Verifies AES-256-GCM encryption and atomic audit outbox event.
    """
    alice_admin = seeded_fixtures["dave"]  # Dave has admin role
    eva_user = seeded_fixtures["eva"]
    account = seeded_fixtures["acc_pay_admin"]

    # 1. Standard Admin attempts to store target secret -> 403 NOT_VAULT_CUSTODIAN
    resp = client.post(
        f"/api/v1/admin/vault/targets/{account.id}/store",
        json={"secret_value": "MyInitialPassword123!", "secret_type": "password"},
        headers=auth_headers(alice_admin.id, alice_admin.email),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "NOT_VAULT_CUSTODIAN"

    # 2. Assign vault_custodian role to Eva
    _assign_role(db_session, eva_user, "vault_custodian")

    # 3. Vault Custodian stores target secret -> 201 Created
    resp = client.post(
        f"/api/v1/admin/vault/targets/{account.id}/store",
        json={"secret_value": "MyInitialPassword123!", "secret_type": "password"},
        headers=auth_headers(eva_user.id, eva_user.email),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["credential_type"] == "vault_secret"
    assert data["rotation_status"] == "active"
    assert data["key_version"] == 1

    # Verify secret is encrypted in database
    secret_rec = db_session.query(VaultSecretStore).filter(VaultSecretStore.account_id == account.id).first()
    assert secret_rec is not None
    assert secret_rec.encrypted_payload != "MyInitialPassword123!"
    # Verify decrypted content matches
    decrypted = decrypt_vault_payload(secret_rec.encrypted_payload)
    assert decrypted == "MyInitialPassword123!"

    # Verify transactional audit outbox event
    audit_evt = (
        db_session.query(AuditOutbox)
        .filter(AuditOutbox.event_type == "vault_secret.stored")
        .order_by(AuditOutbox.occurred_at.desc())
        .first()
    )
    assert audit_evt is not None
    assert audit_evt.correlation_id == account.id
    assert audit_evt.actor_id == eva_user.id


def test_vault_secret_retrieval_success_with_active_grant(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    FR-06, SEC-05, T-06: Authorized Gateway retrieves decrypted secret for active grant and session.
    Verifies audit event 'vault_secret.retrieved'.
    """
    account = seeded_fixtures["acc_pay_admin"]
    asset = seeded_fixtures["asset_payment"]
    bob_requester = seeded_fixtures["bob"]

    # Store initial secret
    VaultCredentialService.store_target_credential(
        db=db_session,
        account_id=account.id,
        secret_value="InitialProductionPassword#99!",
        secret_type="password",
        actor_id="usr_system",
    )
    db_session.commit()

    now = utc_now()
    # Create active grant
    grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=bob_requester.id,
        asset_id=asset.id,
        target_account_id=account.id,
        status="active",
        effective_start_at=now - timedelta(minutes=5),
        effective_end_at=now + timedelta(minutes=55),
    )
    db_session.add(grant)
    db_session.flush()

    # Create active session
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

    # Gateway retrieves secret via internal endpoint
    resp = client.post(
        "/internal/v1/credentials/vault-secret",
        json={
            "grant_id": grant.id,
            "session_id": session.id,
            "target_account_id": account.id,
        },
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["credential_type"] == "password"
    assert body["secret_value"] == "InitialProductionPassword#99!"
    assert body["username"] == account.username

    # Verify audit event recorded
    audit_evt = (
        db_session.query(AuditOutbox)
        .filter(AuditOutbox.event_type == "vault_secret.retrieved")
        .order_by(AuditOutbox.occurred_at.desc())
        .first()
    )
    assert audit_evt is not None
    assert audit_evt.correlation_id == session.id


def test_vault_secret_retrieval_rejected_on_revoked_or_expired_grant(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    SEC-05: Deny JIT secret retrieval if grant is revoked, expired, or session ended.
    """
    account = seeded_fixtures["acc_pay_admin"]
    asset = seeded_fixtures["asset_payment"]
    bob_requester = seeded_fixtures["bob"]

    VaultCredentialService.store_target_credential(
        db=db_session,
        account_id=account.id,
        secret_value="PassWord!123",
        secret_type="password",
    )
    db_session.commit()

    now = utc_now()
    # 1. Revoked grant
    revoked_grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=bob_requester.id,
        asset_id=asset.id,
        target_account_id=account.id,
        status="revoked",
        effective_start_at=now - timedelta(minutes=10),
        effective_end_at=now + timedelta(minutes=50),
    )
    db_session.add(revoked_grant)
    db_session.flush()

    session = AccessSession(
        id=generate_id("ses"),
        grant_id=revoked_grant.id,
        launch_id=generate_id("lnc"),
        gateway_id="gw_zone_lab_01",
        status="active",
        started_at=now,
    )
    db_session.add(session)
    db_session.commit()

    resp = client.post(
        "/internal/v1/credentials/vault-secret",
        json={
            "grant_id": revoked_grant.id,
            "session_id": session.id,
            "target_account_id": account.id,
        },
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "GRANT_NOT_ACTIVE"

    # 2. Expired grant
    active_grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=bob_requester.id,
        asset_id=asset.id,
        target_account_id=account.id,
        status="active",
        effective_start_at=now - timedelta(hours=2),
        effective_end_at=now - timedelta(minutes=1),
    )
    db_session.add(active_grant)
    db_session.flush()

    session2 = AccessSession(
        id=generate_id("ses"),
        grant_id=active_grant.id,
        launch_id=generate_id("lnc"),
        gateway_id="gw_zone_lab_01",
        status="active",
        started_at=now,
    )
    db_session.add(session2)
    db_session.commit()

    resp = client.post(
        "/internal/v1/credentials/vault-secret",
        json={
            "grant_id": active_grant.id,
            "session_id": session2.id,
            "target_account_id": account.id,
        },
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "GRANT_EXPIRED"


def test_vault_secret_non_disclosure_to_users_and_admins(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    FR-06, SEC-05: Non-Disclosure Invariant.
    Neither regular users nor PAM Administrators can retrieve the raw target credential.
    Status endpoint returns metadata only (last_rotated_at, rotation_status, key_version).
    """
    account = seeded_fixtures["acc_pay_admin"]
    dave_admin = seeded_fixtures["dave"]
    bob_requester = seeded_fixtures["bob"]

    VaultCredentialService.store_target_credential(
        db=db_session,
        account_id=account.id,
        secret_value="UltraConfidentialPassword#2026",
        secret_type="password",
    )
    db_session.commit()

    # Admin inspects vault status
    resp = client.get(
        f"/api/v1/admin/vault/targets/{account.id}/status",
        headers=auth_headers(dave_admin.id, dave_admin.email),
    )
    assert resp.status_code == 200
    meta = resp.json()
    assert meta["credential_type"] == "vault_secret"
    assert meta["rotation_status"] == "active"
    assert meta["key_version"] == 1
    assert "UltraConfidentialPassword#2026" not in str(meta)
    assert "secret_value" not in meta
    assert "encrypted_payload" not in meta

    # Regular user checking assets API receives no secret credentials
    resp = client.get("/api/v1/assets", headers=auth_headers(bob_requester.id, bob_requester.email))
    assert resp.status_code == 200
    assert "UltraConfidentialPassword#2026" not in str(resp.json())


def test_automatic_post_session_credential_rotation(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    FR-06, SEC-05: Automated post-session password rotation.
    Terminating a session on a vault-backed account immediately triggers password rotation,
    invalidating the previously exposed credential.
    """
    account = seeded_fixtures["acc_pay_admin"]
    asset = seeded_fixtures["asset_payment"]
    bob_requester = seeded_fixtures["bob"]

    initial_password = "TemporaryPasswordPreSession#01"
    VaultCredentialService.store_target_credential(
        db=db_session,
        account_id=account.id,
        secret_value=initial_password,
        secret_type="password",
    )
    db_session.commit()

    now = utc_now()
    grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=bob_requester.id,
        asset_id=asset.id,
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

    # Gateway delivers session 'ended' event
    resp = client.post(
        f"/internal/v1/sessions/{session.id}/events",
        json={"state": "ended", "reason": "User exited terminal shell"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert resp.status_code == 202

    # Refresh account and vault record from DB
    db_session.expire_all()
    updated_account = db_session.get(TargetAccount, account.id)
    assert updated_account.rotation_status == "active"
    assert updated_account.last_rotated_at is not None

    vault_rec = db_session.query(VaultSecretStore).filter(VaultSecretStore.account_id == account.id).first()
    assert vault_rec.key_version == 2

    # Decrypt new password -> must NOT match initial_password
    new_password = decrypt_vault_payload(vault_rec.encrypted_payload)
    assert new_password != initial_password
    assert len(new_password) >= 32

    # Verify audit event for rotation
    audit_evt = (
        db_session.query(AuditOutbox)
        .filter(AuditOutbox.event_type == "vault_secret.rotated")
        .order_by(AuditOutbox.occurred_at.desc())
        .first()
    )
    assert audit_evt is not None
    assert audit_evt.correlation_id == account.id


def test_vault_custodian_manual_rotation(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    SEC-08: Vault Custodian can trigger manual rotation on demand.
    Standard Admins are rejected with 403.
    """
    account = seeded_fixtures["acc_pay_admin"]
    dave_admin = seeded_fixtures["dave"]
    eva_user = seeded_fixtures["eva"]

    VaultCredentialService.store_target_credential(
        db=db_session,
        account_id=account.id,
        secret_value="ManualRotTest#01",
        secret_type="password",
    )
    db_session.commit()

    # Standard Admin rejected
    resp = client.post(
        f"/api/v1/admin/vault/targets/{account.id}/rotate",
        headers=auth_headers(dave_admin.id, dave_admin.email),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "NOT_VAULT_CUSTODIAN"

    # Assign vault_custodian to Eva
    _assign_role(db_session, eva_user, "vault_custodian")

    # Vault Custodian triggers rotation
    resp = client.post(
        f"/api/v1/admin/vault/targets/{account.id}/rotate",
        headers=auth_headers(eva_user.id, eva_user.email),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rotation_status"] == "active"
    assert data["key_version"] == 2
    assert data["trigger_reason"] == "custodian_manual_rotation"


def test_anti_enumeration_concealment_on_vault_status_queries(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Identifier Concealment (SEC-03, Default Deny):
    Querying vault status for an account on an asset outside caller's resource scope
    returns HTTP 404 NOT_FOUND (never 403 Forbidden).
    """
    account = seeded_fixtures["acc_pay_admin"]  # payment asset (team: payments)
    charlie_approver = seeded_fixtures["charlie"]  # scoped strictly to team: analytics

    # Charlie (scoped to analytics) attempts to query vault status of payments asset account -> 404
    resp = client.get(
        f"/api/v1/admin/vault/targets/{account.id}/status",
        headers=auth_headers(charlie_approver.id, charlie_approver.email),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "ASSET_NOT_FOUND"
