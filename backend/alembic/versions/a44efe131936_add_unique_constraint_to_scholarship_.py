"""add_unique_constraint_to_scholarship_rules

Revision ID: a44efe131936
Revises: 50aa478354de
Create Date: 2025-10-09 15:46:36.518734

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a44efe131936"
down_revision: Union[str, None] = "50aa478354de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint to scholarship_rules table"""

    # Check if the constraint already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = inspector.get_unique_constraints("scholarship_rules")
    constraint_names = [c["name"] for c in constraints]

    if "uq_scholarship_rule_key_fields" not in constraint_names:
        op.create_unique_constraint(
            "uq_scholarship_rule_key_fields",
            "scholarship_rules",
            ["scholarship_type_id", "sub_type", "academic_year", "semester", "rule_name", "rule_type"],
        )
        print("✓ Added unique constraint to scholarship_rules")
    else:
        print("✓ Unique constraint already exists on scholarship_rules")


def downgrade() -> None:
    """Remove unique constraint from scholarship_rules table"""

    # Check if the constraint exists before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = inspector.get_unique_constraints("scholarship_rules")
    constraint_names = [c["name"] for c in constraints]

    if "uq_scholarship_rule_key_fields" in constraint_names:
        op.drop_constraint("uq_scholarship_rule_key_fields", "scholarship_rules", type_="unique")
        print("✓ Removed unique constraint from scholarship_rules")
    else:
        print("✓ Unique constraint does not exist on scholarship_rules")
