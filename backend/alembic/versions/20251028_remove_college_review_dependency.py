"""remove college_review dependency from ranking items

Revision ID: 20251028_remove_dep
Revises: 20251028_status_cleanup
Create Date: 2025-10-28

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251028_remove_dep"
down_revision: Union[str, None] = "20251028_status_cleanup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # 1. 備份資料（安全起見）
    connection.execute(
        sa.text(
            """
        CREATE TABLE college_ranking_items_backup AS
        SELECT * FROM college_ranking_items
    """
        )
    )

    # 2. 將 college_review.final_rank 同步到 application.final_ranking_position（如果有遺漏）
    connection.execute(
        sa.text(
            """
        UPDATE applications a
        SET final_ranking_position = cr.final_rank
        FROM college_reviews cr
        WHERE cr.application_id = a.id
          AND cr.final_rank IS NOT NULL
          AND (a.final_ranking_position IS NULL OR a.final_ranking_position != cr.final_rank)
    """
        )
    )

    # 3. 刪除 foreign key constraint
    op.drop_constraint("college_ranking_items_college_review_id_fkey", "college_ranking_items", type_="foreignkey")

    # 4. 刪除 college_review_id 欄位
    op.drop_column("college_ranking_items", "college_review_id")


def downgrade() -> None:
    # 回滾不支援（需要手動恢復）
    raise NotImplementedError("Manual restoration required from backup table")
