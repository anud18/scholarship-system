"""rename metadata to audit_metadata in roster_audit_logs

Revision ID: 1160dcaa4f23
Revises: 49ddb19b7727
Create Date: 2025-09-28 12:46:36.626792

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1160dcaa4f23"
down_revision: Union[str, None] = "49ddb19b7727"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if column needs renaming
    import sqlalchemy as sa

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if table exists first
    existing_tables = inspector.get_table_names()
    if "roster_audit_logs" not in existing_tables:
        print("⏭️  Skipping column rename - roster_audit_logs table doesn't exist")
        return

    existing_columns = {col["name"] for col in inspector.get_columns("roster_audit_logs")}

    # Only rename if 'metadata' exists and 'audit_metadata' doesn't exist
    if "metadata" in existing_columns and "audit_metadata" not in existing_columns:
        op.alter_column("roster_audit_logs", "metadata", new_column_name="audit_metadata")
    else:
        print("⏭️  Skipping column rename - already renamed or doesn't need renaming")


def downgrade() -> None:
    # Rename audit_metadata column back to metadata in roster_audit_logs table
    op.alter_column("roster_audit_logs", "audit_metadata", new_column_name="metadata")
