"""SOC security alerts table and indexes.

Revision ID: 0004_soc_alerts
Revises: 0003_evidence_and_recordings
Create Date: 2026-11-22 17:45:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004_soc_alerts"
down_revision: Union[str, None] = "0003_evidence_and_recordings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "soc_alerts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("gateway_id", sa.String(length=64), nullable=True),
        sa.Column("asset_id", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, default="open"),
        sa.Column("acknowledged_by_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_soc_alerts_type_severity", "soc_alerts", ["alert_type", "severity"])
    op.create_index("ix_soc_alerts_status", "soc_alerts", ["status"])


def downgrade() -> None:
    op.drop_table("soc_alerts")
