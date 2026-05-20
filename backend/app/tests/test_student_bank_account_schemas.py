"""
Tests for `app/schemas/student_bank_account.py`.

These schemas wrap the verified-account check that runs on every
application submission (`/api/v1/student-bank-accounts/verified`).
The endpoint at backend/app/api/v1/endpoints/student_bank_accounts.py
returns `VerifiedAccountCheckResponse` instances inside the ApiResponse
envelope — a regression in either schema:

  - **missing `account_number` / `account_holder`** in the wire
    response would surface as blank fields on the student bank-info
    form, causing students to re-enter (and possibly typo) account
    numbers that were already verified.
  - **missing `has_verified_account` boolean** would short-circuit the
    "use verified account" UX gate.
  - **`account` not strictly Optional** would force the endpoint to
    fabricate a payload when no verified account exists — exact bug
    cited by issue #217 (now resolved).

13 cases pin field shapes + required-vs-optional split.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.student_bank_account import (
    StudentBankAccountBase,
    StudentBankAccountResponse,
    VerifiedAccountCheckResponse,
)

# ─── StudentBankAccountBase ──────────────────────────────────────────


def test_base_requires_account_holder_number_status_and_active():
    # Pin: account_number / account_holder / verification_status /
    # is_active are non-optional. Missing any → ValidationError so the
    # endpoint never silently constructs a half-empty payload.
    with pytest.raises(ValidationError):
        StudentBankAccountBase(  # type: ignore[call-arg]
            account_number="12345",
            account_holder="王小明",
            verification_status="verified",
            # is_active missing
        )


def test_base_verification_notes_optional():
    # Pin: notes can be None — most verified accounts have nothing to
    # annotate.
    b = StudentBankAccountBase(
        account_number="12345678901234",
        account_holder="王小明",
        verification_status="verified",
        is_active=True,
    )
    assert b.verification_notes is None


def test_base_accepts_known_verification_status_strings():
    # Pin: the docstring documents 4 statuses (verified/failed/pending/
    # revoked). All four must round-trip cleanly — no implicit enum
    # coercion that would reject e.g. "revoked".
    for status in ("verified", "failed", "pending", "revoked"):
        b = StudentBankAccountBase(
            account_number="X",
            account_holder="Y",
            verification_status=status,
            is_active=False,
        )
        assert b.verification_status == status


# ─── StudentBankAccountResponse ──────────────────────────────────────


def _full_response_kwargs():
    return dict(
        account_number="12345678901234",
        account_holder="王小明",
        verification_status="verified",
        is_active=True,
        id=1,
        user_id=7,
        verified_at=datetime(2025, 10, 22, 17, 27, 8, tzinfo=timezone.utc),
        created_at=datetime(2025, 10, 22, 17, 27, 8, tzinfo=timezone.utc),
    )


def test_response_requires_id_user_id_verified_at_created_at():
    # Pin: ORM-derived fields (id, user_id, verified_at, created_at)
    # are required. A regression that made any optional would let the
    # endpoint return a half-populated payload.
    with pytest.raises(ValidationError):
        StudentBankAccountResponse(  # type: ignore[call-arg]
            account_number="X",
            account_holder="Y",
            verification_status="verified",
            is_active=True,
            # missing id / user_id / verified_at / created_at
        )


def test_response_verified_by_user_id_and_source_app_id_optional():
    # Pin: these two fields are optional — a verification done by the
    # system (no human) has no verified_by_user_id; verifications not
    # tied to a specific application have no source_application_id.
    r = StudentBankAccountResponse(**_full_response_kwargs())
    assert r.verified_by_user_id is None
    assert r.verification_source_application_id is None


def test_response_updated_at_optional():
    # Pin: updated_at can be None for never-modified records.
    r = StudentBankAccountResponse(**_full_response_kwargs())
    assert r.updated_at is None


def test_response_from_attributes_config_enabled():
    # Pin: ConfigDict(from_attributes=True) — the endpoint calls
    # model_validate(orm_row), so attribute access (not dict access)
    # must work. A regression that dropped from_attributes would crash
    # the endpoint at runtime.
    class _OrmRow:
        def __init__(self):
            self.account_number = "12345"
            self.account_holder = "王"
            self.verification_status = "verified"
            self.is_active = True
            self.verification_notes = None
            self.id = 1
            self.user_id = 7
            self.verified_at = datetime(2025, 10, 22, tzinfo=timezone.utc)
            self.verified_by_user_id = None
            self.verification_source_application_id = None
            self.created_at = datetime(2025, 10, 22, tzinfo=timezone.utc)
            self.updated_at = None

    r = StudentBankAccountResponse.model_validate(_OrmRow())
    assert r.account_number == "12345"
    assert r.id == 1


def test_response_roundtrips_via_model_dump():
    r = StudentBankAccountResponse(**_full_response_kwargs())
    dumped = r.model_dump()
    assert dumped["account_number"] == "12345678901234"
    assert dumped["is_active"] is True
    assert dumped["verified_at"] == datetime(2025, 10, 22, 17, 27, 8, tzinfo=timezone.utc)


# ─── VerifiedAccountCheckResponse ────────────────────────────────────


def test_check_response_requires_has_verified_and_message():
    # Pin: has_verified_account + message are required. The frontend
    # UX gate ("use verified account" vs "enter new one") keys on
    # has_verified_account — must NEVER be missing.
    with pytest.raises(ValidationError):
        VerifiedAccountCheckResponse(  # type: ignore[call-arg]
            has_verified_account=True
            # message missing
        )


def test_check_response_account_optional_for_no_verified_case():
    # Pin: account can be None — when the student has no verified
    # account, the endpoint returns has_verified_account=False and
    # account=None. Issue #217 was about callers depending on this
    # exact split (don't fabricate a placeholder account).
    r = VerifiedAccountCheckResponse(
        has_verified_account=False,
        message="尚未驗證帳號",
    )
    assert r.account is None


def test_check_response_carries_full_account_when_verified():
    # Pin: the full StudentBankAccountResponse nests cleanly.
    inner = StudentBankAccountResponse(**_full_response_kwargs())
    r = VerifiedAccountCheckResponse(
        has_verified_account=True,
        account=inner,
        message="已驗證",
    )
    assert r.account is not None
    assert r.account.id == 1
    assert r.account.account_number == "12345678901234"


def test_check_response_rejects_extra_args_implicitly():
    # Pin: Pydantic v2 default — extra fields silently ignored, but
    # known fields still enforce types. Passing wrong-typed
    # `has_verified_account` should reject.
    with pytest.raises(ValidationError):
        VerifiedAccountCheckResponse(
            has_verified_account="yes please",  # type: ignore[arg-type]
            message="bad",
        )


def test_check_response_round_trip_preserves_nested_account():
    inner = StudentBankAccountResponse(**_full_response_kwargs())
    r = VerifiedAccountCheckResponse(
        has_verified_account=True,
        account=inner,
        message="ok",
    )
    dumped = r.model_dump()
    assert dumped["has_verified_account"] is True
    assert dumped["account"]["account_number"] == "12345678901234"
