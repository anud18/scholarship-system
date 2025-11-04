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
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if tables exist
    existing_tables = inspector.get_table_names()

    # 1. 備份資料（安全起見）- 只在表存在時
    if "college_ranking_items" in existing_tables:
        # Check if backup already exists
        if "college_ranking_items_backup" not in existing_tables:
            connection.execute(
                sa.text(
                    """
                CREATE TABLE college_ranking_items_backup AS
                SELECT * FROM college_ranking_items
            """
                )
            )
            print("✓ Backed up college_ranking_items table")
        else:
            print("⊘ Backup table already exists, skipping backup")
    else:
        print("⊘ college_ranking_items table does not exist, skipping backup")

    # 2. 將 college_review.final_rank 同步到 application.final_ranking_position（如果有遺漏）
    # 只在 college_reviews 表存在時執行
    if "college_reviews" in existing_tables:
        result = connection.execute(
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
        print(f"✓ Synced {result.rowcount} final_rank values to applications")
    else:
        print("⊘ college_reviews table does not exist, skipping data sync")

    # 3. 刪除 foreign key constraint - 先檢查是否存在
    if "college_ranking_items" in existing_tables:
        existing_columns = {col["name"] for col in inspector.get_columns("college_ranking_items")}

        if "college_review_id" in existing_columns:
            # Check if foreign key constraint exists
            fk_constraints = inspector.get_foreign_keys("college_ranking_items")
            fk_exists = any(fk["name"] == "college_ranking_items_college_review_id_fkey" for fk in fk_constraints)

            if fk_exists:
                op.drop_constraint(
                    "college_ranking_items_college_review_id_fkey",
                    "college_ranking_items",
                    type_="foreignkey",
                )
                print("✓ Dropped foreign key constraint")
            else:
                print("⊘ Foreign key constraint does not exist, skipping")

            # 4. 刪除 college_review_id 欄位
            op.drop_column("college_ranking_items", "college_review_id")
            print("✓ Dropped college_review_id column")
        else:
            print("⊘ college_review_id column does not exist, skipping")
    else:
        print("⊘ college_ranking_items table does not exist, skipping constraint removal")


def downgrade() -> None:
    # 回滾不支援（需要手動恢復）
    raise NotImplementedError("Manual restoration required from backup table")
