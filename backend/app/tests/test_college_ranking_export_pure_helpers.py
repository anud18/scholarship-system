"""
Pure-function tests for `CollegeRankingExportService` row-rendering helpers.

This service produces the official 學生資料彙整表 Excel workbook that
college reviewers use to compare candidates. Bugs in the renderers
produce visible noise in the spreadsheet (wrong gender column, wrong
'直接攻博' flag, grade-year off by one) — visible to reviewers and
audit-prone since the workbook is archived.

7 pure helpers covered (21 cases):
- `_safe_str`                : None → '', everything else → str(x)
- `_render_gender`           : SIS std_sex 1/2 → 男/女
- `_render_direct_phd`       : enroll-type code → 是/否
- `_compute_grade`           : trm_termcount → ceil(/2)
- `_render_enrollment_date`  : (year, term) → 'YYY.M.1'
- `_render_scholarship_type` : sub_type_preferences → '志願' label
- `_extract_dynamic_value`   : form_data['fields'][name]['value']
"""

from types import SimpleNamespace

import pytest

from app.services.college_ranking_export_service import CollegeRankingExportService


@pytest.fixture
def service():
    """Service has no constructor args — fully stateless."""
    return CollegeRankingExportService()


# ─── _safe_str ───────────────────────────────────────────────────────


def test_safe_str_none_returns_empty(service):
    assert service._safe_str(None) == ""


def test_safe_str_int_to_str(service):
    assert service._safe_str(42) == "42"


def test_safe_str_string_passthrough(service):
    assert service._safe_str("hello") == "hello"


# ─── _render_gender ──────────────────────────────────────────────────


def test_render_gender_male(service):
    """SIS std_sex=1 means male — render as 男."""
    assert service._render_gender(1) == "男"


def test_render_gender_female(service):
    assert service._render_gender(2) == "女"


def test_render_gender_unknown_returns_empty(service):
    """3, None, '1' (string), etc → '' (don't guess; show blank)."""
    assert service._render_gender(3) == ""
    assert service._render_gender(None) == ""
    assert service._render_gender("1") == ""


# ─── _render_direct_phd ──────────────────────────────────────────────


def test_render_direct_phd_yes(service):
    """std_enrolltype in {8,9,10,11} = 直接攻博 ⇒ 是."""
    for code in (8, 9, 10, 11):
        assert service._render_direct_phd(code) == "是", f"code={code}"


def test_render_direct_phd_no(service):
    assert service._render_direct_phd(1) == "否"
    assert service._render_direct_phd(7) == "否"
    assert service._render_direct_phd(12) == "否"


def test_render_direct_phd_string_coerces(service):
    """String numeric coerces via int(). '8' → 是."""
    assert service._render_direct_phd("8") == "是"
    assert service._render_direct_phd("3") == "否"


def test_render_direct_phd_unparseable_returns_empty(service):
    """None / non-numeric ⇒ '' (don't render 否 if we have no data)."""
    assert service._render_direct_phd(None) == ""
    assert service._render_direct_phd("invalid") == ""


# ─── _compute_grade ──────────────────────────────────────────────────


def test_compute_grade_termcount_to_grade(service):
    """ceil(termcount/2). term 1-2 → grade 1, 3-4 → 2, 5-6 → 3, 7-8 → 4."""
    assert service._compute_grade(1) == 1
    assert service._compute_grade(2) == 1
    assert service._compute_grade(3) == 2
    assert service._compute_grade(8) == 4


def test_compute_grade_zero_or_negative_returns_empty(service):
    """0 or negative termcount ⇒ '' (no grade derivable)."""
    assert service._compute_grade(0) == ""
    assert service._compute_grade(-1) == ""


def test_compute_grade_unparseable_returns_empty(service):
    assert service._compute_grade(None) == ""
    assert service._compute_grade("not-a-number") == ""


# ─── _render_enrollment_date ─────────────────────────────────────────


def test_render_enrollment_date_term1_is_september(service):
    assert service._render_enrollment_date(112, 1) == "112.9.1"


def test_render_enrollment_date_term2_is_february(service):
    assert service._render_enrollment_date(113, 2) == "113.2.1"


def test_render_enrollment_date_missing_year_returns_empty(service):
    assert service._render_enrollment_date(None, 1) == ""
    assert service._render_enrollment_date("", 1) == ""


def test_render_enrollment_date_unparseable_year_returns_empty(service):
    assert service._render_enrollment_date("not-a-year", 1) == ""


# ─── _render_scholarship_type ────────────────────────────────────────


def test_render_scholarship_type_single_preference(service):
    """Single preference ⇒ just the label (no 第一志願 suffix)."""
    app = SimpleNamespace(sub_type_preferences=["nstc"], sub_scholarship_type=None)
    assert service._render_scholarship_type(app, {"nstc": "國科會"}) == "國科會"


def test_render_scholarship_type_two_preferences(service):
    """Two preferences ⇒ '{第一}(第一志願)暨{第二}(第二志願)'."""
    app = SimpleNamespace(sub_type_preferences=["nstc", "moe_1w"], sub_scholarship_type=None)
    out = service._render_scholarship_type(app, {"nstc": "國科會", "moe_1w": "教育部"})
    assert out == "國科會(第一志願)暨教育部(第二志願)"


def test_render_scholarship_type_fallback_to_sub_scholarship_type(service):
    """No prefs ⇒ fall back to sub_scholarship_type via the label map."""
    app = SimpleNamespace(sub_type_preferences=None, sub_scholarship_type="nstc")
    assert service._render_scholarship_type(app, {"nstc": "國科會"}) == "國科會"


def test_render_scholarship_type_empty_returns_empty(service):
    """No preferences AND no sub_scholarship_type ⇒ ''."""
    app = SimpleNamespace(sub_type_preferences=None, sub_scholarship_type=None)
    assert service._render_scholarship_type(app, {}) == ""


# ─── _extract_dynamic_value ──────────────────────────────────────────


def test_extract_dynamic_value_normal(service):
    fields = {"bank_account": {"value": "123-456", "field_type": "text"}}
    assert service._extract_dynamic_value(fields, "bank_account") == "123-456"


def test_extract_dynamic_value_missing_field_returns_empty(service):
    assert service._extract_dynamic_value({}, "any_field") == ""


def test_extract_dynamic_value_null_or_empty_returns_empty(service):
    fields = {"f": {"value": None}, "g": {"value": ""}}
    assert service._extract_dynamic_value(fields, "f") == ""
    assert service._extract_dynamic_value(fields, "g") == ""


def test_extract_dynamic_value_non_dict_entry_returns_empty(service):
    """If the entry isn't a dict (data corruption / API drift), return ''
    rather than crashing the export."""
    fields = {"f": "not-a-dict-just-a-string"}
    assert service._extract_dynamic_value(fields, "f") == ""
