"""Add display_in_list / requires_upload flags to application_documents

Revision ID: add_doc_display_upload_flags_001
Revises: update_moe_1w_label_001
"""

import sqlalchemy as sa

from alembic import op

revision = "add_doc_display_upload_flags_001"
down_revision = "update_moe_1w_label_001"
branch_labels = None
depends_on = None

TABLE = "application_documents"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}

    if "display_in_list" not in existing_columns:
        op.add_column(TABLE, sa.Column("display_in_list", sa.Boolean(), nullable=False, server_default="true"))
    if "requires_upload" not in existing_columns:
        op.add_column(TABLE, sa.Column("requires_upload", sa.Boolean(), nullable=False, server_default="true"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}

    if "requires_upload" in existing_columns:
        op.drop_column(TABLE, "requires_upload")
    if "display_in_list" in existing_columns:
        op.drop_column(TABLE, "display_in_list")
