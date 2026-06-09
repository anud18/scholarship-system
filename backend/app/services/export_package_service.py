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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application
from app.models.scholarship import ScholarshipType
from app.services.export_summary_tables import build_embedded_summary_tables
from app.services.minio_service import MinIOService

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


def _ext_for_application_document(original_filename: Optional[str], object_name: str) -> str:
    """Extension (with leading dot) for the student-uploaded 申請文件.

    Prefers the original filename's extension, falls back to the stored
    object name's suffix. Only the last path segment is inspected, so a dot
    in a directory name is never mistaken for an extension.
    """
    for source in (original_filename, object_name):
        if source:
            last_segment = source.rsplit("/", 1)[-1]
            if "." in last_segment:
                return "." + last_segment.rsplit(".", 1)[1]
    return ""


def _application_document_entry(
    object_name: Optional[str],
    original_filename: Optional[str],
    base_path: str,
    student_prefix: str,
) -> Optional[Dict[str, str]]:
    """Describe where the student-uploaded 申請文件 goes in the ZIP.

    Returns None when the application has no 申請文件. Otherwise returns a
    fetch job: the source object name, the sanitized ZIP path, the
    error-placeholder path, and a human label for the error text.
    """
    if not object_name:
        return None
    ext = _ext_for_application_document(original_filename, object_name)
    filename = _sanitize_filename(f"{student_prefix}_申請文件{ext}")
    return {
        "object_name": object_name,
        "zip_path": f"{base_path}/{filename}",
        "error_path": f"{base_path}/_錯誤_找不到檔案_申請文件.txt",
        "error_label": original_filename or object_name,
    }


def _application_paths(dept_folder: str, app: Application) -> Tuple[str, str]:
    """ZIP folder for one application: (base_path, student_prefix)."""
    student = app.student_data or {}
    std_code = _sanitize_filename(student.get("std_stdcode", "unknown"))
    std_name = _sanitize_filename(student.get("std_cname", "未知"))
    student_prefix = f"{std_code}_{std_name}"
    return f"{dept_folder}/{student_prefix}", student_prefix


def _collect_fetch_jobs(app: Application, base_path: str, student_prefix: str) -> List[Dict[str, str]]:
    """Fetch jobs for one application's MinIO objects: the uploaded
    ApplicationFile records plus the student-uploaded 申請文件 (stored on the
    application itself, not as an ApplicationFile)."""
    jobs: List[Dict[str, str]] = []

    type_totals = Counter(af.file_type or "other" for af in app.files)
    file_type_counter: Dict[str, int] = defaultdict(int)
    for af in app.files:
        ft = af.file_type or "other"
        file_type_counter[ft] += 1
        count = file_type_counter[ft]
        label = FILE_TYPE_LABELS.get(ft, "其他文件")

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

        jobs.append(
            {
                "object_name": af.object_name,
                "zip_path": f"{base_path}/{_sanitize_filename(filename)}",
                "error_path": f"{base_path}/_錯誤_找不到檔案_{_sanitize_filename(label)}.txt",
                "error_label": af.original_filename or af.object_name,
            }
        )

    entry = _application_document_entry(
        app.application_document_url,
        app.application_document_original_filename,
        base_path,
        student_prefix,
    )
    if entry:
        jobs.append(entry)

    return jobs


# How many MinIO objects may be in flight / held in memory at once while the
# ZIP is being assembled. The writer releases a slot only after the payload is
# written into the ZIP, so peak extra memory is bounded by this many files.
_FETCH_CONCURRENCY = 8


