"""update_emailcategory_enum_values

Revision ID: f333214c4735
Revises: 7465ccd0a0f4
Create Date: 2025-09-30 18:40:06.187074

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f333214c4735"
down_revision: Union[str, None] = "7465ccd0a0f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new EmailCategory enum values to match Python code
    # Note: PostgreSQL doesn't allow removing enum values, only adding them
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'application_whitelist'")
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'application_student'")
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'recommendation_professor'")
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'review_college'")
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'supplement_student'")
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'result_professor'")
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'result_college'")
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'result_student'")
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'roster_student'")
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'system'")
    op.execute("ALTER TYPE emailcategory ADD VALUE IF NOT EXISTS 'other'")


def downgrade() -> None:
    # Note: PostgreSQL does not support removing enum values directly
    # If you need to remove values, you must:
    # 1. Create a new enum type with desired values
    # 2. Alter columns to use the new type
    # 3. Drop the old enum type
    # This is complex and error-prone, so we leave it as a manual process
    pass
