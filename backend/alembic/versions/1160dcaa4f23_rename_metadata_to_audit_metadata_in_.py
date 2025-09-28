"""rename metadata to audit_metadata in roster_audit_logs

Revision ID: 1160dcaa4f23
Revises: 49ddb19b7727
Create Date: 2025-09-28 12:46:36.626792

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1160dcaa4f23"
down_revision: Union[str, None] = "49ddb19b7727"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename metadata column to audit_metadata in roster_audit_logs table
    op.alter_column("roster_audit_logs", "metadata", new_column_name="audit_metadata")


def downgrade() -> None:
    # Rename audit_metadata column back to metadata in roster_audit_logs table
    op.alter_column("roster_audit_logs", "audit_metadata", new_column_name="metadata")
