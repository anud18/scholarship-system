"""Add initial and renewal enable fields to scholarship rules

Revision ID: add_rule_enable_fields
Revises: update_notification_enums_v2
Create Date: 2025-01-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_rule_enable_fields'
down_revision = 'ea5d2bc75b8b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the new columns to scholarship_rules table
    op.add_column('scholarship_rules', sa.Column('is_initial_enabled', sa.Boolean(), nullable=False, default=True))
    op.add_column('scholarship_rules', sa.Column('is_renewal_enabled', sa.Boolean(), nullable=False, default=True))
    
    # Update existing records to have both fields enabled by default
    op.execute("UPDATE scholarship_rules SET is_initial_enabled = true, is_renewal_enabled = true")


def downgrade() -> None:
    # Remove the columns if rolling back
    op.drop_column('scholarship_rules', 'is_renewal_enabled')
    op.drop_column('scholarship_rules', 'is_initial_enabled')