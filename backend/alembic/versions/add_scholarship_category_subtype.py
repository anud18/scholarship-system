"""Add scholarship category and sub-type support

Revision ID: add_scholarship_category_subtype
Revises: latest
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_scholarship_category_subtype'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to scholarship_types table
    op.add_column('scholarship_types', sa.Column('category', sa.String(50), nullable=False, server_default='special'))
    op.add_column('scholarship_types', sa.Column('sub_type', sa.String(50), nullable=False, server_default='general'))
    op.add_column('scholarship_types', sa.Column('is_combined', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('scholarship_types', sa.Column('parent_scholarship_id', sa.Integer(), nullable=True))
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_scholarship_parent',
        'scholarship_types',
        'scholarship_types',
        ['parent_scholarship_id'],
        ['id']
    )
    
    # Create indexes
    op.create_index('idx_scholarship_category', 'scholarship_types', ['category'])
    op.create_index('idx_scholarship_sub_type', 'scholarship_types', ['sub_type'])
    op.create_index('idx_scholarship_parent_id', 'scholarship_types', ['parent_scholarship_id'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_scholarship_parent_id', 'scholarship_types')
    op.drop_index('idx_scholarship_sub_type', 'scholarship_types')
    op.drop_index('idx_scholarship_category', 'scholarship_types')
    
    # Drop foreign key
    op.drop_constraint('fk_scholarship_parent', 'scholarship_types', type_='foreignkey')
    
    # Drop columns
    op.drop_column('scholarship_types', 'parent_scholarship_id')
    op.drop_column('scholarship_types', 'is_combined')
    op.drop_column('scholarship_types', 'sub_type')
    op.drop_column('scholarship_types', 'category')