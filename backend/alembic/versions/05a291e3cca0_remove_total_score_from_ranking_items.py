"""remove_total_score_from_ranking_items

Revision ID: 05a291e3cca0
Revises: 25101514470356be
Create Date: 2025-10-17 10:23:06.058108

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "05a291e3cca0"
down_revision: Union[str, None] = "25101514470356be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove total_score column and related index from college_ranking_items"""

    # Get database connection and inspector
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if index exists before dropping
    indexes = inspector.get_indexes("college_ranking_items")
    index_names = [idx["name"] for idx in indexes]

    if "ix_college_ranking_items_score" in index_names:
        op.drop_index("ix_college_ranking_items_score", table_name="college_ranking_items")

    # Check if column exists before dropping
    columns = inspector.get_columns("college_ranking_items")
    column_names = [col["name"] for col in columns]

    if "total_score" in column_names:
        op.drop_column("college_ranking_items", "total_score")


def downgrade() -> None:
    """Restore total_score column and index"""

    # Get database connection and inspector
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if column exists before adding
    columns = inspector.get_columns("college_ranking_items")
    column_names = [col["name"] for col in columns]

    if "total_score" not in column_names:
        op.add_column(
            "college_ranking_items", sa.Column("total_score", sa.Numeric(precision=8, scale=2), nullable=True)
        )

    # Check if index exists before creating
    indexes = inspector.get_indexes("college_ranking_items")
    index_names = [idx["name"] for idx in indexes]

    if "ix_college_ranking_items_score" not in index_names:
        op.create_index(
            "ix_college_ranking_items_score", "college_ranking_items", [sa.text("total_score DESC")], unique=False
        )
