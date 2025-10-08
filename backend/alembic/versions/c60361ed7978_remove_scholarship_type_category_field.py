"""remove_scholarship_type_category_field

Revision ID: c60361ed7978
Revises: 420d32e7c5c3
Create Date: 2025-10-08 08:39:10.710182

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c60361ed7978"
down_revision: Union[str, None] = "420d32e7c5c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove category column from scholarship_types table"""
    # Check if table and column exist before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "scholarship_types" in existing_tables:
        columns = [col["name"] for col in inspector.get_columns("scholarship_types")]
        if "category" in columns:
            op.drop_column("scholarship_types", "category")


def downgrade() -> None:
    """Add category column back to scholarship_types table"""
    # Check if table exists and column doesn't exist before adding
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "scholarship_types" in existing_tables:
        columns = [col["name"] for col in inspector.get_columns("scholarship_types")]
        if "category" not in columns:
            # Add column with server_default to handle existing rows
            op.add_column(
                "scholarship_types", sa.Column("category", sa.String(50), nullable=False, server_default="phd")
            )
