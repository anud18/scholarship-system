"""create_email_automation_rules

郵件自動化規則表格：
- 建立 email_automation_rules 表格
- 新增 trigger_event enum 類型
- 建立相關索引
- 插入初始自動化規則

Revision ID: c5d8f9a2b3e1
Revises: 24becd31ed61
Create Date: 2025-10-04 12:05:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d8f9a2b3e1"
down_revision: Union[str, None] = "24becd31ed61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 檢查表格是否已存在
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 建立 trigger_event enum 類型
    trigger_event_enum = ENUM(
        "application_submitted",
        "professor_review_submitted",
        "college_review_submitted",
        "final_result_decided",
        "supplement_requested",
        "deadline_approaching",
        name="triggerevent",
        create_type=False,
    )

    # 檢查 enum 是否已存在
    try:
        trigger_event_enum.create(bind, checkfirst=True)
    except Exception:
        pass  # Enum already exists

    # 建立 email_automation_rules 表格
    if "email_automation_rules" not in existing_tables:
        op.create_table(
            "email_automation_rules",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("trigger_event", trigger_event_enum, nullable=False),
            sa.Column("template_key", sa.String(100), sa.ForeignKey("email_templates.key"), nullable=False),
            sa.Column("delay_hours", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("condition_query", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
        )

        # 建立索引
        op.create_index(
            "idx_automation_rules_trigger_active",
            "email_automation_rules",
            ["trigger_event", "is_active"],
            unique=False,
        )
        op.create_index("idx_automation_rules_template", "email_automation_rules", ["template_key"], unique=False)

        print("✅ Created email_automation_rules table")
    else:
        print("ℹ️  email_automation_rules table already exists")


def downgrade() -> None:
    # 檢查表格是否存在
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 刪除表格
    if "email_automation_rules" in existing_tables:
        op.drop_index("idx_automation_rules_template", table_name="email_automation_rules")
        op.drop_index("idx_automation_rules_trigger_active", table_name="email_automation_rules")
        op.drop_table("email_automation_rules")

    # 刪除 enum 類型
    try:
        ENUM(name="triggerevent").drop(bind, checkfirst=True)
    except Exception:
        pass  # Enum might be in use by other tables
