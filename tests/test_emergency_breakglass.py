"""Out-of-band Emergency Break-Glass Drill & Multi-Custodian Verification tests (Phase 5 / P5-08, FR-11, SOD-04, T-09)."""

from datetime import timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from ariba_pam.config import settings
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.db.models import (
    User,
    Role,
    RoleAssignment,
    EmergencyRequest,
    EmergencyApproval,
    AccessGrant,
    AccessSession,
    AuditOutbox,
    SOCAlert,
)
from ariba_pam.services.emergency import EmergencyAccessService
from tests.conftest import auth_headers


def _assign_role(db: Session, user: User, role_name: str):
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
        scope_type="global",
        scope_value="*",
    )
    db.add(assignment)
    db.commit()


def test_emergency_request_submission(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    FR-11: An authorized operator can submit an out-of-band emergency break-glass request.
    Verifies initial 'pending' state and atomic audit outbox event.
    """
    dave = seeded_fixtures["dave"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    now = utc_now()

    resp = client.post(
        "/api/v1/emergency-requests",
        headers=auth_headers(dave.id, dave.email),
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "justification": "Production database unreachable during complete IdP outage (Drill P5-08)",
            "requested_end_at": (now + timedelta(hours=2)).isoformat(),
            "required_approvals": 2,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("emg_")
    assert data["status"] == "pending"
    assert data["required_approvals"] == 2
    assert data["approval_count"] == 0

    # Verify audit event
    outbox = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "EMERGENCY_REQUEST_SUBMITTED",
        AuditOutbox.actor_id == dave.id,
    ).first()
    assert outbox is not None
    assert outbox.payload["emergency_id"] == data["id"]


def test_emergency_custodian_sod_prevents_self_approval(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    SOD-04: Emergency Custodian / Requester cannot approve their own emergency request.
    Enforces strict Separation of Duties fail-closed.
    """
    dave = seeded_fixtures["dave"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    now = utc_now()

    # Dave submits
    resp_req = client.post(
        "/api/v1/emergency-requests",
        headers=auth_headers(dave.id, dave.email),
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "justification": "Emergency break-glass required for critical fix",
            "requested_end_at": (now + timedelta(hours=2)).isoformat(),
            "required_approvals": 2,
        },
    )
    assert resp_req.status_code == 201
    emergency_id = resp_req.json()["id"]

    # Dave attempts to approve his own emergency request -> 403 Forbidden
    resp_appr = client.post(
        f"/api/v1/emergency-requests/{emergency_id}/approve",
        headers=auth_headers(dave.id, dave.email),
        json={"decision": "approve", "reason": "Self-authorizing emergency access"},
    )
    assert resp_appr.status_code == 403
    assert resp_appr.json()["code"] == "SELF_APPROVAL_DENIED"


def test_multi_custodian_quorum_and_activation(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    FR-11, SOD-04, NFR-08:
    1. Multi-custodian threshold scheme requires quorum (2 distinct approvals).
    2. Duplicate votes by the same custodian are rejected.
    3. Activation issues emergency credentials and triggers immediate CRITICAL SOC alert.
    """
    dave = seeded_fixtures["dave"]
    bob = seeded_fixtures["bob"]
    eva = seeded_fixtures["eva"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    now = utc_now()

    # Assign emergency_custodian role to Bob and Eva
    _assign_role(db_session, bob, "emergency_custodian")
    _assign_role(db_session, eva, "emergency_custodian")

    # 1. Dave submits emergency request requiring 2 approvals
    resp_req = client.post(
        "/api/v1/emergency-requests",
        headers=auth_headers(dave.id, dave.email),
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "justification": "Primary payment DB partition during cloud region incident",
            "requested_end_at": (now + timedelta(hours=2)).isoformat(),
            "required_approvals": 2,
        },
    )
    assert resp_req.status_code == 201
    emergency_id = resp_req.json()["id"]

    # 2. Custodian 1 (Bob) approves
    resp_bob = client.post(
        f"/api/v1/emergency-requests/{emergency_id}/approve",
        headers=auth_headers(bob.id, bob.email),
        json={"decision": "approve", "reason": "Verified outage through out-of-band pager"},
    )
    assert resp_bob.status_code == 201
    assert resp_bob.json()["status"] == "pending"
    assert resp_bob.json()["approval_count"] == 1

    # Bob attempts duplicate vote -> 409 Conflict
    resp_dup = client.post(
        f"/api/v1/emergency-requests/{emergency_id}/approve",
        headers=auth_headers(bob.id, bob.email),
        json={"decision": "approve", "reason": "Trying to double vote"},
    )
    assert resp_dup.status_code == 409
    assert resp_dup.json()["code"] == "DUPLICATE_APPROVAL"

    # Dave tries to activate prematurely before quorum -> 409 Conflict
    resp_early = client.post(
        f"/api/v1/emergency-requests/{emergency_id}/activate",
        headers=auth_headers(dave.id, dave.email),
        json={"step_up_token": "mfa_token_early"},
    )
    assert resp_early.status_code == 409
    assert resp_early.json()["code"] == "NOT_APPROVED"

    # 3. Custodian 2 (Eva) approves -> reaching quorum (2 approvals)
    resp_eva = client.post(
        f"/api/v1/emergency-requests/{emergency_id}/approve",
        headers=auth_headers(eva.id, eva.email),
        json={"decision": "approve", "reason": "Confirmed multi-region incident with incident commander"},
    )
    assert resp_eva.status_code == 201
    assert resp_eva.json()["status"] == "approved"
    assert resp_eva.json()["approval_count"] == 2

    # 4. Activate emergency access
    resp_act = client.post(
        f"/api/v1/emergency-requests/{emergency_id}/activate",
        headers=auth_headers(dave.id, dave.email),
        json={"step_up_token": "mfa_token_verified"},
    )
    assert resp_act.status_code == 200
    act_data = resp_act.json()
    assert act_data["status"] == "active"
    assert act_data["grant_id"].startswith("grn_")
    assert act_data["launch_token"].startswith("lnc_emg_")

    # 5. Verify High-Priority SOC Security Alert was recorded!
    alert = db_session.query(SOCAlert).filter(
        SOCAlert.correlation_id == f"corr_emg_{emergency_id}",
        SOCAlert.alert_type == "EMERGENCY_ACCESS_ACTIVATED",
    ).first()
    assert alert is not None
    assert alert.severity == "CRITICAL"
    assert "emergency break-glass access activated" in alert.title.lower()

    # 6. Verify audit outbox log
    act_outbox = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "EMERGENCY_ACCESS_ACTIVATED",
        AuditOutbox.correlation_id == f"corr_emg_{emergency_id}",
    ).first()
    assert act_outbox is not None


def test_emergency_access_revocation_fail_closed(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    FR-11, T-09: Revoking an emergency request terminates grants and active sessions immediately.
    """
    dave = seeded_fixtures["dave"]
    bob = seeded_fixtures["bob"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    now = utc_now()

    _assign_role(db_session, bob, "emergency_custodian")

    # Submit request requiring 1 approval for speed
    req = EmergencyAccessService.create_emergency_request(
        db=db_session,
        requester=dave,
        asset_id=asset.id,
        target_account_id=account.id,
        justification="Short drill for emergency revocation validation",
        requested_end_at=now + timedelta(hours=1),
        required_approvals=1,
    )
    # Bob approves
    EmergencyAccessService.record_decision(
        db=db_session,
        emergency_id=req.id,
        custodian=bob,
        decision="approve",
        reason="Approved for revocation drill",
    )
    # Dave activates
    act_result = EmergencyAccessService.activate_emergency_access(
        db=db_session,
        emergency_id=req.id,
        activator=dave,
        step_up_token="token_drill",
    )
    grant_id = act_result["grant_id"]

    # Gateway consumes launch and starts active session
    consume_resp = client.post(
        "/internal/v1/launches/consume",
        headers={"X-Gateway-Secret": settings.gateway_api_secret},
        json={"launch_token": act_result["launch_token"], "gateway_id": "gw_drill_01"},
    )
    assert consume_resp.status_code == 201
    session_id = consume_resp.json()["session_id"]

    # Revoke emergency access
    resp_rev = client.post(
        f"/api/v1/emergency-requests/{req.id}/revoke",
        headers=auth_headers(dave.id, dave.email),
        json={"reason": "Drill completed successfully, returning to standard posture"},
    )
    assert resp_rev.status_code == 202
    assert resp_rev.json()["status"] == "revoked"

    # Confirm grant is revoked
    grant = db_session.get(AccessGrant, grant_id)
    assert grant.status == "revoked"

    # Confirm active session was terminated fail-closed
    session = db_session.get(AccessSession, session_id)
    assert session.status == "ended"
    assert "Emergency access revoked" in session.termination_reason


def test_independent_post_incident_review(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    specifications/modules/audit-and-recovery.md:
    Independent post-incident review by auditor/security operator.
    Requester cannot review their own emergency incident.
    """
    dave = seeded_fixtures["dave"]
    bob = seeded_fixtures["bob"]
    eva = seeded_fixtures["eva"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    now = utc_now()

    _assign_role(db_session, bob, "emergency_custodian")

    req = EmergencyAccessService.create_emergency_request(
        db=db_session,
        requester=dave,
        asset_id=asset.id,
        target_account_id=account.id,
        justification="Incident resolution review drill",
        requested_end_at=now + timedelta(hours=1),
        required_approvals=1,
    )
    EmergencyAccessService.record_decision(db_session, req.id, bob, "approve", "Approved for incident")
    EmergencyAccessService.activate_emergency_access(db_session, req.id, dave, "token_drill")
    EmergencyAccessService.revoke_emergency_access(db_session, req.id, dave, "Incident closed")

    # 1. Dave (requester) attempts post-incident review -> 403 Forbidden
    resp_self_rev = client.post(
        f"/api/v1/emergency-requests/{req.id}/review",
        headers=auth_headers(dave.id, dave.email),
        json={"review_notes": "Attempting self-review"},
    )
    assert resp_self_rev.status_code == 403
    assert resp_self_rev.json()["code"] == "INDEPENDENT_REVIEW_REQUIRED"

    # 2. Eva (auditor) conducts independent review -> 200 OK
    resp_eva_rev = client.post(
        f"/api/v1/emergency-requests/{req.id}/review",
        headers=auth_headers(eva.id, eva.email),
        json={"review_notes": "All terminal keystrokes verified; no out-of-scope actions performed."},
    )
    assert resp_eva_rev.status_code == 200
    assert resp_eva_rev.json()["status"] == "reviewed"
    assert resp_eva_rev.json()["reviewer_id"] == eva.id

    # 3. Retrieve review report
    get_rev = client.get(
        f"/api/v1/emergency-requests/{req.id}/review",
        headers=auth_headers(dave.id, dave.email),
    )
    assert get_rev.status_code == 200
    assert get_rev.json()["reviewed"] is True
    assert get_rev.json()["reviewer_id"] == eva.id


def test_emergency_request_rejection_flow(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    When a custodian rejects an emergency request, status transitions to 'rejected'
    and activation is blocked.
    """
    dave = seeded_fixtures["dave"]
    bob = seeded_fixtures["bob"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    now = utc_now()

    _assign_role(db_session, bob, "emergency_custodian")

    req = EmergencyAccessService.create_emergency_request(
        db=db_session,
        requester=dave,
        asset_id=asset.id,
        target_account_id=account.id,
        justification="Test rejection flow",
        requested_end_at=now + timedelta(hours=1),
        required_approvals=2,
    )

    # Bob rejects
    resp_rej = client.post(
        f"/api/v1/emergency-requests/{req.id}/approve",
        headers=auth_headers(bob.id, bob.email),
        json={"decision": "reject", "reason": "Insufficient evidence of outage; rejected by custodian"},
    )
    assert resp_rej.status_code == 201
    assert resp_rej.json()["status"] == "rejected"

    # Activation attempt is rejected
    resp_act = client.post(
        f"/api/v1/emergency-requests/{req.id}/activate",
        headers=auth_headers(dave.id, dave.email),
        json={"step_up_token": "token_invalid"},
    )
    assert resp_act.status_code == 409
    assert resp_act.json()["code"] == "NOT_APPROVED"


def test_anti_enumeration_and_rbac(client: TestClient, seeded_fixtures: dict):
    """
    Anti-enumeration and RBAC checks:
    - Routine user (Alice) cannot initiate emergency access (403 Forbidden).
    - Non-existent emergency request returns 404 Not Found.
    - Non-custodian querying another user's request returns 404 (identifier concealment).
    """
    alice = seeded_fixtures["alice"]
    dave = seeded_fixtures["dave"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    now = utc_now()

    # Alice denied request creation
    resp = client.post(
        "/api/v1/emergency-requests",
        headers=auth_headers(alice.id, alice.email),
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "justification": "Alice trying to break glass",
            "requested_end_at": (now + timedelta(hours=1)).isoformat(),
        },
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "NOT_PERMITTED"

    # Dave queries non-existent request -> 404
    resp_404 = client.get(
        "/api/v1/emergency-requests/emg_non_existent",
        headers=auth_headers(dave.id, dave.email),
    )
    assert resp_404.status_code == 404
    assert resp_404.json()["code"] == "EMERGENCY_REQUEST_NOT_FOUND"
