"""add_ranking_id_to_payment_rosters

Revision ID: 0a35efe15189
Revises: 94e544932d78
Create Date: 2025-10-27 01:42:47.520698

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a35efe15189"
down_revision: Union[str, None] = "94e544932d78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add ranking_id foreign key to payment_rosters table.
    This allows rosters to be linked to specific college rankings.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Get existing columns
    existing_columns = [col["name"] for col in inspector.get_columns("payment_rosters")]

    # Add ranking_id column if it doesn't exist
    if "ranking_id" not in existing_columns:
        op.add_column("payment_rosters", sa.Column("ranking_id", sa.Integer(), nullable=True))

    # Get existing foreign keys
    existing_fks = [fk["name"] for fk in inspector.get_foreign_keys("payment_rosters")]

    # Create foreign key constraint if it doesn't exist
    if "fk_payment_rosters_ranking_id" not in existing_fks:
        op.create_foreign_key(
            "fk_payment_rosters_ranking_id",
            "payment_rosters",
            "college_rankings",
            ["ranking_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Get existing indexes
    existing_indexes = [idx["name"] for idx in inspector.get_indexes("payment_rosters")]

    # Create index if it doesn't exist
    if "ix_payment_rosters_ranking_id" not in existing_indexes:
        op.create_index("ix_payment_rosters_ranking_id", "payment_rosters", ["ranking_id"])


def downgrade() -> None:
    """
    Remove ranking_id foreign key from payment_rosters table.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Drop index if exists
    existing_indexes = [idx["name"] for idx in inspector.get_indexes("payment_rosters")]
    if "ix_payment_rosters_ranking_id" in existing_indexes:
        op.drop_index("ix_payment_rosters_ranking_id", table_name="payment_rosters")

    # Drop foreign key if exists
    existing_fks = [fk["name"] for fk in inspector.get_foreign_keys("payment_rosters")]
    if "fk_payment_rosters_ranking_id" in existing_fks:
        op.drop_constraint("fk_payment_rosters_ranking_id", "payment_rosters", type_="foreignkey")

    # Drop column if exists
    existing_columns = [col["name"] for col in inspector.get_columns("payment_rosters")]
    if "ranking_id" in existing_columns:
        op.drop_column("payment_rosters", "ranking_id")
