"""
Tests for `WhitelistExcelService.parse_import_excel`.

This parser is the boundary between admin-uploaded Excel files and the
scholarship-whitelist DB. A bug here either silently drops legitimate
entries (legitimate students miss out) or admits malformed/duplicate
entries that confuse downstream allocation.

Bugs cause:
- Bad headers accepted → row indexing wrong → all data shifts and the
  wrong students get whitelisted
- Empty rows not skipped → 'row N is empty' errors in the admin UI
- Duplicate (nycu_id, sub_type) not detected → allocator double-counts
- Invalid sub_type not rejected → eligibility checks pass silently and
  the bad whitelist entry persists in DB

Pure function over Excel bytes; uses openpyxl to construct in-memory
test fixtures. No DB.
"""

import io

import pytest
from openpyxl import Workbook

from app.services.whitelist_excel_service import WhitelistExcelService


def _build_excel(rows: list[list]) -> bytes:
    """Build an in-memory Excel file from a list of row lists.
    Row 0 is the header; rows[1:] are data rows."""
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def service() -> WhitelistExcelService:
    return WhitelistExcelService()


@pytest.fixture
def valid_sub_types() -> list[str]:
    return ["nstc", "moe_1w", "moe_2w"]


# ─── Header validation ───────────────────────────────────────────────


def test_missing_required_headers_returns_error(service, valid_sub_types):
    """Pin: header row missing '學號' AND '子獎學金類型' → single error
    'Excel 格式錯誤'. The parser short-circuits before processing data."""
    bad_excel = _build_excel(
        [
            ["A", "B", "C"],  # No required headers
            ["0856001", "王小明", "nstc"],
        ]
    )
    success, errors = service.parse_import_excel(bad_excel, valid_sub_types)
    assert success == []
    assert len(errors) == 1
    assert errors[0]["row"] == "1"
    assert "Excel 格式錯誤" in errors[0]["error"]


def test_only_one_required_header_accepted(service, valid_sub_types):
    """Pin: as long as ONE of '學號' or '子獎學金類型' is present, parsing
    continues (defensive against partial header rows). The OTHER missing
    header causes per-row failures, not a global format error."""
    excel = _build_excel(
        [
            ["學號"],  # only one of two required headers
            ["0856001"],
        ]
    )
    # Doesn't short-circuit; data row will fail validation on missing sub_type
    success, errors = service.parse_import_excel(excel, valid_sub_types)
    assert success == []
    # Row 2 fails because sub_type column doesn't exist
    assert any("子獎學金類型" in e["error"] for e in errors)


# ─── Happy path ──────────────────────────────────────────────────────


def test_valid_full_excel_all_rows_succeed(service, valid_sub_types):
    """Standard import: 3 valid rows → 3 success entries, 0 errors."""
    excel = _build_excel(
        [
            ["學號", "姓名", "子獎學金類型", "備註"],
            ["0856001", "王小明", "nstc", "推薦"],
            ["0856002", "李大華", "moe_1w", ""],
            ["0856003", "張三", "moe_2w", "備取"],
        ]
    )
    success, errors = service.parse_import_excel(excel, valid_sub_types)
    assert len(success) == 3
    assert errors == []
    assert success[0] == {"nycu_id": "0856001", "name": "王小明", "sub_type": "nstc", "note": "推薦"}


def test_optional_columns_default_empty_string(service, valid_sub_types):
    """Pin: 姓名 and 備註 are optional. Missing values default to ''
    (not None) — downstream code expects a string."""
    excel = _build_excel(
        [
            ["學號", "子獎學金類型"],
            ["0856001", "nstc"],
        ]
    )
    success, _errors = service.parse_import_excel(excel, valid_sub_types)
    assert success[0]["name"] == ""
    assert success[0]["note"] == ""


# ─── Per-row validation ──────────────────────────────────────────────


