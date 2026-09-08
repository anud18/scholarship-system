"""
Export Package Service

Generates ZIP files containing student application materials organized by
department, with auto-generated summary PDFs and, per student, one merged
申請資料合併檔 PDF holding that summary plus their dynamic documents.
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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional, Tuple

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
from app.services.form_field_labels import (
    ACCOUNT_FIELD_SYNONYMS,
    load_form_field_labels,
    resolve_field_label,
)
from app.services.minio_service import MinIOService
from app.services.pdf_fonts import CJK_FONT_NAME, ensure_cjk_font
from app.services.pdf_merge import MergeItem, build_merged_pdf
from app.services.zip_stream import COPY_CHUNK_SIZE, ZipStreamSink, write_stream_entry

logger = logging.getLogger(__name__)

# Hard cap on applications per export: keeps one request's work (and the
# reviewer's archive) within reason; above it the UI asks for a narrower filter.
# Raised from 200 once the archive streamed instead of being built in RAM.
MAX_EXPORT_APPLICATIONS = 1000

# The per-student summary PDF shipped standalone AND as the first document of
# the merged PDF, and the merged PDF that stitches it together with the
# student's admin-configured dynamic documents.
SUMMARY_PDF_LABEL = "學生資料彙整"
MERGED_PDF_LABEL = "申請資料合併檔"

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

# SIS 攻讀學位 codes. Descending, NOT ascending — 1 is the highest degree.
# Authoritative sources, all agreeing: the `degrees` reference table the
# frontend renders from (1=博士, 2=碩士, 3=學士), the std_degree field doc in
# app/schemas/student.py, and StudentInfo.get_student_type() mapping "1"→phd.
DEGREE_LABELS: Dict[str, str] = {
    "1": "博士",
    "2": "碩士",
    "3": "學士",
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


def _is_dynamic_document_type(file_type: Optional[str]) -> bool:
    """Whether an ApplicationFile carries an admin-configured dynamic
    document (its file_type IS the configured document_name). Fixed types
    and the legacy 其他文件 bucket live in FILE_TYPE_LABELS."""
    return bool(file_type) and file_type not in FILE_TYPE_LABELS


def _zip_has_entry(zf: zipfile.ZipFile, name: str) -> bool:
    """getinfo() is a documented O(1) name lookup — no per-call namelist() scan."""
    try:
        zf.getinfo(name)
        return True
    except KeyError:
        return False


def _unique_zip_path(zf: zipfile.ZipFile, path: str) -> str:
    """Return `path`, suffixed with _2/_3/… if the ZIP already holds an entry
    at that name. zipfile happily writes duplicate names and most extractors
    then keep only the last one, silently shadowing the other file — e.g. an
    admin-configured dynamic document named exactly 申請資料合併檔 colliding with
    the merged PDF, or two same-type download failures sharing one error path."""
    if not _zip_has_entry(zf, path):
        return path
    stem, dot, ext = path.rpartition(".")
    # Only honour a real extension on the final component: a trailing dot
    # ("abc.") would yield "abc_2." (Windows strips trailing dots →
    # re-collision), and a dot only in a parent dir or a leading-dot
    # basename has no extension to preserve.
    if not dot or not ext or "/" in ext or not stem or stem.endswith("/"):
        stem, dot, ext = path, "", ""
    counter = 2
    while True:
        candidate = f"{stem}_{counter}.{ext}" if dot else f"{path}_{counter}"
        if not _zip_has_entry(zf, candidate):
            return candidate
        counter += 1


def _write_fetch_error(
    zf: zipfile.ZipFile, error_path: str, error_label: str, error: Exception, incomplete_entry: bool
) -> str:
    """Write the `_錯誤_…txt` placeholder for a failed object copy and return the
    reason the merged PDF's placeholder page should show."""
    reason = str(error) or "無法自檔案儲存服務下載"
    lines = [f"檔案下載失敗：{error_label}", f"錯誤：{reason}"]
    if incomplete_entry:
        lines.append("注意：下載途中中斷，ZIP 內同名檔案的內容不完整。")
    zf.writestr(_unique_zip_path(zf, error_path), "\n".join(lines))
    return reason


