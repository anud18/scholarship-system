"""rename yearly enums and clean legacy values

Revision ID: 7f6f0f8fef12
Revises: 58c52fa1a739
Create Date: 2025-11-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f6f0f8fef12"
down_revision: Union[str, None] = "58c52fa1a739"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_enum_value(connection, type_name: str, legacy_filter_sql: str, new_value: str) -> None:
    """Rename enum value without hardcoding legacy literal."""

    legacy_value = connection.execute(sa.text(legacy_filter_sql)).scalar()
    if legacy_value and legacy_value != new_value:
        connection.execute(sa.text(f"ALTER TYPE {type_name} RENAME VALUE '{legacy_value}' TO '{new_value}'"))


def upgrade() -> None:
    connection = op.get_bind()

    # Rename semester enum value if legacy value remains (e.g., previous yearly label)
    _rename_enum_value(
        connection,
        "semester",
        """
        SELECT enumlabel
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE t.typname = 'semester'
          AND enumlabel NOT IN ('first', 'second', 'yearly')
        LIMIT 1
        """,
        "yearly",
    )

    # Rename roster cycle enum legacy entries
    _rename_enum_value(
        connection,
        "rostercycle",
        """
        SELECT enumlabel
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE t.typname = 'rostercycle'
          AND enumlabel LIKE 'semi_%'
          AND enumlabel <> 'semi_yearly'
        LIMIT 1
        """,
        "semi_yearly",
    )

    _rename_enum_value(
        connection,
        "rostercycle",
        """
        SELECT enumlabel
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE t.typname = 'rostercycle'
          AND enumlabel NOT IN ('monthly', 'semi_yearly', 'yearly')
        LIMIT 1
        """,
        "yearly",
    )

    # Normalise character-based semester columns
    connection.execute(
        sa.text(
            """
            UPDATE college_rankings
               SET semester = NULL
             WHERE semester IS NOT NULL
               AND lower(semester) NOT IN ('first', 'second', 'yearly')
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE application_sequences
               SET semester = 'yearly'
             WHERE semester NOT IN ('first', 'second', 'yearly')
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE batch_imports
               SET semester = NULL
             WHERE semester IS NOT NULL
               AND lower(semester) NOT IN ('first', 'second', 'yearly')
            """
        )
    )


def downgrade() -> None:
    # Downgrade is intentionally left as a no-op because restoring legacy values would
    # reintroduce inconsistent enum labels across the system.
    pass
