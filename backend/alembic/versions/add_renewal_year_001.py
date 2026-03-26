"""Add renewal_year column to applications table

For batch-imported renewal students, stores the target allocation year
directly instead of requiring a previous_application_id lookup.

Revision ID: add_renewal_year_001
Revises: update_phd_sel_mode_001
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa

revision = "add_renewal_year_001"
down_revision = "update_phd_sel_mode_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("applications")]

    if "renewal_year" not in columns:
        op.add_column(
            "applications",
            sa.Column("renewal_year", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("applications")]

    if "renewal_year" in columns:
        op.drop_column("applications", "renewal_year")
