"""
Pure-function tests for `batch_import_service` module-level helpers.

These run without DB or pandas DataFrame setup. They pin the cell-value
normalizers that gate every Excel-import row — a regression here would
silently mis-parse student NYCU IDs (turning "310460031" stored as
float 310460031.0 by openpyxl into "310460031.0" downstream, breaking
the SIS lookup).

Helpers covered:
- `_normalize_identifier(value)`: required-field normalization;
  empty becomes "".
- `_normalize_optional(value)`: optional-field normalization;
  empty becomes None.
- `_parse_renewal_year(value)`: renewal-year detection from
  Excel cell, returning (is_renewal, year_or_None).

11 cases — covers each helper across None/NaN/integer-float/string-int/
plain-string inputs plus the renewal-year parser's failure mode.
"""

import math

import pandas as pd
import pytest

from app.services.batch_import_service import (
    _normalize_identifier,
    _normalize_optional,
    _parse_renewal_year,
)

# ─── _normalize_identifier ──────────────────────────────────────────


def test_normalize_identifier_none_returns_empty_string():
    """None ⇒ '' (required-field semantics: caller checks emptiness)."""
    assert _normalize_identifier(None) == ""


def test_normalize_identifier_nan_returns_empty_string():
    """pandas reads empty Excel cells as float('nan'); must normalize to ''."""
    assert _normalize_identifier(float("nan")) == ""


def test_normalize_identifier_integer_float_loses_decimal():
    """openpyxl reads numeric cells as floats. 310460031.0 → '310460031'.

    This is THE regression risk for this helper: leaving the '.0' suffix
    would break SIS lookups that key on the string.
    """
    assert _normalize_identifier(310460031.0) == "310460031"


def test_normalize_identifier_non_integer_float_preserved(monkeypatch):
    """Non-integer floats keep their full string repr (not used for IDs,
    but the function shouldn't truncate them silently)."""
    assert _normalize_identifier(3.14) == "3.14"


def test_normalize_identifier_strips_whitespace():
    assert _normalize_identifier("  s123  ") == "s123"


# ─── _normalize_optional ────────────────────────────────────────────


def test_normalize_optional_none_returns_none():
    """Optional-field semantics: None passes through (not '')."""
    assert _normalize_optional(None) is None


def test_normalize_optional_nan_returns_none():
    """NaN from empty Excel cell ⇒ None."""
    assert _normalize_optional(float("nan")) is None


def test_normalize_optional_empty_string_returns_none():
    """Whitespace-only or empty input becomes None (the 'or None' guard)."""
    assert _normalize_optional("") is None
    assert _normalize_optional("   ") is None


def test_normalize_optional_strips_and_returns_string():
    assert _normalize_optional("  hello  ") == "hello"


def test_normalize_optional_integer_float_loses_decimal():
    """Same regression-protection as _normalize_identifier — integer
    floats from openpyxl don't keep their '.0'."""
    assert _normalize_optional(2025.0) == "2025"


# ─── _parse_renewal_year ────────────────────────────────────────────


def test_parse_renewal_year_with_valid_int_returns_renewal_true():
    """Any parseable int ⇒ (True, year)."""
    is_renewal, year = _parse_renewal_year(2024)
    assert is_renewal is True
    assert year == 2024


def test_parse_renewal_year_from_string_int():
    """String '2024' parses cleanly."""
    is_renewal, year = _parse_renewal_year("2024")
    assert is_renewal is True
    assert year == 2024


def test_parse_renewal_year_with_integer_float():
    """Excel-typical: '2024.0' → (True, 2024)."""
    is_renewal, year = _parse_renewal_year(2024.0)
    assert is_renewal is True
    assert year == 2024


def test_parse_renewal_year_none_returns_not_renewal():
    is_renewal, year = _parse_renewal_year(None)
    assert is_renewal is False
    assert year is None


def test_parse_renewal_year_empty_string_returns_not_renewal():
    is_renewal, year = _parse_renewal_year("")
    assert is_renewal is False
    assert year is None


def test_parse_renewal_year_non_numeric_returns_not_renewal():
    """Garbage input (typo, accidental text) silently degrades to 'not
    a renewal' — the parsing ValueError is swallowed by design."""
    is_renewal, year = _parse_renewal_year("not-a-year")
    assert is_renewal is False
    assert year is None
