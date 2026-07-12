"""Align academies.name/name_en with core/college_mappings.py (#1143)

The academies lookup table carried pre-restructuring names that contradict
core/college_mappings.py (the canonical 13-college mapping, consistent with
the departments.academy_code attribution seeded by 7b3f6d9c894f) — e.g. the
table said 1=理學院 / S=科管學院 / O=客家學院 while the rest of the system
treats 1=醫學院 / S=理學院 / O=光電學院. Displays reading academies (quota
matrix, dropdowns) therefore disagreed with student-snapshot college names.

Revision ID: align_academy_names_001
Revises: add_batch_import_type_001
"""

import sqlalchemy as sa

from alembic import op

revision = "align_academy_names_001"
down_revision = "add_batch_import_type_001"
branch_labels = None
depends_on = None

TABLE = "academies"

# Frozen from core/college_mappings.py COLLEGE_MAPPINGS / COLLEGE_MAPPINGS_EN
CANONICAL_NAMES = {
    "E": ("電機學院", "College of Electrical and Computer Engineering"),
    "C": ("資訊學院", "College of Computer Science"),
    "I": ("工學院", "College of Engineering"),
    "S": ("理學院", "College of Science"),
    "B": ("工程生物學院", "College of Biological Science and Technology"),
    "O": ("光電學院", "College of Photonics"),
    "D": ("半導體學院", "College of Semiconductor Research"),
    "1": ("醫學院", "College of Medicine"),
    "6": ("生醫工學院", "College of Biomedical Engineering"),
    "7": ("生命科學院", "College of Life Science"),
    "M": ("管理學院", "College of Management"),
    "A": ("人社院", "College of Humanities and Social Sciences"),
    "K": ("客家學院", "College of Hakka Studies"),
}

# Pre-migration values (dev/staging DB snapshot 2026-07-12), for downgrade.
PREVIOUS_NAMES = {
    "E": ("電機學院", "College of Electrical and Computer Engineering"),
    "C": ("資訊學院", "College of Computer Science"),
    "I": ("工學院", "College of Engineering"),
    "S": ("科管學院", "College of Management"),
    "B": ("生科學院", "College of Biological Science and Technology"),
    "O": ("客家學院", "College of Hakka Studies"),
    "D": ("光電學院", "College of Photonics"),
    "1": ("理學院", "College of Science"),
    "6": ("電資學院", "College of Electrical Engineering and Computer Science"),
    "7": ("科技法律學院", "College of Technology Law"),
    "M": ("管理學院", "College of Management"),
    "A": ("人社學院", "College of Humanities and Social Sciences"),
    "K": ("半導體學院", "College of Semiconductor Research"),
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
