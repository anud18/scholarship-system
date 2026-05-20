"""
Tests for the PhD eligibility plugin pure helpers
(app.services.plugins.phd_eligibility_plugin).

The plugin contains the BUSINESS RULES that determine when an
alternate PhD student is allowed to replace a primary recipient.
A regression here would either:
  * Promote ineligible alternates (cross-college / wrong cohort)
  * Block eligible alternates (over-aggressive rejection)

Both directions hit students directly — pinned tightly.

Two helpers covered:

  - **is_phd_scholarship(scholarship_config)**: code-list lookup.
    Pin the documented codes ("phd_scholarship", "phd", "doctoral"),
    case-insensitive match, and defensive None handling.

  - **check_phd_alternate_eligibility(...)**: rejection branches
    that fire BEFORE the DB call (received_months calculation).
    Pin every rejection reason string verbatim because admins
    read these in the audit log; changing the wording silently
    breaks log greps.

13 cases.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.plugins.phd_eligibility_plugin import (
    PHD_SCHOLARSHIP_CODES,
    check_phd_alternate_eligibility,
    is_phd_scholarship,
)

# ─── PHD_SCHOLARSHIP_CODES constant ──────────────────────────────────


def test_phd_scholarship_codes_are_documented():
    # Pin: three documented codes. The list is hardcoded today
    # (with a TODO to move into DB config); pin so a refactor
    # that drops or adds a code forces explicit review.
    assert PHD_SCHOLARSHIP_CODES == ["phd_scholarship", "phd", "doctoral"]


# ─── is_phd_scholarship ──────────────────────────────────────────────


def _config(code):
    return SimpleNamespace(scholarship_type=SimpleNamespace(code=code))


def test_is_phd_returns_true_for_phd_scholarship_code():
    assert is_phd_scholarship(_config("phd_scholarship")) is True


def test_is_phd_returns_true_for_phd_code():
    assert is_phd_scholarship(_config("phd")) is True


def test_is_phd_returns_true_for_doctoral_code():
    assert is_phd_scholarship(_config("doctoral")) is True


def test_is_phd_case_insensitive():
    # Pin: case-insensitive — "PhD", "DOCTORAL", "Phd_Scholarship"
    # all match. Pin so a refactor to strict-case doesn't silently
    # reject all the existing seed data with capitalized codes.
    assert is_phd_scholarship(_config("PhD")) is True
    assert is_phd_scholarship(_config("DOCTORAL")) is True
    assert is_phd_scholarship(_config("Phd_Scholarship")) is True


def test_is_phd_returns_false_for_non_phd():
    # Pin: undergraduate / academic_excellence / unknown codes
    # are NOT PhD scholarships.
    assert is_phd_scholarship(_config("undergraduate")) is False
    assert is_phd_scholarship(_config("academic_excellence")) is False
    assert is_phd_scholarship(_config("unknown_code")) is False


def test_is_phd_returns_false_for_none_config():
    # Pin: None config → False (defensive). Pin so caller code can
    # rely on this without an explicit None guard.
    assert is_phd_scholarship(None) is False


def test_is_phd_returns_false_for_missing_scholarship_type():
    config = SimpleNamespace(scholarship_type=None)
    assert is_phd_scholarship(config) is False


def test_is_phd_returns_false_for_empty_code():
    # Pin: empty string code → False (not crash, not True).
    assert is_phd_scholarship(_config("")) is False


def test_is_phd_returns_false_for_none_code():
    assert is_phd_scholarship(_config(None)) is False


# ─── check_phd_alternate_eligibility rejection branches ──────────────


@patch("app.services.plugins.phd_eligibility_plugin.get_college_code_from_data")
def test_reject_when_alternate_missing_college(mock_get_college):
    # Pin: rejection reason "備取學生缺少學院資訊" — admins greppable.
    mock_get_college.side_effect = [None, "C"]  # alternate=None, original=C
    is_eligible, reason = check_phd_alternate_eligibility(
        db=MagicMock(),
        student_data={},
        original_student_data={},
        scholarship_config=MagicMock(),
    )
    assert is_eligible is False
    assert reason == "備取學生缺少學院資訊"


@patch("app.services.plugins.phd_eligibility_plugin.get_college_code_from_data")
def test_reject_when_college_mismatch(mock_get_college):
    # Pin: rejection reason includes BOTH college codes for
    # auditor clarity. Cross-college promotion is the #1 PhD
    # rule violation we want to prevent.
    mock_get_college.side_effect = ["A", "B"]
    is_eligible, reason = check_phd_alternate_eligibility(
        db=MagicMock(),
        student_data={},
        original_student_data={},
        scholarship_config=MagicMock(),
    )
    assert is_eligible is False
    assert "A" in reason and "B" in reason
    assert "學院" in reason


@patch("app.services.plugins.phd_eligibility_plugin.get_college_code_from_data")
def test_college_mismatch_is_case_insensitive(mock_get_college):
    # Pin: alternate "a" vs original "A" treated as same college
    # (upper-cased before comparison). Defensive against
    # inconsistent SIS data casing.
    mock_get_college.side_effect = ["a", "A"]
    is_eligible, reason = check_phd_alternate_eligibility(
        db=MagicMock(),
        student_data={"std_enrollyear": 113, "std_enrollterm": 1, "std_stdcode": "x"},
        original_student_data={"std_enrollyear": 113, "std_enrollterm": 1},
        scholarship_config=MagicMock(),
    )
    # Should NOT reject on college — but will fail on something
    # else (likely received_months DB call). We just check the
    # college rejection didn't fire.
    if not is_eligible:
        assert "學院" not in reason


@patch("app.services.plugins.phd_eligibility_plugin.get_college_code_from_data")
def test_reject_when_alternate_missing_enrollment(mock_get_college):
    # Pin: rejection reason "備取學生缺少入學年度或學期資訊".
    mock_get_college.side_effect = ["A", "A"]
    is_eligible, reason = check_phd_alternate_eligibility(
        db=MagicMock(),
        student_data={},  # no std_enrollyear / std_enrollterm
        original_student_data={"std_enrollyear": 113, "std_enrollterm": 1},
        scholarship_config=MagicMock(),
    )
    assert is_eligible is False
    assert reason == "備取學生缺少入學年度或學期資訊"


@patch("app.services.plugins.phd_eligibility_plugin.get_college_code_from_data")
def test_reject_when_cohort_mismatch(mock_get_college):
    # Pin: rejection reason includes BOTH enrollment year/term
    # for auditor clarity. Different cohort → different competition
    # pool, can't substitute.
    mock_get_college.side_effect = ["A", "A"]
    is_eligible, reason = check_phd_alternate_eligibility(
        db=MagicMock(),
        student_data={"std_enrollyear": 114, "std_enrollterm": 1, "std_stdcode": "x"},
        original_student_data={"std_enrollyear": 113, "std_enrollterm": 1},
        scholarship_config=MagicMock(),
    )
    assert is_eligible is False
    assert "114" in reason and "113" in reason


@patch("app.services.plugins.phd_eligibility_plugin.get_college_code_from_data")
def test_reject_when_alternate_missing_student_id(mock_get_college):
    # Pin: rejection reason "備取學生缺少學號資訊". Pinned because
    # without std_stdcode we can't query received_months — must
    # reject conservatively.
    mock_get_college.side_effect = ["A", "A"]
    is_eligible, reason = check_phd_alternate_eligibility(
        db=MagicMock(),
        student_data={"std_enrollyear": 113, "std_enrollterm": 1},  # no std_stdcode/nycu_id
        original_student_data={"std_enrollyear": 113, "std_enrollterm": 1},
        scholarship_config=MagicMock(),
    )
    assert is_eligible is False
    assert reason == "備取學生缺少學號資訊"
