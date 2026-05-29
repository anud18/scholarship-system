"""
Tests for `ExcelExportService._validate_export_data` — the SECURITY-relevant
gate that validates STD_UP_MIXLISTA-format payment Excel data before
write-out.

This validator's `is_valid` flag (and the structured warnings/errors)
determines whether the bank-payment file goes out. A regression here:
- Lets bad rows through (paying students with empty 身分證字號/姓名 — fraud)
- Rejects good rows (delaying valid payments)
- Mis-categorizes "missing bank" as error vs warning (different routing
  downstream)

The method is pure: takes a list of dicts, returns a dict — no DB, no IO.

Wave 6a160.
"""

import pytest

from app.services.excel_export_service import ExcelExportService


@pytest.fixture
def service():
    """Bypass __init__ — _validate_export_data only reads its arg."""
    return ExcelExportService.__new__(ExcelExportService)


def _ok_row(**overrides):
    """A complete, valid STD_UP_MIXLISTA row. Tests override one field
    at a time to exercise each branch."""
    row = {
        "身分證字號": "A123456789",
        "姓名": "王小明",
        "銀行代碼": "012",
        "帳號": "123-456-789",
        "職別(稱)": "學生",
        "是否為學生": "1",
        "給付總額": 10000,
        "扣繳憑單類別": "50",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# 1. Empty input — hard error
# ---------------------------------------------------------------------------


def test_empty_data_is_header_only(service):
    """Pin: empty data list produces a header-only file (is_valid=True, no errors,
    warning present). A zero-qualified roster cycle is valid — it still ships
    a header-only Excel so finance can acknowledge the cycle ran to completion."""
    result = service._validate_export_data([])
    assert result["is_valid"] is True
    assert result["errors"] == []
    assert any("No roster items to export" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# 2. Happy path — fully-valid row
# ---------------------------------------------------------------------------


def test_one_valid_row_is_valid(service):
    """Pin: a single fully-valid row passes all checks."""
    result = service._validate_export_data([_ok_row()])
    assert result["is_valid"] is True
    assert result["errors"] == []
    # bank, amount, format all 0 → no warnings
    assert result["warnings"] == []


def test_valid_row_completion_rate_100(service):
    """Pin: a fully-valid row produces completion_rate == 100.0."""
    result = service._validate_export_data([_ok_row()])
    assert result["statistics"]["completion_rate"] == 100.0


def test_valid_row_is_compliant(service):
    """Pin: a fully-valid row sets std_up_mixlista_compliant=True."""
    result = service._validate_export_data([_ok_row()])
    assert result["statistics"]["std_up_mixlista_compliant"] is True


# ---------------------------------------------------------------------------
# 3. Required-fields gate (身分證字號 / 姓名) — HARD ERROR
# ---------------------------------------------------------------------------


def test_missing_id_number_is_error(service):
    """Pin SECURITY: empty 身分證字號 → is_valid=False. This is the
    primary fraud-prevention gate — never ship a payment row without
    an ID."""
    result = service._validate_export_data([_ok_row(身分證字號="")])
    assert result["is_valid"] is False
    assert any("missing required fields" in e for e in result["errors"])


def test_missing_name_is_error(service):
    """Pin: empty 姓名 → is_valid=False."""
    result = service._validate_export_data([_ok_row(姓名="")])
    assert result["is_valid"] is False


def test_whitespace_only_id_treated_as_missing(service):
    """Pin SECURITY: whitespace-only 身分證字號 is treated as missing
    (uses `.strip() == ""`). Pin so a refactor to `if not row.get(field)`
    only (without strip) doesn't let "   " sneak through as a valid ID."""
    result = service._validate_export_data([_ok_row(身分證字號="   ")])
    assert result["is_valid"] is False


def test_none_id_field_treated_as_missing(service):
    """Pin: explicit None for 身分證字號 → missing."""
    result = service._validate_export_data([_ok_row(身分證字號=None)])
    assert result["is_valid"] is False


def test_compliant_false_when_required_missing(service):
    """Pin: std_up_mixlista_compliant=False when any required field missing."""
    result = service._validate_export_data([_ok_row(身分證字號="")])
    assert result["statistics"]["std_up_mixlista_compliant"] is False


# ---------------------------------------------------------------------------
# 4. Bank-info gate — WARNING (not error)
# ---------------------------------------------------------------------------


def test_missing_bank_code_is_warning_not_error(service):
    """Pin: missing 銀行代碼 → warning, NOT error. Bank ops chase the
    student afterwards; the export still goes out. Pin so a refactor
    promoting bank-missing to an error doesn't block valid payments."""
    result = service._validate_export_data([_ok_row(銀行代碼="")])
    assert result["is_valid"] is True
    assert any("missing bank information" in w for w in result["warnings"])


def test_missing_account_is_warning(service):
    result = service._validate_export_data([_ok_row(帳號="")])
    assert result["is_valid"] is True
    assert any("missing bank information" in w for w in result["warnings"])


def test_missing_bank_lowers_completion_rate(service):
    """Pin: completion_rate = (total - missing_bank) / total * 100.
    Pin the formula so a refactor doesn't accidentally count missing_required
    in completion_rate instead of missing_bank."""
    rows = [_ok_row(), _ok_row(銀行代碼=""), _ok_row(帳號=""), _ok_row()]
    result = service._validate_export_data(rows)
    # 4 total, 2 missing bank → (4-2)/4 * 100 = 50.0
    assert result["statistics"]["completion_rate"] == 50.0
    assert result["statistics"]["missing_bank_info"] == 2


# ---------------------------------------------------------------------------
# 5. Amount validation — WARNING
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_amount", [0, -100, "abc", None])
def test_invalid_amount_is_warning(service, bad_amount):
    """Pin: amount <= 0, non-numeric, or None → invalid_amounts++,
    warning level (not error). Bank ops triages the row manually."""
    result = service._validate_export_data([_ok_row(給付總額=bad_amount)])
    assert result["statistics"]["invalid_amounts"] == 1
    assert any("invalid amounts" in w for w in result["warnings"])


def test_valid_positive_amount_passes(service):
    result = service._validate_export_data([_ok_row(給付總額=5000)])
    assert result["statistics"]["invalid_amounts"] == 0


def test_float_amount_accepted(service):
    """Pin: float amount works (some scholarship configurations carry
    fractional amounts)."""
    result = service._validate_export_data([_ok_row(給付總額=12345.67)])
    assert result["statistics"]["invalid_amounts"] == 0


# ---------------------------------------------------------------------------
# 6. Fixed-value field checks (3 fields)
# ---------------------------------------------------------------------------


def test_wrong_occupation_label_is_invalid_format(service):
    """Pin: 職別(稱) must be exactly '學生'. Anything else increments
    invalid_format. STD_UP_MIXLISTA is a fixed-format upstream file —
    deviations break the bank's parser."""
    result = service._validate_export_data([_ok_row(**{"職別(稱)": "教職員"})])
    assert result["statistics"]["invalid_format"] >= 1


def test_wrong_student_flag_is_invalid_format(service):
    """Pin: 是否為學生 must be exactly '1' (string). Numeric 1 also fails."""
    result = service._validate_export_data([_ok_row(是否為學生="0")])
    assert result["statistics"]["invalid_format"] >= 1


def test_wrong_withholding_code_is_invalid_format(service):
    """Pin: 扣繳憑單類別 must be '50' (string). Any other code routes
    the payment to the wrong tax bucket."""
    result = service._validate_export_data([_ok_row(扣繳憑單類別="9A")])
    assert result["statistics"]["invalid_format"] >= 1


def test_three_format_errors_in_one_row_count_separately(service):
    """Pin: each format-check increments invalid_format independently —
    so the operator can see how many fields are off."""
    bad_row = _ok_row(**{"職別(稱)": "X", "是否為學生": "X", "扣繳憑單類別": "X"})
    result = service._validate_export_data([bad_row])
    assert result["statistics"]["invalid_format"] == 3


def test_invalid_format_marks_not_compliant(service):
    """Pin: std_up_mixlista_compliant=False when invalid_format > 0,
    even if missing_required==0."""
    result = service._validate_export_data([_ok_row(扣繳憑單類別="bad")])
    assert result["statistics"]["std_up_mixlista_compliant"] is False
    # But is_valid stays True (format issues are warnings, not errors)
    assert result["is_valid"] is True


# ---------------------------------------------------------------------------
# 7. Statistics dict shape (downstream consumers depend on keys)
# ---------------------------------------------------------------------------


def test_statistics_has_documented_keys(service):
    """Pin: statistics dict has the 7 documented keys. Pin so a refactor
    dropping a key breaks the dashboard or report that consumes them."""
    result = service._validate_export_data([_ok_row()])
    expected_keys = {
        "total_rows",
        "missing_bank_info",
        "missing_required_info",
        "invalid_amounts",
        "invalid_format",
        "completion_rate",
        "std_up_mixlista_compliant",
    }
    assert set(result["statistics"].keys()) == expected_keys


def test_total_rows_matches_input_length(service):
    rows = [_ok_row(), _ok_row(身分證字號=""), _ok_row(帳號="")]
    result = service._validate_export_data(rows)
    assert result["statistics"]["total_rows"] == 3
