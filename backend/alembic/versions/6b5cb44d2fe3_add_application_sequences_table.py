"""add_application_sequences_table

Revision ID: 6b5cb44d2fe3
Revises: 8d7aa61ad1f9
Create Date: 2025-10-13 19:01:22.584074

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6b5cb44d2fe3"
down_revision: Union[str, None] = "8d7aa61ad1f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create application_sequences table with existence check"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Create application_sequences table if not exists
    if "application_sequences" not in existing_tables:
        op.create_table(
            "application_sequences",
            sa.Column("academic_year", sa.Integer(), nullable=False, comment="民國年，例如 113"),
            sa.Column("semester", sa.String(length=20), nullable=False, comment="學期：first, second, annual"),
            sa.Column("last_sequence", sa.Integer(), nullable=False, server_default="0", comment="最後使用的序號"),
            sa.PrimaryKeyConstraint("academic_year", "semester", name="pk_application_sequences"),
        )

        # Create index for faster lookups
        op.create_index(
            "ix_application_sequences_lookup",
            "application_sequences",
            ["academic_year", "semester"],
            unique=False,
        )

        print("✓ Created application_sequences table")

        # Initialize sequences from existing applications
        # Group by academic_year and semester, count applications for each combination
        connection = op.get_bind()
        result = connection.execute(
            sa.text(
                """
                SELECT academic_year, semester, COUNT(*) as count
                FROM applications
                WHERE academic_year IS NOT NULL
                GROUP BY academic_year, semester
                ORDER BY academic_year, semester
                """
            )
        )

        sequences_to_insert = []
        for row in result:
            academic_year, semester, count = row
            if semester:  # Only process if semester is not NULL
                sequences_to_insert.append(
                    {"academic_year": academic_year, "semester": semester, "last_sequence": count}
                )

        # Insert initial sequences if any exist
        if sequences_to_insert:
            op.bulk_insert(
                sa.table(
                    "application_sequences",
                    sa.column("academic_year", sa.Integer),
                    sa.column("semester", sa.String),
                    sa.column("last_sequence", sa.Integer),
                ),
                sequences_to_insert,
            )
            print(f"✓ Initialized {len(sequences_to_insert)} sequence records from existing applications")
        else:
            print("ℹ No existing applications found, starting with empty sequences")
    else:
        print("⊘ Table application_sequences already exists, skipping creation")


def downgrade() -> None:
    """Drop application_sequences table with existence check"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "application_sequences" in existing_tables:
        # Drop index first
        try:
            op.drop_index("ix_application_sequences_lookup", table_name="application_sequences")
        except Exception:
            pass  # Index might not exist

        # Drop table
        op.drop_table("application_sequences")
        print("✓ Dropped application_sequences table")
    else:
        print("⊘ Table application_sequences does not exist, skipping drop")