def _copy_object_into_zip(
    zf: zipfile.ZipFile,
    minio: MinIOService,
    object_name: str,
    zip_path: str,
    error_path: str,
    error_label: str,
    keep_bytes: bool,
) -> Tuple[Optional[bytes], Optional[str]]:
    """Copy one MinIO object into the ZIP at `zip_path`, chunk by chunk.

    Blocking (network + deflate) — call from a worker thread. Returns
    (file_bytes, None) on success; file_bytes is only collected when
    `keep_bytes` (the merged PDF needs the whole document), otherwise the
    object flows through in COPY_CHUNK_SIZE pieces and never sits in memory
    whole. On any failure writes a `_錯誤_…txt` placeholder at `error_path`
    instead, so a single bad object never aborts the whole ZIP build, and
    returns (None, error message) so the merged PDF's placeholder page can
    show the same concrete reason.
    """
    try:
        response = minio.get_file_stream(object_name)
    except Exception as e:
        logger.exception("Failed to fetch file %s", object_name)
        return None, _write_fetch_error(zf, error_path, error_label, e, incomplete_entry=False)

    entry_path = _unique_zip_path(zf, zip_path)
    try:
        content_length = response.headers.get("Content-Length")
        file_bytes = write_stream_entry(
            zf,
            entry_path,
            response.stream(COPY_CHUNK_SIZE),
            expected_size=int(content_length) if content_length else None,
            keep_bytes=keep_bytes,
        )
        return file_bytes, None
    except Exception as e:
        # A streamed archive cannot take back an entry whose header already
        # left, so the placeholder says whether a truncated copy sits beside it.
        logger.exception("Failed to stream file %s into the ZIP", object_name)
        incomplete_entry = _zip_has_entry(zf, entry_path)
        return None, _write_fetch_error(zf, error_path, error_label, e, incomplete_entry=incomplete_entry)
    finally:
        _release_quietly(response, object_name)


def _release_quietly(response, object_name: str) -> None:
    """Close a storage response without letting a teardown error replace the
    outcome: a half-consumed or already-reset connection can raise from
    close()/release_conn(), and that must not abort the rest of the export."""
    try:
        response.close()
        response.release_conn()
    except Exception:
        logger.warning("Failed to release storage connection for %s", object_name, exc_info=True)


def _uploaded_file_name(af, student_prefix: str, label: str, count: int, total: int) -> str:
    """`{學號_姓名}_{label}[_{n}]{ext}` — the sequence number only when the
    student has several files of one type; extension from the original name,
    else from the mime type."""
    ext = ""
    if af.original_filename and "." in af.original_filename:
        ext = "." + af.original_filename.rsplit(".", 1)[1]
    elif af.mime_type and "/" in af.mime_type:
        ext = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}.get(af.mime_type, "")
    suffix = f"_{count}" if total > 1 else ""
    return f"{student_prefix}_{label}{suffix}{ext}"


def _group_by_department(applications: List[Application]) -> Dict[str, List[Application]]:
    """Folder key per application: `{depno}_{depname}` from the SIS term snapshot."""
    dept_groups: Dict[str, List[Application]] = defaultdict(list)
    for app in applications:
        student = app.student_data or {}
        dep_no = student.get("trm_depno", "unknown")
        dep_name = student.get("trm_depname", "未知系所")
        dept_groups[f"{_sanitize_filename(dep_no)}_{_sanitize_filename(dep_name)}"].append(app)
    return dept_groups


def _first_college_name(applications: List[Application]) -> Optional[str]:
    """College display name from the first application whose snapshot carries one."""
    for app in applications:
        if app.student_data and app.student_data.get("trm_academyname"):
            return app.student_data["trm_academyname"]
    return None


def _build_zip_filename(
    scholarship_name: str, academic_year: int, semester: Optional[str], college_name: Optional[str]
) -> str:
    semester_label = {"first": "1", "second": "2", "annual": "0"}.get(semester, "0") if semester else "0"
    return (
        f"{_sanitize_filename(scholarship_name)}"
        f"_申請資料_{academic_year}_{semester_label}"
        f"_{_sanitize_filename(college_name or '全校')}.zip"
    )


