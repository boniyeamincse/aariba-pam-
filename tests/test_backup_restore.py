"""Disaster recovery backup and restore rehearsal tests (Phase 5 / P5-07, NFR-04, T-09)."""

import time
from datetime import timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.db.models import (
    AccessSession,
    AccessGrant,
    SessionLaunch,
    AuditOutbox,
    BackupRehearsalRecord,
)
from ariba_pam.services.backup import BackupRestoreService
from ariba_pam.core.errors import ConflictException
from tests.conftest import auth_headers


def _setup_active_grant_and_session(db: Session, fixtures: dict):
    """Helper to provision active grant and session for DR testing."""
    alice = fixtures["alice"]
    asset = fixtures["asset_payment"]
    account = fixtures["acc_pay_admin"]
    now = utc_now()

    grant = AccessGrant(
        id=generate_id("grn"),
        revision_id=generate_id("rev"),
        requester_id=alice.id,
        asset_id=asset.id,
        target_account_id=account.id,
        effective_start_at=now - timedelta(minutes=5),
        effective_end_at=now + timedelta(minutes=30),
        status="active",
    )
    db.add(grant)
    db.flush()

    launch = SessionLaunch(
        id=generate_id("lau"),
        grant_id=grant.id,
        launch_token_digest="digest_dr_test_launch",
        expires_at=now + timedelta(minutes=1),
        is_consumed=True,
    )
    db.add(launch)
    db.flush()

    session = AccessSession(
        id=generate_id("ses"),
        grant_id=grant.id,
        launch_id=launch.id,
        gateway_id="gw_zone_internal",
        status="active",
        started_at=now,
    )
    db.add(session)
    db.commit()
    return grant, launch, session


def test_backup_snapshot_creation_and_manifest_digest(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    NFR-04: Backup service generates a complete point-in-time snapshot with SHA-256
    manifest digest and records an atomic audit outbox event.
    """
    grant, launch, session = _setup_active_grant_and_session(db_session, seeded_fixtures)

    snapshot = BackupRestoreService.create_snapshot(
        db=db_session,
        label="rehearsal_test_01",
        operator_id=seeded_fixtures["dave"].id,
    )

    assert snapshot["snapshot_id"].startswith("snp_")
    assert snapshot["label"] == "rehearsal_test_01"
    assert len(snapshot["manifest_sha256"]) == 64
    assert snapshot["table_counts"]["users"] >= 4
    assert snapshot["table_counts"]["access_grants"] >= 1
    assert snapshot["table_counts"]["access_sessions"] >= 1

    # Check audit outbox record
    outbox_entry = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "BACKUP_SNAPSHOT_CREATED",
        AuditOutbox.actor_id == seeded_fixtures["dave"].id,
    ).first()
    assert outbox_entry is not None
    assert outbox_entry.payload["snapshot_id"] == snapshot["snapshot_id"]


def test_backup_restore_rehearsal_meets_rto_and_rpo(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    NFR-04, T-09: Disaster recovery rehearsal executes, measures RTO <= 15m (900s)
    and RPO <= 1m (60s), and verifies WORM integrity on restored evidence.
    """
    grant, launch, session = _setup_active_grant_and_session(db_session, seeded_fixtures)
    dave = seeded_fixtures["dave"]

    snapshot = BackupRestoreService.create_snapshot(db_session, label="rto_rpo_test", operator_id=dave.id)

    record = BackupRestoreService.execute_restore_rehearsal(
        snapshot=snapshot,
        target_db=db_session,
        exercise_ref="EX-2026-DR-REHEARSAL-01",
        operator_id=dave.id,
        simulated_data_loss_seconds=15.0,
    )

    assert record.status == "completed"
    assert record.rto_seconds <= 900.0  # RTO <= 15 minutes
    assert record.rpo_seconds <= 60.0   # RPO <= 1 minute
    assert record.worm_verified is True
    assert record.exercise_ref == "EX-2026-DR-REHEARSAL-01"

    # Verify audit event for rehearsal
    reh_audit = db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "BACKUP_RESTORE_REHEARSAL_COMPLETED",
        AuditOutbox.actor_id == dave.id,
    ).first()
    assert reh_audit is not None
    assert reh_audit.payload["exercise_ref"] == "EX-2026-DR-REHEARSAL-01"


