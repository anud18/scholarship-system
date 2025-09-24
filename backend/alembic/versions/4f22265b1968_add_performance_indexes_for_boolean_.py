"""add_performance_indexes_for_boolean_columns

Revision ID: 4f22265b1968
Revises: add_rule_enable_fields
Create Date: 2025-08-06 11:54:24.636740

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f22265b1968"
down_revision: Union[str, None] = "add_rule_enable_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add indexes for new boolean columns to improve query performance
    # These indexes will be especially useful for filtering rules by enabled/disabled status

    # Index for is_initial_enabled column
    op.create_index(
        "idx_scholarship_rules_is_initial_enabled",
        "scholarship_rules",
        ["is_initial_enabled"],
        postgresql_where=sa.text(
            "is_initial_enabled = true"
        ),  # Partial index for true values only
    )

    # Index for is_renewal_enabled column
    op.create_index(
        "idx_scholarship_rules_is_renewal_enabled",
        "scholarship_rules",
        ["is_renewal_enabled"],
        postgresql_where=sa.text(
            "is_renewal_enabled = true"
        ),  # Partial index for true values only
    )

    # Composite index for common query patterns (enabled rules with scholarship type)
    op.create_index(
        "idx_scholarship_rules_type_initial_enabled",
        "scholarship_rules",
        ["scholarship_type_id", "is_initial_enabled"],
        postgresql_where=sa.text("is_initial_enabled = true"),
    )

    op.create_index(
        "idx_scholarship_rules_type_renewal_enabled",
        "scholarship_rules",
        ["scholarship_type_id", "is_renewal_enabled"],
        postgresql_where=sa.text("is_renewal_enabled = true"),
    )

    # Index for academic period queries (common in rule copying)
    op.create_index(
        "idx_scholarship_rules_academic_period",
        "scholarship_rules",
        ["academic_year", "semester", "scholarship_type_id"],
    )


def downgrade() -> None:
    # Drop indexes in reverse order
    op.drop_index(
        "idx_scholarship_rules_academic_period", table_name="scholarship_rules"
    )
    op.drop_index(
        "idx_scholarship_rules_type_renewal_enabled", table_name="scholarship_rules"
    )
    op.drop_index(
        "idx_scholarship_rules_type_initial_enabled", table_name="scholarship_rules"
    )
    op.drop_index(
        "idx_scholarship_rules_is_renewal_enabled", table_name="scholarship_rules"
    )
    op.drop_index(
        "idx_scholarship_rules_is_initial_enabled", table_name="scholarship_rules"
    )
