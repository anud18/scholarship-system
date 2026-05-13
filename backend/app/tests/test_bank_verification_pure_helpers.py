"""
Pure-function tests for `BankVerificationService` helpers.

These run without DB or OCR — covering the format-validation +
normalization helpers that gate every bank-account verification.
A regression here would either accept malformed account numbers
(funds-routing risk) or reject valid ones (student support load).

Helpers covered (12 cases across 4 helpers):
- validate_postal_account_format: 14-digit Taiwanese postal account format.
- normalize_account_number: strip non-digit characters.
- verify_account_number_exact: form-vs-OCR exact match after normalization.
- normalize_text: case-fold + strip punctuation + collapse whitespace.
"""

import pytest

from app.services.bank_verification_service import BankVerificationService


@pytest.fixture
def service():
    """No DB needed for pure helpers."""
    return BankVerificationService(db=None)  # type: ignore[arg-type]


# ─── validate_postal_account_format ──────────────────────────────────


def test_validate_postal_account_format_valid_14_digits(service):
    is_valid, err = service.validate_postal_account_format("12345678901234")
    assert is_valid is True
    assert err is None


def test_validate_postal_account_format_strips_dashes_and_spaces(service):
    """Real-world input often contains formatting; the function strips it."""
    is_valid, err = service.validate_postal_account_format("1234567-8901234")
    assert is_valid is True

    is_valid2, _ = service.validate_postal_account_format("1234 5678 9012 34")
    assert is_valid2 is True


def test_validate_postal_account_format_empty_rejected(service):
    is_valid, err = service.validate_postal_account_format("")
    assert is_valid is False
    assert "不可為空" in (err or "")


def test_validate_postal_account_format_wrong_length_rejected(service):
    """13 digits → too short. Error message reports the actual length."""
    is_valid, err = service.validate_postal_account_format("1234567890123")
    assert is_valid is False
    assert "13" in (err or "")


# ─── normalize_account_number ───────────────────────────────────────


def test_normalize_account_number_strips_non_digits(service):
    assert service.normalize_account_number("1234-5678-90") == "1234567890"
    assert service.normalize_account_number("ABC 12 34 56 XYZ") == "123456"


def test_normalize_account_number_empty_returns_empty(service):
    assert service.normalize_account_number("") == ""
    assert service.normalize_account_number(None) == ""  # type: ignore[arg-type]


# ─── verify_account_number_exact ────────────────────────────────────


def test_verify_account_number_exact_matches_after_normalization(service):
    """Form and OCR can differ in formatting; must match after normalization."""
    result = service.verify_account_number_exact("1234-5678-9012-34", "12345678901234")
    assert result["is_match"] is True
    assert result["normalized_form"] == "12345678901234"
    assert result["normalized_ocr"] == "12345678901234"


def test_verify_account_number_exact_detects_mismatch(service):
    result = service.verify_account_number_exact("12345678901234", "99999999999999")
    assert result["is_match"] is False
    assert result["normalized_form"] != result["normalized_ocr"]


# ─── normalize_text ─────────────────────────────────────────────────


def test_normalize_text_lowercases_and_strips_punctuation(service):
    assert service.normalize_text("Hello, World!") == "hello world"


def test_normalize_text_collapses_whitespace(service):
    """Multiple internal spaces collapse to one."""
    assert service.normalize_text("foo   bar   baz") == "foo bar baz"


def test_normalize_text_empty_returns_empty(service):
    assert service.normalize_text("") == ""
    assert service.normalize_text(None) == ""  # type: ignore[arg-type]


def test_normalize_text_keeps_cjk_chars(service):
    """Chinese / Japanese / Korean characters survive normalization
    (they're word chars in the \\w regex class)."""
    result = service.normalize_text("王 小明 ，hello!")
    # Punctuation gone, whitespace collapsed, CJK preserved.
    assert "王" in result
    assert "小明" in result
    assert "hello" in result
    assert "，" not in result
    assert "!" not in result
