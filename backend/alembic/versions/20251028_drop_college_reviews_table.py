"""drop college_reviews table (replaced by unified review system)

Revision ID: 20251028_drop_college
Revises: 20251028_remove_dep
Create Date: 2025-10-28

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251028_drop_college"
down_revision: Union[str, None] = "20251028_remove_dep"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if college_reviews table exists
    existing_tables = inspector.get_table_names()

    if "college_reviews" not in existing_tables:
        print("⊘ college_reviews table does not exist, skipping drop")
        return

    # 1. 最後備份
    if "college_reviews_archive" not in existing_tables:
        connection.execute(
            sa.text(
                """
            CREATE TABLE college_reviews_archive AS
            SELECT * FROM college_reviews
        """
            )
        )
        print("✓ Archived college_reviews table")
    else:
        print("⊘ Archive table already exists, skipping backup")

    # 2. 刪除索引 - 檢查是否存在
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("college_reviews")}

    indexes_to_drop = [
        "ix_college_reviews_application_reviewer",
        "ix_college_reviews_recommendation_status",
        "ix_college_reviews_priority_attention",
    ]

    for index_name in indexes_to_drop:
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="college_reviews")
            print(f"✓ Dropped index {index_name}")
        else:
            print(f"⊘ Index {index_name} does not exist, skipping")

    # 3. 刪除表
    op.drop_table("college_reviews")
    print("✓ Dropped college_reviews table")


def downgrade() -> None:
    raise NotImplementedError("Cannot restore dropped table - use archive")
