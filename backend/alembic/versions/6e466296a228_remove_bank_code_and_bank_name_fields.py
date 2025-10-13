"""remove_bank_code_and_bank_name_fields

Revision ID: 6e466296a228
Revises: 8d7aa61ad1f9
Create Date: 2025-10-13 23:34:28.442351

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6e466296a228"
down_revision: Union[str, None] = "8d7aa61ad1f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove bank_code from user_profiles and bank_code, bank_name from payment_roster_items"""
    # Get database inspector to check for existing columns
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check and remove bank_code from user_profiles
    user_profiles_columns = {col["name"] for col in inspector.get_columns("user_profiles")}
    if "bank_code" in user_profiles_columns:
        op.drop_column("user_profiles", "bank_code")
        print("✓ Removed bank_code from user_profiles")
    else:
        print("⏭️  Skipping bank_code removal from user_profiles - column does not exist")

    # Check and remove bank_code and bank_name from payment_roster_items
    roster_items_columns = {col["name"] for col in inspector.get_columns("payment_roster_items")}
    if "bank_code" in roster_items_columns:
        op.drop_column("payment_roster_items", "bank_code")
        print("✓ Removed bank_code from payment_roster_items")
    else:
        print("⏭️  Skipping bank_code removal from payment_roster_items - column does not exist")

    if "bank_name" in roster_items_columns:
        op.drop_column("payment_roster_items", "bank_name")
        print("✓ Removed bank_name from payment_roster_items")
    else:
        print("⏭️  Skipping bank_name removal from payment_roster_items - column does not exist")


def downgrade() -> None:
    """Restore bank_code to user_profiles and bank_code, bank_name to payment_roster_items"""
    # Get database inspector to check for existing columns
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Restore bank_code to user_profiles
    user_profiles_columns = {col["name"] for col in inspector.get_columns("user_profiles")}
    if "bank_code" not in user_profiles_columns:
        op.add_column("user_profiles", sa.Column("bank_code", sa.String(length=20), nullable=True))
        print("✓ Restored bank_code to user_profiles")
    else:
        print("⏭️  Skipping bank_code restoration to user_profiles - column already exists")

    # Restore bank_code and bank_name to payment_roster_items
    roster_items_columns = {col["name"] for col in inspector.get_columns("payment_roster_items")}
    if "bank_code" not in roster_items_columns:
        op.add_column("payment_roster_items", sa.Column("bank_code", sa.String(length=10), nullable=True))
        print("✓ Restored bank_code to payment_roster_items")
    else:
        print("⏭️  Skipping bank_code restoration to payment_roster_items - column already exists")

    if "bank_name" not in roster_items_columns:
        op.add_column("payment_roster_items", sa.Column("bank_name", sa.String(length=100), nullable=True))
        print("✓ Restored bank_name to payment_roster_items")
    else:
        print("⏭️  Skipping bank_name restoration to payment_roster_items - column already exists")
