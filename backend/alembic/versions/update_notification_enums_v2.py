"""Update notification enums for Facebook-style system - Complete Raw SQL

Revision ID: update_notification_enums_v2
Revises: ea5d2bc75b8b
Create Date: 2025-08-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'update_notification_enums_v2'
down_revision = 'ea5d2bc75b8b'
branch_labels = None
depends_on = None


def upgrade():
    # Get the connection
    conn = op.get_bind()
    
    # Check if this migration has already been applied
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name='notifications' AND column_name='frequency'
        )
    """)).scalar()
    
    if result:
        # Migration already applied, nothing to do
        return
    
    # Extend existing notificationtype enum with new values
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
    
    # Create new enum types using raw SQL
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE notificationchannel AS ENUM ('IN_APP', 'EMAIL', 'SMS', 'PUSH');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))
    
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE notificationfrequency AS ENUM ('IMMEDIATE', 'DAILY', 'WEEKLY', 'DISABLED');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))
    
    # Add new columns to notifications table using raw SQL
    conn.execute(text("""
        DO $$ BEGIN
            BEGIN
                ALTER TABLE notifications ADD COLUMN frequency notificationfrequency DEFAULT 'IMMEDIATE';
            EXCEPTION
                WHEN duplicate_column THEN null;
            END;
        END $$;
    """))
    
    conn.execute(text("""
        DO $$ BEGIN
            BEGIN
                ALTER TABLE notifications ADD COLUMN channel notificationchannel DEFAULT 'IN_APP';
            EXCEPTION
                WHEN duplicate_column THEN null;
            END;
        END $$;
    """))
    
    conn.execute(text("""
        DO $$ BEGIN
            BEGIN
                ALTER TABLE notifications ADD COLUMN data JSON DEFAULT '{}';
            EXCEPTION
                WHEN duplicate_column THEN null;
            END;
        END $$;
    """))
    
    conn.execute(text("""
        DO $$ BEGIN
            BEGIN
                ALTER TABLE notifications ADD COLUMN href VARCHAR(500);
            EXCEPTION
                WHEN duplicate_column THEN null;
            END;
        END $$;
    """))
    
    conn.execute(text("""
        DO $$ BEGIN
            BEGIN
                ALTER TABLE notifications ADD COLUMN group_key VARCHAR(100);
            EXCEPTION
                WHEN duplicate_column THEN null;
            END;
        END $$;
    """))
    
    conn.execute(text("""
        DO $$ BEGIN
            BEGIN
                ALTER TABLE notifications ADD COLUMN batch_id VARCHAR(50);
            EXCEPTION
                WHEN duplicate_column THEN null;
            END;
        END $$;
    """))
    
    conn.execute(text("""
        DO $$ BEGIN
            BEGIN
                ALTER TABLE notifications ADD COLUMN is_archived BOOLEAN DEFAULT false;
            EXCEPTION
                WHEN duplicate_column THEN null;
            END;
        END $$;
    """))
    
    conn.execute(text("""
        DO $$ BEGIN
            BEGIN
                ALTER TABLE notifications ADD COLUMN is_hidden BOOLEAN DEFAULT false;
            EXCEPTION
                WHEN duplicate_column THEN null;
            END;
        END $$;
    """))
    
    conn.execute(text("""
        DO $$ BEGIN
            BEGIN
                ALTER TABLE notifications ADD COLUMN scheduled_for TIMESTAMPTZ;
            EXCEPTION
                WHEN duplicate_column THEN null;
            END;
        END $$;
    """))
    
    # Create notification_preferences table using raw SQL
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS notification_preferences (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            notification_type notificationtype NOT NULL,
            channel notificationchannel NOT NULL,
            frequency notificationfrequency NOT NULL DEFAULT 'IMMEDIATE',
            is_enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_user_notification_channel UNIQUE (user_id, notification_type, channel)
        );
    """))
    
    # Create notification_groups table using raw SQL
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS notification_groups (
            id SERIAL PRIMARY KEY,
            group_key VARCHAR(100) NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            notification_count INTEGER NOT NULL DEFAULT 1,
            latest_notification_id INTEGER REFERENCES notifications(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_group_user UNIQUE (group_key, user_id)
        );
    """))
    
    # Create indexes for performance using raw SQL
    indexes_to_create = [
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications (user_id, is_read);",
        "CREATE INDEX IF NOT EXISTS idx_notifications_type_user ON notifications (notification_type, user_id);",
        "CREATE INDEX IF NOT EXISTS idx_notifications_scheduled ON notifications (scheduled_for);",
        "CREATE INDEX IF NOT EXISTS idx_notifications_group ON notifications (group_key, user_id);",
        "CREATE INDEX IF NOT EXISTS idx_notification_preferences_user ON notification_preferences (user_id, is_enabled);"
    ]
    
    for index_sql in indexes_to_create:
        try:
            conn.execute(text(index_sql))
        except Exception:
            # Index might already exist, continue
            pass


def downgrade():
    # Get the connection
    conn = op.get_bind()
    
    # Drop indexes
    indexes_to_drop = [
        "DROP INDEX IF EXISTS idx_notification_preferences_user;",
        "DROP INDEX IF EXISTS idx_notifications_group;",
        "DROP INDEX IF EXISTS idx_notifications_scheduled;",
        "DROP INDEX IF EXISTS idx_notifications_type_user;",
        "DROP INDEX IF EXISTS idx_notifications_user_unread;"
    ]
    
    for index_sql in indexes_to_drop:
        try:
            conn.execute(text(index_sql))
        except Exception:
            pass
    
    # Drop new tables
    conn.execute(text("DROP TABLE IF EXISTS notification_groups CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS notification_preferences CASCADE;"))
    
    # Drop new columns from notifications table
    columns_to_drop = [
        'scheduled_for', 'is_hidden', 'is_archived', 'batch_id',
        'group_key', 'href', 'data', 'channel', 'frequency'
    ]
    
    for column in columns_to_drop:
        try:
            conn.execute(text(f"ALTER TABLE notifications DROP COLUMN IF EXISTS {column} CASCADE;"))
        except Exception:
            pass
    
    # Drop new enum types
    conn.execute(text("DROP TYPE IF EXISTS notificationfrequency CASCADE;"))
    conn.execute(text("DROP TYPE IF EXISTS notificationchannel CASCADE;"))