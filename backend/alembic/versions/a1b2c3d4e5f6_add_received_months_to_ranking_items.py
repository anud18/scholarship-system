"""add received_months to college_ranking_items

Revision ID: a1b2c3d4e5f6
Revises: add_renewal_year_001
Create Date: 2026-04-07 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "add_renewal_year_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add received_months and received_months_source columns to college_ranking_items
    # Check if columns don't exist before adding
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("college_ranking_items")]

    if "received_months" not in columns:
        op.add_column(
            "college_ranking_items",
            sa.Column("received_months", sa.Integer(), nullable=True),
        )

    if "received_months_source" not in columns:
        op.add_column(
            "college_ranking_items",
            sa.Column("received_months_source", sa.String(20), nullable=True),
        )


def downgrade() -> None:
    # Remove received_months and received_months_source columns
    # Check if columns exist before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("college_ranking_items")]

    if "received_months_source" in columns:
        op.drop_column("college_ranking_items", "received_months_source")

    if "received_months" in columns:
        op.drop_column("college_ranking_items", "received_months")
