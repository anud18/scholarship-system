"""Create application fields and documents tables

Revision ID: create_application_fields_tables
Revises: add_application_scholarship_ids
Create Date: 2024-01-01 00:02:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'create_application_fields_tables'
down_revision = 'add_application_scholarship_ids'
branch_labels = None
depends_on = None


def upgrade():
    # Create application_fields table
    op.create_table('application_fields',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scholarship_type', sa.String(length=50), nullable=False),
        sa.Column('field_name', sa.String(length=100), nullable=False),
        sa.Column('field_label', sa.String(length=200), nullable=False),
        sa.Column('field_label_en', sa.String(length=200), nullable=True),
        sa.Column('field_type', sa.String(length=20), nullable=False),
        sa.Column('is_required', sa.Boolean(), nullable=True),
        sa.Column('placeholder', sa.String(length=500), nullable=True),
        sa.Column('placeholder_en', sa.String(length=500), nullable=True),
        sa.Column('max_length', sa.Integer(), nullable=True),
        sa.Column('min_value', sa.Float(), nullable=True),
        sa.Column('max_value', sa.Float(), nullable=True),
        sa.Column('step_value', sa.Float(), nullable=True),
        sa.Column('field_options', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('help_text', sa.Text(), nullable=True),
        sa.Column('help_text_en', sa.Text(), nullable=True),
        sa.Column('validation_rules', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('conditional_rules', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_application_fields_id'), 'application_fields', ['id'], unique=False)
    op.create_index(op.f('ix_application_fields_scholarship_type'), 'application_fields', ['scholarship_type'], unique=False)

    # Create application_documents table
    op.create_table('application_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scholarship_type', sa.String(length=50), nullable=False),
        sa.Column('document_name', sa.String(length=200), nullable=False),
        sa.Column('document_name_en', sa.String(length=200), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('description_en', sa.Text(), nullable=True),
        sa.Column('is_required', sa.Boolean(), nullable=True),
        sa.Column('accepted_file_types', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('max_file_size', sa.String(length=20), nullable=True),
        sa.Column('max_file_count', sa.Integer(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('upload_instructions', sa.Text(), nullable=True),
        sa.Column('upload_instructions_en', sa.Text(), nullable=True),
        sa.Column('validation_rules', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_application_documents_id'), 'application_documents', ['id'], unique=False)
    op.create_index(op.f('ix_application_documents_scholarship_type'), 'application_documents', ['scholarship_type'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_application_documents_scholarship_type'), table_name='application_documents')
    op.drop_index(op.f('ix_application_documents_id'), table_name='application_documents')
    op.drop_table('application_documents')
    op.drop_index(op.f('ix_application_fields_scholarship_type'), table_name='application_fields')
    op.drop_index(op.f('ix_application_fields_id'), table_name='application_fields')
    op.drop_table('application_fields') 