"""The 指導教授評語 page of the per-student 申請資料合併檔.

One A4 page (more if comments run long) listing the professor's verdict and
comment per sub-type, with the same 推薦 / 不推薦 / 未審核 / — wording as the
學生資料彙整表 columns (both read one professor_review_export.ProfessorReviewData).
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Sequence

# Pure string-escaping helper for reportlab Paragraph markup — no XML parsing.
from xml.sax.saxutils import escape as xml_escape  # nosec B406

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.pdf_fonts import CJK_FONT_NAME, ensure_cjk_font
from app.services.professor_review_export import (
    DEFAULT_SUB_TYPE_LABEL,
    ProfessorReviewData,
    ProfessorReviewEntry,
    recommendation_label,
    sub_type_display_name,
)
from app.utils.date_utils import to_taipei_str

PROFESSOR_REVIEW_PDF_LABEL = "指導教授評語"

_TABLE_HEADERS = ["申請類別", "審核結果", "評語", "審核教授", "審核時間"]
# A4 portrait minus 15 mm margins = 180 mm; the comment column takes the slack.
_COL_WIDTHS = [30 * mm, 20 * mm, 75 * mm, 25 * mm, 30 * mm]
_MARGIN = 15 * mm


def _rows(application: Any, review: ProfessorReviewData, sub_type_labels: Dict[str, str]) -> List[List[str]]:
    """One row per professor verdict, plus a 未審核/— row per sub-type nobody
    reviewed. review.sub_types already covers every code a verdict carries."""

    def _label(code: str) -> str:
        return sub_type_display_name(code, sub_type_labels) or DEFAULT_SUB_TYPE_LABEL

    def _entry_row(e: ProfessorReviewEntry) -> List[str]:
        reviewed_at = to_taipei_str(e.reviewed_at) if e.reviewed_at else ""
        return [
            _label(e.sub_type_code),
            recommendation_label(e.recommendation),
            e.comments or "",
            e.reviewer_name or "",
            reviewed_at,
        ]

    entries = review.entries(application)
    rows: List[List[str]] = []
    for code in review.sub_types:
        matching = [e for e in entries if e.sub_type_code == code]
        if matching:
            rows.extend(_entry_row(e) for e in matching)
        else:
            rows.append([_label(code), review.missing_label(application, code), "", "", ""])
    return rows


def build_professor_review_pdf(
    *,
    subtitle_lines: Sequence[str],
    application: Any,
    review: ProfessorReviewData,
    sub_type_labels: Dict[str, str],
) -> bytes:
    """Render the 指導教授評語 PDF for one application."""
    ensure_cjk_font()
    s_title = ParagraphStyle("ProfReviewTitle", fontName=CJK_FONT_NAME, fontSize=16, leading=20, alignment=1)
    s_sub = ParagraphStyle(
        "ProfReviewSub",
        fontName=CJK_FONT_NAME,
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=colors.Color(0.4, 0.4, 0.4),
    )
    s_cell = ParagraphStyle("ProfReviewCell", fontName=CJK_FONT_NAME, fontSize=9.5, leading=13, wordWrap="CJK")
    s_head = ParagraphStyle("ProfReviewHead", parent=s_cell, alignment=1)

    data = [[Paragraph(xml_escape(h), s_head) for h in _TABLE_HEADERS]]
    for row in _rows(application, review, sub_type_labels):
        data.append([Paragraph(xml_escape(v).replace("\n", "<br/>"), s_cell) for v in row])

    # splitInRow lets a very long comment continue on the next page instead of
    # raising LayoutError on a row taller than the page.
    table = Table(data, colWidths=_COL_WIDTHS, repeatRows=1, splitInRow=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.94, 0.94, 0.94)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    elements: list = [Paragraph(xml_escape(line), s_sub) for line in subtitle_lines]
    elements += [Spacer(1, 3 * mm), Paragraph(PROFESSOR_REVIEW_PDF_LABEL, s_title), Spacer(1, 6 * mm), table]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=_MARGIN, rightMargin=_MARGIN, topMargin=20 * mm, bottomMargin=20 * mm
    )
    doc.build(elements)
    return buf.getvalue()
