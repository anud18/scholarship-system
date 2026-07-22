"""Merge student-uploaded documents into a single PDF.

The college export package ships each student's uploaded files individually
inside the ZIP; reviewers additionally get one PDF per student that stitches
the admin-configured dynamic documents together so they can be read in a
single pass.

Supported inputs mirror ``settings.allowed_file_types``: PDF pages are
appended as-is (owner-password-only encryption is unlocked with the empty
user password); JPEG/PNG images are placed on an A4 page scaled to fit; any
other or unreadable file yields a placeholder page pointing the reviewer at
the original file shipped alongside the merged PDF.
"""

import io
import logging
from dataclasses import dataclass

# Pure string-escaping helper for reportlab Paragraph markup (see the
# matching nosec in export_package_service) — no XML parsing happens here.
from xml.sax.saxutils import escape as xml_escape  # nosec B406
from typing import List, Optional

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.services.pdf_fonts import CJK_FONT_NAME, ensure_cjk_font

logger = logging.getLogger(__name__)

_PAGE_MARGIN = 15 * mm


@dataclass
class MergeItem:
    """One document to merge: display label + original filename + raw bytes.

    ``content=None`` means the file could not be downloaded; the merged PDF
    gets a placeholder page for it (carrying ``error``) so the document list
    stays complete.
    """

    label: str
    filename: str
    content: Optional[bytes]
    error: Optional[str] = None


def build_merged_pdf(title: str, subtitle_lines: List[str], items: List[MergeItem]) -> bytes:
    """Build one PDF: a cover page listing every document, then per document
    a separator page followed by its pages (or a placeholder page)."""
    if not items:
        raise ValueError("no documents to merge")
    ensure_cjk_font()

    writer = PdfWriter()
    _append_pdf(writer, _cover_page(title, subtitle_lines, items))

    for index, item in enumerate(items, start=1):
        heading = f"文件 {index}／{len(items)}：{item.label}"
        _append_pdf(writer, _text_page(heading, [f"原始檔名：{item.filename}"]))
        _append_pdf(writer, _render_item(item, heading))

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _render_item(item: MergeItem, heading: str) -> bytes:
    """Render one document's own pages as PDF bytes, degrading to a
    placeholder page on any unreadable/unsupported content."""
    if item.content is None:
        return _placeholder_page(heading, f"檔案下載失敗：{item.error or '未知錯誤'}")

    if _looks_like_pdf(item.filename, item.content):
        try:
            return _normalize_pdf(item.content)
        except Exception:
            logger.warning("merged-pdf: unreadable PDF %s", item.filename, exc_info=True)
            return _placeholder_page(heading, "PDF 檔案無法讀取（可能已加密或損毀），請開啟資料夾內的原始檔案。")

    try:
        return _image_page(item.content)
    except Exception:
        logger.warning("merged-pdf: unsupported or unreadable file %s", item.filename, exc_info=True)
        return _placeholder_page(
            heading, "此檔案格式無法合併（僅支援 PDF 與 JPG/PNG 圖片），請開啟資料夾內的原始檔案。"
        )


def _looks_like_pdf(filename: str, content: bytes) -> bool:
    return content.lstrip()[:5].startswith(b"%PDF") or filename.lower().endswith(".pdf")


def _normalize_pdf(content: bytes) -> bytes:
    """Re-serialize an uploaded PDF so the outer merge only ever appends
    PDFs pypdf fully parsed (unlocking owner-password-only encryption)."""
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        # Raises on a real user password; empty-string works for
        # owner-password-only ("permissions") encryption.
        reader.decrypt("")
    inner = PdfWriter()
    for page in reader.pages:
        inner.add_page(page)
    buf = io.BytesIO()
    inner.write(buf)
    return buf.getvalue()


def _image_page(content: bytes) -> bytes:
    """Place a JPEG/PNG on a single A4 page, scaled to fit, aspect kept."""
    img = Image.open(io.BytesIO(content))
    img.load()  # force full decode so corrupt files fail here

    # Flatten transparency onto white; normalize exotic modes to RGB.
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        img = background
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    page_width, page_height = A4
    avail_width = page_width - 2 * _PAGE_MARGIN
    avail_height = page_height - 2 * _PAGE_MARGIN
    scale = min(avail_width / img.width, avail_height / img.height)
    draw_width = img.width * scale
    draw_height = img.height * scale

    buf = io.BytesIO()
    canvas = pdf_canvas.Canvas(buf, pagesize=A4)
    canvas.drawImage(
        ImageReader(img),
        (page_width - draw_width) / 2,
        (page_height - draw_height) / 2,
        width=draw_width,
        height=draw_height,
    )
    canvas.showPage()
    canvas.save()
    return buf.getvalue()


def _append_pdf(writer: PdfWriter, pdf_bytes: bytes) -> None:
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        writer.add_page(page)


def _styles() -> dict:
    return {
        "title": ParagraphStyle("MergeTitle", fontName=CJK_FONT_NAME, fontSize=16, leading=22, alignment=1),
        "heading": ParagraphStyle("MergeHeading", fontName=CJK_FONT_NAME, fontSize=14, leading=20),
        "normal": ParagraphStyle("MergeNormal", fontName=CJK_FONT_NAME, fontSize=11, leading=16),
        "muted": ParagraphStyle(
            "MergeMuted",
            fontName=CJK_FONT_NAME,
            fontSize=10,
            leading=14,
            textColor=colors.Color(0.45, 0.45, 0.45),
        ),
    }


def _build_page(flowables: list) -> bytes:
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, topMargin=25 * mm, bottomMargin=20 * mm).build(flowables)
    return buf.getvalue()


def _cover_page(title: str, subtitle_lines: List[str], items: List[MergeItem]) -> bytes:
    styles = _styles()
    flowables = [Paragraph(xml_escape(title), styles["title"]), Spacer(1, 4 * mm)]
    for line in subtitle_lines:
        flowables.append(Paragraph(xml_escape(line), styles["muted"]))
    flowables.append(Spacer(1, 8 * mm))
    flowables.append(Paragraph("收錄文件", styles["heading"]))
    flowables.append(Spacer(1, 2 * mm))
    for index, item in enumerate(items, start=1):
        flowables.append(
            Paragraph(f"{index}. {xml_escape(item.label)}（{xml_escape(item.filename)}）", styles["normal"])
        )
    return _build_page(flowables)


def _text_page(heading: str, lines: List[str]) -> bytes:
    styles = _styles()
    flowables = [Paragraph(xml_escape(heading), styles["heading"]), Spacer(1, 3 * mm)]
    for line in lines:
        flowables.append(Paragraph(xml_escape(line), styles["muted"]))
    return _build_page(flowables)


def _placeholder_page(heading: str, reason: str) -> bytes:
    styles = _styles()
    return _build_page(
        [
            Paragraph(xml_escape(heading), styles["heading"]),
            Spacer(1, 4 * mm),
            Paragraph(xml_escape(reason), styles["normal"]),
        ]
    )
