"""Give the built-in ("fixed") form fields and documents a persistable identity

Revision ID: add_fixed_key_columns_001
Revises: drop_nstc_subtype_desc_001
Create Date: 2026-09-13 00:00:00.000000

固定欄位 / 固定文件（系統預設）are built in code and injected into the form
config at request time with `id = 0`, so 審核管理 could render an edit button
for them but the save always hit `PUT /application-fields/documents/0` and
came back 404 ("更新文件要求失敗").

`fixed_key` is the stable identity that lets an edited copy live in the table:
once a row carries it, `inject_fixed_fields` uses that row instead of the
code default, and the admin may rename the item freely without the match
breaking. NULL means an ordinary admin-created field/document.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "add_fixed_key_columns_001"
down_revision: Union[str, None] = "drop_nstc_subtype_desc_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TARGETS = (
    ("application_fields", "ix_application_fields_fixed_key"),
    ("application_documents", "ix_application_documents_fixed_key"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table, index_name in TARGETS:
        if table not in table_names:
            continue

        columns = {col["name"] for col in inspector.get_columns(table)}
        if "fixed_key" not in columns:
            op.add_column(table, sa.Column("fixed_key", sa.String(length=50), nullable=True))

        indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        if index_name not in indexes:
            op.create_index(index_name, table, ["fixed_key"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table, index_name in TARGETS:
        if table not in table_names:
            continue

        indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        if index_name in indexes:
            op.drop_index(index_name, table_name=table)

        columns = {col["name"] for col in inspector.get_columns(table)}
        if "fixed_key" in columns:
            op.drop_column(table, "fixed_key")
