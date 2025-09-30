"""Add configuration management fields and audit log table

Revision ID: 0f8f3a9bbaaf
Revises: 460001
Create Date: 2025-09-27 14:31:02.616489

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0f8f3a9bbaaf'
down_revision: Union[str, None] = '460001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types for configuration management
    config_category_enum = postgresql.ENUM(
        'database', 'api_keys', 'email', 'ocr', 'file_storage',
        'security', 'features', 'integrations', 'performance', 'logging',
        name='configcategory'
    )
    config_category_enum.create(op.get_bind(), checkfirst=True)

    config_data_type_enum = postgresql.ENUM(
        'string', 'integer', 'boolean', 'json', 'float',
        name='configdatatype'
    )
    config_data_type_enum.create(op.get_bind(), checkfirst=True)

    # Add new columns to system_settings table
    op.add_column('system_settings', sa.Column('category', sa.Enum('database', 'api_keys', 'email', 'ocr', 'file_storage', 'security', 'features', 'integrations', 'performance', 'logging', name='configcategory'), nullable=False, server_default='features'))
    op.add_column('system_settings', sa.Column('data_type', sa.Enum('string', 'integer', 'boolean', 'json', 'float', name='configdatatype'), nullable=False, server_default='string'))
    op.add_column('system_settings', sa.Column('is_sensitive', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('system_settings', sa.Column('is_readonly', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('system_settings', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('system_settings', sa.Column('validation_regex', sa.String(length=255), nullable=True))
    op.add_column('system_settings', sa.Column('default_value', sa.Text(), nullable=True))
    op.add_column('system_settings', sa.Column('last_modified_by', sa.Integer(), nullable=True))
    op.add_column('system_settings', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True))

    # Add foreign key constraint for last_modified_by
    op.create_foreign_key('system_settings_last_modified_by_fkey', 'system_settings', 'users', ['last_modified_by'], ['id'])

    # Make unique constraint on key column
    op.create_unique_constraint('system_settings_key_unique', 'system_settings', ['key'])

    # Create configuration_audit_logs table
    op.create_table('configuration_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('setting_key', sa.String(length=100), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('changed_by', sa.Integer(), nullable=False),
        sa.Column('change_reason', sa.Text(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_configuration_audit_logs_id', 'configuration_audit_logs', ['id'], unique=False)
    op.create_index('ix_configuration_audit_logs_setting_key', 'configuration_audit_logs', ['setting_key'], unique=False)
    op.create_index('ix_configuration_audit_logs_changed_at', 'configuration_audit_logs', ['changed_at'], unique=False)


def downgrade() -> None:
    # Drop the audit logs table
    op.drop_index('ix_configuration_audit_logs_changed_at', table_name='configuration_audit_logs')
    op.drop_index('ix_configuration_audit_logs_setting_key', table_name='configuration_audit_logs')
    op.drop_index('ix_configuration_audit_logs_id', table_name='configuration_audit_logs')
    op.drop_table('configuration_audit_logs')

    # Drop foreign key constraint
    op.drop_constraint('system_settings_last_modified_by_fkey', 'system_settings', type_='foreignkey')

    # Drop unique constraint
    op.drop_constraint('system_settings_key_unique', 'system_settings', type_='unique')

    # Remove columns from system_settings
    op.drop_column('system_settings', 'created_at')
    op.drop_column('system_settings', 'last_modified_by')
    op.drop_column('system_settings', 'default_value')
    op.drop_column('system_settings', 'validation_regex')
    op.drop_column('system_settings', 'description')
    op.drop_column('system_settings', 'is_readonly')
    op.drop_column('system_settings', 'is_sensitive')
    op.drop_column('system_settings', 'data_type')
    op.drop_column('system_settings', 'category')

    # Drop enum types
    sa.Enum(name='configdatatype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='configcategory').drop(op.get_bind(), checkfirst=True)