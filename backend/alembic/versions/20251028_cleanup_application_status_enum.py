"""cleanup application_status enum values

Revision ID: 20251028_status_cleanup
Revises: 20251028_review_stage
Create Date: 2025-10-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251028_status_cleanup"
down_revision: Union[str, None] = "20251028_review_stage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # 1. 遷移舊值到新值
    connection.execute(
        sa.text(
            """
        UPDATE applications
        SET status = CASE
            WHEN status = 'professor_review' THEN 'under_review'
            WHEN status = 'recommended' THEN 'under_review'
            WHEN status = 'college_reviewed' THEN 'under_review'
            WHEN status = 'renewal_pending' THEN 'submitted'
            WHEN status = 'renewal_reviewed' THEN 'under_review'
            WHEN status = 'pending_recommendation' THEN 'under_review'
            WHEN status = 'partial_approve' THEN 'partial_approved'
            ELSE status
        END
    """
        )
    )

    # 2. 改變欄位類型為 String (暫時)
    op.alter_column("applications", "status", type_=sa.String(50))

    # 3. 刪除舊 enum (如果存在)
    # Note: 使用 checkfirst 來避免 enum 不存在時報錯
    try:
        old_enum = postgresql.ENUM(name="applicationstatus", create_type=False)
        old_enum.drop(op.get_bind(), checkfirst=True)
    except Exception:
        pass  # Enum 可能不存在，忽略錯誤

    # 4. 建立新的 application_status enum
    new_status_enum = postgresql.ENUM(
        "draft",
        "submitted",
        "under_review",
        "pending_documents",
        "approved",
        "partial_approved",
        "rejected",
        "returned",
        "withdrawn",
        "cancelled",
        "manual_excluded",
        "deleted",
        name="applicationstatus",
        create_type=False,
    )

    # Explicitly create the enum type
    new_status_enum.create(op.get_bind(), checkfirst=True)

    # 5. 改回使用 enum 類型
    op.alter_column(
        "applications",
        "status",
        type_=new_status_enum,
        postgresql_using="status::applicationstatus",
    )


def downgrade() -> None:
    # 回滾不支援（風險太高）
    raise NotImplementedError("Downgrade not supported for this migration")
