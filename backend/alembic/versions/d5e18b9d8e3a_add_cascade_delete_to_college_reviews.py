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


def _drop_existing_constraint(constraints, constraint_name: str) -> None:
    for constraint in constraints:
        if constraint.get("name") == constraint_name:
            op.drop_constraint(constraint_name, "college_reviews", type_="foreignkey")
            break


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    fk_constraints = inspector.get_foreign_keys("college_reviews")

    constraint_name = "college_reviews_application_id_fkey"
    _drop_existing_constraint(fk_constraints, constraint_name)

    op.create_foreign_key(
        constraint_name,
        "college_reviews",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    fk_constraints = inspector.get_foreign_keys("college_reviews")

    constraint_name = "college_reviews_application_id_fkey"
    _drop_existing_constraint(fk_constraints, constraint_name)

    op.create_foreign_key(
        constraint_name,
        "college_reviews",
        "applications",
        ["application_id"],
        ["id"],
    )
