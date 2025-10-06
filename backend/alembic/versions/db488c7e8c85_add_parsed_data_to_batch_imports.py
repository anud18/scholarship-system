"""add parsed_data to batch_imports

Revision ID: db488c7e8c85
Revises: 09a6cf986f5c
Create Date: 2025-10-05 01:44:26.267004

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "db488c7e8c85"
down_revision: Union[str, None] = "09a6cf986f5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add parsed_data column to batch_imports table"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "batch_imports" in existing_tables:
        existing_columns = [col["name"] for col in inspector.get_columns("batch_imports")]
        if "parsed_data" not in existing_columns:
            op.add_column("batch_imports", sa.Column("parsed_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove parsed_data column from batch_imports table"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "batch_imports" in existing_tables:
        existing_columns = [col["name"] for col in inspector.get_columns("batch_imports")]
        if "parsed_data" in existing_columns:
            op.drop_column("batch_imports", "parsed_data")
