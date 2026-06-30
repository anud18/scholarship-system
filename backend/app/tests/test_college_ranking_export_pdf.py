"""Tests for the PDF branch of ``CollegeRankingExportService``.

The PDF export must mirror the xlsx 學生資料彙整表 exactly — same columns, same
per-row values (via the shared ``_headers`` / ``_row_cells``) — and produce a
valid A4-landscape PDF that never overflows horizontally (column widths normalise
to the usable page width).
"""

from types import SimpleNamespace

import pytest

from app.services.college_ranking_export_service import (
    STATIC_HEADERS,
    CollegeRankingExportService,
    DynamicFieldSpec,
    ExportRow,
)


@pytest.fixture
def service():
    return CollegeRankingExportService()


@pytest.fixture
def sample_row():
    app = SimpleNamespace(
        student_data={
            "std_cname": "王小明",
            "std_ename": "Wang",
            "std_stdcode": "310460099",
            "std_pid": "A123456789",
            "com_email": "wang@nycu.edu.tw",
            "com_commadd": "新竹市大學路1001號",
            "trm_academyname": "工學院",
            "trm_depname": "資訊工程學系",
            "std_sex": 1,
            "trm_termcount": 3,
            "std_enrolltype": 8,
            "std_nation": "中華民國",
            "std_enrollyear": 112,
            "std_enrollterm": 1,
        },
        submitted_form_data={"fields": {"essay": {"value": "理由 <b>x</b> & y"}}},
        sub_type_preferences=["nstc"],
        sub_scholarship_type=None,
    )
    return ExportRow(rank_position=1, application=app, bank_account="0001234567", advisor_names="陳教授")


@pytest.fixture
def dynamic_fields():
    return [DynamicFieldSpec(field_name="essay", field_label="得獎理由", export_column_label=None, display_order=1)]


# ─── build_pdf ───────────────────────────────────────────────────────


def test_build_pdf_returns_pdf_bytes(service, sample_row, dynamic_fields):
    out = service.build_pdf(
        rows=[sample_row],
        dynamic_fields=dynamic_fields,
        sub_type_labels={"nstc": "國科會"},
        title="114學年度測試獎學金學生資料彙整表",
    )
    assert out[:5] == b"%PDF-", "must be a real PDF"
    assert len(out) > 1000


def test_build_pdf_empty_rows_still_valid(service):
    """No applicants ⇒ a header-only PDF, not a crash."""
    out = service.build_pdf(rows=[], dynamic_fields=[], sub_type_labels={}, title="空表")
    assert out[:5] == b"%PDF-"


def test_build_pdf_handles_xml_special_chars(service, sample_row, dynamic_fields):
    """Values containing &, <, > must not break reportlab Paragraph markup."""
    out = service.build_pdf(
        rows=[sample_row],
        dynamic_fields=dynamic_fields,
        sub_type_labels={"nstc": "國科會"},
        title="<title> & more",
    )
    assert out[:5] == b"%PDF-"


def test_build_pdf_very_long_cell_does_not_overflow(service, dynamic_fields):
    """A single cell taller than the page must NOT raise LayoutError / 500.

    A reportlab Table cannot split one row across pages; KeepInFrame(mode='shrink')
    must keep an extremely long free-text value within the page so the export still
    succeeds.
    """
    huge = SimpleNamespace(
        student_data={"std_cname": "長文測試", "std_stdcode": "310460900"},
        submitted_form_data={"fields": {"essay": {"value": "長" * 4000}}},  # ~4000 CJK chars
        sub_type_preferences=["nstc"],
        sub_scholarship_type=None,
    )
    out = service.build_pdf(
        rows=[ExportRow(rank_position=1, application=huge)],
        dynamic_fields=dynamic_fields,
        sub_type_labels={"nstc": "國科會"},
        title="長文測試",
    )
    assert out[:5] == b"%PDF-"


def test_build_pdf_none_student_data(service, dynamic_fields):
    """A draft-like row (student_data is None) renders all-empty cells, not a crash."""
    blank = SimpleNamespace(
        student_data=None, submitted_form_data=None, sub_type_preferences=None, sub_scholarship_type=None
    )
    out = service.build_pdf(
        rows=[ExportRow(rank_position=None, application=blank)],
        dynamic_fields=dynamic_fields,
        sub_type_labels={},
        title="空資料",
    )
    assert out[:5] == b"%PDF-"


# ─── shared column model (xlsx/pdf parity) ───────────────────────────


def test_headers_static_plus_dynamic(service, dynamic_fields):
    headers = service._headers(service._sort_dynamic(dynamic_fields))
    assert headers[: len(STATIC_HEADERS)] == STATIC_HEADERS
    assert headers[-1] == "得獎理由"  # dynamic label appended


def test_row_cells_length_and_no_and_rank(service, sample_row, dynamic_fields):
    sorted_dynamic = service._sort_dynamic(dynamic_fields)
    cells = service._row_cells(sample_row, 7, {"nstc": "國科會"}, sorted_dynamic)
    assert len(cells) == len(STATIC_HEADERS) + len(dynamic_fields)
    assert cells[0] == 7  # NO. = row index
    assert cells[1] == 1  # rank_position filled
    assert cells[-1] == "理由 <b>x</b> & y"  # raw dynamic value (escaping happens at render)


def test_row_cells_blank_rank_when_none(service, sample_row):
    blank = ExportRow(rank_position=None, application=sample_row.application)
    cells = service._row_cells(blank, 1, {"nstc": "國科會"}, [])
    assert cells[1] == ""  # template/blank rank renders empty


# ─── column-width normalisation (no horizontal overflow) ─────────────


def test_pdf_col_widths_sum_to_usable_width(service, dynamic_fields):
    headers = service._headers(service._sort_dynamic(dynamic_fields))
    usable = 785.0
    widths = service._pdf_col_widths(headers, usable)
    assert len(widths) == len(headers)
    assert sum(widths) == pytest.approx(usable)
    assert all(w > 0 for w in widths)
