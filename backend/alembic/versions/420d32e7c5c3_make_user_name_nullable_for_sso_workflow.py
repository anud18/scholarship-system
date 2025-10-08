"""make_user_name_nullable_for_sso_workflow

Revision ID: 420d32e7c5c3
Revises: b250d3a7b20b
Create Date: 2025-10-07 17:45:54.570732

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "420d32e7c5c3"
down_revision: Union[str, None] = "b250d3a7b20b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make user.name nullable and add defaults for user_type and status to support SSO workflow"""
    # Check if users table exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "users" in existing_tables:
        # Make name column nullable
        op.alter_column("users", "name", existing_type=sa.String(100), nullable=True)


def downgrade() -> None:
    """Revert user.name to NOT NULL"""
    # Check if users table exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "users" in existing_tables:
        # Revert name column to NOT NULL
        # Note: This will fail if there are any NULL values in the name column
        op.alter_column("users", "name", existing_type=sa.String(100), nullable=False)
