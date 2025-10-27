"""remove main_scholarship_type field

Revision ID: d241e807237f
Revises: normalize_scholarship_subtypes
Create Date: 2025-10-28 04:44:37.195606

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d241e807237f"
down_revision: Union[str, None] = "normalize_scholarship_subtypes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove main_scholarship_type field from applications table"""
    # Check if column exists before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("applications")]

    if "main_scholarship_type" in columns:
        op.drop_column("applications", "main_scholarship_type")
        print("  ✓ Dropped main_scholarship_type column from applications")
    else:
        print("  ⏭️  Column main_scholarship_type does not exist, skipping")


def downgrade() -> None:
    """Not supported - no downgrade for this breaking change"""
    pass
