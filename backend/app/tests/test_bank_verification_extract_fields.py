"""
Behavioral tests for `BankVerificationService.extract_bank_fields_from_application`.

This is the field-aliasing layer between the dynamic-form schema (which
lets administrators name bank-account fields differently per scholarship
type — `postal_account`, `bank_account`, `帳號`, `郵局帳號`, etc.) and
the verification service's normalised internal shape:

    { "account_number": str, "account_holder": str }

It is NOT a pure function — it reads `application.submitted_form_data`
and `application.student_data` from the ORM-loaded Application
instance. But it doesn't issue DB queries inside, so it's testable with
in-memory `Application()` objects built up with the relevant attributes.

Key invariants pinned here:

1. First-matching alias wins (the order of `possible_keys` in the
   mapping is load-bearing).
2. Empty/None/missing form values fall through to the next alias.
3. `account_holder` falls back to `student_data.std_cname` only if the
   form didn't already populate it. This is the documented
   "form-data is authoritative when present" rule.
4. Missing `submitted_form_data` returns `{}` without raising.

A regression that mis-orders the aliases, fails to skip empty values,
or fails the std_cname fallback would silently degrade bank
verification for scholarship configurations using non-default field
names — and those scholarships are a real configuration in production
per CLAUDE.md §3 (configuration-driven, no code changes per type).

Wave 2i — ninth test coverage PR; first one in this session targeting
a non-pure method (reads model attributes but no DB query).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.bank_verification_service import BankVerificationService

pytestmark = pytest.mark.smoke


@pytest.fixture
def service() -> BankVerificationService:
    """The method under test reads `application.submitted_form_data` and
    `application.student_data` but never touches `self.db`, so a MagicMock
    is enough."""
    return BankVerificationService(db=MagicMock())


def _app(form_data=None, student_data=None) -> SimpleNamespace:
    """Build a stub Application with just the two attributes the method
    reads. Using SimpleNamespace instead of `Application()` to avoid
    triggering SQLAlchemy column setup."""
    return SimpleNamespace(
        submitted_form_data=form_data,
        student_data=student_data,
    )


# ---------------------------------------------------------------------------
# Empty / missing input
# ---------------------------------------------------------------------------


class TestEmptyOrMissingInput:
    def test_no_submitted_form_data_returns_empty(self, service: BankVerificationService) -> None:
        result = service.extract_bank_fields_from_application(_app(form_data=None))
        assert result == {}

    def test_empty_submitted_form_data_returns_empty(self, service: BankVerificationService) -> None:
        result = service.extract_bank_fields_from_application(_app(form_data={}))
        assert result == {}

    def test_no_fields_key_returns_empty(self, service: BankVerificationService) -> None:
        """submitted_form_data exists but lacks the 'fields' key → empty."""
        result = service.extract_bank_fields_from_application(_app(form_data={"documents": []}))
        assert result == {}

    def test_empty_fields_dict_returns_empty(self, service: BankVerificationService) -> None:
        result = service.extract_bank_fields_from_application(_app(form_data={"fields": {}}))
        assert result == {}


# ---------------------------------------------------------------------------
# Field aliasing — account_number
# ---------------------------------------------------------------------------


class TestAccountNumberAliasing:
    """The mapping defines 6 aliases for account_number; the first one with
    a non-empty value wins."""

    def test_postal_account_alias(self, service: BankVerificationService) -> None:
        app = _app(
            form_data={"fields": {"postal_account": {"value": "12345678901234"}}},
            student_data={"std_cname": "王小明"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result["account_number"] == "12345678901234"

    def test_bank_account_alias(self, service: BankVerificationService) -> None:
        app = _app(
            form_data={"fields": {"bank_account": {"value": "99988877766655"}}},
            student_data={"std_cname": "王小明"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result["account_number"] == "99988877766655"

    def test_chinese_alias(self, service: BankVerificationService) -> None:
        """Chinese aliases work because admins configuring the form may have
        used native field names."""
        app = _app(
            form_data={"fields": {"郵局帳號": {"value": "11223344556677"}}},
            student_data={"std_cname": "王小明"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result["account_number"] == "11223344556677"

    def test_first_alias_wins(self, service: BankVerificationService) -> None:
        """When multiple aliases are present, the first one in the mapping
        (postal_account) wins. This is load-bearing — re-ordering the
        possible_keys list would change which value is treated as
        authoritative."""
        app = _app(
            form_data={
                "fields": {
                    "bank_account": {"value": "BBBBBBBBBBBBBB"},
                    "postal_account": {"value": "AAAAAAAAAAAAAA"},
                    "帳號": {"value": "CCCCCCCCCCCCCC"},
                }
            },
            student_data={"std_cname": "王小明"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result["account_number"] == "AAAAAAAAAAAAAA"

    def test_empty_string_value_skipped(self, service: BankVerificationService) -> None:
        """If the first alias has an empty string, fall through to the next
        non-empty alias. This is the documented `.get("value")` truthiness
        check."""
        app = _app(
            form_data={
                "fields": {
                    "postal_account": {"value": ""},
                    "bank_account": {"value": "99988877766655"},
                }
            },
            student_data={"std_cname": "王小明"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result["account_number"] == "99988877766655"

    def test_value_coerced_to_string(self, service: BankVerificationService) -> None:
        """If the form serialised the value as a number, the extractor coerces
        to str. Important: account numbers are stored as strings in the
        verification pipeline."""
        app = _app(
            form_data={"fields": {"postal_account": {"value": 12345678901234}}},
            student_data={"std_cname": "王小明"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result["account_number"] == "12345678901234"
        assert isinstance(result["account_number"], str)


# ---------------------------------------------------------------------------
# Field aliasing — account_holder with std_cname fallback
# ---------------------------------------------------------------------------


class TestAccountHolderFallback:
    """The form-data value wins; std_cname is the documented fallback when
    the form didn't capture a holder name."""

    def test_form_value_wins_over_student_data(self, service: BankVerificationService) -> None:
        app = _app(
            form_data={"fields": {"account_holder": {"value": "李大華"}}},
            student_data={"std_cname": "王小明"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result["account_holder"] == "李大華"

    def test_std_cname_fallback_when_form_missing(self, service: BankVerificationService) -> None:
        """When the form has no holder field at all, fall back to std_cname."""
        app = _app(
            form_data={"fields": {"postal_account": {"value": "12345678901234"}}},
            student_data={"std_cname": "王小明"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result["account_holder"] == "王小明"

    def test_std_cname_fallback_when_form_value_empty(self, service: BankVerificationService) -> None:
        """When the form has the field but value is empty, fall back to
        std_cname (the field-alias loop drops empty values via `.get('value')`
        truthiness, then the post-loop fallback kicks in)."""
        app = _app(
            form_data={"fields": {"account_holder": {"value": ""}}},
            student_data={"std_cname": "王小明"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result["account_holder"] == "王小明"

    def test_no_holder_anywhere_returns_no_holder_key(self, service: BankVerificationService) -> None:
        """If the form has no holder, and student_data has no std_cname
        either, the key is simply absent — NOT set to None or empty string.
        Downstream callers `.get("account_holder", "")` for safety."""
        app = _app(
            form_data={"fields": {"postal_account": {"value": "12345678901234"}}},
            student_data={},
        )
        result = service.extract_bank_fields_from_application(app)
        assert "account_holder" not in result

    def test_no_holder_anywhere_no_student_data(self, service: BankVerificationService) -> None:
        """student_data being None entirely should not raise."""
        app = _app(
            form_data={"fields": {"postal_account": {"value": "12345678901234"}}},
            student_data=None,
        )
        result = service.extract_bank_fields_from_application(app)
        assert "account_holder" not in result
        assert result["account_number"] == "12345678901234"

    def test_chinese_alias_for_holder(self, service: BankVerificationService) -> None:
        app = _app(
            form_data={"fields": {"戶名": {"value": "李大華"}}},
            student_data={"std_cname": "王小明"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result["account_holder"] == "李大華"


# ---------------------------------------------------------------------------
# Realistic combined cases
# ---------------------------------------------------------------------------


class TestRealisticInputs:
    def test_typical_student_submission(self, service: BankVerificationService) -> None:
        """A normal student-submitted form with the default English
        field names + a student_data snapshot."""
        app = _app(
            form_data={
                "fields": {
                    "postal_account": {"value": "0001234-5678901-2"},
                    "account_holder": {"value": "王小明"},
                }
            },
            student_data={"std_cname": "王小明", "std_pid": "[REDACTED]"},
        )
        result = service.extract_bank_fields_from_application(app)
        assert result == {
            "account_number": "0001234-5678901-2",
            "account_holder": "王小明",
        }

    def test_admin_renamed_form_fields_to_chinese(self, service: BankVerificationService) -> None:
        """Scholarship admin configured the form with Chinese field names —
        the extractor still finds them via the alias table."""
        app = _app(
            form_data={
                "fields": {
                    "郵局帳號": {"value": "12345678901234"},
                    "戶名": {"value": "王小明"},
                }
            },
            student_data={"std_cname": "李大華"},
        )
        result = service.extract_bank_fields_from_application(app)
        # Form value wins; not student_data
        assert result["account_holder"] == "王小明"
        assert result["account_number"] == "12345678901234"
