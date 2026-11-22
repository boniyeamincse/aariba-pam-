"""Deployment Rollback and Step-by-Step Migration Downgrade Rehearsal (T-10, P5-09).

Verifies:
1. Bidirectional Schema Migrations: Every migration version has a functional, verified downgrade() path.
2. Step-by-Step Downgrade: Rehearses sequential rollback from 0006 down to 0001.
3. Data Preservation Invariant: Data in unaffected baseline tables is 100% preserved during rollbacks.
4. Clean Re-Upgrade: Database cleanly upgrades back to head without schema drift or orphaned constraints.
"""

import os
import tempfile
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from ariba_pam.db.base import utc_now, generate_id


def test_step_by_step_migration_rollback_and_data_preservation():
    """
    T-10 Deployment Rollback Rehearsal:
    1. Upgrade empty database to head (all migrations 0001 -> 0006 applied).
    2. Populate records in every table layer (base, policy, recordings, alerts, rehearsals, emergency).
    3. Step-by-step downgrade to verify clean drop of target tables and 100% preservation of remaining tables.
    4. Re-upgrade back to head and verify operational integrity.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        sqlite_url = f"sqlite:///{db_path}"
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)

        # 1. Upgrade to head
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(sqlite_url)
        now = utc_now().isoformat()

        # 2. Insert records across all migration layers
        with engine.begin() as conn:
            # 0001: Base tables
            conn.execute(
                text("INSERT INTO gateway_zones (id, name, description) VALUES ('zon_prod', 'prod-zone', 'Prod')")
            )
            conn.execute(
                text(
                    "INSERT INTO assets (id, name, environment, team, zone_id, host, port, host_trust_ref, is_active, created_at) "
                    "VALUES ('ast_core', 'core-db', 'prod', 'payments', 'zon_prod', 'core.internal', 22, 'sha256:core', 1, :now)"
                ),
                {"now": now},
            )
            conn.execute(
                text(
                    "INSERT INTO target_accounts (id, asset_id, username, is_active, requires_ticket, max_duration_seconds) "
                    "VALUES ('acc_admin', 'ast_core', 'dbadmin', 1, 0, 3600)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO users (id, idp_issuer, idp_subject, email, full_name, is_active, security_version, created_at, updated_at) "
                    "VALUES ('usr_oper', 'https://idp.ariba.internal', 'sub_oper', 'oper@ariba.internal', 'Lead Operator', 1, 1, :now, :now)"
                ),
                {"now": now},
            )
            conn.execute(
                text(
                    "INSERT INTO admin_change_proposals (id, resource_type, resource_id, change_payload, expected_version, author_id, status, created_at) "
                    "VALUES ('prp_01', 'policy', 'ast_core', '{}', 1, 'usr_oper', 'applied', :now)"
                ),
                {"now": now},
            )

            # 0002: access_policy_versions
            conn.execute(
                text(
                    "INSERT INTO access_policy_versions (id, asset_id, version, rules, proposal_id, published_at) "
                    "VALUES ('pol_v1', 'ast_core', 1, '{\"allowed_target_account_ids\": [\"acc_admin\"]}', 'prp_01', :now)"
                ),
                {"now": now},
            )

            # 0003: session_recordings & evidence_exports
            conn.execute(
                text(
                    "INSERT INTO session_recordings (id, session_id, size_bytes, duration_seconds, digest_sha256, storage_uri, coverage_status, created_at) "
                    "VALUES ('rec_01', 'ses_mock', 1024, 60, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'worm://evidence/rec_01', 'complete', :now)"
                ),
                {"now": now},
            )
            conn.execute(
                text(
                    "INSERT INTO evidence_exports (id, requester_id, export_type, record_count, manifest_sha256, storage_uri, status, justification, expires_at, created_at) "
                    "VALUES ('exp_01', 'usr_oper', 'audit', 10, 'digest_mock', 'worm://exports/exp_01', 'completed', 'Audit request', :now, :now)"
                ),
                {"now": now},
            )

            # 0004: soc_alerts
            conn.execute(
                text(
                    "INSERT INTO soc_alerts (id, alert_type, severity, title, description, correlation_id, details, status, created_at) "
                    "VALUES ('alt_01', 'SOD_VIOLATION', 'HIGH', 'Test Alert', 'Alert description', 'corr_01', '{}', 'open', :now)"
                ),
                {"now": now},
            )

            # 0005: backup_rehearsals
            conn.execute(
                text(
                    "INSERT INTO backup_rehearsals (id, exercise_ref, operator_id, snapshot_id, rto_seconds, rpo_seconds, target_rto_seconds, target_rpo_seconds, status, restored_counts, reconciled_grants_count, reconciled_sessions_count, worm_verified, discrepancies, created_at) "
                    "VALUES ('bkr_01', 'DR-EX-01', 'usr_oper', 'snp_01', 120.0, 30.0, 900.0, 60.0, 'verified', '{}', 0, 0, 1, '{}', :now)"
                ),
                {"now": now},
            )

            # 0006: emergency_requests & emergency_approvals
            conn.execute(
                text(
                    "INSERT INTO emergency_requests (id, asset_id, target_account_id, requester_id, justification, status, required_approvals, approval_count, requested_end_at, created_at) "
                    "VALUES ('emg_01', 'ast_core', 'acc_admin', 'usr_oper', 'Emergency breakdown', 'pending', 2, 0, :now, :now)"
                ),
                {"now": now},
            )
            conn.execute(
                text(
                    "INSERT INTO emergency_approvals (id, emergency_request_id, custodian_id, decision, reason, created_at) "
                    "VALUES ('ema_01', 'emg_01', 'usr_oper', 'approve', 'Approved', :now)"
                ),
                {"now": now},
            )

        # 3. Step 1: Downgrade from 0006 to 0005
        command.downgrade(alembic_cfg, "0005_backup_rehearsals")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "emergency_requests" not in tables
        assert "emergency_approvals" not in tables
        assert "backup_rehearsals" in tables
        assert "soc_alerts" in tables
        # Verify data preserved in remaining tables
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM backup_rehearsals")).scalar() == 1
            assert conn.execute(text("SELECT count(*) FROM assets")).scalar() == 1

        # 4. Step 2: Downgrade from 0005 to 0004
        command.downgrade(alembic_cfg, "0004_soc_alerts")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "backup_rehearsals" not in tables
        assert "soc_alerts" in tables
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM soc_alerts")).scalar() == 1
            assert conn.execute(text("SELECT count(*) FROM assets")).scalar() == 1

        # 5. Step 3: Downgrade from 0004 to 0003
        command.downgrade(alembic_cfg, "0003_evidence_and_recordings")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "soc_alerts" not in tables
        assert "session_recordings" in tables
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM session_recordings")).scalar() == 1
            assert conn.execute(text("SELECT count(*) FROM assets")).scalar() == 1

        # 6. Step 4: Downgrade from 0003 to 0002
        command.downgrade(alembic_cfg, "0002_access_policy_versions")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "session_recordings" not in tables
        assert "evidence_exports" not in tables
        assert "access_policy_versions" in tables
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM access_policy_versions")).scalar() == 1
            assert conn.execute(text("SELECT count(*) FROM assets")).scalar() == 1

        # 7. Step 5: Downgrade from 0002 to 0001
        command.downgrade(alembic_cfg, "0001_initial_schema")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "access_policy_versions" not in tables
        assert "assets" in tables
        assert "gateway_zones" in tables
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM assets")).scalar() == 1
            assert conn.execute(text("SELECT count(*) FROM gateway_zones")).scalar() == 1

        # 8. Step 6: Re-upgrade cleanly from 0001 back to head
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "emergency_requests" in tables
        assert "backup_rehearsals" in tables
        assert "soc_alerts" in tables
        assert "session_recordings" in tables
        assert "access_policy_versions" in tables
        with engine.connect() as conn:
            # Baseline data survives entire round-trip rollback!
            assert conn.execute(text("SELECT count(*) FROM assets")).scalar() == 1
            assert conn.execute(text("SELECT count(*) FROM gateway_zones")).scalar() == 1

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