@dataclass(frozen=True)
class ExportPlan:
    """Everything the streaming phase needs, resolved before the response starts.

    prepare_export() raises every user-facing rejection (unknown scholarship,
    no data, over the cap) while a 4xx can still be sent, and iter_export_zip()
    then works purely from this plan — no DB access once bytes are flowing.
    """

    scholarship_name: str
    academic_year: int
    semester: Optional[str]
    college_name: Optional[str]
    dept_groups: Dict[str, List[Application]]
    field_labels: Dict[str, str]
    summary_tables: Dict[str, bytes]
    zip_filename: str

    @property
    def application_count(self) -> int:
        return sum(len(apps) for apps in self.dept_groups.values())


class ExportPackageService:
    def __init__(self, db: AsyncSession, minio_service: MinIOService):
        self.db = db
        self.minio = minio_service
        ensure_cjk_font()

    async def prepare_export(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
        include_summary_tables: bool = True,
    ) -> ExportPlan:
        """Validate the request and load everything the archive needs.

        Raises ValueError for the user-facing rejections (mapped to 400 by the
        endpoint). All DB work — scholarship type, applications with their
        files, form-field labels, the embedded 申請總表 workbooks — happens here.
        The dry-run precheck passes ``include_summary_tables=False``: it only
        needs the filename and count, and the workbooks are the expensive part.
        """
        # 1. Scholarship type (name drives ZIP/PDF filenames; object passed to the table builder)
        scholarship_type = await self._get_scholarship_type(scholarship_type_id)

        # 2. Applications with their files
        applications = await self._query_applications(scholarship_type_id, academic_year, semester, college_code)
        if not applications:
            raise ValueError("無申請資料可匯出")
        if len(applications) > MAX_EXPORT_APPLICATIONS:
            raise ValueError(
                f"申請筆數超過上限 ({MAX_EXPORT_APPLICATIONS})，請縮小篩選範圍（目前 {len(applications)} 筆）"
            )

        # 2.5 zh-TW labels for the submitted form fields, loaded once for the
        # per-student summary PDFs (built later, off the event loop).
        field_labels = await load_form_field_labels(self.db, scholarship_type.code)

        college_name = _first_college_name(applications) if college_code else None
        dept_groups = _group_by_department(applications)

        # 3. Embedded 申請總表 workbooks from the SAME dept_groups. Best-effort:
        # a wholesale failure (e.g. an aux-data DB error before the per-table
        # try/except) must not lose the primary materials ZIP — degrade to an
        # error placeholder.
        summary_tables: Dict[str, bytes] = {}
        if include_summary_tables:
            try:
                summary_tables = await build_embedded_summary_tables(
                    self.db, scholarship_type, dept_groups, college_name, academic_year
                )
            except Exception as e:
                logger.exception("embedded summary tables generation failed wholesale")
                summary_tables = {"_錯誤_申請總表生成失敗.txt": f"申請總表生成失敗：{e}".encode("utf-8")}

        return ExportPlan(
            scholarship_name=scholarship_type.name,
            academic_year=academic_year,
            semester=semester,
            college_name=college_name,
            dept_groups=dept_groups,
            field_labels=field_labels,
            summary_tables=summary_tables,
            zip_filename=_build_zip_filename(scholarship_type.name, academic_year, semester, college_name),
        )

    async def iter_export_zip(self, plan: ExportPlan) -> AsyncIterator[bytes]:
        """Stream the archive for `plan` in STREAM_BLOCK_SIZE chunks.

        Each application is assembled in a worker thread (MinIO I/O, deflate,
        reportlab and pypdf are all blocking) and whatever it produced is then
        drained from the sink, so the ZIP is never held in memory as a whole
        and the client sees bytes from the first student onward (issue #1376).
        """
        sink = ZipStreamSink()
        with zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED) as zf:
            for dept_folder, apps in sorted(plan.dept_groups.items()):
                for app in apps:
                    await asyncio.to_thread(self._add_application_to_zip, zf, dept_folder, app, plan)
                    for block in sink.take_blocks():
                        yield block
            for inner_path, payload in plan.summary_tables.items():
                # Deflating a department workbook is CPU work too: keep it off
                # the event loop and drain after each so pending stays bounded.
                await asyncio.to_thread(zf.writestr, inner_path, payload)
                for block in sink.take_blocks():
                    yield block
        # Closing the archive appended the central directory; flush what is left.
        for block in sink.take_blocks():
            yield block
        tail = sink.take_all()
        if tail:
            yield tail

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

    def _add_application_to_zip(
        self,
        zf: zipfile.ZipFile,
        dept_folder: str,
        app: Application,
        plan: ExportPlan,
    ) -> None:
        """Add one application's files + summary PDF + merged PDF to the ZIP.

        Blocking end to end (reportlab, MinIO I/O, deflate, pypdf): runs in a
        worker thread from iter_export_zip so the event loop stays free.
        """
        student = app.student_data or {}
        std_code = _sanitize_filename(student.get("std_stdcode", "unknown"))
        std_name = _sanitize_filename(student.get("std_cname", "未知"))
        student_prefix = f"{std_code}_{std_name}"
        base_path = f"{dept_folder}/{student_prefix}"

        summary_item = self._add_summary_pdf(zf, base_path, student_prefix, app, plan)
        dynamic_items = self._add_uploaded_files(zf, base_path, student_prefix, app)
        # Extra per-student PDF stitching the summary and all dynamic documents
        # together. Built for every student — summary_item is always present, so
        # a student who uploaded no dynamic documents still gets one holding
        # just their summary and reviewers work from the same file throughout.
        self._add_merged_pdf(zf, base_path, student_prefix, app, plan, [summary_item] + dynamic_items)

    def _add_summary_pdf(
        self, zf: zipfile.ZipFile, base_path: str, student_prefix: str, app: Application, plan: ExportPlan
    ) -> MergeItem:
        """Write the 學生資料彙整 PDF and return it as the merge's leading item.

        The bytes are kept in memory on purpose: the summary leads the merged
        PDF so reviewers open one file and start at the student's data. On
        failure the ZIP gets an error placeholder and the merge still lists the
        summary as a placeholder page — a reviewer working only from the merged
        PDF must not read a missing summary as "no personal data submitted".
        """
        try:
            pdf_bytes = self._generate_summary_pdf(
                app, plan.scholarship_name, plan.academic_year, plan.semester, plan.field_labels
            )
            # _unique_zip_path here too: two applications can share one
            # base_path (same student code + name in one department, e.g. a
            # rejected and a resubmitted application), and a duplicate ZIP
            # entry would silently drop one of the two summaries.
            summary_path = _unique_zip_path(zf, f"{base_path}/{student_prefix}_{SUMMARY_PDF_LABEL}.pdf")
            zf.writestr(summary_path, pdf_bytes)
            return MergeItem(label=SUMMARY_PDF_LABEL, filename=summary_path.rsplit("/", 1)[-1], content=pdf_bytes)
        except Exception as e:
            logger.exception("Failed to generate summary PDF for app %s", app.id)
            zf.writestr(
                _unique_zip_path(zf, f"{base_path}/_錯誤_彙整PDF生成失敗.txt"),
                f"PDF 生成失敗：{str(e)}",
            )
            return MergeItem(
                label=SUMMARY_PDF_LABEL,
                filename=f"{student_prefix}_{SUMMARY_PDF_LABEL}.pdf",
                content=None,
                error=f"{SUMMARY_PDF_LABEL} PDF 生成失敗：{str(e)}",
            )

    def _add_uploaded_files(
        self, zf: zipfile.ZipFile, base_path: str, student_prefix: str, app: Application
    ) -> List[MergeItem]:
        """Copy every ApplicationFile into the student's folder.

        Fixed-type files stream straight through; dynamic documents are also
        kept in memory and returned as merge items so they can be stitched into
        the 申請資料合併檔 (a failed download becomes a placeholder item there).
        """
        type_totals = Counter(af.file_type or "other" for af in app.files)
        file_type_counter: Dict[str, int] = defaultdict(int)
        dynamic_items: List[MergeItem] = []
        for af in app.files:
            ft = af.file_type or "other"
            file_type_counter[ft] += 1
            count = file_type_counter[ft]
            label = _label_for_file_type(ft)
            filename = _uploaded_file_name(af, student_prefix, label, count, type_totals[ft])

            is_dynamic = _is_dynamic_document_type(ft)
            file_bytes, fetch_error = _copy_object_into_zip(
                zf,
                self.minio,
                object_name=af.object_name,
                zip_path=f"{base_path}/{_sanitize_filename(filename)}",
                error_path=f"{base_path}/_錯誤_找不到檔案_{_sanitize_filename(label)}.txt",
                error_label=af.original_filename or af.object_name or "未知檔案",
                keep_bytes=is_dynamic,
            )

            if is_dynamic:
                item_label = f"{label} {count}" if type_totals[ft] > 1 else label
                dynamic_items.append(
                    MergeItem(
                        label=item_label,
                        filename=af.original_filename or af.object_name or "",
                        content=file_bytes,
                        error=f"檔案下載失敗：{fetch_error}" if fetch_error else None,
                    )
                )
        return dynamic_items

    def _add_merged_pdf(
        self,
        zf: zipfile.ZipFile,
        base_path: str,
        student_prefix: str,
        app: Application,
        plan: ExportPlan,
        items: List[MergeItem],
    ) -> None:
        """Write the per-student 申請資料合併檔, or an error placeholder."""
        student = app.student_data or {}
        semester_map = {"first": "第一學期", "second": "第二學期"}
        semester_label = semester_map.get(plan.semester, "全學年") if plan.semester else "全學年"
        try:
            # pypdf/Pillow/reportlab do seconds of pure CPU per student; this
            # already runs off the event loop (see iter_export_zip).
            merged_bytes = build_merged_pdf(
                title=MERGED_PDF_LABEL,
                subtitle_lines=[
                    f"{plan.scholarship_name} {plan.academic_year}學年度 {semester_label}",
                    # Display surface: raw SIS values (sanitization is for
                    # ZIP paths), with the same fallbacks as folder naming.
                    f"{student.get('std_stdcode', 'unknown')} {student.get('std_cname', '未知')}",
                ],
                items=items,
            )
            zf.writestr(_unique_zip_path(zf, f"{base_path}/{student_prefix}_{MERGED_PDF_LABEL}.pdf"), merged_bytes)
        except Exception as e:
            logger.exception("Failed to build merged application PDF for app %s", app.id)
            zf.writestr(
                _unique_zip_path(zf, f"{base_path}/_錯誤_{MERGED_PDF_LABEL}PDF生成失敗.txt"),
                f"{MERGED_PDF_LABEL} PDF 生成失敗：{str(e)}",
            )

    def _generate_summary_pdf(
        self,
        app: Application,
        scholarship_name: str,
        academic_year: int,
        semester: Optional[str],
        field_labels: Dict[str, str],
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
        elements.append(Paragraph(SUMMARY_PDF_LABEL, s_title))
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
            seen_account_rows = set()
            for field_id in sorted(fields_data.keys()):
                field = fields_data[field_id]
                label = resolve_field_label(field_id, field_labels)
                value = str(field.get("value", "—") or "—")
                # postal_account and account_number are two ids for the one
                # 郵局帳號 the student typed, so once translated they print the
                # identical row twice. Scoped to that pair: two genuinely
                # distinct fields that happen to share a label both stay
                # visible, and differing account values stay visible too.
                if field_id in ACCOUNT_FIELD_SYNONYMS:
                    if (label, value) in seen_account_rows:
                        continue
                    seen_account_rows.add((label, value))
                form_rows.append((label, value))
            # Row order stays keyed on field_id: sorting on the zh-TW label
            # would order by CJK codepoint, no more meaningful to a reviewer
            # than the id and needlessly unstable when a label is edited.
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
