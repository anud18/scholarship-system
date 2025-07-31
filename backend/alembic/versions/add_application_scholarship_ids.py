"""Add scholarship type IDs to applications

Revision ID: add_application_scholarship_ids
Revises: add_scholarship_category_subtype
Create Date: 2024-01-01 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_application_scholarship_ids'
down_revision = 'add_scholarship_category_subtype'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to applications table
    op.add_column('applications', sa.Column('scholarship_type_id', sa.Integer(), nullable=True))
    op.add_column('applications', sa.Column('sub_scholarship_type_id', sa.Integer(), nullable=True))
    
    # Add foreign key constraints
    op.create_foreign_key(
        'fk_application_scholarship_type',
        'applications',
        'scholarship_types',
        ['scholarship_type_id'],
        ['id']
    )
    
    op.create_foreign_key(
        'fk_application_sub_scholarship_type',
        'applications',
        'scholarship_types',
        ['sub_scholarship_type_id'],
        ['id']
    )
    
    # Create indexes
    op.create_index('idx_application_scholarship_type_id', 'applications', ['scholarship_type_id'])
    op.create_index('idx_application_sub_scholarship_type_id', 'applications', ['sub_scholarship_type_id'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_application_sub_scholarship_type_id', 'applications')
    op.drop_index('idx_application_scholarship_type_id', 'applications')
    
    # Drop foreign keys
    op.drop_constraint('fk_application_sub_scholarship_type', 'applications', type_='foreignkey')
    op.drop_constraint('fk_application_scholarship_type', 'applications', type_='foreignkey')
    
    # Drop columns
    op.drop_column('applications', 'sub_scholarship_type_id')
    op.drop_column('applications', 'scholarship_type_id')