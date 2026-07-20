"""Align numeric 陽明-campus academy codes 2/3/5 with SIS reality

align_academy_names_001 (#1143) fixed numeric codes 1/6/7 but left 2/3/4/5
carrying pre-restructuring 交大 names (2=工學院, 3=管理學院, 5=生命科學院).
SIS student data (std_academyno) uses the 陽明-campus semantics for these
codes — fixed by the departments.academy_code attribution seeded by
7b3f6d9c894f (牙醫學系→2, 護理學系→3, 藥學系/生物藥學研究所→5). The stale
rows made the manual-distribution quota matrix label a 藥物科學院 student's
quota row as 管理學院 and duplicate college names across dropdowns.

Code "4" is intentionally untouched: SIS only attributes administrative
units (院本部/選讀學分/短期研究生) to it, never students.

Revision ID: align_academy_names_002
Revises: drop_app_document_001
"""

import sqlalchemy as sa

from alembic import op

revision = "align_academy_names_002"
down_revision = "drop_app_document_001"
branch_labels = None
depends_on = None

TABLE = "academies"

# Aligned with core/college_mappings.py COLLEGE_MAPPINGS / COLLEGE_MAPPINGS_EN
CANONICAL_NAMES = {
    "2": ("牙醫學院", "College of Dentistry"),
    "3": ("護理學院", "College of Nursing"),
    "5": ("藥物科學院", "College of Pharmaceutical Sciences"),
}

# Pre-migration values (seeded by 09a6cf986f5c), for downgrade.
PREVIOUS_NAMES = {
    "2": ("工學院", "College of Engineering"),
    "3": ("管理學院", "College of Management"),
    "5": ("生命科學院", "College of Life Science"),
}

_UPDATE_SQL = sa.text(f"UPDATE {TABLE} SET name = :name, name_en = :name_en WHERE code = :code")


def _apply(names: dict) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    for code, (name, name_en) in names.items():
        bind.execute(_UPDATE_SQL, {"code": code, "name": name, "name_en": name_en})


def upgrade() -> None:
    _apply(CANONICAL_NAMES)


def downgrade() -> None:
    _apply(PREVIOUS_NAMES)
