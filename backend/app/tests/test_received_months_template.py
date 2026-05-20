"""
Tests for `backend/scripts/generate_received_months_sample.py`.

Script had ZERO test references. Generates the Excel template
shipped to admins for the "已領月份數 import" feature — drift
in HEADER columns or sample-row schema would silently break
admin uploads (column mismatch when matched by name in
manual_distribution.importReceivedMonths handler).

Wave 6a145 pins HEADER tuple shape, sample-row contract, and
build_workbook() output structure (sheet title, frozen panes,
column widths, header styling) without invoking file IO.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# Import the script as a module (it's outside the package tree).
_SCRIPT_PATH = Path("/app/scripts/generate_received_months_sample.py")
if not _SCRIPT_PATH.exists():
    # Local dev path fallback
    _SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "generate_received_months_sample.py"


@pytest.fixture(scope="module")
def script_module():
    spec = importlib.util.spec_from_file_location("generate_received_months_sample", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["generate_received_months_sample"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestHeaderContract:
    """Pin SECURITY: HEADER columns drive admin import matching.
    Drift would silently mismatch the `已領月份數` column and
    fail import for all rows."""

    def test_header_is_2_columns(self, script_module):
        # Pin: exactly 2 columns. Pin so refactor adding a column
        # without coordinating with the importer breaks loudly.
        assert len(script_module.HEADER) == 2

    def test_header_first_column_is_xuehao(self, script_module):
        # Pin: zh-TW "學號" (student ID) as first column.
        # Pin so refactor doesn't rename to "Student ID" / "stdcode"
        # which would mismatch the importer's column-by-name lookup.
        assert script_module.HEADER[0] == "學號"

    def test_header_second_column_is_received_months(self, script_module):
        # Pin: zh-TW "已領月份數" as second column.
        # Pin so refactor doesn't change to "Received Months" /
        # "month_count" — admin UI explicitly tells users to fill
        # this column.
        assert script_module.HEADER[1] == "已領月份數"


class TestSampleRowsContract:
    """Pin: 5 sample rows showing admins the expected format."""

    def test_five_sample_rows(self, script_module):
        # Pin: exactly 5 examples. Pin so refactor doesn't shrink
        # to 1 (insufficient for admin to understand format).
        assert len(script_module.SAMPLE_ROWS) == 5

    def test_each_sample_row_is_2_tuple(self, script_module):
        # Pin: (student_id, months) tuple shape.
        for row in script_module.SAMPLE_ROWS:
            assert len(row) == 2

    def test_student_ids_are_strings(self, script_module):
        # Pin: student_id is STRING (NCTU IDs may start with 0 / 4).
        # Pin so refactor doesn't change to int (which would drop
        # leading zeros and break the lookup).
        for sid, _ in script_module.SAMPLE_ROWS:
            assert isinstance(sid, str)
            assert sid  # non-empty

    def test_months_are_non_negative_ints(self, script_module):
        # Pin: 已領月份數 is int >= 0. Pin so refactor doesn't
        # accidentally use float (Excel format) and break the
        # subtraction math in distribution calc.
        for _, months in script_module.SAMPLE_ROWS:
            assert isinstance(months, int)
            assert months >= 0

    def test_zero_months_example_present(self, script_module):
        # Pin: at least ONE sample with months=0. Pin so admins
        # see that "0" is a valid value (don't leave empty cells
        # which Excel→openpyxl maps to None and breaks the import).
        months_values = [m for _, m in script_module.SAMPLE_ROWS]
        assert 0 in months_values

    def test_non_trivial_months_examples_present(self, script_module):
        # Pin: variety of non-zero values (12, 18, 24) showing
        # admins the realistic range.
        months_values = [m for _, m in script_module.SAMPLE_ROWS]
        assert any(m >= 12 for m in months_values)
        assert any(m >= 18 for m in months_values)


class TestBuildWorkbook:
    """Pin: build_workbook() output structure."""

    def test_workbook_has_one_sheet_titled_zh_tw(self, script_module):
        # Pin: single sheet titled "已領月份數" (zh-TW). Pin so
        # refactor doesn't switch to English sheet name (admin
        # might select wrong sheet on multi-sheet uploads).
        wb = script_module.build_workbook()
        assert len(wb.sheetnames) == 1
        assert wb.active.title == "已領月份數"

    def test_header_row_is_row_1(self, script_module):
        # Pin: row 1 contains HEADER. Pin so refactor doesn't add
        # a title/comment row above and shift the data row index.
        wb = script_module.build_workbook()
        ws = wb.active
        assert ws.cell(row=1, column=1).value == "學號"
        assert ws.cell(row=1, column=2).value == "已領月份數"

    def test_header_cells_are_bold(self, script_module):
        # Pin: header row uses bold font. Visual cue for admins.
        wb = script_module.build_workbook()
        ws = wb.active
        assert ws.cell(row=1, column=1).font.bold is True
        assert ws.cell(row=1, column=2).font.bold is True

    def test_sample_rows_appear_starting_at_row_2(self, script_module):
        # Pin: row 2 onwards has sample data.
        wb = script_module.build_workbook()
        ws = wb.active
        # First sample row: ("310551005", 12)
        assert ws.cell(row=2, column=1).value == "310551005"
        assert ws.cell(row=2, column=2).value == 12

    def test_freeze_panes_at_a2_keeps_header_visible(self, script_module):
        # Pin: freeze_panes='A2' so header stays visible when
        # admin scrolls. Pin so refactor doesn't remove the
        # freeze and degrade the UX.
        wb = script_module.build_workbook()
        ws = wb.active
        assert ws.freeze_panes == "A2"

    def test_column_widths_set_for_readability(self, script_module):
        # Pin: column A width=16, column B width=14 for legible
        # display of standard student IDs (9 chars) + zh-TW
        # header text.
        wb = script_module.build_workbook()
        ws = wb.active
        assert ws.column_dimensions["A"].width == 16
        assert ws.column_dimensions["B"].width == 14

    def test_all_5_sample_rows_present(self, script_module):
        # Pin: all 5 sample rows materialize in the worksheet
        # (rows 2-6).
        wb = script_module.build_workbook()
        ws = wb.active
        for offset, (sid, months) in enumerate(script_module.SAMPLE_ROWS):
            row_idx = 2 + offset
            assert ws.cell(row=row_idx, column=1).value == sid
            assert ws.cell(row=row_idx, column=2).value == months

    def test_no_row_7_data_leakage(self, script_module):
        # Pin: only 5 sample rows + 1 header = max row 6.
        # Pin so refactor adding more samples gets a deliberate
        # test update.
        wb = script_module.build_workbook()
        ws = wb.active
        assert ws.cell(row=7, column=1).value is None
