"""Evidence Custodian, WORM integrity verification, and audit export tests (Phase 5 / P5-01, P5-04, P5-05)."""

import hashlib
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from ariba_pam.config import settings
from ariba_pam.db.base import generate_id, utc_now
from ariba_pam.db.models import (
    AccessSession,
    AccessGrant,
    SessionLaunch,
    SessionRecording,
    AuditOutbox,
    EvidenceExport,
)
from ariba_pam.services.audit import AuditService
from tests.conftest import auth_headers


def _create_test_session_and_grant(db: Session, fixtures: dict):
    """Helper to create an active grant and session for testing recordings."""
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
        effective_end_at=now + timedelta(minutes=55),
        status="active",
    )
    db.add(grant)
    db.flush()

    launch = SessionLaunch(
        id=generate_id("lau"),
        grant_id=grant.id,
        launch_token_digest="digest_test_launch_123",
        expires_at=now + timedelta(minutes=1),
        is_consumed=True,
    )
    db.add(launch)
    db.flush()

    session = AccessSession(
        id=generate_id("ses"),
        grant_id=grant.id,
        launch_id=launch.id,
        gateway_id="gw_lab_01",
        status="active",
        started_at=now,
    )
    db.add(session)
    db.commit()
    return session, grant


def test_worm_integrity_verification_success(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Verify WORM integrity passes when audit outbox records are untampered (P5-01 / T-08).
    Evidence Custodian / Auditor receives verified=True with valid record count.
    """
    eva = seeded_fixtures["eva"]
    eva_headers = auth_headers(eva.id, eva.email, ["pwd", "fido2"])

    # Seed several events with valid digests
    for i in range(5):
        AuditService.record_event(
            db=db_session,
            event_type="TEST_EVENT",
            correlation_id=f"corr_{i}",
            actor_id=eva.id,
            payload={"action": "test", "index": i},
        )
    db_session.commit()

    resp = client.post(
        "/api/v1/audit-events/verify-integrity",
        headers=eva_headers,
        json={"batch_limit": 50},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["verified"] is True
    assert data["events_checked"] >= 5
    assert len(data["tampered_event_ids"]) == 0
    assert data["hash_algorithm"] == "SHA-256"


def test_worm_integrity_verification_detects_tampering(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Verify WORM integrity check recalculates SHA-256 and detects modified payload (P5-01 / SEC-08).
    """
    eva = seeded_fixtures["eva"]
    eva_headers = auth_headers(eva.id, eva.email, ["pwd", "fido2"])

    # Record event with legitimate digest
    event = AuditService.record_event(
        db=db_session,
        event_type="FINANCIAL_TRANSFER_RECORDED",
        correlation_id="corr_tamper_target",
        actor_id=eva.id,
        payload={"amount": 1000, "currency": "USD"},
    )
    db_session.commit()

    # Adversary alters the database payload directly bypassing the application
    tampered_event = db_session.get(AuditOutbox, event.id)
    tampered_event.payload = {"amount": 9999999, "currency": "USD"}
    db_session.commit()

    resp = client.post(
        "/api/v1/audit-events/verify-integrity",
        headers=eva_headers,
        json={"batch_limit": 50},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verified"] is False
    assert event.id in data["tampered_event_ids"]
    assert "Integrity violations detected" in data["message"]


def test_custodian_boundary_separation_denies_pam_admin(client: TestClient, seeded_fixtures: dict):
    """
    Verify Separation of Duties: Routine PAM Admin (Dave) CANNOT perform WORM verification
    or create evidence exports without Evidence Custodian role (403 Forbidden).
    """
    dave = seeded_fixtures["dave"]  # Admin & Operator, NOT Evidence Custodian
    dave_headers = auth_headers(dave.id, dave.email, ["pwd", "fido2"])

    # 1. Verification attempt by Admin -> 403 Forbidden
    verify_resp = client.post(
        "/api/v1/audit-events/verify-integrity",
        headers=dave_headers,
        json={"batch_limit": 50},
    )
    assert verify_resp.status_code == 403
    assert "Evidence custodian or auditor role required" in verify_resp.json()["message"]

    # 2. Export attempt by Admin -> 403 Forbidden
    export_resp = client.post(
        "/api/v1/audit-events/exports",
        headers=dave_headers,
        json={"justification": "Admin attempting evidence bundle export"},
    )
    assert export_resp.status_code == 403
    assert "Evidence custodian or auditor role required" in export_resp.json()["message"]


def test_create_and_retrieve_sealed_audit_export(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Verify creating and retrieving sealed audit trail export bundle with SHA-256 manifest (P5-05).
    """
    eva = seeded_fixtures["eva"]
    eva_headers = auth_headers(eva.id, eva.email, ["pwd", "fido2"])

    # Seed events
    AuditService.record_event(
        db=db_session,
        event_type="SESSION_LAUNCHED",
        correlation_id="corr_exp_seed",
        actor_id=eva.id,
        payload={"session_id": "ses_exp_test"},
    )
    db_session.commit()

    # 1. Create Export
    create_resp = client.post(
        "/api/v1/audit-events/exports",
        headers=eva_headers,
        json={
            "justification": "Quarterly regulatory compliance review",
            "limit": 100,
        },
    )
    assert create_resp.status_code == 202, create_resp.text
    export_data = create_resp.json()
    export_id = export_data["export_id"]
    assert export_data["status"] == "completed"
    assert export_data["export_type"] == "audit_trail"
    assert len(export_data["manifest_sha256"]) == 64
    assert export_data["download_url"].endswith(f"/exports/{export_id}/download")

    # 2. Retrieve Export
    get_resp = client.get(
        f"/api/v1/audit-events/exports/{export_id}",
        headers=eva_headers,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["export_id"] == export_id
    assert get_resp.json()["manifest_sha256"] == export_data["manifest_sha256"]


def test_export_retrieval_identifier_concealment_on_unauthorized(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Verify identifier concealment (404 Not Found) when a non-custodian queries an export (SEC-02).
    """
    eva = seeded_fixtures["eva"]
    alice = seeded_fixtures["alice"]  # Requester
    eva_headers = auth_headers(eva.id, eva.email, ["pwd", "fido2"])
    alice_headers = auth_headers(alice.id, alice.email, ["pwd", "fido2"])

    # Create export as Eva
    create_resp = client.post(
        "/api/v1/audit-events/exports",
        headers=eva_headers,
        json={"justification": "Forensic audit request"},
    )
    assert create_resp.status_code == 202
    export_id = create_resp.json()["export_id"]

    # Requester Alice tries to view export -> 404 Concealment (Never 403)
    alice_resp = client.get(
        f"/api/v1/audit-events/exports/{export_id}",
        headers=alice_headers,
    )
    assert alice_resp.status_code == 404
    assert alice_resp.json()["code"] == "EXPORT_NOT_FOUND"


def test_gateway_ingests_and_persists_session_recording(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Verify gateway delivers session recording metadata with SHA-256 digest on session close (P5-02).
    """
    session, grant = _create_test_session_and_grant(db_session, seeded_fixtures)
    gw_headers = {
        "X-Gateway-Secret": settings.gateway_api_secret,
        "X-Correlation-Id": "corr_gw_rec_01",
    }

    rec_digest = hashlib.sha256(b"sample asciinema terminal stream").hexdigest()
    event_payload = {
        "state": "ended",
        "reason": "User executed exit",
        "recording": {
            "digest_sha256": rec_digest,
            "storage_uri": f"s3://ariba-pam-evidence-worm/recordings/{session.id}.cast",
            "size_bytes": 14280,
            "duration_seconds": 185,
            "coverage_status": "complete",
        },
    }

    resp = client.post(
        f"/internal/v1/sessions/{session.id}/events",
        headers=gw_headers,
        json=event_payload,
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "ended"

    # Verify SessionRecording was persisted in DB
    recording = db_session.query(SessionRecording).filter(SessionRecording.session_id == session.id).first()
    assert recording is not None
    assert recording.digest_sha256 == rec_digest
    assert recording.size_bytes == 14280
    assert recording.duration_seconds == 185
    assert recording.coverage_status == "complete"


def test_scoped_recording_playback_authorization(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Verify scoped reviewer can authorize short-lived playback streaming URL (P5-04 / FR-09).
    """
    session, grant = _create_test_session_and_grant(db_session, seeded_fixtures)
    eva = seeded_fixtures["eva"]
    eva_headers = auth_headers(eva.id, eva.email, ["pwd", "fido2"])

    # Persist recording
    rec = SessionRecording(
        id=generate_id("rec"),
        session_id=session.id,
        digest_sha256="abc123digest",
        storage_uri=f"s3://ariba-pam-evidence-worm/recordings/{session.id}.cast",
        size_bytes=4096,
        duration_seconds=60,
        coverage_status="complete",
    )
    db_session.add(rec)
    db_session.commit()

    # 1. List recordings
    list_resp = client.get("/api/v1/recordings", headers=eva_headers)
    assert list_resp.status_code == 200
    recordings = list_resp.json()
    assert any(r["recording_id"] == rec.id for r in recordings)

    # 2. Get specific recording
    get_resp = client.get(f"/api/v1/recordings/{rec.id}", headers=eva_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["recording_id"] == rec.id
    assert get_resp.json()["digest_sha256"] == "abc123digest"

    # 3. Authorize playback session
    play_resp = client.post(
        f"/api/v1/recordings/{rec.id}/playback-sessions",
        headers=eva_headers,
    )
    assert play_resp.status_code == 201
    data = play_resp.json()
    assert data["recording_id"] == rec.id
    assert "token=" in data["playback_url"]
    assert "expires_at" in data

    # Verify audit event written to outbox
    audit_row = (
        db_session.query(AuditOutbox)
        .filter(AuditOutbox.event_type == "RECORDING_PLAYBACK_AUTHORIZED")
        .first()
    )
    assert audit_row is not None
    assert audit_row.payload["recording_id"] == rec.id


def test_cross_scope_recording_playback_returns_404_concealment(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Verify cross-scope attempt returns 404 Concealment (anti-enumeration invariant) (P5-04 / SEC-02).
    """
    session, grant = _create_test_session_and_grant(db_session, seeded_fixtures)
    charlie = seeded_fixtures["charlie"]  # Approver only for analytics, session is on payments
    charlie_headers = auth_headers(charlie.id, charlie.email, ["pwd", "fido2"])

    rec = SessionRecording(
        id=generate_id("rec"),
        session_id=session.id,
        digest_sha256="abc123digest",
        storage_uri=f"s3://ariba-pam-evidence-worm/recordings/{session.id}.cast",
        size_bytes=4096,
        duration_seconds=60,
        coverage_status="complete",
    )
    db_session.add(rec)
    db_session.commit()

    # Charlie queries recording outside his scope -> 404 Not Found
    get_resp = client.get(f"/api/v1/recordings/{rec.id}", headers=charlie_headers)
    assert get_resp.status_code == 404
    assert get_resp.json()["code"] == "RECORDING_NOT_FOUND"

    # Charlie attempts playback authorization -> 404 Not Found
    play_resp = client.post(
        f"/api/v1/recordings/{rec.id}/playback-sessions",
        headers=charlie_headers,
    )
    assert play_resp.status_code == 404
    assert play_resp.json()["code"] == "RECORDING_NOT_FOUND"


def test_scoped_recording_export_lifecycle(client: TestClient, seeded_fixtures: dict, db_session: Session):
    """
    Verify creating and retrieving a scoped recording evidence export (P5-05).
    """
    session, grant = _create_test_session_and_grant(db_session, seeded_fixtures)
    eva = seeded_fixtures["eva"]
    eva_headers = auth_headers(eva.id, eva.email, ["pwd", "fido2"])

    rec = SessionRecording(
        id=generate_id("rec"),
        session_id=session.id,
        digest_sha256="sha256_mock_digest_cast",
        storage_uri=f"s3://ariba-pam-evidence-worm/recordings/{session.id}.cast",
        size_bytes=8192,
        duration_seconds=120,
        coverage_status="complete",
    )
    db_session.add(rec)
    db_session.commit()

    # 1. Create recording export
    create_resp = client.post(
        f"/api/v1/recordings/{rec.id}/exports",
        headers=eva_headers,
        json={"justification": "External compliance audit submission"},
    )
    assert create_resp.status_code == 202
    exp_data = create_resp.json()
    exp_id = exp_data["export_id"]
    assert exp_data["recording_id"] == rec.id
    assert exp_data["status"] == "completed"
    assert exp_data["download_url"].endswith(f"/recording-exports/{exp_id}/download")

    # 2. Retrieve recording export
    get_resp = client.get(
        f"/api/v1/recording-exports/{exp_id}",
        headers=eva_headers,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["export_id"] == exp_id
    assert get_resp.json()["recording_id"] == rec.id
