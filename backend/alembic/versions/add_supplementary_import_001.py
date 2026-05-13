"""Add supplementary import columns to college_rankings and college_ranking_items

Revision ID: add_supplementary_import_001
Revises: 20260513_doc_req_deadline
Create Date: 2026-05-14
"""

import sqlalchemy as sa
from alembic import op

revision = "add_supplementary_import_001"
down_revision = "20260513_doc_req_deadline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_cols = {
        col["name"]
        for col in inspector.get_columns("college_rankings")
    }
    if "allow_supplementary_import" not in existing_cols:
        op.add_column(
            "college_rankings",
            sa.Column(
                "allow_supplementary_import",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    existing_item_cols = {
        col["name"]
        for col in inspector.get_columns("college_ranking_items")
    }
    if "is_supplementary" not in existing_item_cols:
        op.add_column(
            "college_ranking_items",
            sa.Column(
                "is_supplementary",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    op.drop_column("college_ranking_items", "is_supplementary")
    op.drop_column("college_rankings", "allow_supplementary_import")
