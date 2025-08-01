"""Add missing application columns for schema compatibility

Revision ID: add_missing_application_columns  
Revises: add_scholarship_type_column
Create Date: 2025-08-01 04:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_missing_application_columns'
down_revision = 'add_scholarship_type_column'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add missing columns to match the Application model
    op.add_column('applications', sa.Column('scholarship_name', sa.String(length=200), nullable=True))
    op.add_column('applications', sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('applications', sa.Column('main_scholarship_type', sa.String(length=50), nullable=True))
    op.add_column('applications', sa.Column('sub_scholarship_type', sa.String(length=50), nullable=True, server_default='GENERAL'))
    op.add_column('applications', sa.Column('previous_application_id', sa.Integer(), nullable=True))
    op.add_column('applications', sa.Column('priority_score', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('applications', sa.Column('review_deadline', sa.DateTime(timezone=True), nullable=True))
    op.add_column('applications', sa.Column('decision_date', sa.DateTime(timezone=True), nullable=True))
    
    # Add foreign key constraint for previous_application_id
    op.create_foreign_key(
        'applications_previous_application_id_fkey',
        'applications', 'applications',
        ['previous_application_id'], ['id']
    )
    
    # Update existing records with default values where appropriate
    op.execute("UPDATE applications SET sub_scholarship_type = 'GENERAL' WHERE sub_scholarship_type IS NULL")
    op.execute("UPDATE applications SET priority_score = 0 WHERE priority_score IS NULL")


def downgrade() -> None:
    # Remove foreign key constraint first
    op.drop_constraint('applications_previous_application_id_fkey', 'applications', type_='foreignkey')
    
    # Remove added columns
    op.drop_column('applications', 'decision_date')
    op.drop_column('applications', 'review_deadline')
    op.drop_column('applications', 'priority_score')
    op.drop_column('applications', 'previous_application_id')
    op.drop_column('applications', 'sub_scholarship_type')
    op.drop_column('applications', 'main_scholarship_type')
    op.drop_column('applications', 'amount')
    op.drop_column('applications', 'scholarship_name')