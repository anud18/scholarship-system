"""
Pure-function tests for `StudentVerificationService` helpers.

This service verifies student enrollment status against an external
API (with mock-mode fallback). Wrong parsing of the API response, or
wrong label rendering, surfaces to college reviewers as 'verified'
when the student is actually graduated / withdrawn — a real
compliance issue (paying out scholarships to ineligible students).

Helpers covered:
- `_mock_verification`              : dev mode — SIS-mock-first, heuristic fallback (#1141)
- `_mock_sis_verification`          : std_studingstatus / mgd_title → status mapping
- `_last_digit_mock_verification`   : offline fallback — last-digit-driven branching
- `_parse_api_response`             : 5 status strings + unknown + exception
- `get_verification_status_label`   : zh/en label mapping for each status
"""

import pytest
import requests

from app.models.payment_roster import StudentVerificationStatus
from app.services.student_verification_service import StudentVerificationService


@pytest.fixture
def service():
    """Constructor reads settings; mock_mode toggle is set by env."""
    return StudentVerificationService()


# ─── _mock_verification (dev mode, SIS-mock-first — #1141) ───────────


def test_mock_verification_prefers_sis_result(service, monkeypatch):
    """When the SIS mock answers, its status wins — the last-digit heuristic
    must NOT override it (digit 3 would be VERIFIED under the heuristic)."""
    sis_result = {
        "status": StudentVerificationStatus.SUSPENDED,
        "message": "學生目前休學中（SIS mock：休學）",
        "student_info": {},
        "verified_at": None,
        "api_response": {"mock": True, "source": "mock-student-api"},
    }
    monkeypatch.setattr(service, "_mock_sis_verification", lambda *a: sis_result)
    assert service._mock_verification("A123456783", "Test") is sis_result


def test_mock_verification_falls_back_to_last_digit_when_sis_unavailable(service, monkeypatch):
    """SIS mock unreachable (None) ⇒ the offline last-digit heuristic runs."""
    monkeypatch.setattr(service, "_mock_sis_verification", lambda *a: None)
    result = service._mock_verification("A123456787", "Test")
    assert result["status"] == StudentVerificationStatus.GRADUATED


# ─── _mock_sis_verification (std_studingstatus mapping) ──────────────


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


def _sis_payload(status, title=""):
    return {
        "code": 200,
        "data": [
            {
                "std_stdcode": "T00",
                "std_cname": "測試生",
                "std_studingstatus": status,
                "mgd_title": title,
            }
        ],
    }


@pytest.mark.parametrize(
    ("sis_status", "expected"),
    [
        (1, StudentVerificationStatus.VERIFIED),
        (2, StudentVerificationStatus.VERIFIED),
        (3, StudentVerificationStatus.VERIFIED),
        (4, StudentVerificationStatus.SUSPENDED),
        (5, StudentVerificationStatus.WITHDRAWN),
        (11, StudentVerificationStatus.GRADUATED),
    ],
)
def test_sis_verification_status_mapping(service, monkeypatch, sis_status, expected):
    monkeypatch.setattr(service.session, "post", lambda *a, **k: _FakeResponse(_sis_payload(sis_status)))
    result = service._mock_sis_verification("T00", "測試生")
    assert result["status"] == expected


def test_sis_verification_unknown_status_uses_title(service, monkeypatch):
    """Numeric status outside the map falls back to the Chinese title."""
    monkeypatch.setattr(service.session, "post", lambda *a, **k: _FakeResponse(_sis_payload(99, "退學")))
    result = service._mock_sis_verification("T00", "測試生")
    assert result["status"] == StudentVerificationStatus.WITHDRAWN


def test_sis_verification_missing_student_is_not_found(service, monkeypatch):
    """SIS answering 'no such student' is definitive — NOT_FOUND, not fallback."""
    monkeypatch.setattr(service.session, "post", lambda *a, **k: _FakeResponse({"code": 404, "data": []}))
    result = service._mock_sis_verification("T00", "測試生")
    assert result["status"] == StudentVerificationStatus.NOT_FOUND


def test_sis_verification_unreachable_returns_none(service, monkeypatch):
    """Connection error ⇒ None so the caller falls back to the heuristic."""

    def _boom(*a, **k):
        raise requests.ConnectionError("simulated outage")

    monkeypatch.setattr(service.session, "post", _boom)
    assert service._mock_sis_verification("T00", "測試生") is None


# ─── _last_digit_mock_verification (offline fallback) ────────────────


def test_last_digit_0_to_6_is_verified(service):
    """Last digit 0–6 ⇒ VERIFIED — most common path for happy-path tests."""
    for digit in range(7):
        result = service._last_digit_mock_verification(f"A12345678{digit}", "Test")
        assert result["status"] == StudentVerificationStatus.VERIFIED, f"digit={digit}"


def test_last_digit_7_is_graduated(service):
    result = service._last_digit_mock_verification("A123456787", "Test")
    assert result["status"] == StudentVerificationStatus.GRADUATED
    assert "graduation_date" in result["student_info"]


def test_last_digit_8_is_suspended(service):
    result = service._last_digit_mock_verification("A123456788", "Test")
    assert result["status"] == StudentVerificationStatus.SUSPENDED


def test_last_digit_9_is_withdrawn(service):
    result = service._last_digit_mock_verification("A123456789", "Test")
    assert result["status"] == StudentVerificationStatus.WITHDRAWN


def test_last_digit_non_digit_treated_as_zero(service):
    """If last char isn't a digit (corrupted ID), treat as 0 ⇒ VERIFIED.
    Defensive — don't crash if SIS hands us an ID ending in a letter."""
    result = service._last_digit_mock_verification("A12345678X", "Test")
    assert result["status"] == StudentVerificationStatus.VERIFIED


def test_last_digit_metadata_includes_last_digit(service):
    """The api_response dict carries the last_digit for debugging — pin
    the structure so future log analysis can rely on it."""
    result = service._last_digit_mock_verification("A123456783", "Test")
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
