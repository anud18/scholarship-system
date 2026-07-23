"""
Export Package Service

Generates ZIP files containing student application materials
organized by department, with auto-generated summary PDFs.
"""

import asyncio
import io
import logging
import re

# `escape` is a pure string-escaping helper (replaces `<` → `&lt;` etc.) used
# for sanitising values before they are placed inside reportlab Paragraph
# markup. It does not parse untrusted XML, so the B406 warning is a false
# positive here — defusedxml does not provide an equivalent escape function.
from xml.sax.saxutils import escape as xml_escape  # nosec B406
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application
from app.models.scholarship import ScholarshipType
from app.services.export_summary_tables import build_embedded_summary_tables
from app.services.minio_service import MinIOService
from app.services.pdf_fonts import CJK_FONT_NAME, ensure_cjk_font
from app.services.pdf_merge import MergeItem, build_merged_pdf

logger = logging.getLogger(__name__)

# file_type -> Chinese display name
FILE_TYPE_LABELS: Dict[str, str] = {
    "transcript": "成績單",
    "research_proposal": "研究計畫",
    "recommendation_letter": "推薦信",
    "certificate": "證書",
    "insurance_record": "投保紀錄",
    "agreement": "切結書",
    "bank_account_cover": "存摺封面",
    "bank_account_proof": "存摺封面",  # value actually stored on the cloned passbook ApplicationFile
    "id_card": "身份證",  # minted by batch_import doc_type_map — fixed type, NOT a dynamic document
    "bank_book": "存摺封面",  # minted by batch_import doc_type_map — fixed type, NOT a dynamic document
    "other": "其他文件",
}

DEGREE_LABELS: Dict[str, str] = {
    "1": "學士",
    "2": "碩士",
    "3": "博士",
}


def _sanitize_filename(name: str) -> str:
    """Replace characters that are invalid in ZIP file paths."""
    return re.sub(r'[/\\:*?"<>|]', "_", name).strip()


def _label_for_file_type(file_type: str) -> str:
    """Human label for an uploaded file's type in the ZIP filename.

    Fixed document types map through FILE_TYPE_LABELS; admin-configured
    dynamic document types keep their configured name (the ApplicationFile
    file_type IS the configured document_name) so each document stays
    identifiable in the export instead of collapsing into 其他文件.
    """
    if file_type in FILE_TYPE_LABELS:
        return FILE_TYPE_LABELS[file_type]
    if file_type and file_type != "other":
        return file_type
    return "其他文件"


def _is_dynamic_document_type(file_type: str) -> bool:
    """Whether an ApplicationFile carries an admin-configured dynamic
    document (its file_type IS the configured document_name). Fixed types
    and the legacy 其他文件 bucket live in FILE_TYPE_LABELS."""
    return bool(file_type) and file_type not in FILE_TYPE_LABELS


def _unique_zip_path(zf: zipfile.ZipFile, path: str) -> str:
    """Return `path`, suffixed with _2/_3/… if the ZIP already holds an entry
    at that name. zipfile happily writes duplicate names and most extractors
    then keep only the last one, silently shadowing the other file — e.g. an
    admin-configured dynamic document named exactly 動態文件合併 colliding with
    the merged PDF, or two same-type download failures sharing one error path."""
    existing = set(zf.namelist())
    if path not in existing:
        return path
    stem, dot, ext = path.rpartition(".")
    if not dot:
        stem, ext = path, ""
    counter = 2
    while True:
        candidate = f"{stem}_{counter}.{ext}" if dot else f"{stem}_{counter}"
        if candidate not in existing:
            return candidate
        counter += 1


async def _fetch_and_write(
    zf: zipfile.ZipFile,
    minio: MinIOService,
    object_name: str,
    zip_path: str,
    error_path: str,
    error_label: str,
) -> Optional[bytes]:
    """Stream one MinIO object into the ZIP at `zip_path` and return its bytes.

    On any failure, writes a `_錯誤_…txt` placeholder at `error_path`
    instead so a single bad object never aborts the whole ZIP build, and
    returns None.
    """
    try:
        response = await asyncio.to_thread(minio.get_file_stream, object_name)
        try:
            file_bytes = await asyncio.to_thread(response.read)
        finally:
            response.close()
            response.release_conn()
        zf.writestr(_unique_zip_path(zf, zip_path), file_bytes)
        return file_bytes
    except Exception as e:
        logger.exception(f"Failed to fetch file {object_name}")
        zf.writestr(_unique_zip_path(zf, error_path), f"檔案下載失敗：{error_label}\n錯誤：{str(e)}")
        return None


