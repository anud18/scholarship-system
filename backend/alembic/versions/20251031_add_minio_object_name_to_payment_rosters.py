"""add minio_object_name to payment_rosters

Adds minio_object_name field to store MinIO object path for Excel files:
- minio_object_name: MinIO object path for the roster Excel file

Revision ID: 20251031_add_minio_object_name
Revises: 20251028_add_verification_tasks
Create Date: 2025-10-31 04:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251031_add_minio_object_name"
down_revision: Union[str, None] = "20251028_add_verification_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add minio_object_name column to payment_rosters"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if table exists
    existing_tables = inspector.get_table_names()
    if "payment_rosters" not in existing_tables:
        print("payment_rosters table does not exist, skipping")
        return

    # Get existing columns
    existing_columns = [col["name"] for col in inspector.get_columns("payment_rosters")]

    # Add minio_object_name if not exists
    if "minio_object_name" not in existing_columns:
        op.add_column("payment_rosters", sa.Column("minio_object_name", sa.String(length=500), nullable=True))
        print("Added minio_object_name column to payment_rosters")
    else:
        print("minio_object_name column already exists in payment_rosters")


def downgrade() -> None:
    """Remove minio_object_name column from payment_rosters"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if table exists
    existing_tables = inspector.get_table_names()
    if "payment_rosters" not in existing_tables:
        return

    # Get existing columns
    existing_columns = [col["name"] for col in inspector.get_columns("payment_rosters")]

    # Drop column if it exists
    if "minio_object_name" in existing_columns:
        op.drop_column("payment_rosters", "minio_object_name")
        print("Dropped minio_object_name column from payment_rosters")
