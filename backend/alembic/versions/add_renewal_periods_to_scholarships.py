"""Add renewal periods to scholarship_types table

Revision ID: add_renewal_periods_to_scholarships
Revises: add_is_renewal_to_applications
Create Date: 2025-01-03 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_renewal_periods_to_scholarships'
down_revision = 'add_is_renewal_to_applications'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add renewal period columns to scholarship_types table"""
    # Add renewal application period columns
    op.add_column('scholarship_types', sa.Column('renewal_application_start_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('scholarship_types', sa.Column('renewal_application_end_date', sa.DateTime(timezone=True), nullable=True))
    
    # Add renewal review period columns
    op.add_column('scholarship_types', sa.Column('renewal_professor_review_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('scholarship_types', sa.Column('renewal_professor_review_end', sa.DateTime(timezone=True), nullable=True))
    op.add_column('scholarship_types', sa.Column('renewal_college_review_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('scholarship_types', sa.Column('renewal_college_review_end', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove renewal period columns from scholarship_types table"""
    # Remove renewal review period columns
    op.drop_column('scholarship_types', 'renewal_college_review_end')
    op.drop_column('scholarship_types', 'renewal_college_review_start')
    op.drop_column('scholarship_types', 'renewal_professor_review_end')
    op.drop_column('scholarship_types', 'renewal_professor_review_start')
    
    # Remove renewal application period columns
    op.drop_column('scholarship_types', 'renewal_application_end_date')
    op.drop_column('scholarship_types', 'renewal_application_start_date') 