class ExportPackageService:
    def __init__(self, db: AsyncSession, minio_service: MinIOService):
        self.db = db
        self.minio = minio_service
        ensure_cjk_font()

    async def generate_export_zip(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> Tuple[io.BytesIO, str]:
        """
        Generate a ZIP file with all application materials.

        Returns:
            Tuple of (BytesIO buffer, suggested filename)
        """
        # 1. Get scholarship type (name drives ZIP/PDF filenames; object passed to table builder)
        scholarship_type = await self._get_scholarship_type(scholarship_type_id)
        scholarship_name = scholarship_type.name

        # 2. Query applications with files
        applications = await self._query_applications(scholarship_type_id, academic_year, semester, college_code)

        if not applications:
            raise ValueError("無申請資料可匯出")

        if len(applications) > 200:
            raise ValueError(f"申請筆數超過上限 (200)，請縮小篩選範圍（目前 {len(applications)} 筆）")

        # Derive college name from first application's student_data
        college_name = None
        if college_code:
            for app in applications:
                if app.student_data:
                    college_name = app.student_data.get("trm_academyname")
                    if college_name:
                        break

        # 3. Group by department
        dept_groups: Dict[str, List[Application]] = defaultdict(list)
        for app in applications:
            student = app.student_data or {}
            dep_no = student.get("trm_depno", "unknown")
            dep_name = student.get("trm_depname", "未知系所")
            key = f"{_sanitize_filename(dep_no)}_{_sanitize_filename(dep_name)}"
            dept_groups[key].append(app)

        # 3.5 Build the embedded 申請總表 workbooks from the SAME dept_groups.
        # Best-effort: the summary tables are a secondary artifact, so a wholesale
        # failure here (e.g. an aux-data DB error before the per-table try/except)
        # must not lose the primary materials ZIP — degrade to an error placeholder.
        try:
            summary_tables = await build_embedded_summary_tables(
                self.db, scholarship_type, dept_groups, college_name, academic_year
            )
        except Exception as e:
            logger.exception("embedded summary tables generation failed wholesale")
            summary_tables = {"_錯誤_申請總表生成失敗.txt": f"申請總表生成失敗：{e}".encode("utf-8")}

        # 4. Build ZIP
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for dept_folder, apps in sorted(dept_groups.items()):
                for app in apps:
                    await self._add_application_to_zip(zf, dept_folder, app, scholarship_name, academic_year, semester)
            for inner_path, payload in summary_tables.items():
                zf.writestr(inner_path, payload)

        buf.seek(0)

        # 5. Build filename
        semester_label = {"first": "1", "second": "2", "annual": "0"}.get(semester, "0") if semester else "0"
        zip_filename = (
            f"{_sanitize_filename(scholarship_name)}"
            f"_申請資料_{academic_year}_{semester_label}"
            f"_{_sanitize_filename(college_name or '全校')}.zip"
        )

        return buf, zip_filename

    async def _get_scholarship_type(self, scholarship_type_id: int) -> ScholarshipType:
        """Load the full ScholarshipType (with sub_type_configs) — name drives the
        ZIP/PDF filenames; the object is also passed to the summary-table builder."""
        stmt = (
            select(ScholarshipType)
            .where(ScholarshipType.id == scholarship_type_id)
            .options(selectinload(ScholarshipType.sub_type_configs))
        )
        result = await self.db.execute(stmt)
        scholarship = result.scalar_one_or_none()
        if not scholarship:
            raise ValueError(f"找不到獎學金類型 ID={scholarship_type_id}")
        return scholarship

    async def _query_applications(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> List[Application]:
        """Query submitted applications with their files, filtered by college if needed."""
        # Only export applications that have been submitted (exclude drafts/withdrawn)
        valid_statuses = ("submitted", "under_review", "approved", "partial_approved", "rejected")
        stmt = (
            select(Application)
            .options(selectinload(Application.files))
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.status.in_(valid_statuses),
            )
        )

        if semester:
            stmt = stmt.where(Application.semester == semester)

        result = await self.db.execute(stmt)
        applications = list(result.scalars().all())

        # Filter by college_code using student_data
        if college_code:
            applications = [
                app
                for app in applications
                if app.student_data and app.student_data.get("std_academyno") == college_code
            ]

        return applications

    async def _add_application_to_zip(
        self,
        zf: zipfile.ZipFile,
        dept_folder: str,
        app: Application,
        scholarship_name: str,
        academic_year: int,
        semester: Optional[str],
    ) -> None:
        """Add one application's files + summary PDF to the ZIP."""
        student = app.student_data or {}
        std_code = _sanitize_filename(student.get("std_stdcode", "unknown"))
        std_name = _sanitize_filename(student.get("std_cname", "未知"))
        student_folder = f"{std_code}_{std_name}"
        base_path = f"{dept_folder}/{student_folder}"

        # Generate summary PDF
        student_prefix = f"{std_code}_{std_name}"
        try:
            pdf_bytes = self._generate_summary_pdf(app, scholarship_name, academic_year, semester)
            zf.writestr(f"{base_path}/{student_prefix}_學生資料彙整.pdf", pdf_bytes)
        except Exception as e:
            logger.exception(f"Failed to generate summary PDF for app {app.id}")
            zf.writestr(
                f"{base_path}/_錯誤_彙整PDF生成失敗.txt",
                f"PDF 生成失敗：{str(e)}",
            )

        # Add uploaded files from ApplicationFile records; keep the bytes of
        # dynamic documents so they can be stitched into one extra PDF below.
        type_totals = Counter(af.file_type or "other" for af in app.files)
        file_type_counter: Dict[str, int] = defaultdict(int)
        dynamic_items: List[MergeItem] = []
        for af in app.files:
            ft = af.file_type or "other"
            file_type_counter[ft] += 1
            count = file_type_counter[ft]
            label = _label_for_file_type(ft)

            # Determine file extension from original filename or mime_type
            ext = ""
            if af.original_filename and "." in af.original_filename:
                ext = "." + af.original_filename.rsplit(".", 1)[1]
            elif af.mime_type and "/" in af.mime_type:
                ext_map = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
                ext = ext_map.get(af.mime_type, "")

            # Add sequence number only if multiple files of same type
            if type_totals[ft] > 1:
                filename = f"{student_prefix}_{label}_{count}{ext}"
            else:
                filename = f"{student_prefix}_{label}{ext}"

            file_bytes = await _fetch_and_write(
                zf,
                self.minio,
                object_name=af.object_name,
                zip_path=f"{base_path}/{_sanitize_filename(filename)}",
                error_path=f"{base_path}/_錯誤_找不到檔案_{_sanitize_filename(label)}.txt",
                error_label=af.original_filename or af.object_name,
            )

            if _is_dynamic_document_type(ft):
                item_label = f"{label} {count}" if type_totals[ft] > 1 else label
                dynamic_items.append(
                    MergeItem(
                        label=item_label,
                        filename=af.original_filename or af.object_name or "",
                        content=file_bytes,
                        error=None if file_bytes is not None else "無法自檔案儲存服務下載",
                    )
                )

        # Extra per-student PDF stitching all dynamic documents together
        if dynamic_items:
            semester_map = {"first": "第一學期", "second": "第二學期"}
            semester_label = semester_map.get(semester, "全學年") if semester else "全學年"
            try:
                # to_thread: pypdf/Pillow/reportlab do seconds of pure CPU per
                # student — inline they would stall the whole event loop.
                merged_bytes = await asyncio.to_thread(
                    build_merged_pdf,
                    title="學生動態文件合併",
                    subtitle_lines=[
                        f"{scholarship_name} {academic_year}學年度 {semester_label}",
                        f"{std_code} {std_name}",
                    ],
                    items=dynamic_items,
                )
                zf.writestr(_unique_zip_path(zf, f"{base_path}/{student_prefix}_動態文件合併.pdf"), merged_bytes)
            except Exception as e:
                logger.exception(f"Failed to build merged dynamic-documents PDF for app {app.id}")
                zf.writestr(
                    f"{base_path}/_錯誤_動態文件合併PDF生成失敗.txt",
                    f"動態文件合併 PDF 生成失敗：{str(e)}",
                )

    def _generate_summary_pdf(
        self,
        app: Application,
        scholarship_name: str,
        academic_year: int,
        semester: Optional[str],
    ) -> bytes:
        """Generate a student summary PDF using reportlab."""
        student = app.student_data or {}
        submitted = app.submitted_form_data or {}

        degree_raw = str(student.get("trm_degree", ""))
        degree_label = DEGREE_LABELS.get(degree_raw, degree_raw or "—")
        semester_map = {"first": "第一學期", "second": "第二學期"}
        semester_label = semester_map.get(semester, "全學年") if semester else "全學年"
        export_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

        # Styles
        s_normal = ParagraphStyle("CJK", fontName=CJK_FONT_NAME, fontSize=10, leading=14)
        s_title = ParagraphStyle("CJKTitle", fontName=CJK_FONT_NAME, fontSize=16, leading=20, alignment=1)
        s_section = ParagraphStyle(
            "CJKSection",
            fontName=CJK_FONT_NAME,
            fontSize=12,
            leading=16,
            backColor=colors.Color(0.94, 0.94, 0.94),
        )
        s_header = ParagraphStyle(
            "CJKHeader",
            fontName=CJK_FONT_NAME,
            fontSize=9,
            leading=12,
            alignment=1,
            textColor=colors.Color(0.4, 0.4, 0.4),
        )
        s_footer = ParagraphStyle(
            "CJKFooter",
            fontName=CJK_FONT_NAME,
            fontSize=8,
            leading=10,
            alignment=1,
            textColor=colors.Color(0.6, 0.6, 0.6),
        )

        table_style = TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.96, 0.96, 0.96)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )

        elements = []

        # Header + Title
        elements.append(Paragraph(f"{scholarship_name} {academic_year}學年度 {semester_label}", s_header))
        elements.append(Spacer(1, 3 * mm))
        elements.append(Paragraph("學生資料彙整", s_title))
        elements.append(Spacer(1, 6 * mm))

        # Section 1: Basic Info
        elements.append(Paragraph("一、基本資料", s_section))
        elements.append(Spacer(1, 2 * mm))
        basic_rows = [
            ("學號", student.get("std_stdcode", "—")),
            ("姓名", student.get("std_cname", "—")),
            ("英文姓名", student.get("std_ename", "—")),
            ("學院", student.get("trm_academyname", "—")),
            ("系所", student.get("trm_depname", "—")),
            ("學位", degree_label),
            ("入學年度", str(student.get("std_enrollyear", "—"))),
            ("Email", student.get("com_email", "—")),
            ("手機", student.get("com_cellphone", "—")),
        ]
        elements.append(self._build_table(basic_rows, s_normal, table_style))
        elements.append(Spacer(1, 4 * mm))

        # Section 2: Academic Performance
        elements.append(Paragraph("二、學業表現", s_section))
        elements.append(Spacer(1, 2 * mm))
        placings = str(student.get("trm_placings", "—"))
        if student.get("trm_placingsrate"):
            placings += f" ({student['trm_placingsrate']}%)"
        dep_placing = str(student.get("trm_depplacing", "—"))
        if student.get("trm_depplacingrate"):
            dep_placing += f" ({student['trm_depplacingrate']}%)"
        academic_rows = [
            ("學年 / 學期", f"{student.get('trm_year', '—')} / {student.get('trm_term', '—')}"),
            ("GPA", str(student.get("trm_ascore_gpa", "—"))),
            ("班排名", placings),
            ("系排名", dep_placing),
            ("修業學期數", str(student.get("trm_termcount", "—"))),
        ]
        elements.append(self._build_table(academic_rows, s_normal, table_style))
        elements.append(Spacer(1, 4 * mm))

        # Section 3: Form Fields
        fields_data = submitted.get("fields", {})
        if fields_data:
            elements.append(Paragraph("三、表單填寫資料", s_section))
            elements.append(Spacer(1, 2 * mm))
            form_rows = []
            for field_id in sorted(fields_data.keys()):
                field = fields_data[field_id]
                label = field.get("label", field.get("field_id", field_id))
                value = str(field.get("value", "—") or "—")
                form_rows.append((label, value))
            elements.append(self._build_table(form_rows, s_normal, table_style))
            elements.append(Spacer(1, 4 * mm))

        # Section 4: Document List
        doc_list = submitted.get("documents", [])
        if doc_list:
            elements.append(Paragraph("四、上傳文件清單", s_section))
            elements.append(Spacer(1, 2 * mm))
            for doc in doc_list:
                name = doc.get("document_type") or doc.get("document_id", "未知文件")
                upload_time = doc.get("upload_time", "—")
                elements.append(Paragraph(f"• {name}（上傳時間：{upload_time}）", s_normal))

        # Footer
        elements.append(Spacer(1, 10 * mm))
        elements.append(Paragraph(f"匯出時間：{export_time}", s_footer))

        # Build PDF
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
        doc.build(elements)
        return buf.getvalue()

    @staticmethod
    def _build_table(rows: List[Tuple[str, str]], style: ParagraphStyle, table_style: TableStyle) -> Table:
        """Build a two-column label-value table."""
        data = [
            [Paragraph(xml_escape(label), style), Paragraph(xml_escape(str(value)), style)] for label, value in rows
        ]
        t = Table(data, colWidths=[50 * mm, 120 * mm])
        t.setStyle(table_style)
        return t
