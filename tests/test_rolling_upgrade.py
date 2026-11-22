"""Automated tests for zero-downtime rolling upgrades, Expand/Contract schema evolution, and rollback under load (P8-02, ADR-018)."""

from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text
from ariba_pam.config import settings
from ariba_pam.db.base import utc_now, generate_id
from ariba_pam.db.models import User, AccessGrant, AccessSession, SessionLaunch, AuditOutbox
from ariba_pam.services.upgrade import RollingUpgradeService, rolling_upgrade_service
from tests.conftest import auth_headers


def test_expand_contract_schema_compatibility():
    """
    P8-02: Verifies that schema changes are validated against Expand/Contract invariants:
    - Additive changes (nullable columns, columns with defaults) are accepted.
    - Breaking changes (immediate column drops, renames, NOT NULL without default) are rejected.
    """
    svc = RollingUpgradeService()

    # 1. Valid non-breaking additive schema changes
    valid_ddl = [
        "ALTER TABLE assets ADD COLUMN maintenance_window_hours INT DEFAULT 4",
        "ALTER TABLE users ADD COLUMN external_sync_id VARCHAR(128) NULL",
        "CREATE TABLE asset_tags (id VARCHAR(64) PRIMARY KEY, asset_id VARCHAR(64))",
    ]
    ok, violations = svc.validate_schema_compatibility(valid_ddl)
    assert ok is True
    assert len(violations) == 0

    # 2. Breaking schema changes that violate Expand/Contract
    breaking_ddl = [
        "ALTER TABLE assets DROP COLUMN host",
        "ALTER TABLE users RENAME COLUMN email TO primary_email",
        "ALTER TABLE target_accounts ADD COLUMN security_zone_tier VARCHAR(32) NOT NULL",
    ]
    ok_break, break_violations = svc.validate_schema_compatibility(breaking_ddl)
    assert ok_break is False
    assert len(break_violations) == 3
    assert any("DROP COLUMN" in v for v in break_violations)
    assert any("RENAME COLUMN" in v for v in break_violations)
    assert any("NOT NULL" in v for v in break_violations)


def test_active_session_lease_renewal_during_node_drain_and_restart(client: TestClient, db_session: Session, seeded_fixtures: dict):
    """
    P8-02 E2E: Verifies that when a control plane node is drained and restarted during an upgrade,
    active sessions continue renewing leases without interruption or session termination.
    """
    alice = seeded_fixtures["alice"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    now = utc_now()

    # Create active grant, launch, and session
    grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=alice.id,
        asset_id=asset.id,
        target_account_id=account.id,
        effective_start_at=now - timedelta(minutes=10),
        effective_end_at=now + timedelta(hours=2),
        status="active",
    )
    db_session.add(grant)
    db_session.flush()

    session = AccessSession(
        id=generate_id("ses"),
        grant_id=grant.id,
        launch_id=generate_id("lnc"),
        gateway_id="gw_lab_01",
        status="active",
        started_at=now - timedelta(minutes=5),
    )
    db_session.add(session)
    db_session.commit()

    gw_headers = {"X-Gateway-Secret": settings.gateway_api_secret}

    # Simulate lease renewal before upgrade
    resp_pre = client.post(f"/internal/v1/sessions/{session.id}/renew", headers=gw_headers)
    assert resp_pre.status_code == 200
    pre_deadline = resp_pre.json()["lease_deadline"]

    # Drain node 1
    rolling_upgrade_service.drain_node("cp-node-01")
    assert rolling_upgrade_service._nodes["cp-node-01"].status == "draining"

    # In-flight lease renewal during drain succeeds seamlessly on surviving cluster capacity
    resp_during = client.post(f"/internal/v1/sessions/{session.id}/renew", headers=gw_headers)
    assert resp_during.status_code == 200
    during_deadline = resp_during.json()["lease_deadline"]
    assert during_deadline >= pre_deadline

    # Upgrade and activate node 1
    rolling_upgrade_service.upgrade_node("cp-node-01", "1.1.0")
    assert rolling_upgrade_service._nodes["cp-node-01"].status == "active"
    assert rolling_upgrade_service._nodes["cp-node-01"].version == "1.1.0"

    # Post-upgrade renewal succeeds without drop
    resp_post = client.post(f"/internal/v1/sessions/{session.id}/renew", headers=gw_headers)
    assert resp_post.status_code == 200


