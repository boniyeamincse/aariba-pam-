"""Add protocol field to assets for RDP and SSH target infrastructure support.

Revision ID: 0008_rdp_support
Revises: 0007_vault_credentials
Create Date: 2026-11-22 19:50:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0008_rdp_support"
down_revision: Union[str, None] = "0007_vault_credentials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.add_column(sa.Column("protocol", sa.String(length=16), nullable=False, server_default="ssh"))


def downgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_column("protocol")
