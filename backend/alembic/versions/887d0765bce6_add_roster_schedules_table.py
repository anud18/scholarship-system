"""add_roster_schedules_table

Revision ID: 887d0765bce6
Revises: 1160dcaa4f23
Create Date: 2025-09-28 13:42:18.117140

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "887d0765bce6"
down_revision: Union[str, None] = "1160dcaa4f23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create RosterScheduleStatus enum if it doesn't exist
    roster_schedule_status_enum = postgresql.ENUM(
        "active", "paused", "disabled", "error", name="rosterschedulestatus", create_type=False
    )
    roster_schedule_status_enum.create(op.get_bind(), checkfirst=True)

    # Use existing rostercycle enum
    roster_cycle_enum = postgresql.ENUM("monthly", "half_yearly", "yearly", name="rostercycle", create_type=False)

    # Create roster_schedules table
    op.create_table(
        "roster_schedules",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("schedule_name", sa.String(length=100), nullable=False, comment="排程名稱"),
        sa.Column("description", sa.Text(), nullable=True, comment="排程說明"),
        sa.Column("scholarship_configuration_id", sa.Integer(), nullable=False, comment="獎學金配置ID"),
        sa.Column("roster_cycle", roster_cycle_enum, nullable=False, comment="造冊週期"),
        sa.Column("cron_expression", sa.String(length=100), nullable=True, comment="Cron表達式"),
        sa.Column("auto_lock", sa.Boolean(), nullable=True, default=False, comment="自動鎖定產生的造冊"),
        sa.Column("student_verification_enabled", sa.Boolean(), nullable=True, default=True, comment="是否啟用學籍驗證"),
        sa.Column("notification_enabled", sa.Boolean(), nullable=True, default=True, comment="是否發送通知"),
        sa.Column("status", roster_schedule_status_enum, nullable=False, default="active", comment="排程狀態"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True, comment="上次執行時間"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True, comment="下次執行時間"),
        sa.Column("last_run_result", sa.String(length=50), nullable=True, comment="上次執行結果"),
        sa.Column("last_error_message", sa.Text(), nullable=True, comment="上次執行錯誤訊息"),
        sa.Column("total_runs", sa.Integer(), nullable=True, default=0, comment="總執行次數"),
        sa.Column("successful_runs", sa.Integer(), nullable=True, default=0, comment="成功執行次數"),
        sa.Column("failed_runs", sa.Integer(), nullable=True, default=0, comment="失敗執行次數"),
        sa.Column("notification_emails", sa.JSON(), nullable=True, comment="通知信箱清單"),
        sa.Column("notification_settings", sa.JSON(), nullable=True, comment="通知設定"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True, comment="建立者ID"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now(), comment="建立時間"
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, onupdate=sa.func.now(), comment="更新時間"),
        sa.ForeignKeyConstraint(["scholarship_configuration_id"], ["scholarship_configurations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_roster_schedules_id"), "roster_schedules", ["id"], unique=False)


def downgrade() -> None:
    # Drop roster_schedules table
    op.drop_index(op.f("ix_roster_schedules_id"), table_name="roster_schedules")
    op.drop_table("roster_schedules")

    # Drop the rosterschedulestatus enum (only if it was created by this migration)
    roster_schedule_status_enum = postgresql.ENUM(name="rosterschedulestatus")
    roster_schedule_status_enum.drop(op.get_bind(), checkfirst=True)
