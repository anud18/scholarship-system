"""
Tests for `backend/app/services/plugins/phd_eligibility_plugin.py`.

Module had ZERO test references. SECURITY-CRITICAL: PhD-scholarship
eligibility rules drive both primary-allocation continuation
checks and alternate-promotion gates during roster generation.
Drift would silently allow ineligible students into PhD rosters
(36-month-cap violations) or block legitimate alternates.

Wave 6a146 pins PHD_SCHOLARSHIP_CODES allowlist, is_phd_scholarship
case-insensitivity, check_phd_eligibility months-cap branch, and
check_phd_alternate_eligibility 3-rule chain (college / cohort /
months).

The calculate_received_months DB call is mocked. We're pinning the
rule-engine branches, not the SQL.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.plugins.phd_eligibility_plugin import (
    PHD_SCHOLARSHIP_CODES,
    check_phd_alternate_eligibility,
    check_phd_eligibility,
    is_phd_scholarship,
)


def _config(code: str = "phd_scholarship", config_id: int = 1):
    """Build a ScholarshipConfiguration stand-in."""
    return SimpleNamespace(
        id=config_id,
        scholarship_type=SimpleNamespace(code=code),
    )


class TestPhdScholarshipCodes:
    """Pin: 3 PhD scholarship codes allowlisted (phd_scholarship,
    phd, doctoral). Pin so refactor adding a new code without
    coordinating breaks the eligibility gate."""

    def test_three_known_codes(self):
        # Pin: exactly 3 codes. Pin so a refactor adding a new
        # PhD code that doesn't go here fails the eligibility
        # gate loudly.
        assert PHD_SCHOLARSHIP_CODES == ["phd_scholarship", "phd", "doctoral"]


class TestIsPhdScholarship:
    """Pin: is_phd_scholarship case-INSENSITIVE check."""

    def test_lowercase_code_matches(self):
        assert is_phd_scholarship(_config("phd_scholarship")) is True

    def test_uppercase_code_matches(self):
        # Pin: case-insensitive comparison via .lower(). Pin so
        # admin-typed "PHD" or "Doctoral" works.
        assert is_phd_scholarship(_config("PHD")) is True
        assert is_phd_scholarship(_config("DOCTORAL")) is True

    def test_mixed_case_code_matches(self):
        assert is_phd_scholarship(_config("Phd_Scholarship")) is True

    def test_non_phd_code_rejected(self):
        # Pin: non-PhD codes return False (e.g., nstc, moe_1w).
        # Pin so non-PhD scholarships don't trigger PhD-specific
        # eligibility gates.
        assert is_phd_scholarship(_config("nstc")) is False
        assert is_phd_scholarship(_config("moe_1w")) is False
        assert is_phd_scholarship(_config("general")) is False

    def test_none_config_returns_false(self):
        # Pin defensive: None config → False (NOT crash).
        assert is_phd_scholarship(None) is False

    def test_missing_scholarship_type_returns_false(self):
        # Pin defensive: config without scholarship_type → False.
        config = SimpleNamespace(scholarship_type=None)
        assert is_phd_scholarship(config) is False

    def test_empty_code_returns_false(self):
        # Pin: empty string code → False.
        assert is_phd_scholarship(_config("")) is False


class TestCheckPhdEligibilityMonthsCap:
    """Pin: months-received cap branch (default 36) for primary
    students during roster generation."""

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_under_36_months_passes(self, mock_calc):
        mock_calc.return_value = 24
        is_eligible, reason = check_phd_eligibility(
            db=MagicMock(),
            student_nycu_id="310460031",
            scholarship_config=_config(),
        )
        assert is_eligible is True
        assert reason is None

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_exactly_36_months_FAILS(self, mock_calc):
        # Pin: >=36 fails (NOT >36). Pin so refactor changing
        # to strict-greater silently lets 36-month-exact students
        # past the cap.
        mock_calc.return_value = 36
        is_eligible, reason = check_phd_eligibility(
            db=MagicMock(),
            student_nycu_id="310460031",
            scholarship_config=_config(),
        )
        assert is_eligible is False
        assert "36" in reason
        assert "上限" in reason

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_over_36_months_fails_with_actual_count(self, mock_calc):
        mock_calc.return_value = 48
        is_eligible, reason = check_phd_eligibility(
            db=MagicMock(),
            student_nycu_id="310460031",
            scholarship_config=_config(),
        )
        assert is_eligible is False
        assert "48" in reason

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_custom_max_months_override(self, mock_calc):
        # Pin: max_months is configurable per call (default 36).
        # Pin so refactor doesn't hardcode 36 in the comparison.
        mock_calc.return_value = 23
        is_eligible, reason = check_phd_eligibility(
            db=MagicMock(),
            student_nycu_id="x",
            scholarship_config=_config(),
            max_months=24,
        )
        assert is_eligible is True

        mock_calc.return_value = 24
        is_eligible, reason = check_phd_eligibility(
            db=MagicMock(),
            student_nycu_id="x",
            scholarship_config=_config(),
            max_months=24,
        )
        assert is_eligible is False

    def test_missing_nycu_id_returns_false_with_zh_tw_reason(self):
        # Pin: empty student_nycu_id → False with zh-TW reason
        # "缺少學號資訊". Pin so refactor doesn't accidentally pass
        # students with missing IDs.
        is_eligible, reason = check_phd_eligibility(
            db=MagicMock(),
            student_nycu_id="",
            scholarship_config=_config(),
        )
        assert is_eligible is False
        assert reason == "缺少學號資訊"


class TestCheckPhdAlternateEligibility:
    """Pin: 3-rule chain for alternates — college match, cohort
    match (enrollment year/term), months cap."""

    def test_missing_alternate_college_rejected(self):
        # Pin: alternate without college code → reject with
        # zh-TW reason "備取學生缺少學院資訊".
        is_eligible, reason = check_phd_alternate_eligibility(
            db=MagicMock(),
            student_data={"std_stdcode": "x"},  # No college info
            original_student_data={"std_academyno": "A"},
            scholarship_config=_config(),
        )
        assert is_eligible is False
        assert reason == "備取學生缺少學院資訊"

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_college_mismatch_rejected_case_insensitive(self, mock_calc):
        # Pin: college codes compared case-INSENSITIVE (.upper()).
        # Pin so admin-typed "a" vs "A" doesn't reject a
        # legitimate same-college alternate.
        mock_calc.return_value = 0
        # Same college (case differs) — should PASS the college check
        is_eligible, reason = check_phd_alternate_eligibility(
            db=MagicMock(),
            student_data={
                "std_academyno": "a",
                "std_enrollyear": 110,
                "std_enrollterm": 1,
                "std_stdcode": "310460031",
            },
            original_student_data={
                "std_academyno": "A",
                "std_enrollyear": 110,
                "std_enrollterm": 1,
            },
            scholarship_config=_config(),
        )
        assert is_eligible is True

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_different_college_rejected(self, mock_calc):
        # Pin: different college → reject with zh-TW reason.
        mock_calc.return_value = 0
        is_eligible, reason = check_phd_alternate_eligibility(
            db=MagicMock(),
            student_data={"std_academyno": "B", "std_enrollyear": 110, "std_enrollterm": 1, "std_stdcode": "x"},
            original_student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 1},
            scholarship_config=_config(),
        )
        assert is_eligible is False
        assert "學院" in reason
        assert "不符" in reason

    def test_missing_enrollment_year_rejected(self):
        # Pin: missing std_enrollyear → reject (cohort matching
        # requires both year + term).
        is_eligible, reason = check_phd_alternate_eligibility(
            db=MagicMock(),
            student_data={"std_academyno": "A", "std_stdcode": "x"},  # No enrollyear/term
            original_student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 1},
            scholarship_config=_config(),
        )
        assert is_eligible is False
        assert "入學年度" in reason or "學期" in reason

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_cohort_mismatch_rejected(self, mock_calc):
        # Pin: enrollyear or enrollterm differs → reject.
        # Pin so cohort-matching gate (PhD-specific rule) stays
        # strict — admins can't promote alternates from a
        # different intake cycle.
        mock_calc.return_value = 0
        is_eligible, reason = check_phd_alternate_eligibility(
            db=MagicMock(),
            student_data={"std_academyno": "A", "std_enrollyear": 111, "std_enrollterm": 1, "std_stdcode": "x"},
            original_student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 1},
            scholarship_config=_config(),
        )
        assert is_eligible is False
        assert "入學時間" in reason or "不符" in reason

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_term_mismatch_rejected(self, mock_calc):
        # Pin: same year, different term → reject. Term IS part
        # of the cohort definition (1st vs 2nd semester intake).
        mock_calc.return_value = 0
        is_eligible, reason = check_phd_alternate_eligibility(
            db=MagicMock(),
            student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 2, "std_stdcode": "x"},
            original_student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 1},
            scholarship_config=_config(),
        )
        assert is_eligible is False

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_missing_alternate_nycu_id_rejected_after_other_checks(self, mock_calc):
        # Pin: even with same college + cohort, missing nycu_id →
        # reject. Pin so refactor doesn't allow alternate to
        # be promoted without an identifier.
        mock_calc.return_value = 0
        is_eligible, reason = check_phd_alternate_eligibility(
            db=MagicMock(),
            student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 1},  # No std_stdcode
            original_student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 1},
            scholarship_config=_config(),
        )
        assert is_eligible is False
        assert "學號" in reason

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_nycu_id_fallback_from_alternate_id_field(self, mock_calc):
        # Pin: fallback to nycu_id field if std_stdcode missing.
        # Pin so both data shapes (SIS API + manual entry) work.
        mock_calc.return_value = 0
        is_eligible, reason = check_phd_alternate_eligibility(
            db=MagicMock(),
            student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 1, "nycu_id": "x"},
            original_student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 1},
            scholarship_config=_config(),
        )
        assert is_eligible is True

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_alternate_exceeds_months_cap_rejected(self, mock_calc):
        # Pin: same-college, same-cohort, but alternate has already
        # received >=max_months → reject. Pin so the months-cap
        # SECURITY gate stays active for alternates too.
        mock_calc.return_value = 40
        is_eligible, reason = check_phd_alternate_eligibility(
            db=MagicMock(),
            student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 1, "std_stdcode": "x"},
            original_student_data={"std_academyno": "A", "std_enrollyear": 110, "std_enrollterm": 1},
            scholarship_config=_config(),
            max_months=36,
        )
        assert is_eligible is False
        assert "備取" in reason
        assert "40" in reason
        assert "36" in reason


class TestCalculateReceivedMonthsFailOpen:
    """Pin: _calculate_received_months returns 0 on ANY exception
    (fail-open). Roster generation must not block on transient
    DB errors."""

    @patch("app.services.plugins.phd_eligibility_plugin.calculate_received_months")
    def test_exception_returns_zero_via_eligibility_path(self, mock_calc):
        # Pin: when calculate_received_months raises, eligibility
        # check should still return True (treats received_months
        # as 0, well under cap). Pin so refactor changing to
        # fail-CLOSED would silently reject legitimate students
        # during transient DB problems.
        mock_calc.side_effect = RuntimeError("db connection lost")
        is_eligible, reason = check_phd_eligibility(
            db=MagicMock(),
            student_nycu_id="x",
            scholarship_config=_config(),
        )
        assert is_eligible is True
        assert reason is None
