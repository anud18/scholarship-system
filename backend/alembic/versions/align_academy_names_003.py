"""Align the whole academies table with the SIS 學院代碼表

align_academy_names_001/002 only corrected the 16 codes that
core/college_mappings.py knew about. The remaining rows seeded by
09a6cf986f5c were guesses that contradict the official SIS academy code
table (學院代碼表.xlsx): F=國際半導體學院 (really 產創學院), L=永續學院 (科技法律
學院), J=跨域學院 (博雅書苑), X=產學創新學院 (電機資訊學院), P=總務處 (跨院),
Z=服務學習專業知能學程 (國防中心), 0=未分類 (校級); code 8 (人社院) was missing
and code ~ (智能系統學院) does not exist in SIS. Several English names
(B/D/6/7/A/Y) also drifted. The admin 使用者權限 dialog lists this table when
assigning the 學院 role, so those users saw wrong codes and names.

The sheet's placeholder rows 4=選讀生, *=外校生 and ^=校內其他單位 are NOT
colleges and are removed too. Departments attributed to them (選讀學分 /
短期研究生 / 校級行政單位 / 學分學程) get academy_code = NULL — none of them is
a student department, and student college attribution reads
student_data.std_academyno, never departments.academy_code.

Revision ID: align_academy_names_003
Revises: add_fixed_key_columns_001
"""

import logging

import sqlalchemy as sa

from alembic import op

logger = logging.getLogger("alembic.runtime.migration")

revision = "align_academy_names_003"
down_revision = "add_fixed_key_columns_001"
branch_labels = None
depends_on = None

TABLE = "academies"
DEPT_TABLE = "departments"

# Frozen copy of core/college_mappings.py ACADEMY_TABLE (verbatim 學院代碼表).
CANONICAL_ROWS = (
    ("E", "電機學院", "College of Electrical and Computer Engineering"),
    ("Y", "電資學院", "Electrical Engineering and Computer Science"),
    ("C", "資訊學院", "College of Computer Science"),
    ("B", "工程生物學院", "College of Engineering Bioscience"),
    ("M", "管理學院", "College of Management"),
    ("I", "工學院", "College of Engineering"),
    ("S", "理學院", "College of Science"),
    ("A", "人社院", "College of Humanities Arts and Social Sciences"),
    ("K", "客家學院", "College of Hakka Studies"),
    ("X", "電機資訊學院", "Electrical Engineering and Computer Science"),
    ("O", "光電學院", "College of Photonics"),
    ("L", "科技法律學院", "School of Law"),
    ("D", "半導體學院", "International College of Semiconductor Technology"),
    ("G", "綠能學院", "College of Artificial Intelligence"),
    ("Z", "國防中心", "CeNDER"),
    ("8", "人社院", "College of Humanities and Social Sciences"),
    ("1", "醫學院", "College of Medicine"),
    ("2", "牙醫學院", "College of Dentistry"),
    ("3", "護理學院", "College of Nursing"),
    ("5", "藥物科學院", "College of Pharmaceutical Sciences"),
    ("6", "生醫工學院", "College of Biomedical Science and Engineering"),
    ("7", "生命科學院", "College of Life Sciences"),
    ("0", "校級", "School Level"),
    ("F", "產創學院", "Industry Academia Innovation School"),
    ("P", "跨院", "Cross-Domain Integration Promoting Office"),
    ("J", "博雅書苑", "Liberal Arts College"),
)

# Pre-migration values (post align_academy_names_002 snapshot), for downgrade.
# Rows absent here were already correct and are left untouched on downgrade.
PREVIOUS_ROWS = (
    ("B", "工程生物學院", "College of Biological Science and Technology"),
    ("A", "人社院", "College of Humanities and Social Sciences"),
    ("X", "產學創新學院", "College of Industry-Academia Innovation"),
    ("L", "永續學院", "College of Sustainability"),
    ("D", "半導體學院", "College of Semiconductor Research"),
    ("G", "智慧學院", "College of AI"),
    ("Z", "服務學習專業知能學程", "Service Learning Program"),
    ("6", "生醫工學院", "College of Biomedical Engineering"),
    ("7", "生命科學院", "College of Life Science"),
    ("0", "未分類", "Unclassified"),
    ("F", "國際半導體學院", "International College of Semiconductor Technology"),
    ("P", "總務處", "General Affairs Office"),
    ("J", "跨域學院", "College of Interdisciplinary Studies"),
    ("Y", "電資學院", "College of Electrical Engineering and Computer Science"),
    ("4", "人文社會學院", "College of Humanities and Social Sciences"),
    ("*", "海外教育專班", "Overseas Education Program"),
    ("^", "全校性單位", "University-wide Units"),
    ("~", "智能系統學院", "College of Intelligent Systems"),
)
ADDED_CODES = ("8",)

