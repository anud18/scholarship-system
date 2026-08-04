"""Add import_type discriminator to batch_imports

Revision ID: add_batch_import_type_001
Revises: add_app_doc_note_001
"""

import sqlalchemy as sa

from alembic import op

revision = "add_batch_import_type_001"
down_revision = "add_app_doc_note_001"
branch_labels = None
depends_on = None

TABLE = "batch_imports"
COLUMN = "import_type"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}
    if COLUMN not in existing_columns:
        op.add_column(
            TABLE,
            sa.Column(COLUMN, sa.String(length=20), nullable=False, server_default="application"),
        )
        op.create_index(f"ix_{TABLE}_{COLUMN}", TABLE, [COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}
    if COLUMN in existing_columns:
        op.drop_index(f"ix_{TABLE}_{COLUMN}", table_name=TABLE)
        op.drop_column(TABLE, COLUMN)
