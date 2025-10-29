"""add_backup_info_to_payment_roster_items

Revision ID: 07e9ece93d90
Revises: cd2d48ec6d34
Create Date: 2025-10-22 00:08:50.352727

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "07e9ece93d90"
down_revision: Union[str, None] = "cd2d48ec6d34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add backup_info JSONB column to payment_roster_items table"""
    # Check if column already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("payment_roster_items")]

    if "backup_info" not in columns:
        op.add_column("payment_roster_items", sa.Column("backup_info", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """Remove backup_info column from payment_roster_items table"""
    # Check if column exists before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("payment_roster_items")]

    if "backup_info" in columns:
        op.drop_column("payment_roster_items", "backup_info")