# departments.academy_code attribution (from 7b3f6d9c894f) detached on upgrade
# and re-attached on downgrade.
PREVIOUS_DEPARTMENT_ACADEMY = {
    "4": ("12CC", "32CC", "400", "6YYY", "6YYZ"),
    "^": (
        "0U1", "0U2", "0U3", "0U4", "0U5", "0U6", "0U7", "0U8", "0U9", "0UA", "0UB", "0UC",
        "0UD", "0UE", "0UF", "0UH", "0UI", "0UJ", "0UL", "0UM", "0UN", "0UO", "0UV", "0UZ",
        "0t1", "1OU1", "1OU2", "1OU3", "1OU4", "1OU7", "1OU8", "1OU9", "1OUA", "1OUB", "1OUC",
        "1PCD", "2UH", "7KZ", "7LF", "8AB", "8AC", "8AF", "8AG", "8AH", "8AI", "8AK", "8AM",
        "8AO", "8AP", "8AQ", "8AR", "8AS", "8AT", "8AU", "8AV", "8AW", "8AX", "8AY", "8AZ",
        "8BA", "8BB", "8BC", "8BD", "8BE", "8BF", "8BG", "8BH", "8BI", "8BJ", "8BK", "8BL",
        "8BN", "8BO", "8BP", "8BQ", "8BS", "8BU", "8BV", "8BW", "8BX", "8BY", "8BZ", "8CA",
        "8CB", "8CC", "8CD", "8CE", "8CF", "8FJ", "ZKZ",
    ),
}  # fmt: skip

_UPSERT_SQL = sa.text(
    f"INSERT INTO {TABLE} (code, name, name_en) VALUES (:code, :name, :name_en) "
    "ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, name_en = EXCLUDED.name_en"
)
_DETACH_DEPTS_SQL = sa.text(f"UPDATE {DEPT_TABLE} SET academy_code = NULL WHERE academy_code = :code")
_ATTACH_DEPT_SQL = sa.text(
    f"UPDATE {DEPT_TABLE} SET academy_code = :code WHERE code = :dept_code AND academy_code IS NULL"
)
_DELETE_SQL = sa.text(f"DELETE FROM {TABLE} WHERE code = :code")


def _tables_exist(bind) -> bool:
    names = sa.inspect(bind).get_table_names()
    return TABLE in names and DEPT_TABLE in names


def _upsert(bind, rows) -> None:
    bind.execute(_UPSERT_SQL, [{"code": code, "name": name, "name_en": name_en} for code, name, name_en in rows])


def _remove_academy(bind, code: str) -> None:
    bind.execute(_DETACH_DEPTS_SQL, {"code": code})
    bind.execute(_DELETE_SQL, {"code": code})


def upgrade() -> None:
    bind = op.get_bind()
    if not _tables_exist(bind):
        return

    _upsert(bind, CANONICAL_ROWS)

    canonical_codes = {code for code, _, _ in CANONICAL_ROWS}
    existing_codes = [row[0] for row in bind.execute(sa.text(f"SELECT code FROM {TABLE}"))]
    stale_codes = [code for code in existing_codes if code not in canonical_codes]
    if stale_codes:
        logger.info("align_academy_names_003: removing academies not in 學院代碼表: %s", stale_codes)
    for code in stale_codes:
        _remove_academy(bind, code)


def downgrade() -> None:
    bind = op.get_bind()
    if not _tables_exist(bind):
        return

    _upsert(bind, PREVIOUS_ROWS)
    for code, dept_codes in PREVIOUS_DEPARTMENT_ACADEMY.items():
        for dept_code in dept_codes:
            bind.execute(_ATTACH_DEPT_SQL, {"code": code, "dept_code": dept_code})
    for code in ADDED_CODES:
        _remove_academy(bind, code)
