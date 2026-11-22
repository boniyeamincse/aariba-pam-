"""Unit and integration tests for ITSM Ticket Reference Integration (P7-04, ADR-016).

Verifies:
1. Ticket format validation across Jira, ServiceNow, and generic schemes.
2. Active / approved state verification (rejecting closed/cancelled tickets).
3. Requester identity and permission / assignee matching (anti-hijacking).
4. Strict latency timeouts (3.0s) and system error handling.
5. Outage fallback policies:
   - fail_closed: immediate 503 rejection ensuring default-deny.
   - manual_approval: permits submission with degraded warning and outbox audit event.
6. Integration into access request and revision lifecycles (POST /api/v1/requests, POST /api/v1/requests/{id}/revisions).
7. Admin integration status and validation probe endpoints with RBAC protection.
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ariba_pam.config import settings
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.db.models import (
    User,
    Asset,
    TargetAccount,
    AccessPolicyVersion,
    AuditOutbox,
    AccessRequest,
    RequestRevision,
)
from ariba_pam.services.itsm import (
    ITSMAdapter,
    itsm_adapter,
)
from ariba_pam.services.policies import PolicyRules
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def reset_global_itsm_adapter():
    """Ensure global itsm_adapter state is clean before and after each test."""
    original_fallback = itsm_adapter.fallback_mode
    itsm_adapter.fallback_mode = "fail_closed"
    yield
    itsm_adapter.fallback_mode = original_fallback


def test_itsm_ticket_format_validation():
    """
    P7-04: Verifies ticket identifier format validation across Jira, ServiceNow, and generic patterns.
    """
    adapter = ITSMAdapter()

    # Valid Jira
    assert adapter.is_valid_ticket_format("JIRA-1001") is True
    assert adapter.is_valid_ticket_format("PAY-482") is True
    assert adapter.is_valid_ticket_format("LAB-42") is True

    # Valid ServiceNow
    assert adapter.is_valid_ticket_format("INC0019283") is True
    assert adapter.is_valid_ticket_format("CHG009812") is True
    assert adapter.is_valid_ticket_format("REQ12345") is True

    # Invalid patterns
    assert adapter.is_valid_ticket_format("") is False
    assert adapter.is_valid_ticket_format("   ") is False
    assert adapter.is_valid_ticket_format("12345") is False
    assert adapter.is_valid_ticket_format("invalid_identifier") is False
    assert adapter.is_valid_ticket_format("---") is False


def test_itsm_ticket_validation_success():
    """
    P7-04: Verifies successful ticket verification when ticket is in approved state
    and requester is the assigned owner or collaborator.
    """
    adapter = ITSMAdapter()

    # Assigned owner matching
    res = adapter.validate_ticket("JIRA-1001", requester_email="alice@example.com")
    assert res.valid is True
    assert res.code == "VALID"
    assert res.state == "In Progress"
    assert res.assignee == "alice@example.com"

    # Authorized collaborator matching
    res_collab = adapter.validate_ticket("JIRA-1001", requester_email="alice_collaborator@example.com")
    assert res_collab.valid is True
    assert res_collab.code == "VALID"

    # ServiceNow approved incident
    res_inc = adapter.validate_ticket("INC-9911", requester_email="alice@example.com")
    assert res_inc.valid is True
    assert res_inc.state == "Approved"


def test_itsm_ticket_not_found():
    """
    P7-04: Verifies rejection with TICKET_NOT_FOUND when ticket does not exist.
    """
    adapter = ITSMAdapter()
    res = adapter.validate_ticket("JIRA-9999", requester_email="alice@example.com")
    assert res.valid is False
    assert res.code == "TICKET_NOT_FOUND"
    assert "not found" in res.reason.lower()


def test_itsm_ticket_invalid_state_rejected():
    """
    P7-04: Verifies rejection with TICKET_INVALID_STATE when ticket is closed/resolved.
    """
    adapter = ITSMAdapter()
    res = adapter.validate_ticket("JIRA-1002", requester_email="alice@example.com")
    assert res.valid is False
    assert res.code == "TICKET_INVALID_STATE"
    assert res.state == "Closed"
    assert "closed" in res.reason.lower()


def test_itsm_ticket_assignee_mismatch_rejected():
    """
    P7-04: Anti-hijacking check: Verifies rejection with TICKET_ASSIGNEE_MISMATCH
    when requester is not the assigned owner or approved collaborator.
    """
    adapter = ITSMAdapter()
    # JIRA-1003 is assigned to bob@example.com
    res = adapter.validate_ticket("JIRA-1003", requester_email="alice@example.com")
    assert res.valid is False
    assert res.code == "TICKET_ASSIGNEE_MISMATCH"
    assert "not the assigned owner" in res.reason.lower()


def test_itsm_timeout_handling_and_fail_closed():
    """
    P7-04: Verifies timeout protection and default fail-closed rejection.
    """
    adapter = ITSMAdapter(timeout_seconds=3.0, fallback_mode="fail_closed")

    res = adapter.validate_ticket("TIMEOUT-TICKET", requester_email="alice@example.com")
    assert res.valid is False
    assert res.code == "TICKET_TIMEOUT"
    assert res.is_provider_unavailable is True

    # Fallback under fail_closed -> Denied
    allow, msg = adapter.evaluate_fallback(res)
    assert allow is False
    assert "fail-closed" in msg.lower()


def test_itsm_outage_manual_approval_fallback():
    """
    P7-04: Verifies that when fallback_mode is configured as manual_approval,
    the request is accepted with a degraded status flag.
    """
    adapter = ITSMAdapter(fallback_mode="manual_approval")

    res = adapter.validate_ticket("TIMEOUT-TICKET", requester_email="alice@example.com")
    assert res.valid is False
    assert res.is_provider_unavailable is True

    # Fallback under manual_approval -> Allowed with degraded warning
    allow, msg = adapter.evaluate_fallback(res)
    assert allow is True
    assert "degraded manual approval" in msg.lower()
    assert res.degraded_fallback_applied is True


def _setup_ticket_required_account(db: Session, fixtures: dict):
    """Helper to configure an account that strictly requires ticket verification."""
    asset = fixtures["asset_payment"]
    account = fixtures["acc_pay_admin"]
    account.requires_ticket = True
    db.commit()
    return asset, account


def test_request_submission_with_ticket_validation_lifecycle(client: TestClient, db_session: Session, seeded_fixtures: dict, policy_admin):
    """
    P7-04 E2E: Verifies access request submission validating ticket reference:
    1. Valid ticket (JIRA-1001) passes and logs TICKET_VALIDATED outbox event.
    2. Invalid state (JIRA-1002) rejected with 400 TICKET_INVALID_STATE.
    3. Assignee mismatch (JIRA-1003) rejected with 400 TICKET_ASSIGNEE_MISMATCH.
    4. Timeout under fail-closed rejected with 503 TICKET_TIMEOUT.
    """
    assert policy_admin.publish(policy_admin.propose()).status_code == 200
    alice = seeded_fixtures["alice"]
    asset, account = _setup_ticket_required_account(db_session, seeded_fixtures)
    headers = auth_headers(alice.id, alice.email)
    now = utc_now()

    def make_payload(ticket_ref):
        return {
            "asset_id": asset.id,
            "target_account_id": account.id,
            "requested_start_at": now.isoformat(),
            "requested_end_at": (now + timedelta(minutes=30)).isoformat(),
            "justification": "Database change window maintenance",
            "ticket_ref": ticket_ref,
        }

    # 1. Valid ticket succeeds
    resp_ok = client.post("/api/v1/requests", headers=headers, json=make_payload("JIRA-1001"))
    assert resp_ok.status_code == 201
    req_data = resp_ok.json()
    assert req_data["ticket_ref"] == "JIRA-1001"

    # Verify TICKET_VALIDATED audit outbox entry
    outbox_ok = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "TICKET_VALIDATED",
        AuditOutbox.actor_id == alice.id,
    ).first()
    assert outbox_ok is not None
    assert outbox_ok.payload["ticket_ref"] == "JIRA-1001"
    assert outbox_ok.payload["state"] == "In Progress"

    # 2. Closed ticket rejected
    resp_closed = client.post("/api/v1/requests", headers=headers, json=make_payload("JIRA-1002"))
    assert resp_closed.status_code == 422
    assert resp_closed.json()["code"] == "TICKET_INVALID_STATE"

    # 3. Assignee mismatch rejected
    resp_mismatch = client.post("/api/v1/requests", headers=headers, json=make_payload("JIRA-1003"))
    assert resp_mismatch.status_code == 422
    assert resp_mismatch.json()["code"] == "TICKET_ASSIGNEE_MISMATCH"

    # 4. Timeout rejected under default fail_closed policy
    itsm_adapter.fallback_mode = "fail_closed"
    resp_timeout = client.post("/api/v1/requests", headers=headers, json=make_payload("TIMEOUT-TICKET"))
    assert resp_timeout.status_code == 503
    assert resp_timeout.json()["code"] == "TICKET_TIMEOUT"


def test_request_submission_with_degraded_manual_approval_fallback(client: TestClient, db_session: Session, seeded_fixtures: dict, policy_admin):
    """
    P7-04 E2E: When ticketing provider is down and policy permits manual_approval fallback,
    the request is allowed and logs TICKET_VALIDATION_DEGRADED.
    """
    assert policy_admin.publish(policy_admin.propose()).status_code == 200
    alice = seeded_fixtures["alice"]
    asset, account = _setup_ticket_required_account(db_session, seeded_fixtures)
    headers = auth_headers(alice.id, alice.email)
    now = utc_now()

    itsm_adapter.fallback_mode = "manual_approval"

    resp = client.post(
        "/api/v1/requests",
        headers=headers,
        json={
            "asset_id": asset.id,
            "target_account_id": account.id,
            "requested_start_at": now.isoformat(),
            "requested_end_at": (now + timedelta(minutes=30)).isoformat(),
            "justification": "Emergency maintenance while ticketing is down",
            "ticket_ref": "TIMEOUT-TICKET",
        },
    )
    assert resp.status_code == 201

    # Verify TICKET_VALIDATION_DEGRADED audit event
    outbox_degraded = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "TICKET_VALIDATION_DEGRADED",
        AuditOutbox.actor_id == alice.id,
    ).first()
    assert outbox_degraded is not None
    assert outbox_degraded.payload["ticket_ref"] == "TIMEOUT-TICKET"
    assert outbox_degraded.payload["code"] == "TICKET_TIMEOUT"


def test_admin_itsm_status_and_validate_probe(client: TestClient, seeded_fixtures: dict):
    """
    P7-04: Verifies admin endpoints:
    - GET /api/v1/admin/integrations/itsm/status
    - POST /api/v1/admin/integrations/itsm/validate-ticket
    - RBAC: Alice denied with 403 Forbidden. Dave succeeds.
    """
    alice = seeded_fixtures["alice"]
    dave = seeded_fixtures["dave"]

    # Alice denied
    resp_alice = client.get(
        "/api/v1/admin/integrations/itsm/status",
        headers=auth_headers(alice.id, alice.email),
    )
    assert resp_alice.status_code == 403
    assert resp_alice.json()["code"] == "NOT_PERMITTED"

    # Dave gets status
    resp_dave = client.get(
        "/api/v1/admin/integrations/itsm/status",
        headers=auth_headers(dave.id, dave.email),
    )
    assert resp_dave.status_code == 200
    status_data = resp_dave.json()
    assert "provider" in status_data
    assert "allowed_states" in status_data
    assert "timeout_seconds" in status_data
    assert "metrics" in status_data

    # Dave runs validation probe
    resp_probe = client.post(
        "/api/v1/admin/integrations/itsm/validate-ticket",
        headers=auth_headers(dave.id, dave.email),
        params={"ticket_ref": "JIRA-1001", "requester_email": "alice@example.com"},
    )
    assert resp_probe.status_code == 200
    probe_data = resp_probe.json()
    assert probe_data["validation_result"]["valid"] is True
    assert probe_data["validation_result"]["state"] == "In Progress"
