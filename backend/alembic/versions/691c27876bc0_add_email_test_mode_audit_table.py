"""add_email_test_mode_audit_table

郵件測試模式功能：
- 建立 email_test_mode_audit 稽核表
- 新增 email_test_mode 系統設定
- 追蹤測試模式狀態變更和郵件攔截事件

Revision ID: 691c27876bc0
Revises: e5ce4830cc3d
Create Date: 2025-10-04 14:56:08.858093

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "691c27876bc0"
down_revision: Union[str, None] = "e5ce4830cc3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 檢查表格是否已存在
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 建立郵件測試模式稽核表
    if "email_test_mode_audit" not in existing_tables:
        op.create_table(
            "email_test_mode_audit",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            # 測試模式配置快照
            sa.Column("config_before", postgresql.JSONB(), nullable=True),
            sa.Column("config_after", postgresql.JSONB(), nullable=True),
            # 郵件攔截記錄
            sa.Column("original_recipient", sa.String(255), nullable=True),
            sa.Column("actual_recipient", sa.String(255), nullable=True),
            sa.Column("email_subject", sa.Text(), nullable=True),
            sa.Column("session_id", sa.String(100), nullable=True),
            # 請求元數據
            sa.Column("ip_address", postgresql.INET(), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
        )

        # 建立索引
        op.create_index("idx_email_test_audit_timestamp", "email_test_mode_audit", ["timestamp"], unique=False)
        op.create_index("idx_email_test_audit_event", "email_test_mode_audit", ["event_type"], unique=False)
        op.create_index("idx_email_test_audit_session", "email_test_mode_audit", ["session_id"], unique=False)
        op.create_index("idx_email_test_audit_user", "email_test_mode_audit", ["user_id"], unique=False)

    # 新增郵件測試模式系統設定（使用 ON CONFLICT DO NOTHING 避免重複）
    op.execute(
        """
        INSERT INTO system_settings (
            key,
            value,
            category,
            data_type,
            is_sensitive,
            is_readonly,
            description,
            created_at,
            updated_at
        )
        VALUES (
            'email_test_mode',
            '{"enabled": false, "redirect_email": null, "expires_at": null}',
            'email',
            'json',
            false,
            false,
            '郵件測試模式配置：重定向所有外發郵件至測試信箱，用於生產環境安全測試',
            NOW(),
            NOW()
        )
        ON CONFLICT (key) DO NOTHING
    """
    )


def downgrade() -> None:
    # 檢查表格是否存在
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 移除系統設定
    op.execute("DELETE FROM system_settings WHERE key = 'email_test_mode'")

    # 刪除索引和表格
    if "email_test_mode_audit" in existing_tables:
        op.drop_index("idx_email_test_audit_user", table_name="email_test_mode_audit")
        op.drop_index("idx_email_test_audit_session", table_name="email_test_mode_audit")
        op.drop_index("idx_email_test_audit_event", table_name="email_test_mode_audit")
        op.drop_index("idx_email_test_audit_timestamp", table_name="email_test_mode_audit")
        op.drop_table("email_test_mode_audit")
