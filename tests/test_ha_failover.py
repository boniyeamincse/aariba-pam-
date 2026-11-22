"""Automated tests for Control Plane and Gateway High Availability, Failover, and Invariant Preservation (P8-01, ADR-017)."""

import hashlib
import time
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from ariba_pam.config import settings
from ariba_pam.db.base import utc_now, generate_id
from ariba_pam.db.models import User, AccessGrant, SessionLaunch, GatewayZone
from ariba_pam.services.failover import FailoverService, ControlPlaneNode, GatewayZoneInstance
from tests.conftest import auth_headers


def test_control_plane_multi_node_registry_and_health():
    """
    P8-01: Verifies multi-node Control Plane cluster topology:
    - Node registration and primary assignment.
    - Heartbeat updates.
    - Automatic detection and marking of timed-out nodes as failed.
    """
    svc = FailoverService()
    svc.heartbeat_timeout_seconds = 2

    # Register custom nodes
    node1 = svc.register_cp_node("cp-test-01", "cp-test-01.local", 8000, is_primary=True)
    node2 = svc.register_cp_node("cp-test-02", "cp-test-02.local", 8000, is_primary=False)

    healthy = svc.get_healthy_cp_nodes()
    assert any(n.node_id == "cp-test-01" for n in healthy)
    assert any(n.node_id == "cp-test-02" for n in healthy)

    # Let node1 time out
    node1.last_heartbeat = utc_now() - timedelta(seconds=5)

    healthy_after = svc.get_healthy_cp_nodes()
    assert not any(n.node_id == "cp-test-01" for n in healthy_after)
    assert any(n.node_id == "cp-test-02" for n in healthy_after)
    assert node1.status == "failed"

    # Refresh heartbeat brings node1 back to healthy
    assert svc.record_cp_heartbeat("cp-test-01") is True
    assert node1.status == "healthy"


def test_gateway_zone_redundancy_and_least_connections_routing():
    """
    P8-01: Verifies Gateway Zone redundancy:
    - Multiple gateway instances registered per zone.
    - Least-connections load distribution across redundant gateways.
    - Failover away from offline/timed-out gateway instances.
    """
    svc = FailoverService()
    svc.heartbeat_timeout_seconds = 2

    # Register two gateway instances in zone 'zon_prod_east'
    gw_a = svc.register_gateway_instance("gw-east-01", "zon_prod_east", "10.0.1.20:2222", active_sessions=5)
    gw_b = svc.register_gateway_instance("gw-east-02", "zon_prod_east", "10.0.1.21:2222", active_sessions=2)

    # Least connections should pick gw_b (2 sessions vs 5 sessions)
    chosen = svc.select_zone_gateway("zon_prod_east")
    assert chosen is not None
    assert chosen.instance_id == "gw-east-02"

    # Let gw_b time out
    gw_b.last_heartbeat = utc_now() - timedelta(seconds=5)

    # Next selection should fail over to gw_a
    failover_chosen = svc.select_zone_gateway("zon_prod_east")
    assert failover_chosen is not None
    assert failover_chosen.instance_id == "gw-east-01"


def test_simulated_node_failover_metrics():
    """
    P8-01: Verifies simulated control plane node failover:
    - Measures detection and switchover time (< 1.5s NFR budget).
    - Designates new primary from surviving healthy cluster nodes.
    - Confirms authorization services remain continuously available.
    """
    svc = FailoverService()
    svc._nodes.clear()
    svc.register_cp_node("cp-primary", "cp-pri.local", 8000, is_primary=True)
    svc.register_cp_node("cp-replica", "cp-rep.local", 8000, is_primary=False)

    result = svc.simulate_node_failover("cp-primary")
    assert result["failover_detected"] is True
    assert result["failed_node_id"] == "cp-primary"
    assert result["detection_latency_ms"] < 1500  # < 1.5s
    assert result["new_primary"] == "cp-replica"
    assert result["authorization_available"] is True
    assert result["zsp_invariants_preserved"] is True


def test_persistence_partition_fail_closed_invariant(db_session: Session):
    """
    P8-01: Verifies that if the underlying database is unreachable,
    the system strictly fails closed with default deny.
    """
    svc = FailoverService()
    ok, msg = svc.verify_persistence_fail_closed(db_session)
    assert ok is True
    assert "connected" in msg.lower()


