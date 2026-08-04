"""add allow_college_view_distribution to scholarship_configurations

Revision ID: college_view_distribution_001
Revises: college_ranking_college_code_001
Create Date: 2026-06-30

Admin-controlled toggle: open/close college visibility of distribution results.

NOTE: revision id shortened from the brief's `add_college_view_distribution_001`
(33 chars) because alembic_version.version_num is varchar(32). The produced
column name (allow_college_view_distribution) is unchanged.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "college_view_distribution_001"
down_revision = "college_ranking_college_code_001"
branch_labels = None
depends_on = None

TABLE = "scholarship_configurations"
COLUMN = "allow_college_view_distribution"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns(TABLE)}
    if COLUMN not in columns:
        op.add_column(
            TABLE,
            sa.Column(
                COLUMN,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns(TABLE)}
    if COLUMN in columns:
        op.drop_column(TABLE, COLUMN)
