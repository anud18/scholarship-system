"""add college_code to users table

Revision ID: 36976b6fab9f
Revises: 2e7b490e60dc
Create Date: 2025-10-05 01:07:50.391694

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "36976b6fab9f"
down_revision: Union[str, None] = "2e7b490e60dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add college_code column to users table if it doesn't exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("users")]

    if "college_code" not in existing_columns:
        op.add_column("users", sa.Column("college_code", sa.String(10), nullable=True))


def downgrade() -> None:
    # Remove college_code column from users table
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("users")]

    if "college_code" in existing_columns:
        op.drop_column("users", "college_code")
