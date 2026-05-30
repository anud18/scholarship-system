"""
Pure-function tests for `ScholarshipRule` and `ScholarshipSubTypeConfig`.

ScholarshipRule.is_applicable_to_period gates which rules apply when
evaluating a student's eligibility for a given academic year+semester.

A bug causes:
- Wrong rule applied to wrong term → student rejected unfairly
- Template rule accidentally applied → universal eligibility chaos
- Universal rule skipped → mandatory check bypass (eligibility leak)

8 helpers covered (16 cases).
"""

from types import SimpleNamespace

import pytest

from app.models.enums import Semester
from app.models.scholarship import ScholarshipRule, ScholarshipSubTypeConfig


def _rule(**overrides) -> ScholarshipRule:
    """Build an in-memory ScholarshipRule (no DB session)."""
    # scholarship_type is a relationship; tests stub it with a duck-typed
    # SimpleNamespace for validate_sub_type. Pop it out and inject via __dict__
    # afterwards, since the ORM constructor rejects a non-mapped instance.
    scholarship_type = overrides.pop("scholarship_type", None)
    defaults = {
        "id": 1,
        "scholarship_type_id": 1,
        "rule_name": "min_gpa",
        "rule_type": "student_basic",
        "sub_type": None,
        "academic_year": None,
        "semester": None,
        "is_template": False,
    }
    defaults.update(overrides)
    r = ScholarshipRule(**defaults)
    r.__dict__["scholarship_type"] = scholarship_type
    return r


def _config(**overrides) -> ScholarshipSubTypeConfig:
    defaults = {
        "id": 1,
        "name": "國科會",
        "name_en": None,
        "amount": None,
    }
    defaults.update(overrides)
    return ScholarshipSubTypeConfig(**defaults)


# ─── ScholarshipRule.validate_sub_type ───────────────────────────────


def test_validate_sub_type_none_returns_false():
    """Rule without a sub_type is invalid (the validator is asking
    'is this sub-type valid', which requires a sub-type)."""
    assert _rule(sub_type=None).validate_sub_type() is False


def test_validate_sub_type_with_no_parent_returns_false():
    """If scholarship_type isn't loaded or has no sub_type_list, can't
    validate — return False (cautious default)."""
    rule = _rule(sub_type="nstc", scholarship_type=None)
    assert rule.validate_sub_type() is False

    rule2 = _rule(sub_type="nstc", scholarship_type=SimpleNamespace(sub_type_list=None))
    assert rule2.validate_sub_type() is False

    rule3 = _rule(sub_type="nstc", scholarship_type=SimpleNamespace(sub_type_list=[]))
    assert rule3.validate_sub_type() is False


def test_validate_sub_type_membership_check():
    """sub_type IN scholarship_type.sub_type_list → True."""
    rule = _rule(sub_type="nstc", scholarship_type=SimpleNamespace(sub_type_list=["nstc", "moe_1w"]))
    assert rule.validate_sub_type() is True

    rule_bad = _rule(sub_type="unknown", scholarship_type=SimpleNamespace(sub_type_list=["nstc", "moe_1w"]))
    assert rule_bad.validate_sub_type() is False


# ─── ScholarshipRule.academic_period_label ──────────────────────────


def test_academic_period_label_template():
    """Template rules show '模板' regardless of other fields."""
    assert _rule(is_template=True, academic_year=114, semester=Semester.first).academic_period_label == "模板"


def test_academic_period_label_universal():
    """No academic_year (and not template) → '通用'."""
    assert _rule(is_template=False, academic_year=None).academic_period_label == "通用"


def test_academic_period_label_year_only():
    """Year set but no semester → year-only label."""
    assert _rule(academic_year=114, semester=None).academic_period_label == "114學年度"


def test_academic_period_label_with_semester():
    """Year + semester → combined label."""
    assert _rule(academic_year=114, semester=Semester.first).academic_period_label == "114學年度 第一學期"
    assert _rule(academic_year=113, semester=Semester.second).academic_period_label == "113學年度 第二學期"
    assert _rule(academic_year=114, semester=Semester.yearly).academic_period_label == "114學年度 全年"


# ─── ScholarshipRule.is_applicable_to_period ────────────────────────


def test_is_applicable_template_always_false():
    """SECURITY: templates MUST NOT be applied to any period — they're
    blueprints, not rules. Pin so a refactor doesn't accidentally
    'apply template rules as fallback'."""
    rule = _rule(is_template=True)
    assert rule.is_applicable_to_period(114, Semester.first) is False


def test_is_applicable_universal_rule_applies_to_any_period():
    """Rule with no academic_year → applies to ALL periods (universal
    invariant). Pin so a refactor doesn't accidentally scope universals
    to current year only."""
    rule = _rule(academic_year=None)
    assert rule.is_applicable_to_period(113, Semester.first) is True
    assert rule.is_applicable_to_period(114, Semester.second) is True
    assert rule.is_applicable_to_period(115, None) is True


def test_is_applicable_year_mismatch_blocks():
    """Rule scoped to year 114 doesn't apply to year 113."""
    rule = _rule(academic_year=114, semester=Semester.first)
    assert rule.is_applicable_to_period(113, Semester.first) is False


def test_is_applicable_yearly_rule_matches_any_semester_in_year():
    """Rule with semester=None (yearly) applies to both first and second
    of the matching year."""
    rule = _rule(academic_year=114, semester=None)
    assert rule.is_applicable_to_period(114, Semester.first) is True
    assert rule.is_applicable_to_period(114, Semester.second) is True
    # Different year → still blocked.
    assert rule.is_applicable_to_period(113, Semester.first) is False


def test_is_applicable_semester_match_required_when_set():
    """If rule has semester set, it must match exactly."""
    rule = _rule(academic_year=114, semester=Semester.first)
    assert rule.is_applicable_to_period(114, Semester.first) is True
    assert rule.is_applicable_to_period(114, Semester.second) is False


# ─── ScholarshipSubTypeConfig pure properties ───────────────────────


def test_display_name_prefers_english_when_set():
    """If name_en is set, it wins (locale-driven UI)."""
    assert _config(name="國科會", name_en="NSTC").display_name == "NSTC"


def test_display_name_falls_back_to_chinese():
    """name_en None → fall back to name."""
    assert _config(name="國科會", name_en=None).display_name == "國科會"
    assert _config(name="國科會", name_en="").display_name == "國科會"


def test_effective_amount_returns_amount_when_set():
    """Sub-type specific amount takes precedence."""
    assert _config(amount=50000).effective_amount == 50000


def test_effective_amount_none_when_unset():
    """No amount → None (caller falls back further upstream)."""
    assert _config(amount=None).effective_amount is None
