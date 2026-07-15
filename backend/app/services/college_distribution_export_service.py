"""College distribution-results export service.

Pure rendering logic — receives the ``sub_types`` structure produced by
``load_college_distribution_results`` and returns xlsx or PDF bytes. The endpoint
layer is responsible for loading and authorizing the data.

``build_workbook`` and ``build_pdf`` share one source of truth for the column set
(``_headers``) and per-row cell values (``_row_cells``), so the two formats never
drift apart — the same discipline as ``college_ranking_export_service``.

Unlike the 學生資料彙整表 export this carries NO PII (no 身分證字號, no 匯款帳號):
colleges get exactly what the 分發結果 panel already shows them.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# `escape` is a pure string-escaping helper (`<` → `&lt;` …) used to sanitise
# cell values before they go into reportlab Paragraph markup. It does not parse
# untrusted XML, so the B406 warning is a false positive here.
from xml.sax.saxutils import escape as xml_escape  # nosec B406

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepInFrame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.pdf_fonts import CJK_FONT_NAME, ensure_cjk_font
from app.utils.excel_safety import sanitize_excel_cell

# (header label, PDF column weight). HEADERS and the PDF weight vector are both
# derived from this one list so they can never drift — renaming a label can't
# silently mis-size a column. The normalize-to-page-width math lives in
# _pdf_col_widths.
_COLUMNS: List[Tuple[str, float]] = [
    ("類別", 1.4),
    ("結果", 0.7),
    ("名次", 0.6),
    ("學號", 1.2),
    ("姓名", 1.2),
    ("系所", 1.4),
]

HEADERS: List[str] = [label for label, _ in _COLUMNS]
_COL_WEIGHTS: List[float] = [weight for _, weight in _COLUMNS]

# (group key, 結果 label, position field) — drives both flattening order and the
# per-bucket position column, so 正取/備取/未錄取 ordering is defined in one place.
_OUTCOME_BUCKETS: Tuple[Tuple[str, str, str], ...] = (
    ("admitted", "正取", "rank_position"),
    ("backup", "備取", "backup_position"),
    ("rejected", "未錄取", "rank_position"),
)


@dataclass(frozen=True)
class DistributionExportRow:
    """One student's outcome within one sub-type."""

    sub_type_label: str
    outcome: str  # 正取 / 備取 / 未錄取
    position: Optional[int]
    student_number: str
    student_name: str
    department: str


def flatten_sub_types(sub_types: List[Dict[str, Any]]) -> List[DistributionExportRow]:
    """Flatten the grouped loader payload into export rows.

    Preserves the loader's ordering (it already sorted each bucket), so the export
    reads in the same order as the panel.
    """
    rows: List[DistributionExportRow] = []
    for group in sub_types:
        label = group.get("label") or group.get("code") or ""
        for key, outcome, position_field in _OUTCOME_BUCKETS:
            for student in group.get(key) or []:
                rows.append(
                    DistributionExportRow(
                        sub_type_label=label,
                        outcome=outcome,
                        position=student.get(position_field),
                        student_number=student.get("student_number") or "",
                        student_name=student.get("student_name") or "",
                        department=student.get("department") or "",
                    )
                )
    return rows


