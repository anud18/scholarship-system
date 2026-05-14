"""
Tests for `app/schemas/batch_import.py` — the postal_account
validator + length bounds + defaults.

Wave 6a25 covered the SECURITY-critical name-field XSS guard and
student_id alphanumeric validator. This wave covers what 6a25 left:

  - **validate_postal_account**: numbers + hyphens only. Postal
    account format is `12345-67890` or `1234567890`. A regression
    accepting other chars would let admins paste typos into the
    payment file (Finance rejection / re-work loop).

  - **Length bounds**: student_id max=20, student_name max=100,
    postal_account max=20. Drift silently truncates DB rows.

  - **ApplicationDataRow defaults**: sub_types=[], is_renewal=False,
    custom_fields={}.

  - **BatchImportDataRequest.academic_year** Taiwan calendar bounds
    100 ≤ x ≤ 200; data_rows min_length=1 (no empty batches).

  - **BatchImportUpdateRecordRequest.record_index ge=0** (no
    negative indexes into the list).

16 cases.
"""

import pytest
from pydantic import ValidationError

from app.schemas.batch_import import (
    ApplicationDataRow,
    BatchImportDataRequest,
    BatchImportUpdateRecordRequest,
)

# ─── validate_postal_account ────────────────────────────────────────


def test_postal_account_digits_only_accepted():
    # Pin: plain digits common case.
    row = ApplicationDataRow(student_id="A1", student_name="x", postal_account="1234567890")
    assert row.postal_account == "1234567890"


def test_postal_account_with_hyphen_accepted():
    # Pin: hyphen-formatted postal accounts (common at NYCU
    # branch — `12345-67890`).
    row = ApplicationDataRow(student_id="A1", student_name="x", postal_account="12345-67890")
    assert row.postal_account == "12345-67890"


def test_postal_account_alpha_rejected():
    # Pin: letters explicitly rejected (typo guard — admin shouldn't
    # paste "x12345" by accident).
    with pytest.raises(ValidationError):
        ApplicationDataRow(student_id="A1", student_name="x", postal_account="A12345")


def test_postal_account_spaces_rejected():
    with pytest.raises(ValidationError):
        ApplicationDataRow(student_id="A1", student_name="x", postal_account="12345 67890")


def test_postal_account_special_chars_rejected():
    # Pin: explicitly reject @, /, .
    for bad in ("12345@67890", "12345/67890", "12345.67890"):
        with pytest.raises(ValidationError):
            ApplicationDataRow(student_id="A1", student_name="x", postal_account=bad)


def test_postal_account_none_passes_through():
    row = ApplicationDataRow(student_id="A1", student_name="x", postal_account=None)
    assert row.postal_account is None


def test_postal_account_outer_whitespace_stripped():
    # Pin: trim before pattern check.
    row = ApplicationDataRow(student_id="A1", student_name="x", postal_account="  12345  ")
    assert row.postal_account == "12345"


# ─── Length bounds ───────────────────────────────────────────────────


def test_student_id_max_length_20():
    # Pin: 20-char cap. Drift silently truncates DB rows.
    with pytest.raises(ValidationError):
        ApplicationDataRow(student_id="A" * 21, student_name="x")


def test_student_name_max_length_100():
    with pytest.raises(ValidationError):
        ApplicationDataRow(student_id="A1", student_name="王" * 101)


def test_postal_account_max_length_20():
    with pytest.raises(ValidationError):
        ApplicationDataRow(student_id="A1", student_name="x", postal_account="1" * 21)


# ─── ApplicationDataRow defaults ────────────────────────────────────


def test_sub_types_defaults_empty_list():
    # Pin: empty list, not None — endpoint code calls .extend() on
    # this without null-checks.
    row = ApplicationDataRow(student_id="A1", student_name="x")
    assert row.sub_types == []


def test_is_renewal_defaults_false():
    # Pin: most imports are NEW applications. Flipping default to
    # True would silently mark every row as renewal, causing the
    # endpoint to query renewal-only eligibility.
    row = ApplicationDataRow(student_id="A1", student_name="x")
    assert row.is_renewal is False


def test_custom_fields_defaults_empty_dict():
    # Pin: empty dict — frontend .Object.entries() iteration safe.
    row = ApplicationDataRow(student_id="A1", student_name="x")
    assert row.custom_fields == {}


# ─── BatchImportDataRequest bounds ──────────────────────────────────


def _row():
    return ApplicationDataRow(student_id="A1", student_name="x")


def test_batch_request_academic_year_taiwan_calendar_bounds():
    # Pin: 100 ≤ year ≤ 200 (Taiwan calendar, 民國年). Reject 99
    # and 201.
    for bad_year in (99, 201):
        with pytest.raises(ValidationError):
            BatchImportDataRequest(scholarship_type="general", academic_year=bad_year, data_rows=[_row()])


def test_batch_request_data_rows_min_length_1():
    # Pin: at least one row. Empty batches are admin error —
    # reject so we don't create a useless batch record.
    with pytest.raises(ValidationError):
        BatchImportDataRequest(scholarship_type="general", academic_year=113, data_rows=[])


# ─── BatchImportUpdateRecordRequest ─────────────────────────────────


def test_update_record_request_index_rejects_negative():
    # Pin: ge=0 — negative would index from the end of the list
    # (Python list behavior) and silently update the wrong row.
    with pytest.raises(ValidationError):
        BatchImportUpdateRecordRequest(record_index=-1, updates={"x": 1})
