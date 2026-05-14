"""
Tests for the remaining pure helpers on `BankVerificationService`.

Wave 6h covered the validators (postal-format, normalize_account_
number, normalize_text) + exact account-number match. This wave
fills the rest:

  - **calculate_similarity(text1, text2)** — Wraps difflib
    SequenceMatcher with normalization. Two empty strings return
    **1.0** (matched), one empty returns **0.0**.

  - **extract_bank_fields_from_application** — Resolves bank fields
    from the form's nested fields dict via a multi-key lookup
    table (CJK + English keys). Falls back to student_data.std_cname
    for account_holder.

  - **generate_recommendations** — Status-driven recommendation
    builder. Pinned outputs for each (status, account_number_status,
    account_holder_status) combination so a regression that drops
    a label silently breaks the admin verification dashboard.

16 cases. Pure helpers via SimpleNamespace fixtures.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.bank_verification_service import BankVerificationService


@pytest.fixture
def service():
    db = MagicMock()
    return BankVerificationService(db)


# ─── calculate_similarity ────────────────────────────────────────────


def test_similarity_both_empty_is_one(service):
    # Pin: two empty strings considered identical (1.0). Common at
    # the start of verification before form fields are filled.
    assert service.calculate_similarity("", "") == 1.0


def test_similarity_one_empty_is_zero(service):
    # Pin: one empty → 0.0. Pure mismatch.
    assert service.calculate_similarity("", "王小明") == 0.0
    assert service.calculate_similarity("王小明", "") == 0.0


def test_similarity_identical_after_normalize_is_one(service):
    # Pin: case + whitespace + punctuation are stripped by
    # normalize_text first.
    assert service.calculate_similarity("Hello World!", "hello   world") == 1.0


def test_similarity_completely_different_strings_low_value(service):
    sim = service.calculate_similarity("abc", "xyz")
    assert sim < 0.5


def test_similarity_partial_overlap_between_0_and_1(service):
    sim = service.calculate_similarity("王小明", "王大明")
    assert 0.0 < sim < 1.0


def test_similarity_returns_float(service):
    # Pin: return type is float (difflib ratio).
    sim = service.calculate_similarity("a", "a")
    assert isinstance(sim, float)


# ─── extract_bank_fields_from_application ───────────────────────────


def _app(form_fields=None, student_data=None):
    app = SimpleNamespace()
    app.submitted_form_data = {"fields": form_fields or {}} if form_fields is not None else None
    app.student_data = student_data
    return app


def test_extract_returns_empty_when_no_form_data(service):
    # Pin: None form data → empty dict. Endpoint receives {} not None.
    app = SimpleNamespace(submitted_form_data=None, student_data=None)
    assert service.extract_bank_fields_from_application(app) == {}


def test_extract_returns_empty_when_no_fields_key(service):
    app = SimpleNamespace(submitted_form_data={}, student_data=None)
    assert service.extract_bank_fields_from_application(app) == {}


def test_extract_resolves_postal_account_key(service):
    # Pin: "postal_account" is the first alias in the mapping list.
    app = _app(form_fields={"postal_account": {"value": "12345-67890"}})
    out = service.extract_bank_fields_from_application(app)
    assert out["account_number"] == "12345-67890"


def test_extract_resolves_chinese_account_key(service):
    # Pin: "郵局帳號" Chinese alias works. Documented multi-locale
    # support.
    app = _app(form_fields={"郵局帳號": {"value": "98765"}})
    out = service.extract_bank_fields_from_application(app)
    assert out["account_number"] == "98765"


def test_extract_falls_back_to_student_data_cname_when_form_has_other_fields(service):
    # Pin: if form has some fields (passes the early-return guard)
    # but no holder field, fallback to student_data["std_cname"].
    # The OCR-extracted name and SIS name are matched separately
    # to detect typos.
    app = _app(
        form_fields={"postal_account": {"value": "12345"}},
        student_data={"std_cname": "王小明"},
    )
    out = service.extract_bank_fields_from_application(app)
    assert out["account_holder"] == "王小明"


def test_extract_returns_empty_when_fields_dict_empty(service):
    # Pin: empty fields dict triggers the early-return guard
    # (line 122 `not ...get("fields")` is True for `{}`). No
    # fallback runs.
    app = _app(form_fields={}, student_data={"std_cname": "王小明"})
    out = service.extract_bank_fields_from_application(app)
    assert out == {}


def test_extract_form_holder_takes_precedence_over_student_data(service):
    # Pin: form-supplied holder wins over student_data fallback.
    app = _app(
        form_fields={"戶名": {"value": "陳大文"}},
        student_data={"std_cname": "王小明"},
    )
    out = service.extract_bank_fields_from_application(app)
    assert out["account_holder"] == "陳大文"


def test_extract_skips_field_with_empty_value(service):
    # Pin: empty value field is skipped, mapping falls through to
    # the next alias.
    app = _app(form_fields={"postal_account": {"value": ""}, "bank_account": {"value": "OK"}})
    out = service.extract_bank_fields_from_application(app)
    assert out["account_number"] == "OK"


# ─── generate_recommendations ───────────────────────────────────────


def test_recommendations_verified_status_emits_pass_message(service):
    # Pin: "verified" status puts ✅ message at the start.
    recs = service.generate_recommendations(
        status="verified",
        comparisons={},
        account_number_status="verified",
        account_holder_status="verified",
    )
    assert any("✅ 郵局帳號資訊驗證通過" in r for r in recs)
    assert any("✅ 帳號" in r for r in recs)
    assert any("✅ 戶名" in r for r in recs)


def test_recommendations_failed_status_includes_form_vs_ocr_values(service):
    # Pin: failed status surfaces both form_value and ocr_value in
    # the recommendation so admins see the diff inline.
    recs = service.generate_recommendations(
        status="verification_failed",
        comparisons={
            "account_number": {"form_value": "12345", "ocr_value": "67890"},
        },
        account_number_status="failed",
        account_holder_status="verified",
    )
    failed_msg = next((r for r in recs if "❌ 帳號" in r), None)
    assert failed_msg is not None
    assert "12345" in failed_msg
    assert "67890" in failed_msg


def test_recommendations_low_confidence_triggers_warning(service):
    # Pin: any field with low confidence appends the manual-
    # confirmation hint. Used when OCR struggled to read the
    # passbook image.
    recs = service.generate_recommendations(
        status="verified",
        comparisons={
            "account_number": {"confidence": "high"},
            "account_holder": {"confidence": "low"},
        },
        account_number_status="verified",
        account_holder_status="verified",
    )
    assert any("OCR信心度較低" in r for r in recs)


def test_recommendations_likely_verified_emits_review_message(service):
    # Pin: middle-state status surfaces a "review细節" message.
    recs = service.generate_recommendations(
        status="likely_verified",
        comparisons={},
        account_number_status="needs_review",
        account_holder_status="needs_review",
    )
    assert any("⚠️ 郵局帳號資訊基本一致" in r for r in recs)
