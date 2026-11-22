"""P4-01 & P4-02: Isolated Ephemeral SSH Certificate Authority & CA Rollover Tests.

Verifies:
1. Native Ed25519 OpenSSH User Certificate generation and signature.
2. Principal restriction (only approved target account allowed).
3. Short validity window and grant expiration bounding.
4. Key rollover and dual-trust verification (P4-02).
5. Internal Control Plane API endpoint: /internal/v1/sessions/{session_id}/sign-certificate.
6. Audit outbox recording of SSH_CERTIFICATE_ISSUED events.
"""

from datetime import datetime, timezone, timedelta
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_ssh_public_key,
    load_ssh_public_identity,
    SSHCertificateType,
)

from ariba_pam.services.ca import SSHUserCAService
from ariba_pam.core.errors import ValidationException, ForbiddenException
from ariba_pam.config import settings
from ariba_pam.db.models import AuditOutbox
from tests.conftest import auth_headers


def _gen_client_pubkey() -> str:
    key = ed25519.Ed25519PrivateKey.generate()
    pub_bytes = key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
    return pub_bytes.decode("ascii")


def test_ca_key_generation_and_public_key_format():
    """Verify CA initialization, public key string, and fingerprint."""
    ca = SSHUserCAService()
    pub = ca.get_active_public_key()
    assert pub.startswith("ssh-ed25519 ")
    assert pub.endswith(" ariba-pam-user-ca")

    fp = ca.get_active_fingerprint()
    assert fp.startswith("SHA256:")
    assert len(fp) > 10


def test_ca_sign_ephemeral_user_certificate():
    """Verify OpenSSH User Certificate structure, principals, and bounded validity."""
    ca = SSHUserCAService()
    client_pub_str = _gen_client_pubkey()

    now = datetime.now(timezone.utc)
    grant_end = now + timedelta(minutes=45)

    cert_str, valid_before, serial_int, ca_fp = ca.sign_grant_certificate(
        client_public_key_openssh=client_pub_str,
        principal="payadmin",
        grant_id="grnt_test_101",
        grant_end_at=grant_end,
        max_validity_seconds=300,
    )

    # Validate output formats
    assert cert_str.startswith("ssh-ed25519-cert-v01@openssh.com ")
    assert valid_before > now
    assert valid_before <= now + timedelta(seconds=305)
    assert serial_int > 0
    assert ca_fp == ca.get_active_fingerprint()

    # Parse and inspect with cryptography
    cert_obj = load_ssh_public_identity(cert_str.encode("ascii"))
    assert cert_obj.type == SSHCertificateType.USER
    assert cert_obj.valid_principals == [b"payadmin"]
    assert cert_obj.key_id == b"ariba_grnt_test_101_payadmin"
    assert cert_obj.serial == serial_int
    assert b"permit-pty" in cert_obj.extensions


def test_ca_reject_invalid_principal():
    """Ensure shell injection and path traversal principals fail closed."""
    ca = SSHUserCAService()
    client_pub_str = _gen_client_pubkey()
    grant_end = datetime.now(timezone.utc) + timedelta(minutes=30)

    for invalid in ["", "; rm -rf /", "root\nadmin", "../../etc/passwd", "user with spaces"]:
        with pytest.raises(ValidationException) as exc:
            ca.sign_grant_certificate(
                client_public_key_openssh=client_pub_str,
                principal=invalid,
                grant_id="grnt_invalid",
                grant_end_at=grant_end,
            )
        assert exc.value.code == "INVALID_PRINCIPAL"


def test_ca_reject_invalid_public_key():
    """Submitting malformed public key bytes fails closed."""
    ca = SSHUserCAService()
    grant_end = datetime.now(timezone.utc) + timedelta(minutes=30)

    with pytest.raises(ValidationException) as exc:
        ca.sign_grant_certificate(
            client_public_key_openssh="not_a_valid_ssh_key_string",
            principal="payadmin",
            grant_id="grnt_bad_key",
            grant_end_at=grant_end,
        )
    assert exc.value.code == "INVALID_PUBLIC_KEY"


def test_ca_reject_expired_grant():
    """Cannot sign certificate for an expired grant window."""
    ca = SSHUserCAService()
    client_pub_str = _gen_client_pubkey()
    expired_end = datetime.now(timezone.utc) - timedelta(minutes=5)

    with pytest.raises(ForbiddenException) as exc:
        ca.sign_grant_certificate(
            client_public_key_openssh=client_pub_str,
            principal="payadmin",
            grant_id="grnt_expired",
            grant_end_at=expired_end,
        )
    assert exc.value.code == "GRANT_EXPIRED"


def test_ca_key_rollover_and_dual_trust():
    """Verify CA key rollover (P4-02): dual-trust keys preserved during transition."""
    ca = SSHUserCAService()
    old_pub = ca.get_active_public_key()

    new_pub = ca.rotate_ca_key()
    assert new_pub != old_pub
    assert ca.get_active_public_key() == new_pub

    trusted_keys = ca.get_trusted_ca_keys()
    assert len(trusted_keys) == 2
    assert trusted_keys[0].startswith(new_pub.split()[0])
    assert trusted_keys[1].startswith(old_pub.split()[0])


