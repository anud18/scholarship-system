"""Add professor student relationships table

Revision ID: 460001
Revises: 59b65a4de996
Create Date: 2025-09-27 13:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '460001'
down_revision: Union[str, None] = '59b65a4de996'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create professor_student_relationships table
    op.create_table(
        'professor_student_relationships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('professor_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('relationship_type', sa.String(length=50), nullable=False),
        sa.Column('department', sa.String(length=100), nullable=True),
        sa.Column('academic_year', sa.Integer(), nullable=True),
        sa.Column('semester', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('can_view_applications', sa.Boolean(), nullable=False, default=True),
        sa.Column('can_upload_documents', sa.Boolean(), nullable=False, default=False),
        sa.Column('can_review_applications', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['professor_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('professor_id', 'student_id', 'relationship_type', name='uq_prof_student_type')
    )
    op.create_index(op.f('ix_professor_student_relationships_id'), 'professor_student_relationships', ['id'], unique=False)
    op.create_index(op.f('ix_professor_student_relationships_professor_id'), 'professor_student_relationships', ['professor_id'], unique=False)
    op.create_index(op.f('ix_professor_student_relationships_student_id'), 'professor_student_relationships', ['student_id'], unique=False)


def downgrade() -> None:
    # Drop the table and indexes
    op.drop_index(op.f('ix_professor_student_relationships_student_id'), table_name='professor_student_relationships')
    op.drop_index(op.f('ix_professor_student_relationships_professor_id'), table_name='professor_student_relationships')
    op.drop_index(op.f('ix_professor_student_relationships_id'), table_name='professor_student_relationships')
    op.drop_table('professor_student_relationships')
