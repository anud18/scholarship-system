"""
Pure-function tests for `StudentVerificationService` helpers.

This service verifies student enrollment status against an external
API (with mock-mode fallback). Wrong parsing of the API response, or
wrong label rendering, surfaces to college reviewers as 'verified'
when the student is actually graduated / withdrawn — a real
compliance issue (paying out scholarships to ineligible students).

3 helpers covered (16 cases):
- `_mock_verification`              : dev mode — last-digit-driven branching
- `_parse_api_response`             : 5 status strings + unknown + exception
- `get_verification_status_label`   : zh/en label mapping for each status
"""

import pytest

from app.models.payment_roster import StudentVerificationStatus
from app.services.student_verification_service import StudentVerificationService


@pytest.fixture
def service():
    """Constructor reads settings; mock_mode toggle is set by env."""
    return StudentVerificationService()


# ─── _mock_verification (dev mode) ───────────────────────────────────


def test_mock_verification_last_digit_0_to_6_is_verified(service):
    """Last digit 0–6 ⇒ VERIFIED — most common path for happy-path tests."""
    for digit in range(7):
        result = service._mock_verification(f"A12345678{digit}", "Test")
        assert result["status"] == StudentVerificationStatus.VERIFIED, f"digit={digit}"


def test_mock_verification_digit_7_is_graduated(service):
    result = service._mock_verification("A123456787", "Test")
    assert result["status"] == StudentVerificationStatus.GRADUATED
    assert "graduation_date" in result["student_info"]


def test_mock_verification_digit_8_is_suspended(service):
    result = service._mock_verification("A123456788", "Test")
    assert result["status"] == StudentVerificationStatus.SUSPENDED


def test_mock_verification_digit_9_is_withdrawn(service):
    result = service._mock_verification("A123456789", "Test")
    assert result["status"] == StudentVerificationStatus.WITHDRAWN


def test_mock_verification_non_digit_treated_as_zero(service):
    """If last char isn't a digit (corrupted ID), treat as 0 ⇒ VERIFIED.
    Defensive — don't crash if SIS hands us an ID ending in a letter."""
    result = service._mock_verification("A12345678X", "Test")
    assert result["status"] == StudentVerificationStatus.VERIFIED


def test_mock_verification_metadata_includes_last_digit(service):
    """The api_response dict carries the last_digit for debugging — pin
    the structure so future log analysis can rely on it."""
    result = service._mock_verification("A123456783", "Test")
    assert result["api_response"]["mock"] is True
    assert result["api_response"]["last_digit"] == 3


# ─── _parse_api_response ─────────────────────────────────────────────


def test_parse_api_response_active_to_verified(service):
    """Both English 'active'/'enrolled' and Chinese '在學' → VERIFIED."""
    assert service._parse_api_response({"status": "active"}, "A1")["status"] == StudentVerificationStatus.VERIFIED
    assert service._parse_api_response({"status": "enrolled"}, "A1")["status"] == StudentVerificationStatus.VERIFIED
    assert service._parse_api_response({"status": "在學"}, "A1")["status"] == StudentVerificationStatus.VERIFIED


def test_parse_api_response_graduated_mapping(service):
    assert service._parse_api_response({"status": "graduated"}, "A1")["status"] == StudentVerificationStatus.GRADUATED
    assert service._parse_api_response({"status": "畢業"}, "A1")["status"] == StudentVerificationStatus.GRADUATED


def test_parse_api_response_suspended_and_withdrawn(service):
    assert service._parse_api_response({"status": "suspended"}, "A1")["status"] == StudentVerificationStatus.SUSPENDED
    assert service._parse_api_response({"status": "休學"}, "A1")["status"] == StudentVerificationStatus.SUSPENDED
    assert service._parse_api_response({"status": "withdrawn"}, "A1")["status"] == StudentVerificationStatus.WITHDRAWN
    assert service._parse_api_response({"status": "退學"}, "A1")["status"] == StudentVerificationStatus.WITHDRAWN


def test_parse_api_response_unknown_status_to_not_found(service):
    """Unknown status string ⇒ NOT_FOUND (don't auto-pass as VERIFIED)."""
    assert service._parse_api_response({"status": "alien"}, "A1")["status"] == StudentVerificationStatus.NOT_FOUND


def test_parse_api_response_status_is_case_insensitive(service):
    """API may return uppercase / mixed case — the impl lowercases first."""
    assert service._parse_api_response({"status": "GRADUATED"}, "A1")["status"] == StudentVerificationStatus.GRADUATED


def test_parse_api_response_exception_path_returns_api_error(service):
    """If the .get() chain blows up (e.g., data is not a dict),
    return API_ERROR — don't crash the import pipeline."""

    class _BadData:
        def get(self, *args, **kwargs):
            raise RuntimeError("simulated parse failure")

    result = service._parse_api_response(_BadData(), "A1")
    assert result["status"] == StudentVerificationStatus.API_ERROR
    assert "API回應解析錯誤" in result["message"]


# ─── get_verification_status_label ───────────────────────────────────


def test_status_label_zh_all_six_statuses(service):
    expected = {
        StudentVerificationStatus.VERIFIED: "已驗證",
        StudentVerificationStatus.GRADUATED: "已畢業",
        StudentVerificationStatus.SUSPENDED: "休學中",
        StudentVerificationStatus.WITHDRAWN: "已退學",
        StudentVerificationStatus.API_ERROR: "驗證錯誤",
        StudentVerificationStatus.NOT_FOUND: "查無此人",
    }
    for status, label in expected.items():
        assert service.get_verification_status_label(status, locale="zh") == label


def test_status_label_en_all_six_statuses(service):
    expected = {
        StudentVerificationStatus.VERIFIED: "Verified",
        StudentVerificationStatus.GRADUATED: "Graduated",
        StudentVerificationStatus.SUSPENDED: "Suspended",
        StudentVerificationStatus.WITHDRAWN: "Withdrawn",
        StudentVerificationStatus.API_ERROR: "API Error",
        StudentVerificationStatus.NOT_FOUND: "Not Found",
    }
    for status, label in expected.items():
        assert service.get_verification_status_label(status, locale="en") == label


def test_status_label_unknown_locale_falls_back_to_zh(service):
    """Unknown locale (e.g. 'fr', 'ja') falls back to zh — pin behavior so
    if multi-locale support is added later, the default isn't accidentally
    changed."""
    assert service.get_verification_status_label(StudentVerificationStatus.VERIFIED, locale="fr") == "已驗證"
