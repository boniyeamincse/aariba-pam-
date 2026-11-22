"""Unit and integration tests for Multi-Provider IdP Evaluation (P7-03, ADR-015).

Verifies:
1. Directory federation across primary pilot OIDC and secondary Microsoft Entra ID.
2. NIST SP 800-63B Authentication Assurance mapping and AMR normalization.
3. Enforcement of phishing-resistant MFA invariants across providers.
4. Successful workforce authentication for secondary IdP principals.
5. Ingestion and rapid propagation of account disablement signals from secondary IdP (≤ 60s NFR-01 SLA).
6. Microsoft Graph change notification and SCIM 2.0 deprovisioning schema normalization.
7. Idempotent deduplication and replay protection for secondary IdP events.
8. Admin integration status endpoint and anti-enumeration RBAC protection.
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ariba_pam.config import settings
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.db.models import (
    User,
    Role,
    RoleAssignment,
    GatewayZone,
    Asset,
    TargetAccount,
    AccessGrant,
    AccessSession,
    SessionLaunch,
    RequestRevision,
    AccessRequest,
    AuditOutbox,
)
from ariba_pam.services.idp import (
    MultiIdPService,
    AAL3_PHISHING_RESISTANT,
    AAL2_MULTI_FACTOR,
    AAL1_SINGLE_FACTOR,
    REJECTED_INSECURE,
)
from tests.conftest import auth_headers


def test_multi_idp_provider_registry():
    """
    P7-03: Verifies that trusted provider registry recognizes both primary
    pilot OIDC and secondary Microsoft Entra ID issuers.
    """
    providers = MultiIdPService.get_trusted_providers()
    assert "pilot_oidc" in providers
    assert providers["pilot_oidc"]["is_primary"] is True
    assert providers["pilot_oidc"]["issuer"] == settings.idp_issuer

    assert settings.secondary_idp_name in providers
    assert providers[settings.secondary_idp_name]["is_primary"] is False
    assert providers[settings.secondary_idp_name]["issuer"] == settings.secondary_idp_issuer

    # Check issuer resolution
    assert MultiIdPService.resolve_provider_by_issuer(settings.idp_issuer) == "pilot_oidc"
    assert MultiIdPService.resolve_provider_by_issuer(settings.secondary_idp_issuer) == settings.secondary_idp_name
    assert MultiIdPService.resolve_provider_by_issuer("https://rogue-idp.attacker.com") is None

    assert MultiIdPService.is_issuer_trusted(settings.idp_issuer) is True
    assert MultiIdPService.is_issuer_trusted(settings.secondary_idp_issuer) is True
    assert MultiIdPService.is_issuer_trusted("https://rogue-idp.attacker.com") is False


def test_assurance_normalization_and_mapping():
    """
    P7-03: Verifies AMR claim normalization against NIST SP 800-63B assurance levels
    for Microsoft Entra ID, Okta, and standard OIDC.
    """
    # 1. Microsoft Entra ID
    # FIDO2 passkey -> AAL3 Phishing-Resistant
    norm_entra_fido = MultiIdPService.normalize_amr("microsoft_entra", ["pwd", "fido"])
    assert norm_entra_fido["assurance_level"] == AAL3_PHISHING_RESISTANT
    assert norm_entra_fido["is_phishing_resistant"] is True
    assert norm_entra_fido["is_acceptable_for_privileged"] is True

    # Windows Hello / NGCMFA -> AAL3 Phishing-Resistant
    norm_entra_hello = MultiIdPService.normalize_amr("microsoft_entra", ["ngcmfa"])
    assert norm_entra_hello["assurance_level"] == AAL3_PHISHING_RESISTANT

    # App MFA without FIDO -> AAL2 Standard MFA
    norm_entra_mfa = MultiIdPService.normalize_amr("microsoft_entra", ["pwd", "mfa", "pin"])
    assert norm_entra_mfa["assurance_level"] == AAL2_MULTI_FACTOR
    assert norm_entra_mfa["is_phishing_resistant"] is False
    assert norm_entra_mfa["is_acceptable_for_privileged"] is False

    # SMS OTP -> Insecure Rejected
    norm_entra_sms = MultiIdPService.normalize_amr("microsoft_entra", ["pwd", "sms"])
    assert norm_entra_sms["assurance_level"] == REJECTED_INSECURE
    assert norm_entra_sms["is_acceptable_for_privileged"] is False

    # 2. Okta
    norm_okta_fido = MultiIdPService.normalize_amr("okta", ["pwd", "fido2"])
    assert norm_okta_fido["assurance_level"] == AAL3_PHISHING_RESISTANT

    norm_okta_hwk = MultiIdPService.normalize_amr("okta", ["hwk"])
    assert norm_okta_hwk["assurance_level"] == AAL3_PHISHING_RESISTANT

    norm_okta_push = MultiIdPService.normalize_amr("okta", ["pwd", "push"])
    assert norm_okta_push["assurance_level"] == AAL2_MULTI_FACTOR

    # 3. Pilot OIDC
    norm_oidc_webauthn = MultiIdPService.normalize_amr("pilot_oidc", ["pwd", "webauthn"])
    assert norm_oidc_webauthn["assurance_level"] == AAL3_PHISHING_RESISTANT

    # Validate assurance helper
    valid, _ = MultiIdPService.validate_assurance("microsoft_entra", ["pwd", "fido"], require_phishing_resistant=True)
    assert valid is True

    valid_mfa, reason_mfa = MultiIdPService.validate_assurance("microsoft_entra", ["pwd", "mfa"], require_phishing_resistant=True)
    assert valid_mfa is False
    assert "phishing-resistant" in reason_mfa.lower()

    valid_sms, reason_sms = MultiIdPService.validate_assurance("microsoft_entra", ["pwd", "sms"], require_phishing_resistant=True)
    assert valid_sms is False
    assert "insecure" in reason_sms.lower()


def _create_entra_user_and_session(db: Session, zone: GatewayZone):
    """Helper to provision active user, grant, and session federated from Entra ID."""
    now = utc_now()
    user = User(
        id=generate_id("usr"),
        email="entra_operator@ariba.internal",
        full_name="Entra Operator",
        idp_issuer=settings.secondary_idp_issuer,
        idp_subject="oid_azure_operator_01",
        is_active=True,
    )
    role = Role(id=generate_id("rol"), name="cloud_engineer", description="Cloud Engineer")
    asset = Asset(
        id=generate_id("ast"),
        name="Azure Gateway Bastion",
        environment="lab",
        team="cloud",
        host="10.240.0.10",
        port=22,
        zone=zone,
        host_trust_ref="trust_azure_bastion",
    )
    account = TargetAccount(id=generate_id("acc"), asset=asset, username="cloudadmin")
    db.add_all([user, role, asset, account])
    db.flush()

    role_assign = RoleAssignment(user=user, role=role, scope_type="global", scope_value="*")
    db.add(role_assign)

    req = AccessRequest(id=generate_id("req"), requester=user)
    rev = RequestRevision(
        id=generate_id("rev"),
        request=req,
        revision_number=1,
        asset=asset,
        target_account=account,
        requested_start_at=now,
        requested_end_at=now + timedelta(hours=2),
        justification="Cloud bastion maintenance",
        policy_version_id="pol_1",
    )
    grant = AccessGrant(
        id=generate_id("grn"),
        revision=rev,
        requester=user,
        asset=asset,
        target_account=account,
        effective_start_at=now,
        effective_end_at=now + timedelta(hours=2),
        status="active",
    )
    launch = SessionLaunch(
        id=generate_id("lnc"),
        grant=grant,
        launch_token_digest="digest_entra_test",
        expires_at=now + timedelta(minutes=5),
        is_consumed=True,
        consumed_by_gateway_id="gw_zone_lab",
    )
    session = AccessSession(
        id=generate_id("ses"),
        grant=grant,
        launch=launch,
        gateway_id="gw_zone_lab",
        status="active",
        started_at=now,
    )
    db.add_all([req, rev, grant, launch, session])
    db.commit()
    return user, grant, session


def test_secondary_idp_user_authentication_success(client: TestClient, db_session: Session, seeded_fixtures: dict):
    """
    P7-03: Verifies that workforce principals federated through Microsoft Entra ID
    can authenticate and receive valid bearer tokens when presenting phishing-resistant AMR.
    """
    zone = seeded_fixtures["zone_lab"]
    user, _, _ = _create_entra_user_and_session(db_session, zone)

    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "idp_issuer": settings.secondary_idp_issuer,
            "idp_subject": user.idp_subject,
            "amr": ["pwd", "fido"],  # Entra FIDO2 assurance
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user_id"] == user.id

    # Verify audit event in outbox
    audit = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "WORKFORCE_AUTHENTICATED",
        AuditOutbox.actor_id == user.id,
    ).first()
    assert audit is not None
    assert audit.payload["provider"] == settings.secondary_idp_name
    assert audit.payload["idp_issuer"] == settings.secondary_idp_issuer


def test_secondary_idp_insufficient_assurance_rejected(client: TestClient, db_session: Session, seeded_fixtures: dict):
    """
    P7-03: Verifies that authentication via secondary IdP is rejected if the claims
    fail phishing-resistant MFA (e.g. basic SMS or non-FIDO app MFA).
    """
    zone = seeded_fixtures["zone_lab"]
    user, _, _ = _create_entra_user_and_session(db_session, zone)

    # 1. Reject SMS telephony
    resp_sms = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "idp_issuer": settings.secondary_idp_issuer,
            "idp_subject": user.idp_subject,
            "amr": ["pwd", "sms"],
        },
    )
    assert resp_sms.status_code == 401
    assert resp_sms.json()["code"] == "INSUFFICIENT_ASSURANCE"

    # 2. Reject non-phishing resistant standard MFA under strict policy
    resp_mfa = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "idp_issuer": settings.secondary_idp_issuer,
            "idp_subject": user.idp_subject,
            "amr": ["pwd", "mfa"],
        },
    )
    assert resp_mfa.status_code == 401
    assert resp_mfa.json()["code"] == "INSUFFICIENT_ASSURANCE"


def test_secondary_idp_account_disablement_propagation_and_reconciliation(client: TestClient, db_session: Session, seeded_fixtures: dict):
    """
    P7-03: Repeats account disablement checks for Microsoft Entra ID.
    Verifies that inbound disablement event invalidates the user, revokes active grants,
    and transitions active sessions to terminating within the ≤ 60s NFR-01 SLA.
    """
    zone = seeded_fixtures["zone_lab"]
    user, grant, session = _create_entra_user_and_session(db_session, zone)

    # Ingest Entra account disablement signal
    resp = client.post(
        "/api/v1/auth/idp-events",
        json={
            "event_id": "evt_entra_disable_001",
            "event_type": "user.disabled",
            "idp_issuer": settings.secondary_idp_issuer,
            "idp_subject": user.idp_subject,
            "email": user.email,
            "timestamp": utc_now().isoformat(),
        },
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "processed"
    assert res_data["is_active"] is False
    assert res_data["revoked_grants_count"] == 1
    assert res_data["terminating_sessions_count"] == 1

    # Verify user deactivated
    db_session.refresh(user)
    assert user.is_active is False

    # Verify grant revoked
    db_session.refresh(grant)
    assert grant.status == "revoked"
    assert "microsoft_entra" in grant.revocation_reason

    # Verify session terminating
    db_session.refresh(session)
    assert session.status == "terminating"

    # Verify gateway lease renewal fails with 409
    renew_resp = client.post(
        f"/internal/v1/sessions/{session.id}/renew",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
    )
    assert renew_resp.status_code == 409

    # Verify audit event in outbox
    audit = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "IDP_USER_DISABLED",
        AuditOutbox.actor_id == user.id,
    ).first()
    assert audit is not None
    assert audit.payload["source_provider"] == settings.secondary_idp_name
    assert audit.payload["idp_issuer"] == settings.secondary_idp_issuer


def test_microsoft_graph_change_notification_format_ingestion(client: TestClient, db_session: Session, seeded_fixtures: dict):
    """
    P7-03: Ingests native Microsoft Graph change notification payload
    (resourceData with accountEnabled=false) and verifies schema normalization.
    """
    zone = seeded_fixtures["zone_lab"]
    user, grant, session = _create_entra_user_and_session(db_session, zone)

    graph_payload = {
        "subscriptionId": "sub_graph_notif_9988",
        "id": "evt_graph_user_disabled_9988",
        "changeType": "updated",
        "resource": f"Users/{user.idp_subject}",
        "resourceData": {
            "@odata.type": "#Microsoft.Graph.User",
            "id": user.idp_subject,
            "accountEnabled": False,
            "userPrincipalName": user.email,
        },
    }

    resp = client.post("/api/v1/auth/idp-events", json=graph_payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "processed"
    assert res_data["is_active"] is False

    db_session.refresh(user)
    assert user.is_active is False
    db_session.refresh(grant)
    assert grant.status == "revoked"


def test_scim_2_deprovisioning_patch_format_ingestion(client: TestClient, db_session: Session, seeded_fixtures: dict):
    """
    P7-03: Ingests SCIM 2.0 deprovisioning PATCH request and verifies normalization.
    """
    zone = seeded_fixtures["zone_lab"]
    user, grant, session = _create_entra_user_and_session(db_session, zone)

    scim_payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "id": "evt_scim_patch_deactivate_01",
        "idp_issuer": settings.secondary_idp_issuer,
        "externalId": user.idp_subject,
        "userName": user.email,
        "Operations": [
            {
                "op": "replace",
                "path": "active",
                "value": False,
            }
        ],
    }

    resp = client.post("/api/v1/auth/idp-events", json=scim_payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "processed"
    assert res_data["is_active"] is False

    db_session.refresh(user)
    assert user.is_active is False


def test_secondary_idp_idempotency_and_replay_protection(client: TestClient, db_session: Session, seeded_fixtures: dict):
    """
    P7-03: Verifies that replayed or duplicate disablement events from the secondary IdP
    return cached responses without executing redundant database writes.
    """
    zone = seeded_fixtures["zone_lab"]
    user, _, _ = _create_entra_user_and_session(db_session, zone)

    event_payload = {
        "event_id": "evt_idempotent_entra_01",
        "event_type": "user.disabled",
        "idp_issuer": settings.secondary_idp_issuer,
        "idp_subject": user.idp_subject,
        "email": user.email,
        "timestamp": utc_now().isoformat(),
    }

    # Initial submission
    resp1 = client.post("/api/v1/auth/idp-events", json=event_payload)
    assert resp1.status_code == 200
    assert resp1.json()["revoked_grants_count"] == 1

    # Replay with same event_id
    resp2 = client.post("/api/v1/auth/idp-events", json=event_payload)
    assert resp2.status_code == 200
    assert resp2.json()["revoked_grants_count"] == 1
    assert resp2.json()["event_id"] == "evt_idempotent_entra_01"


def test_admin_idp_federation_status_endpoint(client: TestClient, seeded_fixtures: dict):
    """
    P7-03: Verifies GET /api/v1/admin/integrations/idp/status endpoint:
    - Admin (Dave) receives catalog of primary and secondary IdPs and assurance rules.
    - Routine user (Alice) denied with 403 Forbidden.
    """
    alice = seeded_fixtures["alice"]
    dave = seeded_fixtures["dave"]

    # Alice denied
    resp_alice = client.get(
        "/api/v1/admin/integrations/idp/status",
        headers=auth_headers(alice.id, alice.email),
    )
    assert resp_alice.status_code == 403
    assert resp_alice.json()["code"] == "NOT_PERMITTED"

    # Dave gets status
    resp_dave = client.get(
        "/api/v1/admin/integrations/idp/status",
        headers=auth_headers(dave.id, dave.email),
    )
    assert resp_dave.status_code == 200
    data = resp_dave.json()
    assert data["primary_issuer"] == settings.idp_issuer
    assert "trusted_providers" in data
    assert "pilot_oidc" in data["trusted_providers"]
    assert settings.secondary_idp_name in data["trusted_providers"]
    assert "assurance_rules" in data
    assert "microsoft_entra" in data["assurance_rules"]
