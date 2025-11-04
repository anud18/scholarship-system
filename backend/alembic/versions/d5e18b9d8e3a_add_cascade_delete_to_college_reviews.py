"""add cascade delete to college reviews

Revision ID: d5e18b9d8e3a
Revises: 7f6f0f8fef12
Create Date: 2025-10-15 01:36:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e18b9d8e3a"
down_revision: Union[str, None] = "7f6f0f8fef12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fk_if_exists(table_name: str, constraint_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    fk_constraints = inspector.get_foreign_keys(table_name)

    for constraint in fk_constraints:
        if constraint.get("name") == constraint_name:
            op.drop_constraint(constraint_name, table_name, type_="foreignkey")
            break


def upgrade() -> None:
    # Check if tables exist before attempting to modify them
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # Skip if college_reviews table doesn't exist
    # (may have been removed in earlier migrations or never created)
    if "college_reviews" not in tables:
        print("⊘ Skipping: college_reviews table does not exist")
        return

    # Skip if college_ranking_items table doesn't exist
    if "college_ranking_items" not in tables:
        print("⊘ Skipping: college_ranking_items table does not exist")
        return

    _drop_fk_if_exists("college_reviews", "college_reviews_application_id_fkey")
    op.create_foreign_key(
        "college_reviews_application_id_fkey",
        "college_reviews",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="CASCADE",
    )

    _drop_fk_if_exists("college_ranking_items", "college_ranking_items_college_review_id_fkey")
    op.create_foreign_key(
        "college_ranking_items_college_review_id_fkey",
        "college_ranking_items",
        "college_reviews",
        ["college_review_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Check if tables exist before attempting to modify them
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # Skip if college_reviews table doesn't exist
    if "college_reviews" not in tables:
        print("⊘ Skipping downgrade: college_reviews table does not exist")
        return

    # Skip if college_ranking_items table doesn't exist
    if "college_ranking_items" not in tables:
        print("⊘ Skipping downgrade: college_ranking_items table does not exist")
        return

    _drop_fk_if_exists("college_reviews", "college_reviews_application_id_fkey")
    op.create_foreign_key(
        "college_reviews_application_id_fkey",
        "college_reviews",
        "applications",
        ["application_id"],
        ["id"],
    )

    _drop_fk_if_exists("college_ranking_items", "college_ranking_items_college_review_id_fkey")
    op.create_foreign_key(
        "college_ranking_items_college_review_id_fkey",
        "college_ranking_items",
        "college_reviews",
        ["college_review_id"],
        ["id"],
    )
