"""Add is_renewal field to applications table

Revision ID: add_is_renewal_to_applications
Revises: add_scholarship_subtype_config
Create Date: 2025-01-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_is_renewal_to_applications'
down_revision = 'add_scholarship_subtype_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add is_renewal column to applications table"""
    op.add_column('applications', sa.Column('is_renewal', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    """Remove is_renewal column from applications table"""
    op.drop_column('applications', 'is_renewal') 