"""
Tests for pure helpers on `ExcelExportService`.

`ExcelExportService` is mostly side-effect heavy (openpyxl Workbook
writes, DB queries via sessionmaker, file I/O for the generated .xlsx).
But four helpers are pure transformations or filesystem-deterministic
operations that can be tested in isolation:

- `_format_allocation_display` — staticmethod, formats `allocated_sub_type`
  + `allocation_year` for the Excel "scholarship type" column. Drives
  what appears in the payment roster operators read.
- `_extract_postal_code` — pure regex extractor for the leading 3-5
  digits of a Taiwan address. Used by every roster export.
- `_get_verification_status_label` — pure enum/string → human label map.
  Misclassifying these would mislabel students as 已驗證 / 已退學 / etc.
- `_calculate_file_hash` — SHA256 hash of file bytes. Used to detect
  whether a regenerated export differs from the previous one.

This PR opens coverage on the last truly-untested backend service per
the audit re-check in PR #231 (excel_export_service.py had 0 tests).

Wave 2h — eighth pure-function test coverage PR.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from types import SimpleNamespace
from typing import Optional

import pytest

from app.services.excel_export_service import ExcelExportService

pytestmark = pytest.mark.smoke


@pytest.fixture
def service() -> ExcelExportService:
    """
    Instantiate the service. `__init__` reads a few template-path config
    values and loads a structure dict — none of the methods under test
    actually need those for their pure-function behavior, so the default
    construction works.
    """
    return ExcelExportService()


# ---------------------------------------------------------------------------
# _format_allocation_display
# ---------------------------------------------------------------------------


def _item(sub_type: Optional[str], year: Optional[int] = None) -> SimpleNamespace:
    """Build a stub PaymentRosterItem with just the two attributes
    `_format_allocation_display` reads."""
    return SimpleNamespace(allocated_sub_type=sub_type, allocation_year=year)


class TestFormatAllocationDisplay:
    """Staticmethod — formats the scholarship-type column in the Excel roster."""

    def test_none_sub_type_returns_empty(self) -> None:
        """No allocated sub-type → blank cell."""
        assert ExcelExportService._format_allocation_display(_item(None)) == ""

    def test_empty_string_sub_type_returns_empty(self) -> None:
        assert ExcelExportService._format_allocation_display(_item("")) == ""

    def test_nstc_with_year(self) -> None:
        result = ExcelExportService._format_allocation_display(_item("nstc", 114))
        assert result == "114年 國科會"

    def test_moe_1w_with_year(self) -> None:
        result = ExcelExportService._format_allocation_display(_item("moe_1w", 113))
        assert result == "113年 教育部(5000)"

    def test_moe_2w_with_year(self) -> None:
        result = ExcelExportService._format_allocation_display(_item("moe_2w", 113))
        assert result == "113年 教育部(2萬)"

    def test_no_year_strips_prefix(self) -> None:
        """Year omitted → just the localised sub-type label."""
        assert ExcelExportService._format_allocation_display(_item("nstc", None)) == "國科會"

    def test_unknown_sub_type_falls_back_to_raw(self) -> None:
        """An unknown / new sub-type (e.g. a custom config-driven addition
        per CLAUDE.md §3) renders as its raw key. Documented behavior."""
        assert ExcelExportService._format_allocation_display(_item("custom_x", None)) == "custom_x"

    def test_unknown_sub_type_with_year(self) -> None:
        result = ExcelExportService._format_allocation_display(_item("custom_x", 115))
        assert result == "115年 custom_x"


# ---------------------------------------------------------------------------
# _extract_postal_code
# ---------------------------------------------------------------------------


class TestExtractPostalCode:
    """Pure regex: leading 3-5 digits of a Taiwan address."""

    def test_none_returns_empty(self, service: ExcelExportService) -> None:
        assert service._extract_postal_code(None) == ""

    def test_empty_string_returns_empty(self, service: ExcelExportService) -> None:
        assert service._extract_postal_code("") == ""

    def test_3_digit_postal(self, service: ExcelExportService) -> None:
        assert service._extract_postal_code("300新竹市東區大學路1001號") == "300"

    def test_5_digit_postal(self, service: ExcelExportService) -> None:
        assert service._extract_postal_code("30010新竹市東區大學路1001號") == "30010"

    def test_4_digit_postal(self, service: ExcelExportService) -> None:
        assert service._extract_postal_code("3001新竹市") == "3001"

    def test_leading_whitespace_stripped(self, service: ExcelExportService) -> None:
        assert service._extract_postal_code("  300 新竹市") == "300"

    def test_no_digits_returns_empty(self, service: ExcelExportService) -> None:
        """Address that doesn't START with digits returns empty — the regex
        is anchored to the beginning."""
        assert service._extract_postal_code("新竹市東區大學路1001號") == ""


# ---------------------------------------------------------------------------
# _get_verification_status_label
# ---------------------------------------------------------------------------


class _MockStatus(Enum):
    verified = "verified"
    graduated = "graduated"
    suspended = "suspended"
    other = "other"


class TestGetVerificationStatusLabel:
    """Pure label lookup. Accepts both enum-with-.value and bare strings."""

    def test_verified_enum(self, service: ExcelExportService) -> None:
        assert service._get_verification_status_label(_MockStatus.verified) == "已驗證"

    def test_graduated_enum(self, service: ExcelExportService) -> None:
        assert service._get_verification_status_label(_MockStatus.graduated) == "已畢業"

    def test_suspended_enum(self, service: ExcelExportService) -> None:
        assert service._get_verification_status_label(_MockStatus.suspended) == "休學中"

    def test_string_input_works(self, service: ExcelExportService) -> None:
        """Bare strings (not enum members) also resolve — useful for legacy
        DB rows that stored raw status text."""
        assert service._get_verification_status_label("withdrawn") == "已退學"
        assert service._get_verification_status_label("api_error") == "驗證錯誤"
        assert service._get_verification_status_label("not_found") == "查無此人"

    def test_unknown_status_returns_raw_value(self, service: ExcelExportService) -> None:
        """An unknown status (enum value or string) falls back to str(status)
        rather than raising — operators see SOMETHING in the cell rather than
        a crash."""
        assert service._get_verification_status_label(_MockStatus.other) == "_MockStatus.other"
        assert service._get_verification_status_label("unknown_state") == "unknown_state"


# ---------------------------------------------------------------------------
# _calculate_file_hash
# ---------------------------------------------------------------------------


class TestCalculateFileHash:
    """SHA256 of file bytes. Used to detect whether a regenerated export
    differs from the previous one. Hash collisions across regenerations
    would falsely report 'no change'."""

    def test_hash_matches_hashlib_sha256(self, service: ExcelExportService, tmp_path) -> None:
        """The returned hex digest must match the standard library SHA256 of
        the same bytes. Don't reinvent the wheel — just verify we're using
        sha256 as documented."""
        payload = b"hello world\n" * 1000  # large enough to span multiple 4KB chunks
        f = tmp_path / "export.xlsx"
        f.write_bytes(payload)
        expected = hashlib.sha256(payload).hexdigest()
        assert service._calculate_file_hash(str(f)) == expected

    def test_empty_file(self, service: ExcelExportService, tmp_path) -> None:
        f = tmp_path / "empty.xlsx"
        f.write_bytes(b"")
        assert service._calculate_file_hash(str(f)) == hashlib.sha256(b"").hexdigest()

    def test_different_content_different_hash(self, service: ExcelExportService, tmp_path) -> None:
        a = tmp_path / "a.xlsx"
        b = tmp_path / "b.xlsx"
        a.write_bytes(b"one")
        b.write_bytes(b"two")
        assert service._calculate_file_hash(str(a)) != service._calculate_file_hash(str(b))

    def test_streaming_chunk_size_64_chars_hex(self, service: ExcelExportService, tmp_path) -> None:
        """SHA256 hex digest is always 64 hex chars regardless of file size.
        Implementation streams in 4KB chunks; this test ensures the chunking
        doesn't truncate the digest."""
        f = tmp_path / "x.xlsx"
        f.write_bytes(b"a" * 10000)  # spans multiple chunks
        digest = service._calculate_file_hash(str(f))
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)
