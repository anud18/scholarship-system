"""Add comprehensive scholarship system tables

Revision ID: 001_scholarship_system
Revises: 
Create Date: 2025-07-31 01:59:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_scholarship_system'
down_revision = 'create_application_fields_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    scholarship_main_type = postgresql.ENUM(
        'UNDERGRADUATE_FRESHMAN', 'PHD', 'DIRECT_PHD',
        name='scholarshipmaintype'
    )
    scholarship_main_type.create(op.get_bind())
    
    scholarship_sub_type = postgresql.ENUM(
        'GENERAL', 'NSTC', 'MOE_1W', 'MOE_2W',
        name='scholarshipsubtype'
    )
    scholarship_sub_type.create(op.get_bind())
    
    review_cycle = postgresql.ENUM(
        'SEMESTER', 'MONTHLY',
        name='reviewcycle'
    )
    review_cycle.create(op.get_bind())
    
    application_status = postgresql.ENUM(
        'DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'PROFESSOR_REVIEW',
        'APPROVED', 'REJECTED', 'WITHDRAWN',
        name='applicationstatus'
    )
    application_status.create(op.get_bind())
    
    review_status = postgresql.ENUM(
        'PENDING', 'IN_PROGRESS', 'COMPLETED', 'OVERDUE',
        name='reviewstatus'
    )
    review_status.create(op.get_bind())

    # Create scholarship_sub_type_configs table
    op.create_table('scholarship_sub_type_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('main_type', scholarship_main_type, nullable=False),
        sa.Column('sub_type', scholarship_sub_type, nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('name_en', sa.String(length=200), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('description_en', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=True),
        sa.Column('review_cycle', review_cycle, nullable=True),
        sa.Column('quota_per_college', sa.JSON(), nullable=True),
        sa.Column('total_quota', sa.Integer(), nullable=True),
        sa.Column('renewal_priority', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scholarship_sub_type_configs_id'), 'scholarship_sub_type_configs', ['id'], unique=False)

    # Create applications table
    op.create_table('applications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scholarship_type_id', sa.Integer(), nullable=False),
        sa.Column('sub_type_config_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('application_number', sa.String(length=50), nullable=True),
        sa.Column('semester', sa.String(length=20), nullable=False),
        sa.Column('academic_year', sa.String(length=10), nullable=False),
        sa.Column('is_renewal', sa.Boolean(), nullable=True),
        sa.Column('previous_application_id', sa.Integer(), nullable=True),
        sa.Column('status', application_status, nullable=True),
        sa.Column('priority_score', sa.Integer(), nullable=True),
        sa.Column('application_data', sa.JSON(), nullable=True),
        sa.Column('requested_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('student_notes', sa.Text(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['previous_application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['scholarship_type_id'], ['scholarship_types.id'], ),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ),
        sa.ForeignKeyConstraint(['sub_type_config_id'], ['scholarship_sub_type_configs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_applications_application_number'), 'applications', ['application_number'], unique=True)
    op.create_index(op.f('ix_applications_id'), 'applications', ['id'], unique=False)

    # Create application_files table
    op.create_table('application_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('original_name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_type', sa.String(length=50), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('document_type', sa.String(length=50), nullable=True),
        sa.Column('is_required', sa.Boolean(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column('verified_by', sa.Integer(), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_application_files_id'), 'application_files', ['id'], unique=False)

    # Create application_reviews table
    op.create_table('application_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('reviewer_id', sa.Integer(), nullable=False),
        sa.Column('review_stage', sa.String(length=50), nullable=True),
        sa.Column('status', review_status, nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('recommendation', sa.String(length=20), nullable=True),
        sa.Column('score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('max_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_application_reviews_id'), 'application_reviews', ['id'], unique=False)

    # Create professor_reviews table
    op.create_table('professor_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('professor_id', sa.Integer(), nullable=False),
        sa.Column('review_type', sa.String(length=50), nullable=True),
        sa.Column('is_required', sa.Boolean(), nullable=True),
        sa.Column('overall_rating', sa.Integer(), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('recommendation', sa.String(length=20), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', review_status, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_professor_reviews_id'), 'professor_reviews', ['id'], unique=False)

    # Create professor_review_items table
    op.create_table('professor_review_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('professor_review_id', sa.Integer(), nullable=False),
        sa.Column('item_name', sa.String(length=100), nullable=False),
        sa.Column('item_description', sa.Text(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('max_rating', sa.Integer(), nullable=True),
        sa.Column('weight', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['professor_review_id'], ['professor_reviews.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_professor_review_items_id'), 'professor_review_items', ['id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f('ix_professor_review_items_id'), table_name='professor_review_items')
    op.drop_table('professor_review_items')
    
    op.drop_index(op.f('ix_professor_reviews_id'), table_name='professor_reviews')
    op.drop_table('professor_reviews')
    
    op.drop_index(op.f('ix_application_reviews_id'), table_name='application_reviews')
    op.drop_table('application_reviews')
    
    op.drop_index(op.f('ix_application_files_id'), table_name='application_files')
    op.drop_table('application_files')
    
    op.drop_index(op.f('ix_applications_id'), table_name='applications')
    op.drop_index(op.f('ix_applications_application_number'), table_name='applications')
    op.drop_table('applications')
    
    op.drop_index(op.f('ix_scholarship_sub_type_configs_id'), table_name='scholarship_sub_type_configs')
    op.drop_table('scholarship_sub_type_configs')
    
    # Drop enum types
    sa.Enum(name='reviewstatus').drop(op.get_bind())
    sa.Enum(name='applicationstatus').drop(op.get_bind())
    sa.Enum(name='reviewcycle').drop(op.get_bind())
    sa.Enum(name='scholarshipsubtype').drop(op.get_bind())
    sa.Enum(name='scholarshipmaintype').drop(op.get_bind())