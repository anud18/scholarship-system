"""add_student_bank_accounts_table

Adds student_bank_accounts table to track verified bank account information.
When an administrator verifies a student's bank account, the verified account
is saved here so students can see the verification status in future applications.

Revision ID: 2e6c27484cb1
Revises: 74c5e697282c
Create Date: 2025-10-27 09:40:05.512517

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e6c27484cb1"
down_revision: Union[str, None] = "74c5e697282c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add student_bank_accounts table"""
    # Check if table already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "student_bank_accounts" not in existing_tables:
        op.create_table(
            "student_bank_accounts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("account_number", sa.String(length=20), nullable=False),
            sa.Column("account_holder", sa.String(length=100), nullable=False),
            sa.Column("verification_status", sa.String(length=20), nullable=False, server_default="verified"),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("verified_by_user_id", sa.Integer(), nullable=True),
            sa.Column("verification_source_application_id", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("verification_notes", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["verification_source_application_id"], ["applications.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "account_number", name="uq_student_bank_account_user_number"),
        )

        # Create indexes
        op.create_index("ix_student_bank_accounts_id", "student_bank_accounts", ["id"])
        op.create_index("ix_student_bank_accounts_user_id", "student_bank_accounts", ["user_id"])
        op.create_index("ix_student_bank_accounts_account_number", "student_bank_accounts", ["account_number"])


def downgrade() -> None:
    """Remove student_bank_accounts table"""
    # Check if table exists before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "student_bank_accounts" in existing_tables:
        op.drop_index("ix_student_bank_accounts_account_number", table_name="student_bank_accounts")
        op.drop_index("ix_student_bank_accounts_user_id", table_name="student_bank_accounts")
        op.drop_index("ix_student_bank_accounts_id", table_name="student_bank_accounts")
        op.drop_table("student_bank_accounts")
