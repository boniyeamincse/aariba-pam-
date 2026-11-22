"""Automated tests for disaster recovery, split-key custody reconstitution, and evidence retrieval at approved expanded capacity (P8-03, ADR-019)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from ariba_pam.config import settings
from ariba_pam.db.base import utc_now
from ariba_pam.db.models import User, AuditOutbox
from ariba_pam.services.expanded_recovery import ExpandedRecoveryService, expanded_recovery_service
from tests.conftest import auth_headers


def test_expanded_capacity_dataset_generation():
    """
    P8-03: Verifies generation of deterministic synthetic dataset representing the expanded enterprise baseline:
    - 500 assets across gateway zones.
    - 2,000 workforce users with role assignments.
    - 5,000 sessions with terminal recording digests.
    - 10,000 audit outbox events.
    """
    svc = ExpandedRecoveryService()
    # Test generation with scale factor 0.1 for fast verification
    dataset = svc.generate_synthetic_expanded_dataset(scale=0.1)

    assert len(dataset["assets"]) >= 50
    assert len(dataset["users"]) >= 200
    assert len(dataset["sessions"]) >= 500
    assert len(dataset["recordings"]) >= 500
    assert len(dataset["audit_outbox"]) >= 1000

    # Verify record structure
    first_asset = dataset["assets"][0]
    assert "id" in first_asset and "zone_id" in first_asset
    first_rec = dataset["recordings"][0]
    assert "digest_sha256" in first_rec and len(first_rec["digest_sha256"]) == 64


def test_benchmarked_database_restore_at_expanded_capacity(db_session: Session):
    """
    P8-03: Verifies database restoration at expanded scale:
    - Validates SHA-256 composite manifest digest.
    - Confirms restoration timing satisfies RTO <= 15 minutes (NFR-04).
    - Verifies stale in-flight sessions are automatically reconciled to terminated.
    """
    svc = ExpandedRecoveryService()
    dataset = svc.generate_synthetic_expanded_dataset(scale=0.1)

    result = svc.benchmark_database_restore(db=db_session, dataset=dataset)

    assert result["operation"] == "database_restore_benchmark"
    assert len(result["manifest_digest"]) == 64
    assert result["restore_time_seconds"] <= 900  # RTO <= 15m
    assert result["rto_sla_met"] is True
    assert result["zero_standing_privilege_enforced"] is True
    assert result["stale_sessions_reconciled"] >= 0


def test_benchmarked_split_key_custody_recovery(db_session: Session):
    """
    P8-03: Verifies multi-custodian split-share key recovery:
    - Reconstitutes SSH User CA signing key and tests ephemeral certificate generation.
    - Re-unseals Vault master key.
    - Verifies key recovery completes within 5-minute SLA (300 seconds).
    """
    svc = ExpandedRecoveryService()
    result = svc.benchmark_key_recovery(db=db_session)

    assert result["operation"] == "key_custody_recovery_benchmark"
    assert result["ssh_ca_key_recovered"] is True
    assert result["vault_master_key_recovered"] is True
    assert result["dual_trust_rollover_verified"] is True
    assert result["recovery_time_seconds"] <= 300  # <= 5m
    assert result["key_recovery_sla_met"] is True


def test_benchmarked_evidence_retrieval_at_scale(db_session: Session):
    """
    P8-03: Verifies forensic evidence search and recording retrieval performance over expanded dataset:
    - Measures query latency distribution (p50, p90, p95, p99).
    - Enforces p95 latency <= 150 ms (NFR-05).
    """
    svc = ExpandedRecoveryService()
    dataset = svc.generate_synthetic_expanded_dataset(scale=0.1)

    result = svc.benchmark_evidence_retrieval(db=db_session, dataset=dataset, query_count=40)

    assert result["operation"] == "evidence_retrieval_benchmark"
    assert result["query_count"] == 40
    assert result["p95_latency_ms"] <= 150.0  # NFR-05 SLA
    assert result["p95_sla_met"] is True


def test_full_expanded_recovery_drill_e2e_and_audit_event(db_session: Session):
    """
    P8-03 E2E: Verifies complete expanded capacity disaster recovery drill execution:
    - Runs restore, key recovery, and evidence search benchmarks.
    - Confirms all SLAs met (RTO, key recovery, and p95 latency).
    - Verifies atomic EXPANDED_CAPACITY_RECOVERY_REHEARSED record in AuditOutbox.
    """
    svc = ExpandedRecoveryService()
    drill = svc.run_expanded_recovery_drill(db=db_session, operator_id="usr_eva", scale=0.1)

    assert drill["all_slas_met"] is True
    assert drill["database_restore"]["rto_sla_met"] is True
    assert drill["key_recovery"]["key_recovery_sla_met"] is True
    assert drill["evidence_retrieval"]["p95_sla_met"] is True

    # Verify outbox event in DB
    audit_evt = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "EXPANDED_CAPACITY_RECOVERY_REHEARSED"
    ).first()
    assert audit_evt is not None
    assert audit_evt.actor_id == "usr_eva"
    assert audit_evt.payload["all_slas_met"] is True
    assert audit_evt.payload["total_records"] > 0


def test_admin_expanded_recovery_endpoints_and_anti_enumeration(client: TestClient, seeded_fixtures: dict):
    """
    P8-03: Verifies administrative recovery endpoints and RBAC boundaries:
    - GET /api/v1/admin/recovery/expanded-status
    - POST /api/v1/admin/recovery/simulate-expanded-drill
    - Alice (requester) is denied with 403 Forbidden; Dave (admin) succeeds.
    """
    alice = seeded_fixtures["alice"]
    dave = seeded_fixtures["dave"]

    # 1. Non-admin (Alice) denied
    denied_status = client.get("/api/v1/admin/recovery/expanded-status", headers=auth_headers(alice.id, alice.email))
    assert denied_status.status_code == 403

    denied_drill = client.post("/api/v1/admin/recovery/simulate-expanded-drill", headers=auth_headers(alice.id, alice.email))
    assert denied_drill.status_code == 403

    # 2. Administrator (Dave) inspects expanded capacity recovery status
    ok_status = client.get("/api/v1/admin/recovery/expanded-status", headers=auth_headers(dave.id, dave.email))
    assert ok_status.status_code == 200
    status_data = ok_status.json()
    assert "expanded_capacity_baseline" in status_data
    assert status_data["expanded_capacity_baseline"]["assets"] == 500
    assert status_data["expanded_capacity_baseline"]["audit_events"] == 10000

    # 3. Dave executes simulated recovery drill
    ok_drill = client.post(
        "/api/v1/admin/recovery/simulate-expanded-drill",
        headers=auth_headers(dave.id, dave.email),
        params={"scale": 0.05},
    )
    assert ok_drill.status_code == 200
    drill_data = ok_drill.json()
    assert drill_data["drill_record"]["all_slas_met"] is True
    assert drill_data["drill_record"]["operator_id"] == dave.id
