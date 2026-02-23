"""add allocation_year to college_ranking_items

Revision ID: add_allocation_year_001
Revises: normalize_scholarship_subtypes
Create Date: 2026-02-24

Tracks which academic year's quota was used when allocating a student.
Supports multi-year supplementary distribution (補發) where prior-year
remaining quotas can be used for current-year students.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "add_allocation_year_001"
down_revision = "normalize_scholarship_subtypes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("college_ranking_items")]

    if "allocation_year" not in columns:
        op.add_column(
            "college_ranking_items",
            sa.Column("allocation_year", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("college_ranking_items")]

    if "allocation_year" in columns:
        op.drop_column("college_ranking_items", "allocation_year")
