"""
Tests for the hardcoded NYCU ``std_enrolltype`` fallback.

Context: the ``enroll_types`` DB table has historically been empty on every
environment (no seed migration), so the frontend ``getEnrollTypeName`` helper
always fell back to ``未知入學方式 (code)``. ``app.core.enroll_types`` ships a
hardcoded canonical mapping merged into the reference-data endpoints so every
valid NYCU code resolves to a real name.

These tests pin the contract:
  - empty DB ⇒ all 17 codes × 3 degrees are returned (51 rows)
  - code 1 resolves to ``招生考試一般生`` (the reported bug)
  - direct-PhD codes 8-11 are present with their canonical names
  - DB rows take precedence over the hardcoded fallback (admin override path)
  - the merge is idempotent and sorted by (degree_id, code)
"""

import pytest

from app.core.enroll_types import get_hardcoded_enroll_types, merge_enroll_types


class _FakeRow:
    """Mimics a SQLAlchemy ``EnrollType`` row for the merge function."""

    def __init__(self, degree_id, code, name="DB_ROW", name_en="DB Row", degree=None):
        self.degreeId = degree_id
        self.code = code
        self.name = name
        self.name_en = name_en
        self.degree = degree


def test_hardcoded_list_covers_all_three_degrees_and_canonical_codes():
    """The seed must cover degrees 1/2/3 and the 17 canonical NYCU codes."""
    entries = get_hardcoded_enroll_types()
    degree_ids = {e["degree_id"] for e in entries}
    assert degree_ids == {1, 2, 3}, f"missing degrees: {degree_ids}"

    # 17 canonical codes × 3 degrees = 51
    assert len(entries) == 51, f"expected 51 entries, got {len(entries)}"

    codes_per_degree = {
        degree_id: sorted(int(e["code"]) for e in entries if e["degree_id"] == degree_id) for degree_id in (1, 2, 3)
    }
    expected_codes = sorted([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 17, 18, 26, 29, 30])
    for degree_id, codes in codes_per_degree.items():
        assert codes == expected_codes, f"degree {degree_id} codes mismatch: {codes}"


def test_code_1_resolves_to_admission_exam_general():
    """Pin the reported bug: code 1 must NOT show '未知入學方式'.

    Regression guard for the issue where every student's 入學方式 displayed as
    '未知入學方式 (1)' because the enroll_types table was empty."""
    entries = get_hardcoded_enroll_types()
    for degree_id in (1, 2, 3):
        match = next(e for e in entries if e["degree_id"] == degree_id and e["code"] == "1")
        assert (
            match["name"] == "招生考試一般生"
        ), f"degree {degree_id} code 1 should be 招生考試一般生, got {match['name']!r}"


def test_direct_phd_codes_8_through_11_present_with_canonical_names():
    """Codes 8-11 identify direct-track PhD students and are referenced by
    ``DIRECT_PHD_ENROLLTYPE_CODES`` in college_ranking_export_service.py and
    by the 逕讀博士獎學金 eligibility rule in seed_scholarship_configs.py."""
    entries = get_hardcoded_enroll_types()
    expected = {
        "8": "大學逕博",
        "9": "碩士逕博",
        "10": "跨校學士逕博",
        "11": "跨校碩士逕博",
    }
    phd_entries = {e["code"]: e["name"] for e in entries if e["degree_id"] == 1}
    for code, name in expected.items():
        assert phd_entries.get(code) == name, f"PhD code {code} should be {name!r}, got {phd_entries.get(code)!r}"


def test_merge_with_empty_db_returns_full_hardcoded_set():
    """Empty DB rows ⇒ merge falls back to the full hardcoded list."""
    merged = merge_enroll_types([])
    assert len(merged) == 51
    # Sorted by (degree_id, code-as-int)
    assert merged[0] == {
        "degree_id": 1,
        "code": "1",
        "name": "招生考試一般生",
        "name_en": "Admission Exam - General",
        "degree_name": None,
    }


def test_db_rows_take_precedence_over_hardcoded_fallback():
    """When the DB has a row for (degree_id, code), it wins over the hardcoded
    value — so admins can still override via the database if a future migration
    populates the table with corrected names."""
    db_row = _FakeRow(degree_id=3, code=1, name="DB_OVERRIDE", name_en="DB Override")
    merged = merge_enroll_types([db_row])

    match = next(d for d in merged if d["degree_id"] == 3 and d["code"] == "1")
    assert match["name"] == "DB_OVERRIDE"
    assert match["name_en"] == "DB Override"

    # Other codes for degree 3 still come from the hardcoded fallback
    other = next(d for d in merged if d["degree_id"] == 3 and d["code"] == "8")
    assert other["name"] == "大學逕博"


def test_merge_is_sorted_by_degree_id_then_numeric_code():
    """The merge output must be sorted by (degree_id, numeric code) so the
    frontend dropdown renders codes in natural order (1, 2, ..., 30) rather
    than lexicographic (1, 10, 11, 12, 17, 18, 2, 26, ...)."""
    merged = merge_enroll_types([])
    for degree_id in (1, 2, 3):
        codes = [int(d["code"]) for d in merged if d["degree_id"] == degree_id]
        assert codes == sorted(codes), f"codes not sorted for degree {degree_id}: {codes}"
