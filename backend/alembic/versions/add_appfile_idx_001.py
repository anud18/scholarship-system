"""Index application_files(application_id, file_type).

Every document upload now runs a stale-duplicate SELECT keyed on these two
columns, and selectinload(Application.files) filters on application_id —
PostgreSQL does not auto-index FK columns, so both were full-table scans.

Revision ID: add_appfile_idx_001
Revises: dedupe_application_files_001
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "add_appfile_idx_001"
down_revision = "dedupe_application_files_001"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_application_files_app_type"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "application_files" not in inspector.get_table_names():
        return
    existing = {idx["name"] for idx in inspector.get_indexes("application_files")}
    if INDEX_NAME not in existing:
        op.create_index(INDEX_NAME, "application_files", ["application_id", "file_type"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "application_files" not in inspector.get_table_names():
        return
    existing = {idx["name"] for idx in inspector.get_indexes("application_files")}
    if INDEX_NAME in existing:
        op.drop_index(INDEX_NAME, table_name="application_files")
