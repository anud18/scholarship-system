"""
Regression tests for Semester.yearly handling across model labels and
util helpers. Pins commits be08e9a (Application.get_semester_label),
9cc8864 (ScholarshipRule + ScholarshipConfiguration academic_year_label,
academic_period.format_academic_term), and 2c90aa1 (semester→enum mapping
in scholarship endpoints — covered separately).

Pre-fix: these label sites only mapped first/second; yearly fell into the
default branch and rendered as "" or "Second", silently misnaming yearly
scholarships everywhere they appeared.
"""

import pytest

from app.models.application import Application
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipRule
from app.utils.academic_period import format_academic_term


# ---- Application.get_semester_label ----------------------------------------


def _application_with_semester(semester: Semester) -> Application:
    """Build an in-memory Application for label-only assertion (no DB)."""
    app = Application.__new__(Application)
    app.semester = semester
    app.academic_year = 114
    return app


def test_application_get_semester_label_first():
    assert _application_with_semester(Semester.first).get_semester_label() == "第一學期"


def test_application_get_semester_label_second():
    assert _application_with_semester(Semester.second).get_semester_label() == "第二學期"


def test_application_get_semester_label_yearly():
    """The fix in be08e9a — pre-fix this returned empty string."""
    assert _application_with_semester(Semester.yearly).get_semester_label() == "全年"


# ---- ScholarshipRule.academic_year_label -----------------------------------


def _rule_with_year_semester(year: int, semester: Semester | None) -> ScholarshipRule:
    rule = ScholarshipRule.__new__(ScholarshipRule)
    rule.is_template = False
    rule.academic_year = year
    rule.semester = semester
    return rule


def test_scholarship_rule_label_first():
    assert _rule_with_year_semester(114, Semester.first).academic_year_label == "114學年度 第一學期"


def test_scholarship_rule_label_second():
    assert _rule_with_year_semester(114, Semester.second).academic_year_label == "114學年度 第二學期"


def test_scholarship_rule_label_yearly():
    """Pre-fix: returned '114學年度 ' (trailing space, blank semester label)."""
    assert _rule_with_year_semester(114, Semester.yearly).academic_year_label == "114學年度 全年"


def test_scholarship_rule_label_no_semester():
    assert _rule_with_year_semester(114, None).academic_year_label == "114學年度"


# ---- ScholarshipConfiguration.academic_year_label --------------------------


def _config_with_year_semester(year: int, semester: Semester | None) -> ScholarshipConfiguration:
    config = ScholarshipConfiguration.__new__(ScholarshipConfiguration)
    config.academic_year = year
    config.semester = semester
    return config


def test_scholarship_config_label_yearly():
    assert _config_with_year_semester(114, Semester.yearly).academic_year_label == "114學年度 全年"


# ---- academic_period.format_academic_term ----------------------------------


def test_format_academic_term_yearly_zh():
    assert format_academic_term(114, "yearly", "zh") == "114學年度全年"


def test_format_academic_term_yearly_en():
    assert format_academic_term(114, "yearly", "en") == "AY 114 Yearly"


def test_format_academic_term_first_zh():
    assert format_academic_term(114, "first", "zh") == "114學年度第一學期"


def test_format_academic_term_second_en():
    assert format_academic_term(114, "second", "en") == "AY 114 Second Semester"


def test_format_academic_term_unknown_falls_back_to_yearly():
    """Pre-fix English path used a binary `if first else 'Second'` which
    silently labelled everything-not-first as "Second" — including yearly
    AND any future enum value. Post-fix uses an explicit mapping with a
    sane fallback to Yearly / 全年."""
    assert format_academic_term(114, "future_value", "en") == "AY 114 Yearly"
    assert format_academic_term(114, "future_value", "zh") == "114學年度全年"
