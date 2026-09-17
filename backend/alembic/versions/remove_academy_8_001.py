"""Remove duplicate academy code 8 (人社院)

align_academy_names_003 added code 8 = 人社院 from the SIS 學院代碼表, but the
same college already exists as code A = 人社院, so the admin 使用者權限 dialog
offered two identical 人社院 options. Code 8 is dropped; departments
(departments.academy_code is an FK) and college-role users still pointing at 8
are moved to A, the same college. Downgrade restores the academy row only —
the moved rows are indistinguishable from native A rows and stay on A.

Revision ID: remove_academy_8_001
Revises: align_academy_names_003
"""

import logging

import sqlalchemy as sa

from alembic import op

logger = logging.getLogger("alembic.runtime.migration")

revision = "remove_academy_8_001"
down_revision = "align_academy_names_003"
branch_labels = None
depends_on = None

TABLE = "academies"
DEPT_TABLE = "departments"
USER_TABLE = "users"

REMOVED_ROWS = (("8", "人社院", "College of Humanities and Social Sciences"),)
# Removed code -> surviving code of the same college.
REPLACEMENT_CODES = {"8": "A"}


def _tables_exist(bind) -> bool:
    names = sa.inspect(bind).get_table_names()
    return TABLE in names and DEPT_TABLE in names


def upgrade() -> None:
    bind = op.get_bind()
    if not _tables_exist(bind):
        return

    tables = set(sa.inspect(bind).get_table_names())
    for old_code, new_code in REPLACEMENT_CODES.items():
        moved = bind.execute(
            sa.text(f"UPDATE {DEPT_TABLE} SET academy_code = :new WHERE academy_code = :old"),
            {"old": old_code, "new": new_code},
        ).rowcount
        if moved:
            logger.info("remove_academy_8_001: moved %s departments from %s to %s", moved, old_code, new_code)
        if USER_TABLE in tables:
            moved = bind.execute(
                sa.text(f"UPDATE {USER_TABLE} SET college_code = :new WHERE college_code = :old"),
                {"old": old_code, "new": new_code},
            ).rowcount
            if moved:
                logger.info("remove_academy_8_001: moved %s users from %s to %s", moved, old_code, new_code)

    for code, _, _ in REMOVED_ROWS:
        bind.execute(sa.text(f"DELETE FROM {TABLE} WHERE code = :code"), {"code": code})


def downgrade() -> None:
    bind = op.get_bind()
    if not _tables_exist(bind):
        return

    bind.execute(
        sa.text(
            f"INSERT INTO {TABLE} (code, name, name_en) VALUES (:code, :name, :name_en) ON CONFLICT (code) DO NOTHING"
        ),
        [{"code": code, "name": name, "name_en": name_en} for code, name, name_en in REMOVED_ROWS],
    )
