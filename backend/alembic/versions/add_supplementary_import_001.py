"""Add supplementary import columns to scholarship_configurations and college_ranking_items

Revision ID: add_supplementary_import_001
Revises: email_tpl_scholar_type_001
Create Date: 2026-05-14

Schema:
  - scholarship_configurations.allow_supplementary_import (Boolean) — admin toggle,
    one flag per (scholarship_type, academic_year, semester) configuration, applies
    to all colleges' rankings under that config.
  - college_ranking_items.is_supplementary (Boolean) — per-item flag set on rows
    appended via the post-distribution supplementary import flow.
"""

import sqlalchemy as sa
from alembic import op

revision = "add_supplementary_import_001"
down_revision = "email_tpl_scholar_type_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    config_cols = {col["name"] for col in inspector.get_columns("scholarship_configurations")}
    if "allow_supplementary_import" not in config_cols:
        op.add_column(
            "scholarship_configurations",
            sa.Column(
                "allow_supplementary_import",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    item_cols = {col["name"] for col in inspector.get_columns("college_ranking_items")}
    if "is_supplementary" not in item_cols:
        op.add_column(
            "college_ranking_items",
            sa.Column(
                "is_supplementary",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    # Clean up old column on college_rankings if a prior version of this migration
    # added it there (PR #745 early state). Safe no-op on fresh databases.
    ranking_cols = {col["name"] for col in inspector.get_columns("college_rankings")}
    if "allow_supplementary_import" in ranking_cols:
        op.drop_column("college_rankings", "allow_supplementary_import")


def downgrade() -> None:
    op.drop_column("college_ranking_items", "is_supplementary")
    op.drop_column("scholarship_configurations", "allow_supplementary_import")
