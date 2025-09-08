"""Update notification enums for Facebook-style system

Revision ID: update_notification_enums
Revises: ea5d2bc75b8b
Create Date: 2025-08-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'update_notification_enums'
down_revision = 'ea5d2bc75b8b'
branch_labels = None
depends_on = None


def upgrade():
    # Get the connection
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('notifications')]
    
    # Check if this migration has already been applied by looking for new columns
    has_new_columns = any(col in existing_columns for col in ['frequency', 'channel', 'data'])
    if has_new_columns:
        # Migration already applied, nothing to do
        return
    
    # For fresh installations, we need to extend the existing enum types with new values
    # Add new enum values to existing notificationtype enum
    new_notification_values = [
        'APPLICATION_SUBMITTED', 'APPLICATION_APPROVED', 'APPLICATION_REJECTED',
        'APPLICATION_REQUIRES_REVIEW', 'APPLICATION_UNDER_REVIEW',
        'DOCUMENT_REQUIRED', 'DOCUMENT_APPROVED', 'DOCUMENT_REJECTED',
        'DEADLINE_APPROACHING', 'DEADLINE_EXTENDED', 'REVIEW_DEADLINE', 'APPLICATION_DEADLINE',
        'NEW_SCHOLARSHIP_AVAILABLE', 'MATCHING_SCHOLARSHIP', 'SCHOLARSHIP_OPENING_SOON',
        'PROFESSOR_REVIEW_REQUESTED', 'PROFESSOR_REVIEW_COMPLETED', 'ADMIN_REVIEW_REQUESTED',
        'SYSTEM_MAINTENANCE', 'ADMIN_MESSAGE', 'ACCOUNT_UPDATE', 'SECURITY_ALERT'
    ]
    
    for value in new_notification_values:
        try:
            conn.execute(text(f"ALTER TYPE notificationtype ADD VALUE '{value}'"))
        except Exception:
            # Value might already exist, continue
            pass
    
    # Create new enum types for additional functionality
    conn.execute(text("DROP TYPE IF EXISTS notificationchannel CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS notificationfrequency CASCADE"))
    
    notificationchannel_enum = sa.Enum(
        'IN_APP', 'EMAIL', 'SMS', 'PUSH',
        name='notificationchannel'
    )
    notificationchannel_enum.create(conn)
    
    notificationfrequency_enum = sa.Enum(
        'IMMEDIATE', 'DAILY', 'WEEKLY', 'DISABLED',
        name='notificationfrequency'
    )
    notificationfrequency_enum.create(conn)
    
    # Add new columns with proper defaults
    columns_to_add = [
        ('frequency', sa.Enum(name='notificationfrequency'), 'IMMEDIATE'),
        ('channel', sa.Enum(name='notificationchannel'), 'IN_APP'),
        ('data', sa.JSON(), '{}'),
        ('href', sa.String(500), None),
        ('group_key', sa.String(100), None),
        ('batch_id', sa.String(50), None),
        ('is_archived', sa.Boolean(), False),
        ('is_hidden', sa.Boolean(), False),
        ('scheduled_for', sa.DateTime(timezone=True), None),
    ]
    
    for col_name, col_type, default_value in columns_to_add:
        if col_name not in existing_columns:
            kwargs = {'nullable': True}
            if default_value is not None:
                if isinstance(default_value, str) and default_value not in ['{}']:
                    # For enum values, use the enum default
                    kwargs['server_default'] = f"'{default_value}'"
                elif isinstance(default_value, bool):
                    kwargs['server_default'] = 'true' if default_value else 'false'
                elif default_value == '{}':
                    kwargs['server_default'] = "'{}'"
                else:
                    kwargs['server_default'] = str(default_value)
            op.add_column('notifications', sa.Column(col_name, col_type, **kwargs))
    
    # Create new tables for Facebook-style features
    op.create_table('notification_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notification_type', sa.Enum(name='notificationtype'), nullable=False),
        sa.Column('channel', sa.Enum(name='notificationchannel'), nullable=False),
        sa.Column('frequency', sa.Enum(name='notificationfrequency'), nullable=False, server_default='IMMEDIATE'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'notification_type', 'channel', name='uq_user_notification_channel')
    )

    op.create_table('notification_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_key', sa.String(100), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notification_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('latest_notification_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['latest_notification_id'], ['notifications.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_key', 'user_id', name='uq_group_user')
    )

    # Create indexes for performance
    op.create_index('idx_notifications_user_unread', 'notifications', ['user_id', 'is_read'])
    op.create_index('idx_notifications_type_user', 'notifications', ['notification_type', 'user_id'])
    op.create_index('idx_notifications_scheduled', 'notifications', ['scheduled_for'])
    op.create_index('idx_notifications_group', 'notifications', ['group_key', 'user_id'])
    op.create_index('idx_notification_preferences_user', 'notification_preferences', ['user_id', 'is_enabled'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_notification_preferences_user', table_name='notification_preferences')
    op.drop_index('idx_notifications_group', table_name='notifications')
    op.drop_index('idx_notifications_scheduled', table_name='notifications')
    op.drop_index('idx_notifications_type_user', table_name='notifications')
    op.drop_index('idx_notifications_user_unread', table_name='notifications')
    
    # Drop new tables
    op.drop_table('notification_groups')
    op.drop_table('notification_preferences')
    
    # Drop new columns
    op.drop_column('notifications', 'scheduled_for')
    op.drop_column('notifications', 'is_hidden')
    op.drop_column('notifications', 'is_archived')
    op.drop_column('notifications', 'batch_id')
    op.drop_column('notifications', 'group_key')
    op.drop_column('notifications', 'href')
    op.drop_column('notifications', 'data')
    op.drop_column('notifications', 'channel')
    op.drop_column('notifications', 'frequency')
    
    # Drop new enum types
    op.execute('DROP TYPE IF EXISTS notificationfrequency CASCADE')
    op.execute('DROP TYPE IF EXISTS notificationchannel CASCADE')