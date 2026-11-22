"""Disaster recovery backup rehearsals table and indexes.

Revision ID: 0005_backup_rehearsals
Revises: 0004_soc_alerts
Create Date: 2026-11-22 18:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005_backup_rehearsals"
down_revision: Union[str, None] = "0004_soc_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backup_rehearsals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("exercise_ref", sa.String(length=128), nullable=False),
        sa.Column("operator_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("rto_seconds", sa.Float(), nullable=False),
        sa.Column("rpo_seconds", sa.Float(), nullable=False),
        sa.Column("target_rto_seconds", sa.Float(), nullable=False, default=900.0),
        sa.Column("target_rpo_seconds", sa.Float(), nullable=False, default=60.0),
        sa.Column("status", sa.String(length=32), nullable=False, default="completed"),
        sa.Column("restored_counts", sa.JSON(), nullable=False),
        sa.Column("reconciled_grants_count", sa.Integer(), nullable=False, default=0),
        sa.Column("reconciled_sessions_count", sa.Integer(), nullable=False, default=0),
        sa.Column("worm_verified", sa.Boolean(), nullable=False, default=True),
        sa.Column("discrepancies", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_backup_rehearsals_exercise", "backup_rehearsals", ["exercise_ref"])
    op.create_index("ix_backup_rehearsals_status", "backup_rehearsals", ["status"])


def downgrade() -> None:
    op.drop_table("backup_rehearsals")
