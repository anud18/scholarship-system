"""add deletion tracking fields to applications

Revision ID: 3e2ed9878cad
Revises: a44efe131936
Create Date: 2025-10-11 02:43:46.730432

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3e2ed9878cad"
down_revision: Union[str, None] = "a44efe131936"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if columns already exist before adding them
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("applications")]

    if "deleted_at" not in existing_columns:
        op.add_column("applications", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    if "deleted_by_id" not in existing_columns:
        op.add_column("applications", sa.Column("deleted_by_id", sa.Integer(), nullable=True))
        # Add foreign key constraint
        op.create_foreign_key("fk_applications_deleted_by_id", "applications", "users", ["deleted_by_id"], ["id"])

    if "deletion_reason" not in existing_columns:
        op.add_column("applications", sa.Column("deletion_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    # Check if columns exist before dropping them
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("applications")]

    if "deletion_reason" in existing_columns:
        op.drop_column("applications", "deletion_reason")

    if "deleted_by_id" in existing_columns:
        # Drop foreign key constraint first
        op.drop_constraint("fk_applications_deleted_by_id", "applications", type_="foreignkey")
        op.drop_column("applications", "deleted_by_id")

    if "deleted_at" in existing_columns:
        op.drop_column("applications", "deleted_at")
