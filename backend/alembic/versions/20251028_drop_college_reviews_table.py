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

    # 1. 最後備份
    connection.execute(
        sa.text(
            """
        CREATE TABLE college_reviews_archive AS
        SELECT * FROM college_reviews
    """
        )
    )

    # 2. 刪除索引
    op.drop_index("ix_college_reviews_application_reviewer", table_name="college_reviews")
    op.drop_index("ix_college_reviews_recommendation_status", table_name="college_reviews")
    op.drop_index("ix_college_reviews_priority_attention", table_name="college_reviews")

    # 3. 刪除表
    op.drop_table("college_reviews")


def downgrade() -> None:
    raise NotImplementedError("Cannot restore dropped table - use archive")
