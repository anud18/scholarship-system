"""Seed the 學生領獎紀錄查詢 visibility switches

Revision ID: student_history_visibility_001
Revises: add_footer_links_001
Create Date: 2026-08-02 00:00:00.000000

Adds two `features` system settings so an admin can open/close 領獎紀錄查詢 for
students and for colleges independently:

- student_history_visible_to_student
- student_history_visible_to_college

Both are seeded to 'true', which is the behaviour the feature shipped with.
The application also treats a MISSING row as open, so this migration only
makes the setting visible/editable in 系統設定 on databases that predate it.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "student_history_visibility_001"
down_revision: Union[str, None] = "add_footer_links_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SETTINGS = (
    (
        "student_history_visible_to_student",
        "開放學生查詢自己的獎學金領獎紀錄（已領總月數）",
    ),
    (
        "student_history_visible_to_college",
        "開放學院查詢本學院學生的獎學金領獎紀錄",
    ),
)

INSERT_SQL = sa.text("""
    INSERT INTO system_settings (
        key, value, category, data_type,
        is_sensitive, is_readonly, allow_empty,
        description, default_value, created_at, updated_at
    )
    SELECT
        :key, 'true', 'features'::configcategory, 'boolean'::configdatatype,
        false, false, false,
        :description, 'true', NOW(), NOW()
    WHERE NOT EXISTS (SELECT 1 FROM system_settings WHERE key = :key)
    """)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "system_settings" not in inspector.get_table_names():
        return

    for key, description in SETTINGS:
        bind.execute(INSERT_SQL, {"key": key, "description": description})


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "system_settings" not in inspector.get_table_names():
        return

    # configuration_audit_logs rows are left in place: setting_key is a plain
    # string (no FK), and the change history of a since-removed key is still
    # legitimate audit trail.
    bind.execute(
        sa.text("DELETE FROM system_settings WHERE key = ANY(:keys)"),
        {"keys": [key for key, _ in SETTINGS]},
    )