class CollegeDistributionExportService:
    """Builds 分發結果 workbooks and PDFs."""

    def build_workbook(self, *, rows: List[DistributionExportRow], title: str, sheet_name: str) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name

        headers = self._headers()
        total_cols = len(headers)

        # Row 1: title (merged across all columns)
        ws.cell(row=1, column=1, value=title)
        if total_cols > 1:
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
        title_cell = ws.cell(row=1, column=1)
        title_cell.font = Font(bold=True, size=14)
        title_cell.alignment = Alignment(horizontal="center", vertical="center")

        # Row 2: header
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=2, column=col_idx, value=header)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.fill = PatternFill("solid", fgColor="DDDDDD")

        # Data rows — written from the same _row_cells used by the PDF export
        for idx, row in enumerate(rows, start=1):
            excel_row = idx + 2  # +2 because rows 1-2 are title/header
            for col_idx, value in enumerate(self._row_cells(row), start=1):
                # SECURITY: neutralize spreadsheet formula injection — openpyxl writes
                # a leading "=" as a LIVE formula and 姓名/系所 come from SIS.
                ws.cell(row=excel_row, column=col_idx, value=sanitize_excel_cell(value))

        max_row = len(rows) + 2
        self._apply_borders(ws, max_row=max_row, max_col=total_cols)
        self._apply_column_widths(ws, headers)
        ws.freeze_panes = "A3"

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def build_pdf(self, *, rows: List[DistributionExportRow], title: str) -> bytes:
        """Render the same 分發結果 table as an A4-landscape PDF.

        Mirrors ``build_workbook`` exactly (same columns, rows and ordering via
        ``_headers`` / ``_row_cells``). Column widths are normalised to the usable
        page width; rows paginate vertically with the header repeated per page.

        ``sanitize_excel_cell`` is deliberately NOT applied here: reportlab has no
        formula semantics, so the apostrophe prefix would be a visible artifact.
        This is the one place the two formats legitimately diverge.
        """
        ensure_cjk_font()

        headers = self._headers()

        page_width, page_height = landscape(A4)
        usable_width = page_width - (self._PDF_MARGIN_PT * 2)
        col_widths = self._pdf_col_widths(headers, usable_width)
        # A reportlab Table cannot split ONE row across pages, so cap each cell to the
        # usable content height and let KeepInFrame shrink anything taller.
        cell_max_height = page_height - (self._PDF_MARGIN_PT * 2) - self._PDF_HEADER_RESERVE_PT

        title_style = ParagraphStyle(
            "DistributionPdfTitle",
            fontName=CJK_FONT_NAME,
            fontSize=12,
            leading=15,
            alignment=1,  # center
        )
        header_style = ParagraphStyle(
            "DistributionPdfHeader",
            fontName=CJK_FONT_NAME,
            fontSize=8,
            leading=10,
            alignment=1,
            wordWrap="CJK",
        )
        cell_style = ParagraphStyle(
            "DistributionPdfCell",
            fontName=CJK_FONT_NAME,
            fontSize=7.5,
            leading=9,
            wordWrap="CJK",  # break long CJK and unspaced ASCII
        )

        data: List[list] = [[Paragraph(xml_escape(h), header_style) for h in headers]]
        for row in rows:
            values = self._row_cells(row)
            data.append(
                [
                    KeepInFrame(
                        col_widths[col],
                        cell_max_height,
                        [Paragraph(xml_escape(self._safe_str(v)), cell_style)],
                        mode="shrink",
                    )
                    for col, v in enumerate(values)
                ]
            )

        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.Color(0.6, 0.6, 0.6)),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.87, 0.87, 0.87)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTNAME", (0, 0), (-1, -1), CJK_FONT_NAME),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            leftMargin=self._PDF_MARGIN_PT,
            rightMargin=self._PDF_MARGIN_PT,
            topMargin=self._PDF_MARGIN_PT,
            bottomMargin=self._PDF_MARGIN_PT,
        )
        doc.build([Paragraph(xml_escape(title), title_style), Spacer(1, 4 * mm), table])
        return buf.getvalue()

    # -------- PDF layout helpers --------

    _PDF_MARGIN_PT = 10 * mm
    # Vertical space reserved (per page) for the title + spacer + repeated header row.
    _PDF_HEADER_RESERVE_PT = 60

    def _pdf_col_widths(self, headers: List[str], usable_width: float) -> List[float]:
        total = sum(_COL_WEIGHTS) or 1.0
        return [usable_width * w / total for w in _COL_WEIGHTS]

    # -------- Shared column/value model (single source of truth) --------

    def _headers(self) -> List[str]:
        return list(HEADERS)

    def _row_cells(self, row: DistributionExportRow) -> List[Any]:
        """Ordered cell values for one row.

        The xlsx writer keeps the native int for 名次 (proper Excel typing); the PDF
        renderer stringifies it. Both share this list so the formats render identical
        content.
        """
        return [
            row.sub_type_label,
            row.outcome,
            row.position if row.position is not None else "",
            row.student_number,
            row.student_name,
            row.department,
        ]

    def _safe_str(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    # -------- Formatting --------

    def _apply_borders(self, ws, *, max_row: int, max_col: int) -> None:
        thin = Side(style="thin", color="999999")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for r in range(2, max_row + 1):
            for c in range(1, max_col + 1):
                ws.cell(row=r, column=c).border = border

    def _apply_column_widths(self, ws, headers: List[str]) -> None:
        for idx, header in enumerate(headers, start=1):
            text_len = max(len(str(header)), 6)
            width = min(max(text_len + 4, 10), 30)
            ws.column_dimensions[get_column_letter(idx)].width = width
