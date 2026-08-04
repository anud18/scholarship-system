"""Add sub_type_preferences to applications table

Revision ID: add_sub_type_prefs_001
Revises: add_roster_item_dist_001
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "add_sub_type_prefs_001"
down_revision = "add_roster_item_dist_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("applications")]

    if "sub_type_preferences" not in columns:
        op.add_column(
            "applications",
            sa.Column("sub_type_preferences", sa.JSON, nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("applications")]

    if "sub_type_preferences" in columns:
        op.drop_column("applications", "sub_type_preferences")
