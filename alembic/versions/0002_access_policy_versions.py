"""Store independently published access policy history."""

import sqlalchemy as sa
from alembic import op

revision = "0002_access_policy_versions"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_policy_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column(
            "proposal_id",
            sa.String(64),
            sa.ForeignKey("admin_change_proposals.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("asset_id", "version", name="uq_policy_asset_version"),
    )


def downgrade() -> None:
    op.drop_table("access_policy_versions")
