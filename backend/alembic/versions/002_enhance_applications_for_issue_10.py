"""Enhance applications table for issue #10 - comprehensive scholarship system

Revision ID: 002_enhance_applications
Revises: 
Create Date: 2025-07-31 02:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_enhance_applications'
down_revision = '001_scholarship_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to applications table for comprehensive scholarship system
    op.add_column('applications', sa.Column('scholarship_type_id', sa.Integer(), nullable=True))
    op.add_column('applications', sa.Column('main_scholarship_type', sa.String(length=50), nullable=True))
    op.add_column('applications', sa.Column('sub_scholarship_type', sa.String(length=50), nullable=True))
    op.add_column('applications', sa.Column('is_renewal', sa.Boolean(), nullable=True))
    op.add_column('applications', sa.Column('previous_application_id', sa.Integer(), nullable=True))
    op.add_column('applications', sa.Column('priority_score', sa.Integer(), nullable=True))
    op.add_column('applications', sa.Column('review_deadline', sa.DateTime(timezone=True), nullable=True))
    op.add_column('applications', sa.Column('decision_date', sa.DateTime(timezone=True), nullable=True))
    
    # Add foreign key constraints
    op.create_foreign_key(
        'fk_applications_scholarship_type',
        'applications', 'scholarship_types',
        ['scholarship_type_id'], ['id']
    )
    
    op.create_foreign_key(
        'fk_applications_previous_application',
        'applications', 'applications',
        ['previous_application_id'], ['id']
    )
    
    # Set default values for existing records
    op.execute("UPDATE applications SET sub_scholarship_type = 'GENERAL' WHERE sub_scholarship_type IS NULL")
    op.execute("UPDATE applications SET is_renewal = FALSE WHERE is_renewal IS NULL")
    op.execute("UPDATE applications SET priority_score = 0 WHERE priority_score IS NULL")
    
    # Create indexes for better performance
    op.create_index('ix_applications_main_scholarship_type', 'applications', ['main_scholarship_type'])
    op.create_index('ix_applications_sub_scholarship_type', 'applications', ['sub_scholarship_type'])
    op.create_index('ix_applications_is_renewal', 'applications', ['is_renewal'])
    op.create_index('ix_applications_priority_score', 'applications', ['priority_score'])
    op.create_index('ix_applications_review_deadline', 'applications', ['review_deadline'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_applications_review_deadline', table_name='applications')
    op.drop_index('ix_applications_priority_score', table_name='applications')
    op.drop_index('ix_applications_is_renewal', table_name='applications')
    op.drop_index('ix_applications_sub_scholarship_type', table_name='applications')
    op.drop_index('ix_applications_main_scholarship_type', table_name='applications')
    
    # Drop foreign key constraints
    op.drop_constraint('fk_applications_previous_application', 'applications', type_='foreignkey')
    op.drop_constraint('fk_applications_scholarship_type', 'applications', type_='foreignkey')
    
    # Drop columns
    op.drop_column('applications', 'decision_date')
    op.drop_column('applications', 'review_deadline')
    op.drop_column('applications', 'priority_score')
    op.drop_column('applications', 'previous_application_id')
    op.drop_column('applications', 'is_renewal')
    op.drop_column('applications', 'sub_scholarship_type')
    op.drop_column('applications', 'main_scholarship_type')
    op.drop_column('applications', 'scholarship_type_id')