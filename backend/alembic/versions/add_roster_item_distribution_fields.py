"""Add allocated_sub_type and application_identity to payment_roster_items

Revision ID: add_roster_item_dist_001
Revises: add_prior_quota_years_001
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa

revision = "add_roster_item_dist_001"
down_revision = "add_prior_quota_years_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [c["name"] for c in inspector.get_columns("payment_roster_items")]

    if "allocated_sub_type" not in existing_columns:
        op.add_column(
            "payment_roster_items",
            sa.Column("allocated_sub_type", sa.String(50), nullable=True),
        )

    if "application_identity" not in existing_columns:
        op.add_column(
            "payment_roster_items",
            sa.Column("application_identity", sa.String(50), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [c["name"] for c in inspector.get_columns("payment_roster_items")]

    if "application_identity" in existing_columns:
        op.drop_column("payment_roster_items", "application_identity")
    if "allocated_sub_type" in existing_columns:
        op.drop_column("payment_roster_items", "allocated_sub_type")
