"""Emergency break-glass requests and approvals tables and indexes.

Revision ID: 0006_emergency_requests
Revises: 0005_backup_rehearsals
Create Date: 2026-11-22 18:45:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0006_emergency_requests"
down_revision: Union[str, None] = "0005_backup_rehearsals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "emergency_requests",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("asset_id", sa.String(length=64), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("target_account_id", sa.String(length=64), sa.ForeignKey("target_accounts.id"), nullable=False),
        sa.Column("requester_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, default="pending"),
        sa.Column("required_approvals", sa.Integer(), nullable=False, default=2),
        sa.Column("approval_count", sa.Integer(), nullable=False, default=0),
        sa.Column("requested_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("grant_id", sa.String(length=64), sa.ForeignKey("access_grants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_emergency_requests_status", "emergency_requests", ["status"])

    op.create_table(
        "emergency_approvals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("emergency_request_id", sa.String(length=64), sa.ForeignKey("emergency_requests.id"), nullable=False),
        sa.Column("custodian_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("emergency_request_id", "custodian_id", name="uq_emg_custodian_vote"),
    )
    op.create_index("ix_emergency_approvals_req_id", "emergency_approvals", ["emergency_request_id"])


def downgrade() -> None:
    op.drop_table("emergency_approvals")
    op.drop_table("emergency_requests")
