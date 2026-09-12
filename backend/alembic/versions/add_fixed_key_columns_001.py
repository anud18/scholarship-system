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

The backfill is not optional. 儲存所有設定 posts the injected copies back
through `bulk_update_fields`, so any database where that button was ever
pressed already holds a built-in item as a real row with no key. Without the
backfill the merge would not recognise it, the built-in would be injected
beside it, and the admin's next edit would collide with
`uq_application_field_type_name` — a 500 in place of the 404 this migration
exists to remove.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "add_fixed_key_columns_001"
down_revision: Union[str, None] = "drop_nstc_subtype_desc_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TARGETS = (
    ("application_fields", "ix_application_fields_fixed_key", "uq_application_fields_fixed_key"),
    ("application_documents", "ix_application_documents_fixed_key", "uq_application_documents_fixed_key"),
)

# The built-in fields are identified by `field_name`, which is also the form
# data key, so it is the same string as the fixed key.
FIELD_KEYS = ("postal_account", "advisor_name", "advisor_email", "advisor_nycu_id")

# The one built-in document has no such key, so the legacy rows are matched on
# the name the code shipped with. Only the oldest row per scholarship type is
# adopted: a name is not unique, and the partial unique index below would
# reject a second claimant.
BACKFILL_DOCUMENTS = sa.text("""
    UPDATE application_documents SET fixed_key = 'bank_statement'
    WHERE id IN (
        SELECT MIN(id) FROM application_documents
        WHERE fixed_key IS NULL AND document_name = '存摺封面'
        GROUP BY scholarship_type
    )
    """)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table, index_name, unique_name in TARGETS:
        if table not in table_names:
            continue

        columns = {col["name"] for col in inspector.get_columns(table)}
        if "fixed_key" not in columns:
            op.add_column(table, sa.Column("fixed_key", sa.String(length=50), nullable=True))

        indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        if index_name not in indexes:
            op.create_index(index_name, table, ["fixed_key"])

    if "application_fields" in table_names:
        bind.execute(
            sa.text(
                "UPDATE application_fields SET fixed_key = field_name "
                "WHERE fixed_key IS NULL AND field_name = ANY(:keys)"
            ),
            {"keys": list(FIELD_KEYS)},
        )

    if "application_documents" in table_names:
        bind.execute(BACKFILL_DOCUMENTS)

    # One row per built-in item per scholarship type. This is what makes the
    # `fixed_key` upsert in create_field/create_document safe against two
    # admins (or a double-click) racing the first save.
    for table, _index_name, unique_name in TARGETS:
        if table not in table_names:
            continue

        indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        if unique_name not in indexes:
            op.create_index(
                unique_name,
                table,
                ["scholarship_type", "fixed_key"],
                unique=True,
                postgresql_where=sa.text("fixed_key IS NOT NULL"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table, index_name, unique_name in TARGETS:
        if table not in table_names:
            continue

        indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        for name in (unique_name, index_name):
            if name in indexes:
                op.drop_index(name, table_name=table)

        columns = {col["name"] for col in inspector.get_columns(table)}
        if "fixed_key" in columns:
            op.drop_column(table, "fixed_key")
