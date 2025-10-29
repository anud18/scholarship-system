"""add passbook cover and verification details to student_bank_accounts

Adds fields to store passbook cover image and verification method details:
- passbook_cover_object_name: MinIO object path for the passbook cover image
- verification_method: How the account was verified (ai_verified, manual_verified)
- ai_verification_confidence: AI confidence score if verified by AI

Revision ID: 20251028_add_passbook_cover
Revises: 20251028_add_indexes
Create Date: 2025-10-28 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251028_add_passbook_cover"
down_revision: Union[str, None] = "20251028_add_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add passbook cover and verification details columns"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if table exists
    existing_tables = inspector.get_table_names()
    if "student_bank_accounts" not in existing_tables:
        print("student_bank_accounts table does not exist, skipping")
        return

    # Get existing columns
    existing_columns = [col["name"] for col in inspector.get_columns("student_bank_accounts")]

    # Add passbook_cover_object_name if not exists
    if "passbook_cover_object_name" not in existing_columns:
        op.add_column(
            "student_bank_accounts", sa.Column("passbook_cover_object_name", sa.String(length=500), nullable=True)
        )

    # Add verification_method if not exists
    if "verification_method" not in existing_columns:
        op.add_column("student_bank_accounts", sa.Column("verification_method", sa.String(length=20), nullable=True))

    # Add ai_verification_confidence if not exists
    if "ai_verification_confidence" not in existing_columns:
        op.add_column("student_bank_accounts", sa.Column("ai_verification_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove passbook cover and verification details columns"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if table exists
    existing_tables = inspector.get_table_names()
    if "student_bank_accounts" not in existing_tables:
        return

    # Get existing columns
    existing_columns = [col["name"] for col in inspector.get_columns("student_bank_accounts")]

    # Drop columns if they exist
    if "ai_verification_confidence" in existing_columns:
        op.drop_column("student_bank_accounts", "ai_verification_confidence")

    if "verification_method" in existing_columns:
        op.drop_column("student_bank_accounts", "verification_method")

    if "passbook_cover_object_name" in existing_columns:
        op.drop_column("student_bank_accounts", "passbook_cover_object_name")
