"""add backup_allocations to college_ranking_items

Revision ID: cd2d48ec6d34
Revises: 6d5b1940bf8a
Create Date: 2025-10-21 11:44:55.501577

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cd2d48ec6d34"
down_revision: Union[str, None] = "6d5b1940bf8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add backup_allocations column to college_ranking_items
    # Check if column doesn't exist before adding
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("college_ranking_items")]

    if "backup_allocations" not in columns:
        op.add_column(
            "college_ranking_items",
            sa.Column("backup_allocations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    # Remove backup_allocations column
    # Check if column exists before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("college_ranking_items")]

    if "backup_allocations" in columns:
        op.drop_column("college_ranking_items", "backup_allocations")
