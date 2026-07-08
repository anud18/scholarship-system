"""Add application_document_note columns to scholarship_types

Revision ID: add_app_doc_note_001
Revises: add_doc_display_upload_flags_001
"""

import sqlalchemy as sa

from alembic import op

revision = "add_app_doc_note_001"
down_revision = "add_doc_display_upload_flags_001"
branch_labels = None
depends_on = None

TABLE = "scholarship_types"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}

    if "application_document_note" not in existing_columns:
        op.add_column(TABLE, sa.Column("application_document_note", sa.Text(), nullable=True))
    if "application_document_note_en" not in existing_columns:
        op.add_column(TABLE, sa.Column("application_document_note_en", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}

    if "application_document_note_en" in existing_columns:
        op.drop_column(TABLE, "application_document_note_en")
    if "application_document_note" in existing_columns:
        op.drop_column(TABLE, "application_document_note")
