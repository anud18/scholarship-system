"""Add performance indexes for quota management

Revision ID: performance_indexes
Revises: fdbf3cdbfe6d
Create Date: 2024-08-04 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250805_061614'
down_revision = 'fdbf3cdbfe6d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance indexes for quota management"""
    
    # Index for scholarship_configurations table - critical for quota queries
    op.create_index(
        'idx_scholarship_configs_lookup',
        'scholarship_configurations',
        ['scholarship_type_id', 'academic_year', 'semester', 'is_active'],
        unique=False
    )
    
    # Index for applications table - critical for usage calculations
    op.create_index(
        'idx_applications_quota_usage',
        'applications',
        ['scholarship_type_id', 'academic_year', 'status'],
        unique=False
    )
    
    # Additional index for applications with semester
    op.create_index(
        'idx_applications_semester_usage',
        'applications',
        ['scholarship_type_id', 'academic_year', 'semester', 'status'],
        unique=False
    )
    
    # Index for students table - for college-based filtering
    op.create_index(
        'idx_students_college',
        'students',
        ['std_aca_no'],
        unique=False
    )
    
    # Index for student_id in applications for JOIN performance
    op.create_index(
        'idx_applications_student_lookup',
        'applications',
        ['student_id', 'scholarship_type_id'],
        unique=False
    )


def downgrade() -> None:
    """Remove performance indexes"""
    
    op.drop_index('idx_applications_student_lookup', table_name='applications')
    op.drop_index('idx_students_college', table_name='students')
    op.drop_index('idx_applications_semester_usage', table_name='applications')
    op.drop_index('idx_applications_quota_usage', table_name='applications')
    op.drop_index('idx_scholarship_configs_lookup', table_name='scholarship_configurations')