def test_stale_and_expired_grants_reconciled_fail_closed(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Critical Security Invariant (T-09):
    A database restore must NEVER resurrect stale, expired, or revoked access.
    Grants whose validity window ended during an outage must be reconciled to 'ended',
    and active sessions tied to them must be terminated fail-closed.
    """
    grant, launch, session = _setup_active_grant_and_session(db_session, seeded_fixtures)
    dave = seeded_fixtures["dave"]

    snapshot = BackupRestoreService.create_snapshot(db_session, label="stale_grant_test", operator_id=dave.id)

    # Simulate that time has advanced past the grant's validity window:
    # Modify the grant in snapshot data so effective_end_at is 10 minutes in the past
    past_time = (utc_now() - timedelta(minutes=10)).isoformat()
    for g in snapshot["data"]["access_grants"]:
        if g["id"] == grant.id:
            g["effective_end_at"] = past_time

    # Update manifest digest so snapshot integrity matches modified test data
    snapshot["manifest_sha256"] = BackupRestoreService.compute_manifest_digest(snapshot["data"])

    # Clear current DB grant, launch, and session to simulate fresh restore into staging DB
    db_session.delete(session)
    db_session.delete(launch)
    db_session.delete(grant)
    db_session.commit()

    # Execute restore rehearsal
    record = BackupRestoreService.execute_restore_rehearsal(
        snapshot=snapshot,
        target_db=db_session,
        exercise_ref="EX-2026-STALE-GRANT-CHECK",
        operator_id=dave.id,
    )

    assert record.reconciled_grants_count >= 1
    assert record.reconciled_sessions_count >= 1

    # Verify the restored grant is ended
    restored_grant = db_session.get(AccessGrant, grant.id)
    assert restored_grant is not None
    assert restored_grant.status == "ended"

    # Verify the restored session is ended with explicit termination reason
    restored_session = db_session.get(AccessSession, session.id)
    assert restored_session is not None
    assert restored_session.status == "ended"
    assert "Reconciled after backup restore" in restored_session.termination_reason


def test_revoked_grant_preservation_after_restore(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    T-09: A grant that was revoked must remain revoked after a restore.
    """
    grant, launch, session = _setup_active_grant_and_session(db_session, seeded_fixtures)
    dave = seeded_fixtures["dave"]

    grant.status = "revoked"
    db_session.commit()

    snapshot = BackupRestoreService.create_snapshot(db_session, label="revoked_grant_test", operator_id=dave.id)

    # Delete locally to simulate restoration
    db_session.delete(session)
    db_session.delete(launch)
    db_session.delete(grant)
    db_session.commit()

    record = BackupRestoreService.execute_restore_rehearsal(
        snapshot=snapshot,
        target_db=db_session,
        exercise_ref="EX-2026-REVOKED-PRESERVATION",
        operator_id=dave.id,
    )

    restored_grant = db_session.get(AccessGrant, grant.id)
    assert restored_grant is not None
    assert restored_grant.status == "revoked"


def test_tampered_snapshot_rejected_fail_closed(db_session: Session, seeded_fixtures: dict):
    """
    T-09: If snapshot data is tampered with or modified without manifest update,
    restore rehearsal aborts immediately fail-closed with SNAPSHOT_CORRUPTED.
    """
    dave = seeded_fixtures["dave"]
    snapshot = BackupRestoreService.create_snapshot(db_session, label="tamper_test", operator_id=dave.id)

    # Tamper with user email without updating manifest_sha256
    if snapshot["data"]["users"]:
        snapshot["data"]["users"][0]["email"] = "tampered@adversary.com"

    try:
        BackupRestoreService.execute_restore_rehearsal(
            snapshot=snapshot,
            target_db=db_session,
            exercise_ref="EX-TAMPER-TEST",
            operator_id=dave.id,
        )
        assert False, "Should have raised ConflictException"
    except ConflictException as e:
        assert e.code == "SNAPSHOT_CORRUPTED"


def test_admin_backup_api_endpoints_and_rbac(client: TestClient, seeded_fixtures: dict):
    """
    RBAC verification:
    - Admin/Operator can create snapshots, run rehearsals, and list reports.
    - Regular users (e.g. Alice) are denied with 403 Forbidden.
    """
    alice = seeded_fixtures["alice"]
    dave = seeded_fixtures["dave"]

    # 1. Alice denied snapshot creation
    resp_denied = client.post(
        "/api/v1/admin/backup/snapshots",
        headers=auth_headers(alice.id, alice.email),
        json={"label": "unauthorized_snapshot"},
    )
    assert resp_denied.status_code == 403
    assert resp_denied.json()["code"] == "NOT_PERMITTED"

    # 2. Dave succeeds snapshot creation
    resp_snap = client.post(
        "/api/v1/admin/backup/snapshots",
        headers=auth_headers(dave.id, dave.email),
        json={"label": "api_test_snapshot"},
    )
    assert resp_snap.status_code == 201
    snap_data = resp_snap.json()
    assert snap_data["label"] == "api_test_snapshot"

    # 3. Dave executes restore rehearsal via API
    resp_reh = client.post(
        "/api/v1/admin/backup/restore-rehearsal",
        headers=auth_headers(dave.id, dave.email),
        json={
            "exercise_ref": "EX-API-DR-01",
            "simulated_data_loss_seconds": 10.0,
        },
    )
    assert resp_reh.status_code == 201
    reh_data = resp_reh.json()
    assert reh_data["status"] == "completed"
    assert reh_data["exercise_ref"] == "EX-API-DR-01"
    assert reh_data["rto_seconds"] <= 900.0
    assert reh_data["rpo_seconds"] <= 60.0

    # 4. Dave lists rehearsals
    resp_list = client.get(
        "/api/v1/admin/backup/rehearsals",
        headers=auth_headers(dave.id, dave.email),
    )
    assert resp_list.status_code == 200
    assert len(resp_list.json()) >= 1
    assert any(r["exercise_ref"] == "EX-API-DR-01" for r in resp_list.json())
