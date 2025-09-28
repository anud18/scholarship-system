"""remove summer from semester enum

Revision ID: 96c65aa1feb9
Revises: a7c76a19a59e
Create Date: 2025-09-28 12:08:20.399582

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "96c65aa1feb9"
down_revision: Union[str, None] = "a7c76a19a59e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update the enum by creating new enum and replacing it
    op.execute("CREATE TYPE semester_new AS ENUM ('first', 'second', 'annual')")

    # Convert existing semester columns to new enum (no data exists to convert)
    op.execute("ALTER TABLE applications ALTER COLUMN semester TYPE semester_new USING semester::text::semester_new")
    op.execute(
        "ALTER TABLE scholarship_configurations ALTER COLUMN semester TYPE semester_new USING semester::text::semester_new"
    )
    op.execute(
        "ALTER TABLE scholarship_rules ALTER COLUMN semester TYPE semester_new USING semester::text::semester_new"
    )

    # Drop old enum and rename new one
    op.execute("DROP TYPE semester")
    op.execute("ALTER TYPE semester_new RENAME TO semester")


def downgrade() -> None:
    # Recreate the original enum with summer
    op.execute("CREATE TYPE semester_new AS ENUM ('first', 'second', 'summer', 'annual')")

    # Convert columns back
    op.execute("ALTER TABLE applications ALTER COLUMN semester TYPE semester_new USING semester::text::semester_new")
    op.execute(
        "ALTER TABLE scholarship_configurations ALTER COLUMN semester TYPE semester_new USING semester::text::semester_new"
    )
    op.execute(
        "ALTER TABLE scholarship_rules ALTER COLUMN semester TYPE semester_new USING semester::text::semester_new"
    )

    # Drop old enum and rename new one
    op.execute("DROP TYPE semester")
    op.execute("ALTER TYPE semester_new RENAME TO semester")