def test_api_sign_session_certificate_e2e(client, seeded_fixtures, policy_admin, db_session):
    """Full API verification of POST /internal/v1/sessions/{session_id}/sign-certificate."""
    alice = seeded_fixtures["alice"]
    bob = seeded_fixtures["bob"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    assert policy_admin.publish(policy_admin.propose()).status_code == 200

    now = datetime.now(timezone.utc)
    # 1. Create request & Bob approves
    req_resp = client.post(
        "/api/v1/requests",
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "requested_start_at": (now - timedelta(minutes=2)).isoformat(),
            "requested_end_at": (now + timedelta(minutes=45)).isoformat(),
            "justification": "SSH CA certificate signing verification",
        },
        headers=auth_headers(alice.id, alice.email),
    )
    req_data = req_resp.json()

    approve_resp = client.post(
        f"/api/v1/approval-steps/{req_data['step_id']}/decisions",
        json={"expected_revision_id": req_data["revision_id"], "decision": "approved"},
        headers=auth_headers(bob.id, bob.email),
    )
    grant_id = approve_resp.json()["grant_id"]

    # 2. Launch & consume to start active session
    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    launch_token = launch_resp.json()["launch_token"]

    consume_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_token, "gateway_id": "gw_zone_lab_01"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    session_id = consume_resp.json()["session_id"]

    # 3. Gateway requests signed SSH certificate
    ephemeral_client_pub = _gen_client_pubkey()
    cert_resp = client.post(
        f"/internal/v1/sessions/{session_id}/sign-certificate",
        json={"client_public_key": ephemeral_client_pub},
        headers={
            "X-Gateway-Secret": settings.gateway_api_secret,
            "X-Correlation-Id": "corr_gw_cert_sign_test",
        },
    )
    assert cert_resp.status_code == 201
    cert_data = cert_resp.json()
    assert cert_data["certificate"].startswith("ssh-ed25519-cert-v01@openssh.com ")
    assert cert_data["principal"] == "dbadmin"
    assert "expires_at" in cert_data
    assert "serial" in cert_data

    # 4. Verify audit outbox record
    outbox_row = (
        db_session.query(AuditOutbox)
        .filter(AuditOutbox.correlation_id == "corr_gw_cert_sign_test")
        .first()
    )
    assert outbox_row is not None
    assert outbox_row.event_type == "SSH_CERTIFICATE_ISSUED"
    assert outbox_row.payload["principal"] == "dbadmin"
    assert outbox_row.payload["session_id"] == session_id


def test_api_sign_rejected_on_ended_session(client, seeded_fixtures, policy_admin):
    """Cannot sign certificate for an ended session."""
    alice = seeded_fixtures["alice"]
    bob = seeded_fixtures["bob"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    policy_admin.publish(policy_admin.propose())

    now = datetime.now(timezone.utc)
    req_resp = client.post(
        "/api/v1/requests",
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "requested_start_at": (now - timedelta(minutes=2)).isoformat(),
            "requested_end_at": (now + timedelta(minutes=45)).isoformat(),
            "justification": "Ended session signing test",
        },
        headers=auth_headers(alice.id, alice.email),
    )
    req_data = req_resp.json()

    approve_resp = client.post(
        f"/api/v1/approval-steps/{req_data['step_id']}/decisions",
        json={"expected_revision_id": req_data["revision_id"], "decision": "approved"},
        headers=auth_headers(bob.id, bob.email),
    )
    grant_id = approve_resp.json()["grant_id"]

    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    consume_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_resp.json()["launch_token"], "gateway_id": "gw_zone_lab_01"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    session_id = consume_resp.json()["session_id"]

    # Terminate session
    client.post(
        f"/internal/v1/sessions/{session_id}/events",
        json={"state": "ended", "reason": "Normal exit"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )

    # Signing certificate on ended session must fail
    sign_resp = client.post(
        f"/internal/v1/sessions/{session_id}/sign-certificate",
        json={"client_public_key": _gen_client_pubkey()},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert sign_resp.status_code == 409
    assert sign_resp.json()["code"] == "SESSION_NOT_ACTIVE"


def test_api_sign_unauthorized_gateway(client, seeded_fixtures, policy_admin):
    """Missing or incorrect X-Gateway-Secret returns 401."""
    alice = seeded_fixtures["alice"]
    bob = seeded_fixtures["bob"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    policy_admin.publish(policy_admin.propose())

    now = datetime.now(timezone.utc)
    req_resp = client.post(
        "/api/v1/requests",
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "requested_start_at": (now - timedelta(minutes=2)).isoformat(),
            "requested_end_at": (now + timedelta(minutes=45)).isoformat(),
            "justification": "Unauthorized gateway test",
        },
        headers=auth_headers(alice.id, alice.email),
    )
    req_data = req_resp.json()

    approve_resp = client.post(
        f"/api/v1/approval-steps/{req_data['step_id']}/decisions",
        json={"expected_revision_id": req_data["revision_id"], "decision": "approved"},
        headers=auth_headers(bob.id, bob.email),
    )
    grant_id = approve_resp.json()["grant_id"]

    launch_resp = client.post(
        f"/api/v1/grants/{grant_id}/launches",
        headers=auth_headers(alice.id, alice.email),
    )
    consume_resp = client.post(
        "/internal/v1/launches/consume",
        json={"launch_token": launch_resp.json()["launch_token"], "gateway_id": "gw_zone_lab_01"},
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    session_id = consume_resp.json()["session_id"]

    # Call without secret
    unauth_resp = client.post(
        f"/internal/v1/sessions/{session_id}/sign-certificate",
        json={"client_public_key": _gen_client_pubkey()},
        headers={},
    )
    assert unauth_resp.status_code == 401
    assert unauth_resp.json()["code"] == "GATEWAY_UNAUTHORIZED"
