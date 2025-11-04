"""add review_stage to applications

Revision ID: 20251028_review_stage
Revises: 5616016f542a
Create Date: 2025-10-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251028_review_stage"
down_revision: Union[str, None] = "5616016f542a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if review_stage column already exists
    existing_columns = [col["name"] for col in inspector.get_columns("applications")]

    # 1. 創建 PostgreSQL enum for ReviewStage
    review_stage_enum = postgresql.ENUM(
        "student_draft",
        "student_submitted",
        "professor_review",
        "professor_reviewed",
        "college_review",
        "college_reviewed",
        "college_ranking",
        "college_ranked",
        "admin_review",
        "admin_reviewed",
        "quota_distribution",
        "quota_distributed",
        "roster_preparation",
        "roster_prepared",
        "roster_submitted",
        "completed",
        "archived",
        name="reviewstage",
        create_type=False,
    )

    # Explicitly create the enum type
    review_stage_enum.create(op.get_bind(), checkfirst=True)

    # 2. 新增 review_stage 欄位 (先檢查是否存在)
    if "review_stage" in existing_columns:
        print("⊘ Skipping: review_stage column already exists")
        return

    op.add_column("applications", sa.Column("review_stage", review_stage_enum, nullable=True))

    # 3. 資料遷移：根據現有 status 設定初始 review_stage
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
        UPDATE applications
        SET review_stage = (CASE
            WHEN status = 'draft' THEN 'student_draft'
            WHEN status = 'submitted' THEN 'student_submitted'
            WHEN status = 'under_review' THEN 'college_review'
            WHEN status IN ('approved', 'rejected', 'partial_approve', 'partial_approved') THEN 'completed'
            WHEN status = 'professor_review' THEN 'professor_review'
            WHEN status = 'recommended' THEN 'professor_reviewed'
            WHEN status = 'college_reviewed' THEN 'college_reviewed'
            WHEN status = 'returned' THEN 'student_draft'
            WHEN status = 'withdrawn' THEN 'archived'
            WHEN status = 'cancelled' THEN 'archived'
            WHEN status = 'deleted' THEN 'archived'
            ELSE 'student_submitted'
        END)::reviewstage
        WHERE review_stage IS NULL
    """
        )
    )

    # 4. 設為 NOT NULL
    op.alter_column("applications", "review_stage", nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if review_stage column exists before dropping
    existing_columns = [col["name"] for col in inspector.get_columns("applications")]

    if "review_stage" in existing_columns:
        op.drop_column("applications", "review_stage")
    else:
        print("⊘ Skipping: review_stage column does not exist")

    # 刪除 enum type (safely, may be in use)
    review_stage_enum = postgresql.ENUM(name="reviewstage", create_type=False)
    try:
        review_stage_enum.drop(op.get_bind(), checkfirst=True)
    except Exception as e:
        print(f"⊘ Could not drop reviewstage enum: {e}")
