"""add matrix distribution fields to college_ranking_items

Revision ID: 58c52fa1a739
Revises: 31ff09e2beed
Create Date: 2025-10-14 15:18:54.171337

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "58c52fa1a739"
down_revision: Union[str, None] = "31ff09e2beed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns for matrix distribution
    # Check if columns don't exist before adding
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("college_ranking_items")]

    if "allocated_sub_type" not in columns:
        op.add_column("college_ranking_items", sa.Column("allocated_sub_type", sa.String(length=50), nullable=True))

    if "backup_position" not in columns:
        op.add_column("college_ranking_items", sa.Column("backup_position", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Remove matrix distribution columns
    # Check if columns exist before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("college_ranking_items")]

    if "backup_position" in columns:
        op.drop_column("college_ranking_items", "backup_position")

    if "allocated_sub_type" in columns:
        op.drop_column("college_ranking_items", "allocated_sub_type")
