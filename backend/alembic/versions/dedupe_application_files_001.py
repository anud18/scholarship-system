"""Remove duplicate application_files rows left by repeated draft saves.

The student wizard used to re-upload every document once per 儲存草稿/提交
click, so one document slot accumulated N identical rows (same application,
file type, original filename and size) — the college export then listed
「成績 1..6」copies of a single PDF. Keep only the newest row (max id) of
each identical group; MinIO objects of the removed rows are left in place
(they are orphans, harmless, and object storage is not reachable from a
migration).

Revision ID: dedupe_application_files_001
Revises: align_academy_names_002
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "dedupe_application_files_001"
down_revision = "align_academy_names_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "application_files" not in inspector.get_table_names():
        return

    # Identical group = same application + type + original filename + size.
    # Differing content under the same name yields a different file_size and
    # is therefore preserved; only true re-uploads collapse to one row.
    bind.execute(sa.text("""
            DELETE FROM application_files stale
            USING application_files newer
            WHERE newer.application_id = stale.application_id
              AND COALESCE(newer.file_type, '') = COALESCE(stale.file_type, '')
              AND COALESCE(newer.original_filename, '') = COALESCE(stale.original_filename, '')
              AND COALESCE(newer.file_size, -1) = COALESCE(stale.file_size, -1)
              AND newer.id > stale.id
            """))


def downgrade() -> None:
    # Data cleanup is not reversible — the duplicate rows are gone by design.
    pass
