"""Evidence exports, session recordings, and outbox payload digest schema.

Revision ID: 0003_evidence_and_recordings
Revises: 0002_access_policy_versions
Create Date: 2026-11-22 17:30:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003_evidence_and_recordings"
down_revision: Union[str, None] = "0002_access_policy_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add payload_digest to audit_outbox
    op.add_column("audit_outbox", sa.Column("payload_digest", sa.String(length=64), nullable=True))

    # 2. Create session_recordings table
    op.create_table(
        "session_recordings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=64), sa.ForeignKey("access_sessions.id"), unique=True, nullable=False),
        sa.Column("digest_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, default=0),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, default=0),
        sa.Column("coverage_status", sa.String(length=32), nullable=False, default="complete"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_session_recordings_session", "session_recordings", ["session_id"])

    # 3. Create evidence_exports table
    op.create_table(
        "evidence_exports",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("requester_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("export_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("scope_filter", sa.String(length=128), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False, default=0),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, default="completed"),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_exports_requester", "evidence_exports", ["requester_id"])


def downgrade() -> None:
    op.drop_table("evidence_exports")
    op.drop_table("session_recordings")
    op.drop_column("audit_outbox", "payload_digest")
