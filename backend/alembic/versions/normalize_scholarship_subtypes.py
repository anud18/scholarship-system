"""normalize scholarship subtypes to lowercase

統一獎學金子類型為小寫格式：
- 將所有 sub_scholarship_type 和 main_scholarship_type 統一為小寫
- 符合 CLAUDE.md Enum Consistency Guidelines

Revision ID: normalize_scholarship_subtypes
Revises: 9dca472f0b61
Create Date: 2025-10-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "normalize_scholarship_subtypes"
down_revision: Union[str, None] = "9dca472f0b61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    統一獎學金類型為小寫格式
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if applications table exists
    existing_tables = inspector.get_table_names()
    if "applications" not in existing_tables:
        print("Applications table does not exist, skipping migration")
        return

    # Check if columns exist
    columns = [col["name"] for col in inspector.get_columns("applications")]

    # Normalize sub_scholarship_type values
    if "sub_scholarship_type" in columns:
        # Update known uppercase values to lowercase
        conn = bind

        # Map of uppercase to lowercase values
        mappings = {
            "GENERAL": "general",
            "NSTC": "nstc",
            "MOE_1W": "moe_1w",
            "MOE_2W": "moe_2w",
            "MOE": "moe",  # Legacy value if exists
        }

        for upper_val, lower_val in mappings.items():
            conn.execute(
                sa.text(
                    "UPDATE applications SET sub_scholarship_type = :lower_val "
                    "WHERE UPPER(sub_scholarship_type) = :upper_val"
                ),
                {"lower_val": lower_val, "upper_val": upper_val},
            )
            print(f"Normalized {upper_val} -> {lower_val}")

    # Normalize main_scholarship_type values
    if "main_scholarship_type" in columns:
        conn = bind

        # Map of uppercase to lowercase values
        main_type_mappings = {
            "UNDERGRADUATE_FRESHMAN": "undergraduate_freshman",
            "PHD": "phd",
            "DIRECT_PHD": "direct_phd",
        }

        for upper_val, lower_val in main_type_mappings.items():
            conn.execute(
                sa.text(
                    "UPDATE applications SET main_scholarship_type = :lower_val "
                    "WHERE UPPER(main_scholarship_type) = :upper_val"
                ),
                {"lower_val": lower_val, "upper_val": upper_val},
            )
            print(f"Normalized {upper_val} -> {lower_val}")

    print("Migration completed: All scholarship types normalized to lowercase")


def downgrade() -> None:
    """
    No downgrade - lowercase values are canonical format
    """
    pass
