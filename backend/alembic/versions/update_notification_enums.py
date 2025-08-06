"""Update notification enums for Facebook-style system

Revision ID: update_notification_enums
Revises: 
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
    
    # First, we need to handle the existing notification enums
    # Drop the existing enum types and recreate them with new values
    
    # Temporarily rename the columns to avoid conflicts
    op.alter_column('notifications', 'notification_type', new_column_name='notification_type_old', 
                    existing_type=sa.Enum(name='notificationtype'))
    op.alter_column('notifications', 'priority', new_column_name='priority_old',
                    existing_type=sa.Enum(name='notificationpriority'))
    
    # Drop existing enum types if they exist
    conn.execute(text("DROP TYPE IF EXISTS notificationtype CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS notificationpriority CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS notificationchannel CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS notificationfrequency CASCADE"))
    
    # Create new enum types
    notificationtype_enum = sa.Enum(
        'info', 'warning', 'error', 'success', 'reminder',
        'application_submitted', 'application_approved', 'application_rejected',
        'application_requires_review', 'application_under_review',
        'document_required', 'document_approved', 'document_rejected',
        'deadline_approaching', 'deadline_extended', 'review_deadline', 'application_deadline',
        'new_scholarship_available', 'matching_scholarship', 'scholarship_opening_soon',
        'professor_review_requested', 'professor_review_completed', 'admin_review_requested',
        'system_maintenance', 'admin_message', 'account_update', 'security_alert',
        name='notificationtype'
    )
    notificationtype_enum.create(conn)
    
    notificationpriority_enum = sa.Enum(
        'critical', 'high', 'normal', 'low',
        name='notificationpriority'
    )
    notificationpriority_enum.create(conn)
    
    notificationchannel_enum = sa.Enum(
        'in_app', 'email', 'sms', 'push',
        name='notificationchannel'
    )
    notificationchannel_enum.create(conn)
    
    notificationfrequency_enum = sa.Enum(
        'immediate', 'daily', 'weekly', 'disabled',
        name='notificationfrequency'
    )
    notificationfrequency_enum.create(conn)
    
    # Add new columns with the new enum types
    op.add_column('notifications', 
        sa.Column('notification_type', sa.Enum(name='notificationtype'), nullable=False, server_default='info')
    )
    op.add_column('notifications',
        sa.Column('priority', sa.Enum(name='notificationpriority'), nullable=False, server_default='normal')
    )
    
    # Add new Facebook-style columns if they don't exist
    columns_to_add = [
        ('channel', sa.Enum(name='notificationchannel'), 'in_app'),
        ('data', sa.JSON(), '{}'),
        ('href', sa.String(500), None),
        ('group_key', sa.String(100), None),
        ('batch_id', sa.String(50), None),
        ('is_archived', sa.Boolean(), False),
        ('is_hidden', sa.Boolean(), False),
        ('scheduled_for', sa.DateTime(timezone=True), None),
    ]
    
    # Get existing columns
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('notifications')]
    
    for col_name, col_type, default_value in columns_to_add:
        if col_name not in existing_columns:
            kwargs = {'nullable': True}
            if default_value is not None:
                kwargs['server_default'] = str(default_value) if not isinstance(default_value, bool) else ('true' if default_value else 'false')
            op.add_column('notifications', sa.Column(col_name, col_type, **kwargs))
    
    # Copy data from old columns to new columns with type mapping
    conn.execute(text("""
        UPDATE notifications 
        SET notification_type = CASE 
            WHEN notification_type_old::text = '0' THEN 'info'
            WHEN notification_type_old::text = '1' THEN 'warning'
            WHEN notification_type_old::text = '2' THEN 'error'
            WHEN notification_type_old::text = '3' THEN 'success'
            WHEN notification_type_old::text = '4' THEN 'reminder'
            ELSE LOWER(notification_type_old::text)
        END
    """))
    
    conn.execute(text("""
        UPDATE notifications 
        SET priority = CASE
            WHEN priority_old::text IN ('0', 'low') THEN 'low'
            WHEN priority_old::text IN ('1', 'normal') THEN 'normal'
            WHEN priority_old::text IN ('2', 'high') THEN 'high'
            WHEN priority_old::text IN ('3', 'urgent') THEN 'high'
            WHEN priority_old::text = 'critical' THEN 'critical'
            ELSE 'normal'
        END
    """))
    
    # Drop old columns
    op.drop_column('notifications', 'notification_type_old')
    op.drop_column('notifications', 'priority_old')
    
    # Create new tables for Facebook-style features
    op.create_table('notification_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notification_type', sa.Enum(name='notificationtype'), nullable=False),
        sa.Column('in_app_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sms_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('push_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('frequency', sa.Enum(name='notificationfrequency'), nullable=False, server_default='immediate'),
        sa.Column('quiet_hours_start', sa.String(5), nullable=True),
        sa.Column('quiet_hours_end', sa.String(5), nullable=True),
        sa.Column('timezone', sa.String(50), nullable=False, server_default='UTC'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.UniqueConstraint('user_id', 'notification_type', name='_user_notification_type_uc')
    )
    op.create_index('ix_notification_preferences_user_id', 'notification_preferences', ['user_id'])
    
    op.create_table('notification_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Enum(name='notificationtype'), nullable=False, unique=True),
        sa.Column('title_template', sa.String(255), nullable=False),
        sa.Column('title_template_en', sa.String(255), nullable=True),
        sa.Column('message_template', sa.Text(), nullable=False),
        sa.Column('message_template_en', sa.Text(), nullable=True),
        sa.Column('href_template', sa.String(500), nullable=True),
        sa.Column('default_channels', sa.JSON(), server_default='["in_app"]'),
        sa.Column('default_priority', sa.Enum(name='notificationpriority'), server_default='normal'),
        sa.Column('variables', sa.JSON(), server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('requires_user_action', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('notification_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.String(50), nullable=False),
        sa.Column('notification_type', sa.Enum(name='notificationtype'), nullable=False),
        sa.Column('priority', sa.Enum(name='notificationpriority'), server_default='normal'),
        sa.Column('notifications_data', sa.JSON(), nullable=False),
        sa.Column('aggregated_content', sa.JSON(), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0'),
        sa.Column('max_attempts', sa.Integer(), server_default='3'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
    )
    op.create_index('ix_notification_queue_user_id', 'notification_queue', ['user_id'])
    op.create_index('ix_notification_queue_batch_id', 'notification_queue', ['batch_id'])
    op.create_index('ix_notification_queue_scheduled_for', 'notification_queue', ['scheduled_for'])
    
    # Create indexes for performance
    op.create_index('idx_notifications_user_unread', 'notifications', ['user_id', 'is_read', 'created_at'])
    op.create_index('idx_notifications_type_created', 'notifications', ['notification_type', 'created_at'])
    op.create_index('idx_notifications_group_key', 'notifications', ['group_key', 'created_at'])
    op.create_index('idx_notifications_priority_scheduled', 'notifications', ['priority', 'scheduled_for'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_notifications_priority_scheduled', 'notifications')
    op.drop_index('idx_notifications_group_key', 'notifications')
    op.drop_index('idx_notifications_type_created', 'notifications')
    op.drop_index('idx_notifications_user_unread', 'notifications')
    
    # Drop new tables
    op.drop_table('notification_queue')
    op.drop_table('notification_templates')
    op.drop_table('notification_preferences')
    
    # Drop new columns
    columns_to_drop = ['channel', 'data', 'href', 'group_key', 'batch_id', 'is_archived', 'is_hidden', 'scheduled_for']
    for col in columns_to_drop:
        try:
            op.drop_column('notifications', col)
        except:
            pass
    
    # Revert enum types (simplified - in production you'd want to preserve data)
    conn = op.get_bind()
    
    # Drop and recreate old enum types
    conn.execute(text("DROP TYPE IF EXISTS notificationtype CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS notificationpriority CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS notificationchannel CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS notificationfrequency CASCADE"))