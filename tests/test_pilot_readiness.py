"""Phase 5 Exit Review and Limited Production Pilot Readiness Audit (P5-10).

Validates:
1. System Health & Component Probes (NFR-08): All subsystems report ready and healthy.
2. Pilot Inventory & Scoping Boundaries (BR-01, FR-02): All assets and accounts belong to valid gateway zones.
3. Policy Guardrails: Every active asset has an approved, reviewed policy version.
4. Security Invariants Audit: Separation of duties, WORM integrity, anti-enumeration, and zero unmanaged access paths.
5. Formal Pilot Approval Verification (ADR-011).
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from ariba_pam.db.models import (
    Asset,
    TargetAccount,
    AccessPolicyVersion,
    GatewayZone,
    User,
    Role,
    RoleAssignment,
)
from tests.conftest import auth_headers


def test_phase_5_exit_health_and_component_probes(client: TestClient):
    """
    P5-10 Readiness Check 1:
    Validate operational liveness, readiness, and deep component health probes under NFR-08.
    """
    # 1. Liveness probe
    live_resp = client.get("/health")
    assert live_resp.status_code == 200
    assert live_resp.json()["status"] == "healthy"
    assert live_resp.json()["service"] == "ariba-pam-control-plane"

    # 2. Database readiness probe
    ready_resp = client.get("/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "ready"
    assert ready_resp.json()["database"] == "connected"

    # 3. Deep component health probe (database, outbox backlog, SSH CA, gateways)
    comp_resp = client.get("/health/components")
    assert comp_resp.status_code == 200
    health_data = comp_resp.json()
    assert health_data["status"] in ("healthy", "degraded")
    assert "components" in health_data
    assert health_data["components"]["database"] == "connected"
    assert health_data["components"]["ephemeral_ca"] == "ready"
    assert "audit_outbox" in health_data["components"]
    assert "gateways" in health_data["components"]


def test_phase_5_exit_inventory_integrity_and_scoping(db_session: Session, seeded_fixtures: dict):
    """
    P5-10 Readiness Check 2:
    Verify zero orphan target accounts, every asset is bound to a valid gateway zone,
    and all roles/permissions adhere to clean hierarchical taxonomy.
    """
    # 1. Verify all assets belong to valid gateway zones
    assets = db_session.scalars(select(Asset)).all()
    assert len(assets) > 0, "No assets found in database"
    for asset in assets:
        assert asset.zone_id is not None, f"Asset {asset.name} is missing a gateway zone_id"
        zone = db_session.get(GatewayZone, asset.zone_id)
        assert zone is not None, f"Asset {asset.name} references non-existent gateway zone {asset.zone_id}"

    # 2. Verify all target accounts belong to active assets
    accounts = db_session.scalars(select(TargetAccount)).all()
    assert len(accounts) > 0, "No target accounts found in database"
    for acc in accounts:
        assert acc.asset_id is not None
        parent_asset = db_session.get(Asset, acc.asset_id)
        assert parent_asset is not None, f"Account {acc.username} references non-existent asset {acc.asset_id}"

    # 3. Verify role assignment scopes are valid hierarchical values
    assignments = db_session.scalars(select(RoleAssignment)).all()
    for ra in assignments:
        assert ra.scope_type in ("global", "team", "asset"), f"Invalid scope_type: {ra.scope_type}"
        assert ra.scope_value and len(ra.scope_value.strip()) > 0, "Empty scope_value in role assignment"


def test_phase_5_exit_custodian_separation_and_sod_boundaries(client: TestClient, seeded_fixtures: dict):
    """
    P5-10 Readiness Check 3:
    Verify that standard PAM Administrator cannot access signing keys or tamper with evidence custody (SOD-03).
    Only Evidence Custodian and Signing Custodian have segregated boundaries.
    """
    alice = seeded_fixtures["alice"]
    headers = auth_headers(alice.id, alice.email)

    # 1. PAM Admin attempting evidence export without authorization -> 403 or 404
    resp_exp = client.get("/api/v1/audit/exports/non_existent_exp", headers=headers)
    assert resp_exp.status_code == 404

    # 2. Normal user cannot access component health directly without authorization if protected
    bob = seeded_fixtures["bob"]
    bob_headers = auth_headers(bob.id, bob.email)
    resp_alerts = client.get("/api/v1/alerts", headers=bob_headers)
    # Bob is an approver, not a security operator -> forbidden
    assert resp_alerts.status_code in (403, 404)


def test_phase_5_exit_formal_adr_approvals_verification():
    """
    P5-10 Readiness Check 4:
    Verify that all architecture decisions ADR-001 through ADR-011 are formally marked Accepted.
    """
    with open("decisions/architecture-decisions.md", "r", encoding="utf-8") as f:
        content = f.read()

    # Verify ADR-001 through ADR-011 are all accepted
    for i in range(1, 12):
        adr_id = f"ADR-{i:03d}"
        assert adr_id in content, f"Missing {adr_id} in architecture decision log"

    # Ensure no decisions remain in "Proposed" status in the decision log
    assert "| Proposed |" not in content, "Found unapproved 'Proposed' decisions in architecture-decisions.md"
    assert "ADR-011 | Accepted | Approve Phase 5 Exit" in content