def test_rolling_upgrade_drill_under_load(client: TestClient, db_session: Session, seeded_fixtures: dict):
    """
    P8-02: Verifies simulated rolling upgrade under concurrent session load:
    - 100% of tested sessions remain intact (0% session drop rate).
    - Transactional audit outbox records CLUSTER_ROLLING_UPGRADE_COMPLETED event.
    """
    dave = seeded_fixtures["dave"]

    resp = client.post(
        "/api/v1/admin/upgrade/simulate-roll",
        headers=auth_headers(dave.id, dave.email),
        params={"simulated_active_sessions": 30},
    )
    assert resp.status_code == 200
    data = resp.json()["drill_result"]
    assert data["status"] == "success"
    assert data["session_loss_rate_percent"] == 0.0
    assert data["session_renewals_succeeded"] == 30
    assert data["session_renewals_failed"] == 0

    # Verify audit event in DB
    audit_evt = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "CLUSTER_ROLLING_UPGRADE_COMPLETED"
    ).first()
    assert audit_evt is not None
    assert audit_evt.payload["sessions_preserved"] == 30


def test_deployment_rollback_under_load(client: TestClient, db_session: Session, seeded_fixtures: dict):
    """
    P8-02: Verifies simulated deployment rollback under concurrent active session load:
    - Rollback from v1.1.0 to v1.0.0 preserves 100% of sessions.
    - Transactional audit outbox records CLUSTER_ROLLBACK_COMPLETED event.
    """
    dave = seeded_fixtures["dave"]

    resp = client.post(
        "/api/v1/admin/upgrade/simulate-rollback",
        headers=auth_headers(dave.id, dave.email),
        params={"simulated_active_sessions": 25},
    )
    assert resp.status_code == 200
    data = resp.json()["drill_result"]
    assert data["status"] == "success"
    assert data["session_loss_rate_percent"] == 0.0
    assert data["session_renewals_succeeded"] == 25
    assert data["session_renewals_failed"] == 0

    # Verify audit event in DB
    audit_evt = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "CLUSTER_ROLLBACK_COMPLETED"
    ).first()
    assert audit_evt is not None
    assert audit_evt.payload["sessions_preserved"] == 25


def test_admin_upgrade_endpoints_and_anti_enumeration(client: TestClient, seeded_fixtures: dict):
    """
    P8-02: Verifies upgrade administration endpoints and RBAC boundaries:
    - GET /api/v1/admin/upgrade/status
    - Alice (requester) is denied with 403 Forbidden.
    - Dave (admin) succeeds.
    """
    alice = seeded_fixtures["alice"]
    dave = seeded_fixtures["dave"]

    # Alice denied
    denied_status = client.get("/api/v1/admin/upgrade/status", headers=auth_headers(alice.id, alice.email))
    assert denied_status.status_code == 403

    denied_roll = client.post("/api/v1/admin/upgrade/simulate-roll", headers=auth_headers(alice.id, alice.email))
    assert denied_roll.status_code == 403

    # Dave succeeds
    ok_status = client.get("/api/v1/admin/upgrade/status", headers=auth_headers(dave.id, dave.email))
    assert ok_status.status_code == 200
    status_data = ok_status.json()
    assert "current_app_version" in status_data
    assert "current_schema_version" in status_data
    assert status_data["expand_contract_enforced"] is True
    assert len(status_data["nodes"]) >= 2
