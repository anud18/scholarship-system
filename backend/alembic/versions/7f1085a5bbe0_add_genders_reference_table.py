"""add_genders_reference_table

Revision ID: 7f1085a5bbe0
Revises: adcbec818138
Create Date: 2025-10-23 08:02:55.322415

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f1085a5bbe0"
down_revision: Union[str, None] = "adcbec818138"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create genders reference table and seed initial data"""

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Create genders table if it doesn't exist
    if "genders" not in existing_tables:
        op.create_table(
            "genders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("id", name="genders_pkey"),
        )
        print("  ✓ Created genders table")

    # Seed gender data
    print("  👥 Seeding genders...")
    genders_data = [
        {"id": 1, "name": "男性"},
        {"id": 2, "name": "女性"},
    ]

    for gender in genders_data:
        conn.execute(
            sa.text(
                """
                INSERT INTO genders (id, name)
                VALUES (:id, :name)
                ON CONFLICT (id) DO NOTHING
            """
            ),
            gender,
        )

    print("  ✓ Genders seeded successfully!")


def downgrade() -> None:
    """Remove genders table and data"""

    conn = op.get_bind()

    print("  🗑️ Clearing genders data...")
    conn.execute(sa.text("DELETE FROM genders WHERE id IN (1, 2)"))

    # Drop table
    op.drop_table("genders")
    print("  ✓ Genders table dropped!")
