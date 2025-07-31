"""Add scholarship sub-type configuration table

Revision ID: add_scholarship_subtype_config
Revises: add_scholarship_category_subtype
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_scholarship_subtype_config'
down_revision = 'add_scholarship_category_subtype'
branch_labels = None
depends_on = None


def upgrade():
    # Create scholarship_sub_type_configs table
    op.create_table('scholarship_sub_type_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scholarship_type_id', sa.Integer(), nullable=False),
        sa.Column('sub_type_code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('name_en', sa.String(length=200), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('description_en', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['scholarship_type_id'], ['scholarship_types.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_scholarship_sub_type_configs_id'), 'scholarship_sub_type_configs', ['id'], unique=False)
    op.create_index(op.f('ix_scholarship_sub_type_configs_scholarship_type_id'), 'scholarship_sub_type_configs', ['scholarship_type_id'], unique=False)
    op.create_index(op.f('ix_scholarship_sub_type_configs_sub_type_code'), 'scholarship_sub_type_configs', ['sub_type_code'], unique=False)
    
    # Add unique constraint for scholarship_type_id + sub_type_code combination
    op.create_unique_constraint('uq_scholarship_subtype_config', 'scholarship_sub_type_configs', ['scholarship_type_id', 'sub_type_code'])


def downgrade():
    # Drop indexes and constraints
    op.drop_constraint('uq_scholarship_subtype_config', 'scholarship_sub_type_configs', type_='unique')
    op.drop_index(op.f('ix_scholarship_sub_type_configs_sub_type_code'), table_name='scholarship_sub_type_configs')
    op.drop_index(op.f('ix_scholarship_sub_type_configs_scholarship_type_id'), table_name='scholarship_sub_type_configs')
    op.drop_index(op.f('ix_scholarship_sub_type_configs_id'), table_name='scholarship_sub_type_configs')
    
    # Drop table
    op.drop_table('scholarship_sub_type_configs') 