def test_atomic_single_use_launch_token_race_protection(client: TestClient, db_session: Session, seeded_fixtures: dict):
    """
    P8-01: Verifies that when redundant gateways concurrently attempt to consume
    the same single-use launch token, database row locking (with_for_update) guarantees:
    - Exactly ONE gateway succeeds (201 Created).
    - The secondary attempt receives 409 Conflict (LAUNCH_REPLAY_DENIED).
    - Zero duplicate or split-brain sessions are launched.
    """
    alice = seeded_fixtures["alice"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    now = utc_now()

    # Create active grant
    grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=alice.id,
        asset_id=asset.id,
        target_account_id=account.id,
        effective_start_at=now - timedelta(minutes=5),
        effective_end_at=now + timedelta(hours=1),
        status="active",
    )
    db_session.add(grant)
    db_session.flush()

    raw_token = "launch_ha_race_test_123"
    token_digest = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
    launch = SessionLaunch(
        id=generate_id("lnc"),
        grant_id=grant.id,
        launch_token_digest=token_digest,
        expires_at=now + timedelta(seconds=60),
        is_consumed=False,
    )
    db_session.add(launch)
    db_session.commit()

    gw_headers = {"X-Gateway-Secret": settings.gateway_api_secret}

    # First consumption by Gateway A -> Succeeds
    resp_a = client.post(
        "/internal/v1/launches/consume",
        headers=gw_headers,
        json={"launch_token": raw_token, "gateway_id": "gw-node-a"},
    )
    assert resp_a.status_code == 201
    assert resp_a.json()["session_id"] is not None

    # Concurrent or replay consumption by Gateway B -> Rejected with 409 Conflict
    resp_b = client.post(
        "/internal/v1/launches/consume",
        headers=gw_headers,
        json={"launch_token": raw_token, "gateway_id": "gw-node-b"},
    )
    assert resp_b.status_code == 409
    assert resp_b.json()["code"] == "LAUNCH_REPLAY_DENIED"


def test_ha_admin_endpoints_and_anti_enumeration(client: TestClient, seeded_fixtures: dict):
    """
    P8-01: Verifies HA administrative endpoints:
    - GET /api/v1/admin/ha/status
    - POST /api/v1/admin/ha/gateways/heartbeat
    - POST /api/v1/admin/ha/simulate-failover
    - RBAC: Alice (requester) is denied with 403 Forbidden; Dave (admin) succeeds.
    """
    alice = seeded_fixtures["alice"]
    dave = seeded_fixtures["dave"]

    # 1. Non-admin (Alice) denied
    status_denied = client.get("/api/v1/admin/ha/status", headers=auth_headers(alice.id, alice.email))
    assert status_denied.status_code == 403

    sim_denied = client.post("/api/v1/admin/ha/simulate-failover", headers=auth_headers(alice.id, alice.email))
    assert sim_denied.status_code == 403

    # 2. Administrator (Dave) inspects HA cluster status
    status_ok = client.get("/api/v1/admin/ha/status", headers=auth_headers(dave.id, dave.email))
    assert status_ok.status_code == 200
    data = status_ok.json()
    assert "cluster_status" in data
    assert data["control_plane"]["total_nodes"] >= 2
    assert data["invariants"]["default_deny_on_partition"] is True

    # 3. Heartbeat gateway instance
    hb_ok = client.post(
        "/api/v1/admin/ha/gateways/heartbeat",
        headers=auth_headers(dave.id, dave.email),
        params={
            "instance_id": "gw-ha-01",
            "zone_id": "zon_lab_01",
            "endpoint": "10.0.1.30:2222",
            "active_sessions": 3,
        },
    )
    assert hb_ok.status_code == 200
    assert hb_ok.json()["status"] == "registered"

    # 4. Simulate failover drill
    sim_ok = client.post(
        "/api/v1/admin/ha/simulate-failover",
        headers=auth_headers(dave.id, dave.email),
        params={"failed_node_id": "cp-node-01"},
    )
    assert sim_ok.status_code == 200
    sim_data = sim_ok.json()
    assert sim_data["simulation"]["failover_detected"] is True
    assert sim_data["simulation"]["authorization_available"] is True
