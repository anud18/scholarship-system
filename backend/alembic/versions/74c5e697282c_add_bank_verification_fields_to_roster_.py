"""add_bank_verification_fields_to_roster_items

Adds separate bank verification fields for account number and account holder
to enable individual status tracking and manual review support.

Revision ID: 74c5e697282c
Revises: 0a35efe15189
Create Date: 2025-10-27 16:42:41.896722

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "74c5e697282c"
down_revision: Union[str, None] = "0a35efe15189"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add separate bank verification status fields for account number and holder"""
    # Check if columns already exist before adding
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("payment_roster_items")]

    if "bank_account_number_status" not in existing_columns:
        op.add_column(
            "payment_roster_items", sa.Column("bank_account_number_status", sa.String(length=20), nullable=True)
        )

    if "bank_account_holder_status" not in existing_columns:
        op.add_column(
            "payment_roster_items", sa.Column("bank_account_holder_status", sa.String(length=20), nullable=True)
        )

    if "bank_verification_details" not in existing_columns:
        op.add_column(
            "payment_roster_items",
            sa.Column("bank_verification_details", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        )

    if "bank_manual_review_notes" not in existing_columns:
        op.add_column("payment_roster_items", sa.Column("bank_manual_review_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove separate bank verification status fields"""
    # Check if columns exist before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("payment_roster_items")]

    if "bank_manual_review_notes" in existing_columns:
        op.drop_column("payment_roster_items", "bank_manual_review_notes")

    if "bank_verification_details" in existing_columns:
        op.drop_column("payment_roster_items", "bank_verification_details")

    if "bank_account_holder_status" in existing_columns:
        op.drop_column("payment_roster_items", "bank_account_holder_status")

    if "bank_account_number_status" in existing_columns:
        op.drop_column("payment_roster_items", "bank_account_number_status")
