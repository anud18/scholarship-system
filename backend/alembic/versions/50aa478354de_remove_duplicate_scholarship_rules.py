"""remove_duplicate_scholarship_rules

Revision ID: 50aa478354de
Revises: c60361ed7978
Create Date: 2025-10-09 15:45:22.155778

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "50aa478354de"
down_revision: Union[str, None] = "c60361ed7978"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove duplicate scholarship rules, keeping only the first occurrence of each unique combination"""

    # Use CTE to identify and remove duplicates
    # Duplicates are identified by: scholarship_type_id, sub_type, academic_year, semester, rule_name, rule_type
    # We keep the row with the minimum ID for each unique combination
    op.execute(
        """
        WITH duplicates AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY
                           scholarship_type_id,
                           COALESCE(sub_type, ''),
                           COALESCE(academic_year, 0),
                           COALESCE(semester::text, ''),
                           rule_name,
                           rule_type
                       ORDER BY id
                   ) as rn
            FROM scholarship_rules
        )
        DELETE FROM scholarship_rules
        WHERE id IN (SELECT id FROM duplicates WHERE rn > 1)
    """
    )

    # Log the number of deleted duplicates
    print("✓ Removed duplicate scholarship rules")


def downgrade() -> None:
    """
    Downgrade is not possible for data cleanup migrations.
    Once duplicates are removed, we cannot restore them without backup data.
    """
    print("⚠️  Warning: Cannot restore deleted duplicate records without backup")
    pass
