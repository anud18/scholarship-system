"""add_unique_constraint_application_reviewer

Revision ID: 5616016f542a
Revises: d241e807237f
Create Date: 2025-10-27 21:42:28.818659

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5616016f542a"
down_revision: Union[str, None] = "d241e807237f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if constraint already exists before creating
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Get existing constraints
    constraints = inspector.get_unique_constraints("application_reviews")
    constraint_names = [c["name"] for c in constraints]

    if "uq_application_reviewer" not in constraint_names:
        op.create_unique_constraint("uq_application_reviewer", "application_reviews", ["application_id", "reviewer_id"])
        print("  ✓ Created unique constraint uq_application_reviewer on application_reviews")
    else:
        print("  ⏭️  Constraint uq_application_reviewer already exists, skipping")


def downgrade() -> None:
    # Remove unique constraint from application_reviews table
    op.drop_constraint("uq_application_reviewer", "application_reviews", type_="unique")
