"""Vault credentials and target account secret rotation support.

Revision ID: 0007_vault_credentials
Revises: 0006_emergency_requests
Create Date: 2026-11-22 19:40:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0007_vault_credentials"
down_revision: Union[str, None] = "0006_emergency_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("target_accounts") as batch_op:
        batch_op.add_column(sa.Column("credential_type", sa.String(length=32), nullable=False, server_default="ssh_certificate"))
        batch_op.add_column(sa.Column("vault_secret_path", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("auto_rotate_on_session_end", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("rotation_status", sa.String(length=32), nullable=False, server_default="active"))

    op.create_table(
        "vault_secret_store",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), sa.ForeignKey("target_accounts.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("secret_type", sa.String(length=32), nullable=False, server_default="password"),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vault_secret_store_account_id", "vault_secret_store", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_vault_secret_store_account_id", table_name="vault_secret_store")
    op.drop_table("vault_secret_store")

    with op.batch_alter_table("target_accounts") as batch_op:
        batch_op.drop_column("rotation_status")
        batch_op.drop_column("last_rotated_at")
        batch_op.drop_column("auto_rotate_on_session_end")
        batch_op.drop_column("vault_secret_path")
        batch_op.drop_column("credential_type")
