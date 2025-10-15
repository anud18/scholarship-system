"""remove summer from semester enum

Revision ID: 96c65aa1feb9
Revises: a7c76a19a59e
Create Date: 2025-09-28 12:08:20.399582

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "96c65aa1feb9"
down_revision: Union[str, None] = "a7c76a19a59e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if semester_new type already exists
    bind = op.get_bind()
    result = bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'semester_new')"))
    semester_new_exists = result.scalar()

    # Check if semester type exists
    result = bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'semester')"))
    semester_exists = result.scalar()

    if not semester_new_exists and semester_exists:
        # Update the enum by creating new enum and replacing it
        op.execute("CREATE TYPE semester_new AS ENUM ('first', 'second', 'yearly')")

        # Check which tables exist before converting columns
        result = bind.execute(
            sa.text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'applications')")
        )
        if result.scalar():
            op.execute(
                "ALTER TABLE applications ALTER COLUMN semester TYPE semester_new USING semester::text::semester_new"
            )

        result = bind.execute(
            sa.text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'scholarship_configurations')"
            )
        )
        if result.scalar():
            op.execute(
                "ALTER TABLE scholarship_configurations ALTER COLUMN semester TYPE semester_new USING semester::text::semester_new"
            )

        result = bind.execute(
            sa.text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'scholarship_rules')")
        )
        if result.scalar():
            op.execute(
                "ALTER TABLE scholarship_rules ALTER COLUMN semester TYPE semester_new USING semester::text::semester_new"
            )

        # Drop old enum and rename new one
        op.execute("DROP TYPE semester")
        op.execute("ALTER TYPE semester_new RENAME TO semester")


def downgrade() -> None:
    # Recreate the original enum with summer
    op.execute("CREATE TYPE semester_new AS ENUM ('first', 'second', 'summer', 'yearly')")

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
