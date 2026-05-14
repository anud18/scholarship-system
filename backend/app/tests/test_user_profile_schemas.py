"""
Tests for `app/schemas/user_profile.py`.

The advisor + bank + privacy schemas are what every student fills out
on the My Profile page (and what professors see when reviewing). The
non-obvious behaviour:

  - **empty-string → None coercion** on `advisor_email`: form inputs
    with the field cleared post empty strings, NOT null. The
    `validate_email` validator at lines 25-38 maps "" → None so the
    DB column doesn't store stray '' values. A regression here would
    surface as students unable to clear advisor email once set.

  - **Email regex validation**: the duplicated raw-string pattern
    `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$`
    is duplicated across BankInfoBase/AdvisorInfoBase/Create/Update.
    All four duplicates must agree — a drift would let one entry
    point accept invalid emails another rejects.

  - **Max-length caps** on advisor_name (100), advisor_nycu_id (20),
    account_number (50), preferred_language (10).

19 cases pinning the 8 schemas in the module.
"""

import pytest
from pydantic import ValidationError

from app.schemas.user_profile import (
    AdvisorInfoBase,
    AdvisorInfoUpdate,
    BankInfoBase,
    BankInfoUpdate,
    UserProfileCreate,
    UserProfileUpdate,
)

# ─── empty-string → None coercion (the validator pattern) ────────────


def test_advisor_email_empty_string_becomes_none_on_advisor_info_base():
    # Pin: '' → None. Allows students to clear the field via the form
    # without DB rejecting the empty string.
    a = AdvisorInfoBase(advisor_email="")
    assert a.advisor_email is None


def test_advisor_email_empty_string_becomes_none_on_create():
    c = UserProfileCreate(advisor_email="")
    assert c.advisor_email is None


def test_advisor_email_empty_string_becomes_none_on_update():
    u = UserProfileUpdate(advisor_email="")
    assert u.advisor_email is None


def test_advisor_email_none_passes_through_unchanged():
    # Pin: None stays None (don't coerce to other falsy value).
    a = AdvisorInfoBase(advisor_email=None)
    assert a.advisor_email is None


# ─── Email regex validation (consistency across 4 entry points) ──────


@pytest.mark.parametrize(
    "schema_cls",
    [AdvisorInfoBase, UserProfileCreate, UserProfileUpdate, AdvisorInfoUpdate],
)
def test_email_regex_rejects_obviously_invalid(schema_cls):
    # Pin: all four entry points share the same regex. Drift would
    # let students enter "not-an-email" on one screen but not another.
    with pytest.raises(ValidationError):
        schema_cls(advisor_email="not-an-email")


@pytest.mark.parametrize(
    "schema_cls",
    [AdvisorInfoBase, UserProfileCreate, UserProfileUpdate, AdvisorInfoUpdate],
)
def test_email_regex_accepts_standard_addresses(schema_cls):
    obj = schema_cls(advisor_email="prof@nycu.edu.tw")
    assert obj.advisor_email == "prof@nycu.edu.tw"


def test_email_regex_rejects_tld_under_two_chars():
    # Pin: `[a-zA-Z]{2,}` — single-char TLDs are rejected (typo
    # protection on "nycu.e" form input).
    with pytest.raises(ValidationError):
        AdvisorInfoBase(advisor_email="prof@nycu.e")


def test_email_regex_rejects_double_at():
    with pytest.raises(ValidationError):
        AdvisorInfoBase(advisor_email="prof@@nycu.edu.tw")


def test_email_regex_rejects_missing_at():
    with pytest.raises(ValidationError):
        AdvisorInfoBase(advisor_email="prof.nycu.edu.tw")


# ─── Length caps (max_length) ───────────────────────────────────────


def test_advisor_info_base_advisor_name_max_100():
    with pytest.raises(ValidationError):
        AdvisorInfoBase(advisor_name="x" * 101)


def test_advisor_info_base_advisor_nycu_id_max_20():
    with pytest.raises(ValidationError):
        AdvisorInfoBase(advisor_nycu_id="x" * 21)


def test_bank_info_base_account_number_max_50():
    with pytest.raises(ValidationError):
        BankInfoBase(account_number="x" * 51)


def test_user_profile_update_preferred_language_max_10():
    # Pin: locale strings are short (zh-TW, en-US). Cap prevents
    # arbitrary text in the field.
    with pytest.raises(ValidationError):
        UserProfileUpdate(preferred_language="x" * 11)


# ─── UserProfileCreate defaults ─────────────────────────────────────


def test_create_preferred_language_defaults_to_zh_tw():
    # Pin: default locale is Traditional Chinese (the system's primary
    # language per CLAUDE.md). A regression flipping to en or "" would
    # silently change UI language for new users.
    c = UserProfileCreate()
    assert c.preferred_language == "zh-TW"


def test_create_optional_fields_all_default_to_none():
    c = UserProfileCreate()
    assert c.account_number is None
    assert c.advisor_name is None
    assert c.advisor_email is None
    assert c.advisor_nycu_id is None
    assert c.privacy_settings is None
    assert c.custom_fields is None


# ─── Update variants ─────────────────────────────────────────────────


def test_user_profile_update_all_optional():
    # Pin: PATCH semantics — empty payload valid.
    u = UserProfileUpdate()
    assert u.account_number is None
    assert u.advisor_name is None
    assert u.preferred_language is None


def test_bank_info_update_carries_change_reason():
    # Pin: bank-info edits MUST optionally carry a change_reason
    # (audit-trail requirement). A regression dropping this field
    # would lose the reason on every bank-info update.
    b = BankInfoUpdate(account_number="12345", change_reason="新帳號")
    assert b.change_reason == "新帳號"


def test_advisor_info_update_inherits_email_validation():
    # Pin: AdvisorInfoUpdate inherits the empty-string coercion from
    # AdvisorInfoBase. A regression that skipped the validator would
    # let students post '' and corrupt the DB.
    a = AdvisorInfoUpdate(advisor_email="", change_reason="cleared")
    assert a.advisor_email is None
    assert a.change_reason == "cleared"
