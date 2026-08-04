"""add allocation_year to payment_roster_items

Revision ID: add_alloc_year_roster_001
Revises: add_distribution_history_001
Create Date: 2026-03-01

Tracks which academic year's quota was used for each roster item.
Required to distinguish current-year vs prior-year (補發) allocations
when generating payment rosters for NSTC scholarships.
"""

from alembic import op
import sqlalchemy as sa

revision = "add_alloc_year_roster_001"
down_revision = "add_distribution_history_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("payment_roster_items")]

    if "allocation_year" not in columns:
        op.add_column(
            "payment_roster_items",
            sa.Column("allocation_year", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("payment_roster_items")]

    if "allocation_year" in columns:
        op.drop_column("payment_roster_items", "allocation_year")
