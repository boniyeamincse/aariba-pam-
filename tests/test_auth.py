"""Workforce sign-in, assurance validation, and session tests (Task P1-03 / FR-01 / T-01)."""

import pytest
from tests.conftest import auth_headers
from ariba_pam.core.security import create_session_token


def test_auth_valid_login_and_get_me(client, seeded_fixtures):
    """Test successful synthetic IdP login and GET /api/v1/me with permitted scopes."""
    alice = seeded_fixtures["alice"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": alice.email,
            "idp_subject": alice.idp_subject,
            "amr": ["pwd", "fido2"],
        },
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Verify GET /api/v1/me
    me_resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["id"] == alice.id
    assert data["email"] == alice.email
    assert data["is_active"] is True
    assert len(data["roles"]) == 1
    assert data["roles"][0]["role"] == "requester"
    assert data["roles"][0]["scope_type"] == "team"
    assert data["roles"][0]["scope_value"] == "payments"


def test_auth_reject_insufficient_assurance(client, seeded_fixtures):
    """Reject authentication token missing phishing-resistant MFA (e.g. password only)."""
    alice = seeded_fixtures["alice"]

    # Token with only password, no fido2/webauthn
    weak_token = create_session_token(
        user_id=alice.id,
        email=alice.email,
        auth_methods=["pwd"],  # Non-phishing-resistant
    )

    resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {weak_token}"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "INSUFFICIENT_ASSURANCE"


def test_auth_reject_disabled_user(client, seeded_fixtures):
    """Reject authentication and session calls for disabled workforce accounts."""
    disabled = seeded_fixtures["disabled"]

    # Attempt synthetic login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": disabled.email,
            "idp_subject": disabled.idp_subject,
            "amr": ["pwd", "fido2"],
        },
    )
    assert login_resp.status_code == 401
    assert login_resp.json()["code"] == "ACCOUNT_DISABLED"

    # Token forged or created before disablement
    token = create_session_token(user_id=disabled.id, email=disabled.email)
    resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "ACCOUNT_DISABLED"


def test_auth_reject_unknown_identity(client, seeded_fixtures):
    """Reject un-enrolled identities not matching organization directory."""
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "stranger@unknown-domain.com",
            "idp_subject": "sub_attacker_999",
            "amr": ["pwd", "fido2"],
        },
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNKNOWN_IDENTITY"


def test_auth_reject_expired_or_invalid_signature_token(client, seeded_fixtures):
    """Reject expired tokens and forged tokens."""
    alice = seeded_fixtures["alice"]

    # Expired token (expires_in_seconds = -10)
    expired_token = create_session_token(
        user_id=alice.id,
        email=alice.email,
        expires_in_seconds=-10,
    )
    resp_exp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp_exp.status_code == 401
    assert resp_exp.json()["code"] == "TOKEN_EXPIRED"

    # Tampered token
    tampered = expired_token[:-4] + "fake"
    resp_tampered = client.get("/api/v1/me", headers={"Authorization": f"Bearer {tampered}"})
    assert resp_tampered.status_code == 401
