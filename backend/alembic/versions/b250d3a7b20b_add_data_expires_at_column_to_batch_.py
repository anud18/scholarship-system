"""Add data_expires_at column to batch_imports for TTL cleanup

Revision ID: b250d3a7b20b
Revises: a570bbf999e7
Create Date: 2025-10-07 07:34:59.836649

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b250d3a7b20b"
down_revision: Union[str, None] = "a570bbf999e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add data_expires_at column to batch_imports table for TTL functionality"""
    # Check if column already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("batch_imports")]

    if "data_expires_at" not in existing_columns:
        op.add_column("batch_imports", sa.Column("data_expires_at", sa.DateTime(timezone=True), nullable=True))
        # Add index for efficient cleanup queries
        op.create_index("ix_batch_imports_data_expires_at", "batch_imports", ["data_expires_at"], unique=False)


def downgrade() -> None:
    """Remove data_expires_at column from batch_imports table"""
    # Check if column exists before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("batch_imports")]

    if "data_expires_at" in existing_columns:
        # Drop index first
        op.drop_index("ix_batch_imports_data_expires_at", table_name="batch_imports")
        # Drop column
        op.drop_column("batch_imports", "data_expires_at")
