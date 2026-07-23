"""
Hardcoded NYCU ``std_enrolltype`` reference values.

The ``enroll_types`` table in the database has historically been empty (no seed
migration, no SQL dump) on every environment — dev, staging, and prod alike.
As a result the frontend ``getEnrollTypeName`` helper
(``frontend/hooks/use-reference-data.ts``) could never resolve a name and fell
back to ``未知入學方式 (code)`` for every student, even for valid codes like
``1`` (招生考試一般生).

Rather than ship a database migration (the values are a stable NYCU SIS
contract, not environment-specific config), we hardcode the canonical mapping
here and expose it as a fallback that the reference-data endpoints merge in
whenever the DB lookup comes up short.

Source of truth: NYCU Student Information System ``std_enrolltype`` field.
Confirmed against codebase usage in:
  - ``mock-student-api/main.py`` (codes 1, 2, 4, 8, 9)
  - ``backend/app/db/seed_scholarship_configs.py`` (codes 2,5,6,7 and 8,9,10,11)
  - ``backend/app/services/college_ranking_export_service.py``
    (``DIRECT_PHD_ENROLLTYPE_CODES = {8,9,10,11}``)
  - ``backend/app/tests/test_college_ranking_export_service.py``
"""

from typing import Any

# Degree IDs (matches ``backend/app/db/seed_scholarship_configs.py`` and the
# ``degrees`` table seed in migration 6d5b1940bf8a):
#   1 = 博士 (PhD)
#   2 = 碩士 (Master)
#   3 = 學士 (Undergraduate)
_DEGREE_IDS: tuple[int, ...] = (1, 2, 3)

# Canonical NYCU std_enrolltype code → (Chinese name, English name).
# Codes are stable across all degrees; the same enrollment channel can apply
# to PhD / Master / Undergrad students (e.g. code 1 = 招生考試一般生 is valid
# for all three). Degree-specific channels like 逕博 (8-11) are technically
# PhD-only, but including them for all degrees is harmless — the eligibility
# rules in ``seed_scholarship_configs.py`` enforce degree constraints, not
# this display-only reference table.
_ENROLL_TYPE_ENTRIES: tuple[tuple[int, str, str], ...] = (
    (1, "招生考試一般生", "Admission Exam - General"),
    (2, "招生考試在職生", "Admission Exam - In-service"),
    (3, "選讀生", "Selected Studies"),
    (4, "推甄一般生", "Recommendation - General"),
    (5, "推甄在職生", "Recommendation - In-service"),
    (6, "僑生", "Overseas Chinese Student"),
    (7, "外籍生", "International Student"),
    (8, "大學逕博", "Direct PhD (from Bachelor)"),
    (9, "碩士逕博", "Direct PhD (from Master)"),
    (10, "跨校學士逕博", "Direct PhD (Cross-university, from Bachelor)"),
    (11, "跨校碩士逕博", "Direct PhD (Cross-university, from Master)"),
    (12, "雙聯學位", "Dual Degree"),
    (17, "陸生", "Mainland Chinese Student"),
    (18, "轉校", "Transfer Student"),
    (26, "專案入學", "Project Admission"),
    (29, "TIGP", "TIGP (Taiwan International Graduate Program)"),
    (30, "其他", "Other"),
)


def get_hardcoded_enroll_types() -> list[dict[str, Any]]:
    """Return the canonical NYCU enroll_types list, one entry per
    (degree_id, code) pair.

    The shape mirrors what ``reference_data.py`` builds from DB rows so the
    frontend ``getEnrollTypeName`` helper can consume it unchanged:
    ``{degree_id, code, name, name_en, degree_name}``.

    ``degree_name`` is left ``None`` — the frontend does not read it for the
    lookup (only ``degree_id`` + ``code`` + ``name``), and the DB-sourced
    version populates it via a join that has no equivalent here.
    """
    return [
        {
            "degree_id": degree_id,
            "code": str(code),
            "name": name_zh,
            "name_en": name_en,
            "degree_name": None,
        }
        for degree_id in _DEGREE_IDS
        for code, name_zh, name_en in _ENROLL_TYPE_ENTRIES
    ]


def merge_enroll_types(db_rows: list[Any]) -> list[dict[str, Any]]:
    """Merge DB-sourced enroll_types with the hardcoded fallback.

    DB rows win when present (so admins can still override via the DB if a
    future migration populates the table). For any ``(degree_id, code)`` pair
    missing from the DB, the hardcoded value fills the gap — guaranteeing that
    every valid NYCU ``std_enrolltype`` code resolves to a real display name
    instead of the ``未知入學方式 (code)`` fallback.

    Args:
        db_rows: SQLAlchemy ``EnrollType`` model instances (or any objects
            with ``degreeId``, ``code``, ``name``, ``name_en``, ``degree``
            attributes) as returned by ``select(EnrollType)``.

    Returns:
        List of dicts shaped like the ``enroll_types`` entries in the
        ``/reference-data/all`` response.
    """
    seen: set[tuple[int, str]] = set()
    merged: list[dict[str, Any]] = []

    for row in db_rows:
        degree_id = getattr(row, "degreeId", None)
        code = getattr(row, "code", None)
        if degree_id is None or code is None:
            continue
        code_str = str(code)
        key = (int(degree_id), code_str)
        if key in seen:
            continue
        seen.add(key)
        degree = getattr(row, "degree", None)
        merged.append(
            {
                "degree_id": int(degree_id),
                "code": code_str,
                "name": getattr(row, "name", None),
                "name_en": getattr(row, "name_en", None),
                "degree_name": getattr(degree, "name", None) if degree is not None else None,
            }
        )

    for entry in get_hardcoded_enroll_types():
        key = (int(entry["degree_id"]), str(entry["code"]))
        if key not in seen:
            merged.append(entry)
            seen.add(key)

    merged.sort(key=lambda e: (e["degree_id"], int(e["code"])))
    return merged
