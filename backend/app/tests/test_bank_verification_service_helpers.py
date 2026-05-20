"""
Unit tests for `BankVerificationService` pure helpers.

These methods are pure functions on the service class — no DB, no SMTP,
no MinIO — but they encode load-bearing comparison logic used in every
batch bank-verification run:

- `validate_postal_account_format` — guards the 14-digit Taiwan postal
  account format. A regression here would let mis-typed accounts slip
  through to AI verification, wasting GPU time.
- `normalize_account_number` — strips whitespace / dashes before
  comparison. Used by `verify_account_number_exact`, the new
  `_application_uses_verified_account` short-circuit (PR #224), and the
  manual-review UI.
- `verify_account_number_exact` — exact-match decision after
  normalisation. Production-critical: false positives = payment to the
  wrong account.
- `normalize_text` + `calculate_similarity` — fuzzy match for
  account-holder names. Used to decide between "verified" and
  "needs_manual_review".

Wave 2b of the production-readiness rollout.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.bank_verification_service import (
    ACCOUNT_NUMBER_EXACT_MATCH_REQUIRED,
    BankVerificationService,
)

pytestmark = pytest.mark.smoke


@pytest.fixture
def service() -> BankVerificationService:
    """
    Construct the service with a dummy DB. None of the helpers under test
    actually touch `self.db`, so a MagicMock is sufficient.
    """
    return BankVerificationService(db=MagicMock())


class TestValidatePostalAccountFormat:
    """14-digit format gate."""

    def test_valid_14_digit_account(self, service: BankVerificationService) -> None:
        ok, err = service.validate_postal_account_format("12345678901234")
        assert ok is True
        assert err is None

    def test_valid_with_dashes_and_spaces(self, service: BankVerificationService) -> None:
        """Real-world bank pamphlets format as '0001234-5678901' (7-7 split,
        14 digits) — the validator strips non-digits before counting.

        Previously this test asserted "0001234-5678901-2" (15 digits) was
        valid, but the validator correctly requires exactly 14 digits; the
        test input had an extra trailing "-2" by mistake.
        """
        ok, err = service.validate_postal_account_format("0001234-5678901")
        assert ok is True
        assert err is None

    def test_15_digit_input_rejected(self, service: BankVerificationService) -> None:
        """Pin: 15 digits (one too many) → rejected with explicit count.
        Regression guard for the off-by-one fix above."""
        ok, err = service.validate_postal_account_format("0001234-5678901-2")
        assert ok is False
        assert err is not None and "15 位" in err

    def test_empty_string_rejected(self, service: BankVerificationService) -> None:
        ok, err = service.validate_postal_account_format("")
        assert ok is False
        assert err == "帳號不可為空"

    @pytest.mark.parametrize(
        "wrong_length",
        ["1", "1234567890", "123456789012345", "1234567890123"],
    )
    def test_wrong_length_rejected(self, service: BankVerificationService, wrong_length: str) -> None:
        ok, err = service.validate_postal_account_format(wrong_length)
        assert ok is False
        # Error message includes the actual count so operators can debug
        assert "14 位數字" in (err or "")

    def test_letters_rejected_after_strip(self, service: BankVerificationService) -> None:
        """Letters get stripped along with other non-digits; if the remaining
        digits aren't 14, the format error fires."""
        ok, err = service.validate_postal_account_format("ABC-1234-5678")
        assert ok is False
        # 8 digits after strip → "14 位數字" length error
        assert "14 位數字" in (err or "")


class TestNormalizeAccountNumber:
    """Strip everything non-numeric."""

    def test_already_normalized(self, service: BankVerificationService) -> None:
        assert service.normalize_account_number("12345678901234") == "12345678901234"

    def test_strips_dashes(self, service: BankVerificationService) -> None:
        assert service.normalize_account_number("0001234-5678901-2") == "00012345678901" + "2"

    def test_strips_spaces(self, service: BankVerificationService) -> None:
        assert service.normalize_account_number("0001 2345 6789 012") == "000123456789012"

    def test_strips_mixed_punctuation(self, service: BankVerificationService) -> None:
        assert service.normalize_account_number("(0001) 2345-6789.012") == "000123456789012"

    def test_strips_letters(self, service: BankVerificationService) -> None:
        """Letters are not digits; they get stripped, not preserved."""
        assert service.normalize_account_number("ABC123") == "123"

    def test_empty_returns_empty(self, service: BankVerificationService) -> None:
        assert service.normalize_account_number("") == ""

    def test_no_digits_returns_empty(self, service: BankVerificationService) -> None:
        assert service.normalize_account_number("ABC-DEF") == ""