def test_empty_nycu_id_row_rejected(service, valid_sub_types):
    """Pin: empty 學號 → row error '學號不能為空'."""
    excel = _build_excel(
        [
            ["學號", "子獎學金類型"],
            ["", "nstc"],
        ]
    )
    success, errors = service.parse_import_excel(excel, valid_sub_types)
    assert success == []
    assert any("學號不能為空" in e["error"] for e in errors)


def test_empty_sub_type_row_rejected(service, valid_sub_types):
    excel = _build_excel(
        [
            ["學號", "子獎學金類型"],
            ["0856001", ""],
        ]
    )
    success, errors = service.parse_import_excel(excel, valid_sub_types)
    assert success == []
    assert any("子獎學金類型不能為空" in e["error"] for e in errors)
    # Pin: nycu_id is preserved in the error entry for UI highlighting
    assert any(e["nycu_id"] == "0856001" for e in errors)


def test_invalid_sub_type_row_rejected(service, valid_sub_types):
    """Pin: sub_type not in valid_sub_types → row error WITH the list
    of valid values (admin needs this hint to fix their CSV)."""
    excel = _build_excel(
        [
            ["學號", "子獎學金類型"],
            ["0856001", "garbage_subtype"],
        ]
    )
    success, errors = service.parse_import_excel(excel, valid_sub_types)
    assert success == []
    assert len(errors) == 1
    assert "無效的子獎學金類型" in errors[0]["error"]
    assert "garbage_subtype" in errors[0]["error"]
    # The valid options are listed in the error message
    assert "nstc" in errors[0]["error"]


# ─── Duplicate detection ─────────────────────────────────────────────


def test_duplicate_nycu_id_subtype_combo_rejected(service, valid_sub_types):
    """CRITICAL: same (nycu_id, sub_type) twice → second instance
    rejected. Without this, the allocator double-counts the student
    against the sub-type quota."""
    excel = _build_excel(
        [
            ["學號", "子獎學金類型"],
            ["0856001", "nstc"],
            ["0856001", "nstc"],  # duplicate
        ]
    )
    success, errors = service.parse_import_excel(excel, valid_sub_types)
    assert len(success) == 1  # first instance only
    assert len(errors) == 1
    assert "重複" in errors[0]["error"]


def test_same_nycu_id_different_subtype_accepted(service, valid_sub_types):
    """Pin: same student in TWO different sub-types is OK (the dedup
    key is the combo, not just nycu_id). A student can be eligible for
    both NSTC and MOE-1w simultaneously."""
    excel = _build_excel(
        [
            ["學號", "子獎學金類型"],
            ["0856001", "nstc"],
            ["0856001", "moe_1w"],
        ]
    )
    success, errors = service.parse_import_excel(excel, valid_sub_types)
    assert len(success) == 2
    assert errors == []


# ─── Whitespace + empty rows ─────────────────────────────────────────


def test_completely_empty_rows_skipped_silently(service, valid_sub_types):
    """Pin: rows where all cells are None or '' → SKIPPED (no error
    entry, no success entry). Defensive against trailing blank rows
    in admin-pasted Excel files."""
    excel = _build_excel(
        [
            ["學號", "子獎學金類型"],
            ["0856001", "nstc"],
            [None, None],  # completely empty
            ["", ""],  # whitespace-empty
            ["0856002", "moe_1w"],
        ]
    )
    success, errors = service.parse_import_excel(excel, valid_sub_types)
    assert len(success) == 2
    assert errors == []  # empty rows not counted as errors


def test_surrounding_whitespace_stripped_from_values(service, valid_sub_types):
    """Pin: cells are .strip()'d before validation. Defends against
    admin paste-with-trailing-spaces from formatted documents."""
    excel = _build_excel(
        [
            ["學號", "子獎學金類型"],
            ["  0856001  ", "  nstc  "],
        ]
    )
    success, _ = service.parse_import_excel(excel, valid_sub_types)
    assert len(success) == 1
    assert success[0]["nycu_id"] == "0856001"
    assert success[0]["sub_type"] == "nstc"
