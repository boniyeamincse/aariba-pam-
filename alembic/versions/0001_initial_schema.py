"""Initial schema for Ariba PAM baseline.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-22 15:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("idp_issuer", sa.String(length=255), nullable=False),
        sa.Column("idp_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("security_version", sa.Integer(), nullable=False, default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idp_issuer", "idp_subject", name="uq_user_idp_identity"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # Roles table
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("description", sa.String(length=255), default=""),
    )

    # Role assignments table
    op.create_table(
        "role_assignments",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.String(length=64), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_value", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_role_assignments_user_scope", "role_assignments", ["user_id", "scope_type", "scope_value"])

    # Gateway zones table
    op.create_table(
        "gateway_zones",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("description", sa.String(length=255), default=""),
    )

    # Assets table
    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("team", sa.String(length=64), nullable=False),
        sa.Column("zone_id", sa.String(length=64), sa.ForeignKey("gateway_zones.id"), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, default=22),
        sa.Column("host_trust_ref", sa.String(length=255), default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Target accounts table
    op.create_table(
        "target_accounts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("asset_id", sa.String(length=64), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("requires_ticket", sa.Boolean(), nullable=False, default=False),
        sa.Column("max_duration_seconds", sa.Integer(), nullable=False, default=3600),
        sa.UniqueConstraint("asset_id", "username", name="uq_asset_account"),
    )

    # Admin change proposals table
    op.create_table(
        "admin_change_proposals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("change_payload", sa.JSON(), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False, default=1),
        sa.Column("author_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewer_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, default="pending"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Access requests table
    op.create_table(
        "access_requests",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("requester_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, default="pending"),
        sa.Column("current_revision_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Request revisions table
    op.create_table(
        "request_revisions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("request_id", sa.String(length=64), sa.ForeignKey("access_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False, default=1),
        sa.Column("asset_id", sa.String(length=64), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("target_account_id", sa.String(length=64), sa.ForeignKey("target_accounts.id"), nullable=False),
        sa.Column("requested_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("ticket_ref", sa.String(length=128), nullable=True),
        sa.Column("policy_version_id", sa.String(length=64), nullable=False, default="pol_v1"),
        sa.Column("is_frozen", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "revision_number", name="uq_request_revision"),
    )

    # Approval steps table
    op.create_table(
        "approval_steps",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("revision_id", sa.String(length=64), sa.ForeignKey("request_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False, default=1),
        sa.Column("status", sa.String(length=32), nullable=False, default="pending"),
        sa.Column("required_role", sa.String(length=64), nullable=False, default="approver"),
    )

    # Approval decisions table
    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("step_id", sa.String(length=64), sa.ForeignKey("approval_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approver_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("step_id", "approver_id", name="uq_step_approver"),
    )

    # Access grants table
    op.create_table(
        "access_grants",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("revision_id", sa.String(length=64), sa.ForeignKey("request_revisions.id"), nullable=False, unique=True),
        sa.Column("requester_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("asset_id", sa.String(length=64), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("target_account_id", sa.String(length=64), sa.ForeignKey("target_accounts.id"), nullable=False),
        sa.Column("effective_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, default="active"),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=True),
    )

    # Session launches table
    op.create_table(
        "session_launches",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("grant_id", sa.String(length=64), sa.ForeignKey("access_grants.id"), nullable=False),
        sa.Column("launch_token_digest", sa.String(length=128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_consumed", sa.Boolean(), nullable=False, default=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_gateway_id", sa.String(length=64), nullable=True),
    )

    # Access sessions table
    op.create_table(
        "access_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("grant_id", sa.String(length=64), sa.ForeignKey("access_grants.id"), nullable=False),
        sa.Column("launch_id", sa.String(length=64), sa.ForeignKey("session_launches.id"), nullable=False, unique=True),
        sa.Column("gateway_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_reason", sa.String(length=128), nullable=True),
    )

    # Audit outbox table
    op.create_table(
        "audit_outbox",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_state", sa.String(length=32), nullable=False, default="pending"),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, default=0),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audit_outbox_delivery", "audit_outbox", ["delivery_state", "occurred_at"])

    # Idempotency records table
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("actor_id", "operation", "idempotency_key", name="uq_actor_op_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("audit_outbox")
    op.drop_table("access_sessions")
    op.drop_table("session_launches")
    op.drop_table("access_grants")
    op.drop_table("approval_decisions")
    op.drop_table("approval_steps")
    op.drop_table("request_revisions")
    op.drop_table("access_requests")
    op.drop_table("admin_change_proposals")
    op.drop_table("target_accounts")
    op.drop_table("assets")
    op.drop_table("gateway_zones")
    op.drop_table("role_assignments")
    op.drop_table("roles")
    op.drop_table("users")
