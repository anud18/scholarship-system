"""add supplementary_docs table

Revision ID: add_supp_docs_001
Revises: merge_renewal_main_001
Create Date: 2026-05-27

"""
from alembic import op
import sqlalchemy as sa


revision = "add_supp_docs_001"
down_revision = "merge_renewal_main_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "supplementary_docs" not in inspector.get_table_names():
        op.create_table(
            "supplementary_docs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("object_name", sa.String(length=500), nullable=False),
            sa.Column("original_filename", sa.String(length=500), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column(
                "sort_order",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "created_by",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "idx_supp_docs_sort",
            "supplementary_docs",
            ["sort_order"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "supplementary_docs" in inspector.get_table_names():
        op.drop_index(
            "idx_supp_docs_sort",
            table_name="supplementary_docs",
            if_exists=True,
        )
        op.drop_table("supplementary_docs")
