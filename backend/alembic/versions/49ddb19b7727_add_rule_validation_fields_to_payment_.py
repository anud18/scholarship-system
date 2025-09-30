"""add rule validation fields to payment roster items

Revision ID: 49ddb19b7727
Revises: 5ee2f1e2708b
Create Date: 2025-09-28 12:44:39.233605

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "49ddb19b7727"
down_revision: Union[str, None] = "5ee2f1e2708b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if columns already exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("payment_roster_items")}

    # Add rule validation fields to payment_roster_items table only if they don't exist
    if "rule_validation_result" not in existing_columns:
        op.add_column("payment_roster_items", sa.Column("rule_validation_result", sa.JSON(), nullable=True))
    if "failed_rules" not in existing_columns:
        op.add_column("payment_roster_items", sa.Column("failed_rules", sa.JSON(), nullable=True))
    if "warning_rules" not in existing_columns:
        op.add_column("payment_roster_items", sa.Column("warning_rules", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove rule validation fields from payment_roster_items table
    op.drop_column("payment_roster_items", "warning_rules")
    op.drop_column("payment_roster_items", "failed_rules")
    op.drop_column("payment_roster_items", "rule_validation_result")
