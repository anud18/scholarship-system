"""add college_rejected to college_ranking_items

Revision ID: add_college_rejected_001
Revises: a1b2c3d4e5f6
Create Date: 2026-04-28 00:00:00.000000

Adds a flag to indicate that a student was marked "N" (rejected) by the college
during ranking import. Distinct from `status='rejected'` which is set by admin
manual action and triggers exclusion from alternate-promotion and final allocation.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "add_college_rejected_001"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("college_ranking_items")]

    if "college_rejected" not in columns:
        op.add_column(
            "college_ranking_items",
            sa.Column(
                "college_rejected",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("college_ranking_items")]

    if "college_rejected" in columns:
        op.drop_column("college_ranking_items", "college_rejected")