async def _fetch_object_bytes(minio: MinIOService, object_name: str) -> bytes:
    """Read one MinIO object fully in a worker thread (connection always released)."""

    def _read() -> bytes:
        response = minio.get_file_stream(object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await asyncio.to_thread(_read)


def _write_fetch_result(
    zf: zipfile.ZipFile,
    job: Dict[str, str],
    data: Optional[bytes],
    error: Optional[str],
) -> None:
    """Write fetched bytes at the job's zip_path, or a `_錯誤_…txt` placeholder
    at its error_path so a single bad object never aborts the whole ZIP build."""
    if error is None:
        zf.writestr(job["zip_path"], data)
    else:
        zf.writestr(job["error_path"], f"檔案下載失敗：{job['error_label']}\n錯誤：{error}")


CJK_FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
_font_registered = False


def _ensure_font():
    """Register CJK font once for reportlab."""
    global _font_registered
    if not _font_registered:
        pdfmetrics.registerFont(TTFont("WQY", CJK_FONT_PATH, subfontIndex=0))
        _font_registered = True


class ExportPackageService:
    def __init__(self, db: AsyncSession, minio_service: MinIOService):
        self.db = db
        self.minio = minio_service
        _ensure_font()

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

        # 4. Build ZIP. The dominant cost is one MinIO round trip per student
        # file, so all fetch jobs are collected up front and run as windowed
        # concurrent tasks while the summary PDFs render in a worker thread.
        fetch_jobs: List[Dict[str, str]] = []
        pdf_specs: List[Tuple[str, str, Application]] = []
        for dept_folder, apps in sorted(dept_groups.items()):
            for app in apps:
                base_path, student_prefix = _application_paths(dept_folder, app)
                pdf_specs.append((base_path, student_prefix, app))
                fetch_jobs.extend(_collect_fetch_jobs(app, base_path, student_prefix))

        window = asyncio.Semaphore(_FETCH_CONCURRENCY)

        async def _windowed_fetch(job: Dict[str, str]) -> Tuple[Optional[bytes], Optional[str]]:
            # The slot is released by the writer loop only after the payload is
            # written into the ZIP, keeping held payloads bounded by the window.
            await window.acquire()
            try:
                return await _fetch_object_bytes(self.minio, job["object_name"]), None
            except Exception as e:
                logger.exception(f"Failed to fetch file {job['object_name']}")
                return None, str(e)

        tasks = [asyncio.create_task(_windowed_fetch(job)) for job in fetch_jobs]

        buf = io.BytesIO()
        try:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                # Summary PDFs render off the event loop while fetches progress.
                for base_path, student_prefix, app in pdf_specs:
                    try:
                        pdf_bytes = await asyncio.to_thread(
                            self._generate_summary_pdf, app, scholarship_name, academic_year, semester
                        )
                        zf.writestr(f"{base_path}/{student_prefix}_學生資料彙整.pdf", pdf_bytes)
                    except Exception as e:
                        logger.exception(f"Failed to generate summary PDF for app {app.id}")
                        zf.writestr(f"{base_path}/_錯誤_彙整PDF生成失敗.txt", f"PDF 生成失敗：{str(e)}")

                for job, task in zip(fetch_jobs, tasks):
                    data, error = await task
                    _write_fetch_result(zf, job, data, error)
                    window.release()

                for inner_path, payload in summary_tables.items():
                    zf.writestr(inner_path, payload)
        except BaseException:
            for task in tasks:
                task.cancel()
            raise

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
        s_normal = ParagraphStyle("CJK", fontName="WQY", fontSize=10, leading=14)
        s_title = ParagraphStyle("CJKTitle", fontName="WQY", fontSize=16, leading=20, alignment=1)
        s_section = ParagraphStyle(
            "CJKSection",
            fontName="WQY",
            fontSize=12,
            leading=16,
            backColor=colors.Color(0.94, 0.94, 0.94),
        )
        s_header = ParagraphStyle(
            "CJKHeader",
            fontName="WQY",
            fontSize=9,
            leading=12,
            alignment=1,
            textColor=colors.Color(0.4, 0.4, 0.4),
        )
        s_footer = ParagraphStyle(
            "CJKFooter",
            fontName="WQY",
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
