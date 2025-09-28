"""add payment roster tables

Revision ID: 5ee2f1e2708b
Revises: 96c65aa1feb9
Create Date: 2025-09-28 12:26:26.133161

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5ee2f1e2708b"
down_revision: Union[str, None] = "96c65aa1feb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy will automatically create enum types when creating tables

    # Create payment_rosters table
    op.create_table(
        "payment_rosters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("roster_code", sa.String(length=50), nullable=False),
        sa.Column("scholarship_configuration_id", sa.Integer(), nullable=False),
        sa.Column("period_label", sa.String(length=20), nullable=False),
        sa.Column("academic_year", sa.Integer(), nullable=False),
        sa.Column("roster_cycle", sa.Enum("monthly", "semi_annual", "annual", name="rostercycle"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "processing", "completed", "locked", "failed", name="rosterstatus"),
            nullable=False,
        ),
        sa.Column("trigger_type", sa.Enum("manual", "scheduled", "dry_run", name="rostertriggertype"), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.Integer(), nullable=True),
        sa.Column("total_applications", sa.Integer(), nullable=True),
        sa.Column("qualified_count", sa.Integer(), nullable=True),
        sa.Column("disqualified_count", sa.Integer(), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("excel_filename", sa.String(length=255), nullable=True),
        sa.Column("excel_file_path", sa.String(length=500), nullable=True),
        sa.Column("excel_file_size", sa.Integer(), nullable=True),
        sa.Column("excel_file_hash", sa.String(length=64), nullable=True),
        sa.Column("student_verification_enabled", sa.Boolean(), nullable=True),
        sa.Column("verification_api_failures", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("processing_log", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["locked_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["scholarship_configuration_id"],
            ["scholarship_configurations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("roster_code"),
        sa.UniqueConstraint("scholarship_configuration_id", "period_label", name="uq_roster_scholarship_period"),
    )
    op.create_index(op.f("ix_payment_rosters_id"), "payment_rosters", ["id"], unique=False)
    op.create_index(op.f("ix_payment_rosters_period_label"), "payment_rosters", ["period_label"], unique=False)
    op.create_index(op.f("ix_payment_rosters_roster_code"), "payment_rosters", ["roster_code"], unique=False)

    # Create payment_roster_items table
    op.create_table(
        "payment_roster_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("roster_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("student_id_number", sa.String(length=20), nullable=False),
        sa.Column("student_name", sa.String(length=100), nullable=False),
        sa.Column("student_email", sa.String(length=255), nullable=True),
        sa.Column("bank_account", sa.String(length=20), nullable=True),
        sa.Column("bank_code", sa.String(length=10), nullable=True),
        sa.Column("bank_name", sa.String(length=100), nullable=True),
        sa.Column("permanent_address", sa.String(length=500), nullable=True),
        sa.Column("mailing_address", sa.String(length=500), nullable=True),
        sa.Column("scholarship_name", sa.String(length=200), nullable=False),
        sa.Column("scholarship_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("scholarship_subtype", sa.String(length=50), nullable=True),
        sa.Column(
            "verification_status",
            sa.Enum(
                "verified",
                "graduated",
                "suspended",
                "withdrawn",
                "api_error",
                "not_found",
                name="studentverificationstatus",
            ),
            nullable=False,
        ),
        sa.Column("verification_message", sa.String(length=500), nullable=True),
        sa.Column("verification_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_snapshot", sa.JSON(), nullable=True),
        sa.Column("is_included", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=500), nullable=True),
        sa.Column("excel_row_data", sa.JSON(), nullable=True),
        sa.Column("excel_remarks", sa.Text(), nullable=True),
        sa.Column("nationality_code", sa.String(length=2), nullable=True),
        sa.Column("residence_days_over_183", sa.String(length=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
        ),
        sa.ForeignKeyConstraint(
            ["roster_id"],
            ["payment_rosters.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payment_roster_items_application_id"), "payment_roster_items", ["application_id"], unique=False
    )
    op.create_index(op.f("ix_payment_roster_items_id"), "payment_roster_items", ["id"], unique=False)
    op.create_index(op.f("ix_payment_roster_items_roster_id"), "payment_roster_items", ["roster_id"], unique=False)

    # Create roster_audit_logs table
    op.create_table(
        "roster_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("roster_id", sa.Integer(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "create",
                "update",
                "delete",
                "lock",
                "unlock",
                "export",
                "download",
                "student_verify",
                "schedule_run",
                "manual_run",
                "dry_run",
                "status_change",
                "item_add",
                "item_remove",
                "item_update",
                name="rosterauditaction",
            ),
            nullable=False,
        ),
        sa.Column("level", sa.Enum("info", "warning", "error", "critical", name="rosterauditlevel"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_name", sa.String(length=100), nullable=True),
        sa.Column("user_role", sa.String(length=50), nullable=True),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("old_values", sa.JSON(), nullable=True),
        sa.Column("new_values", sa.JSON(), nullable=True),
        sa.Column("api_endpoint", sa.String(length=200), nullable=True),
        sa.Column("request_method", sa.String(length=10), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("affected_items_count", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("warning_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(
            ["roster_id"],
            ["payment_rosters.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_roster_audit_logs_created_at"), "roster_audit_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_roster_audit_logs_id"), "roster_audit_logs", ["id"], unique=False)
    op.create_index(op.f("ix_roster_audit_logs_roster_id"), "roster_audit_logs", ["roster_id"], unique=False)

    # Create roster_schedules table
    op.create_table(
        "roster_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scholarship_configuration_id", sa.Integer(), nullable=False),
        sa.Column("schedule_name", sa.String(length=100), nullable=False),
        sa.Column("is_enabled", sa.JSON(), nullable=True),
        sa.Column("cron_expression", sa.String(length=100), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True),
        sa.Column("retry_delay_minutes", sa.Integer(), nullable=True),
        sa.Column("notify_on_success", sa.JSON(), nullable=True),
        sa.Column("notify_on_failure", sa.JSON(), nullable=True),
        sa.Column("notification_emails", sa.JSON(), nullable=True),
        sa.Column("student_verification_enabled", sa.JSON(), nullable=True),
        sa.Column("auto_lock_after_completion", sa.JSON(), nullable=True),
        sa.Column("max_execution_time_minutes", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=20), nullable=True),
        sa.Column("last_run_roster_id", sa.Integer(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["last_run_roster_id"],
            ["payment_rosters.id"],
        ),
        sa.ForeignKeyConstraint(
            ["scholarship_configuration_id"],
            ["scholarship_configurations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_roster_schedules_id"), "roster_schedules", ["id"], unique=False)


def downgrade() -> None:
    # Drop tables (enum types will be dropped automatically)
    op.drop_index(op.f("ix_roster_schedules_id"), table_name="roster_schedules")
    op.drop_table("roster_schedules")

    op.drop_index(op.f("ix_roster_audit_logs_roster_id"), table_name="roster_audit_logs")
    op.drop_index(op.f("ix_roster_audit_logs_id"), table_name="roster_audit_logs")
    op.drop_index(op.f("ix_roster_audit_logs_created_at"), table_name="roster_audit_logs")
    op.drop_table("roster_audit_logs")

    op.drop_index(op.f("ix_payment_roster_items_roster_id"), table_name="payment_roster_items")
    op.drop_index(op.f("ix_payment_roster_items_id"), table_name="payment_roster_items")
    op.drop_index(op.f("ix_payment_roster_items_application_id"), table_name="payment_roster_items")
    op.drop_table("payment_roster_items")

    op.drop_index(op.f("ix_payment_rosters_roster_code"), table_name="payment_rosters")
    op.drop_index(op.f("ix_payment_rosters_period_label"), table_name="payment_rosters")
    op.drop_index(op.f("ix_payment_rosters_id"), table_name="payment_rosters")
    op.drop_table("payment_rosters")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS rosterauditlevel")
    op.execute("DROP TYPE IF EXISTS rosterauditaction")
    op.execute("DROP TYPE IF EXISTS studentverificationstatus")
    op.execute("DROP TYPE IF EXISTS rostertriggertype")
    op.execute("DROP TYPE IF EXISTS rosterstatus")
    op.execute("DROP TYPE IF EXISTS rostercycle")
