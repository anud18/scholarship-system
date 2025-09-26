"""001_complete_initial_schema

Complete initial schema with all tables and enums.
This replaces all previous migrations.

Revision ID: 59b65a4de996
Revises:
Create Date: 2025-09-25 02:12:21.898181

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "59b65a4de996"
down_revision: Union[str, None] = None  # This is the root migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if running on SQLite (for tests) or PostgreSQL (for production)
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if not is_sqlite:
        # Create all enum types (PostgreSQL only)
        op.execute(
            """
            DO $$ BEGIN
                CREATE TYPE usertype AS ENUM ('student', 'employee');
                CREATE TYPE userrole AS ENUM ('student', 'professor', 'college', 'admin', 'super_admin');
                CREATE TYPE employeestatus AS ENUM ('在職', '退休', '在學', '畢業');
                CREATE TYPE notificationtype AS ENUM ('INFO', 'WARNING', 'ERROR', 'SUCCESS', 'REMINDER');
                CREATE TYPE notificationpriority AS ENUM ('LOW', 'NORMAL', 'HIGH', 'URGENT');
                CREATE TYPE semester AS ENUM ('FIRST', 'SECOND', 'SUMMER', 'ANNUAL');
                CREATE TYPE applicationstatus AS ENUM ('draft', 'submitted', 'under_review', 'approved', 'rejected', 'withdrawn');
                CREATE TYPE applicationcycle AS ENUM ('semester', 'yearly');
                CREATE TYPE subtypeselectionmode AS ENUM ('single', 'multiple', 'hierarchical');
                CREATE TYPE quotamanagementmode AS ENUM ('none', 'simple', 'college_based', 'matrix_based');
                CREATE TYPE emailcategory AS ENUM ('application_confirmation', 'review_request', 'decision_notification', 'reminder', 'system_notification', 'custom');
                CREATE TYPE emailstatus AS ENUM ('pending', 'sent', 'failed', 'cancelled');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """
        )

    # Use Base.metadata.create_all() for all tables
    # This ensures all tables are created correctly regardless of dialect
    import app.models.application
    import app.models.application_field
    import app.models.audit_log
    import app.models.college_review
    import app.models.email_management
    import app.models.notification
    import app.models.scholarship
    import app.models.student
    import app.models.system_setting
    import app.models.user
    import app.models.user_profile
    from app.db.base_class import Base

    # Create all tables using SQLAlchemy metadata
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # Drop all tables in reverse order
    tables_to_drop = [
        "professor_review_items",
        "college_ranking_items",
        "scheduled_emails",
        "professor_reviews",
        "email_history",
        "college_reviews",
        "application_reviews",
        "application_files",
        "applications",
        "scholarship_sub_type_configs",
        "scholarship_rules",
        "scholarship_configurations",
        "notification_reads",
        "college_rankings",
        "admin_scholarships",
        "user_profiles",
        "user_profile_history",
        "scholarship_types",
        "quota_distributions",
        "notifications",
        "notification_queue",
        "notification_preferences",
        "enroll_types",
        "audit_logs",
        "application_fields",
        "application_documents",
        "users",
        "system_settings",
        "studying_statuses",
        "school_identities",
        "notification_templates",
        "identities",
        "email_templates",
        "departments",
        "degrees",
        "academies",
    ]

    for table in tables_to_drop:
        op.drop_table(table, if_exists=True)

    # Drop enum types (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.execute("DROP TYPE IF EXISTS emailstatus CASCADE")
        op.execute("DROP TYPE IF EXISTS emailcategory CASCADE")
        op.execute("DROP TYPE IF EXISTS quotamanagementmode CASCADE")
        op.execute("DROP TYPE IF EXISTS subtypeselectionmode CASCADE")
        op.execute("DROP TYPE IF EXISTS applicationcycle CASCADE")
        op.execute("DROP TYPE IF EXISTS applicationstatus CASCADE")
        op.execute("DROP TYPE IF EXISTS semester CASCADE")
        op.execute("DROP TYPE IF EXISTS notificationpriority CASCADE")
        op.execute("DROP TYPE IF EXISTS notificationtype CASCADE")
        op.execute("DROP TYPE IF EXISTS employeestatus CASCADE")
        op.execute("DROP TYPE IF EXISTS userrole CASCADE")
        op.execute("DROP TYPE IF EXISTS usertype CASCADE")