class TestVerifyAccountNumberExact:
    """Exact-match decision after normalisation. Production-critical — false
    positives here mean paying the wrong account."""

    def test_identical_inputs_match(self, service: BankVerificationService) -> None:
        result = service.verify_account_number_exact("12345678901234", "12345678901234")
        assert result["is_match"] is True
        assert result["normalized_form"] == "12345678901234"
        assert result["normalized_ocr"] == "12345678901234"
        assert result["exact_match_required"] is ACCOUNT_NUMBER_EXACT_MATCH_REQUIRED

    def test_match_after_normalisation(self, service: BankVerificationService) -> None:
        """Form has dashes, OCR has spaces — should still match."""
        result = service.verify_account_number_exact("0001234-5678901-2", "0001 2345 6789 012")
        assert result["is_match"] is True
        assert result["normalized_form"] == result["normalized_ocr"]

    def test_differ_by_one_digit_no_match(self, service: BankVerificationService) -> None:
        """The whole point of exact match: a single-digit typo is NOT verified."""
        result = service.verify_account_number_exact("12345678901234", "12345678901235")
        assert result["is_match"] is False

    def test_both_empty_match(self, service: BankVerificationService) -> None:
        """Pathological case: both inputs empty → normalised to empty → match.
        This is documented behavior — the surrounding 14-digit validator catches
        this case earlier so it never reaches here in production."""
        result = service.verify_account_number_exact("", "")
        assert result["is_match"] is True
        assert result["normalized_form"] == ""
        assert result["normalized_ocr"] == ""


class TestNormalizeText:
    """Used as the pre-step for fuzzy name matching."""

    def test_lowercases_input(self, service: BankVerificationService) -> None:
        assert service.normalize_text("Wang Xiao Ming") == "wang xiao ming"

    def test_strips_special_chars(self, service: BankVerificationService) -> None:
        assert service.normalize_text("Mr. Wang!") == "mr wang"

    def test_collapses_whitespace(self, service: BankVerificationService) -> None:
        assert service.normalize_text("Wang   Xiao  Ming") == "wang xiao ming"

    def test_strips_leading_trailing_whitespace(self, service: BankVerificationService) -> None:
        assert service.normalize_text("  Wang Xiao Ming  ") == "wang xiao ming"

    def test_preserves_cjk_chars(self, service: BankVerificationService) -> None:
        """`\\w` in Python's re matches Unicode word chars by default, which
        includes CJK. Important — most real account holders are Chinese names."""
        assert service.normalize_text("王小明") == "王小明"

    def test_empty_input_returns_empty(self, service: BankVerificationService) -> None:
        assert service.normalize_text("") == ""


class TestCalculateSimilarity:
    """Fuzzy match scoring for account-holder names."""

    def test_identical_returns_1(self, service: BankVerificationService) -> None:
        assert service.calculate_similarity("王小明", "王小明") == 1.0

    def test_both_empty_returns_1(self, service: BankVerificationService) -> None:
        """Documented: both-empty is a degenerate match. Callers usually guard
        for empties upstream."""
        assert service.calculate_similarity("", "") == 1.0

    def test_one_empty_returns_0(self, service: BankVerificationService) -> None:
        assert service.calculate_similarity("", "王小明") == 0.0
        assert service.calculate_similarity("王小明", "") == 0.0

    def test_completely_different_low_score(self, service: BankVerificationService) -> None:
        # Two non-overlapping strings should have a similarity well below 0.5
        score = service.calculate_similarity("王小明", "abcdef")
        assert 0.0 <= score < 0.5

    def test_case_insensitive_via_normalize(self, service: BankVerificationService) -> None:
        """`calculate_similarity` runs `normalize_text` first, which lowercases.
        So 'WANG' vs 'wang' should be a perfect match."""
        assert service.calculate_similarity("WANG", "wang") == 1.0

    def test_score_in_unit_interval(self, service: BankVerificationService) -> None:
        """Score must always be a probability-like value in [0, 1]."""
        score = service.calculate_similarity("partial", "partially")
        assert 0.0 <= score <= 1.0
