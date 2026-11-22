"""Migration runner tests verifying schema application and idempotency (Task P1-02 / T-10)."""

import tempfile
import os
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from ariba_pam.db.models import GatewayZone


def test_migration_runner_upgrade_and_rerun():
    """
    Apply migration on an empty database and rerun safely.
    Verifies all tables are created and rerun is idempotent.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        sqlite_url = f"sqlite:///{db_path}"

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)

        # Upgrade an existing baseline while preserving its data.
        command.upgrade(alembic_cfg, "0001_initial_schema")
        engine = create_engine(sqlite_url)
        with Session(engine) as db:
            db.add(GatewayZone(id="zon_existing", name="existing-zone"))
            db.commit()
        command.upgrade(alembic_cfg, "head")
        with Session(engine) as db:
            assert db.get(GatewayZone, "zon_existing").name == "existing-zone"
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())

        expected_tables = {
            "users",
            "roles",
            "role_assignments",
            "gateway_zones",
            "assets",
            "target_accounts",
            "admin_change_proposals",
            "access_policy_versions",
            "access_requests",
            "request_revisions",
            "approval_steps",
            "approval_decisions",
            "access_grants",
            "session_launches",
            "access_sessions",
            "session_recordings",
            "evidence_exports",
            "soc_alerts",
            "audit_outbox",
            "idempotency_records",
            "alembic_version",
        }

        assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"

        # 2. Rerun safely (idempotent head execution)
        command.upgrade(alembic_cfg, "head")

        # 3. Test downgrade then upgrade
        command.downgrade(alembic_cfg, "base")
        inspector_post_down = inspect(engine)
        assert "users" not in inspector_post_down.get_table_names()

        command.upgrade(alembic_cfg, "head")
        inspector_post_up = inspect(engine)
        assert "users" in inspector_post_up.get_table_names()

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
