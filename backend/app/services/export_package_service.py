"""
Export Package Service

Generates ZIP files containing student application materials
organized by department, with auto-generated summary PDFs.
"""

import io
import logging
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import weasyprint
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application, ApplicationFile
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
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


class ExportPackageService:
    def __init__(self, db: AsyncSession, minio_service: MinIOService):
        self.db = db
        self.minio = minio_service
        template_dir = Path(__file__).resolve().parent.parent / "templates"
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
        )

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
        # 1. Get scholarship info for naming
        scholarship_name, college_name = await self._get_scholarship_and_college_info(
            scholarship_type_id, academic_year, semester, college_code
        )

        # 2. Query applications with files
        applications = await self._query_applications(
            scholarship_type_id, academic_year, semester, college_code
        )

        if not applications:
            raise ValueError("無申請資料可匯出")

        # 3. Group by department
        dept_groups: Dict[str, List[Application]] = defaultdict(list)
        for app in applications:
            student = app.student_data or {}
            dep_no = student.get("trm_depno", "unknown")
            dep_name = student.get("trm_depname", "未知系所")
            key = f"{_sanitize_filename(dep_no)}_{_sanitize_filename(dep_name)}"
            dept_groups[key].append(app)

        # 4. Build ZIP
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for dept_folder, apps in sorted(dept_groups.items()):
                for app in apps:
                    await self._add_application_to_zip(
                        zf, dept_folder, app, scholarship_name, academic_year, semester
                    )

        buf.seek(0)

        # 5. Build filename
        semester_label = {"first": "1", "second": "2"}.get(semester, "0") if semester else "0"
        zip_filename = (
            f"{_sanitize_filename(scholarship_name)}"
            f"_申請資料_{academic_year}_{semester_label}"
            f"_{_sanitize_filename(college_name or '全校')}.zip"
        )

        return buf, zip_filename

    async def _get_scholarship_and_college_info(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> Tuple[str, Optional[str]]:
        """Get scholarship name and college name for ZIP filename."""
        stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_type_id)
        result = await self.db.execute(stmt)
        scholarship = result.scalar_one_or_none()
        if not scholarship:
            raise ValueError(f"找不到獎學金類型 ID={scholarship_type_id}")

        scholarship_name = scholarship.name

        # Get college name from first matching application's student_data
        college_name = None
        if college_code:
            app_stmt = (
                select(Application)
                .where(
                    Application.scholarship_type_id == scholarship_type_id,
                    Application.academic_year == academic_year,
                )
                .limit(1)
            )
            if semester:
                app_stmt = app_stmt.where(Application.semester == semester)
            app_result = await self.db.execute(app_stmt)
            sample_app = app_result.scalar_one_or_none()
            if sample_app and sample_app.student_data:
                college_name = sample_app.student_data.get("trm_academyname")

        return scholarship_name, college_name

    async def _query_applications(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> List[Application]:
        """Query applications with their files, filtered by college if needed."""
        stmt = (
            select(Application)
            .options(selectinload(Application.files))
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
            )
        )

        if semester:
            stmt = stmt.where(Application.semester == semester)

        result = await self.db.execute(stmt)
        applications = list(result.scalars().all())

        # Filter by college_code using student_data
        if college_code:
            applications = [
                app for app in applications
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
        try:
            pdf_bytes = self._generate_summary_pdf(app, scholarship_name, academic_year, semester)
            zf.writestr(f"{base_path}/學生資料彙整.pdf", pdf_bytes)
        except Exception as e:
            logger.error(f"Failed to generate summary PDF for app {app.id}: {e}")
            zf.writestr(
                f"{base_path}/_錯誤_彙整PDF生成失敗.txt",
                f"PDF 生成失敗：{str(e)}",
            )

        # Add uploaded files from ApplicationFile records
        file_type_counter: Dict[str, int] = defaultdict(int)
        for af in app.files:
            file_type_counter[af.file_type or "other"] += 1
            count = file_type_counter[af.file_type or "other"]
            label = FILE_TYPE_LABELS.get(af.file_type or "other", "其他文件")

            # Determine file extension from original filename or mime_type
            ext = ""
            if af.original_filename and "." in af.original_filename:
                ext = "." + af.original_filename.rsplit(".", 1)[1]
            elif af.mime_type and "/" in af.mime_type:
                ext_map = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
                ext = ext_map.get(af.mime_type, "")

            # Add sequence number only if multiple files of same type
            total_of_type = sum(1 for f in app.files if (f.file_type or "other") == (af.file_type or "other"))
            if total_of_type > 1:
                filename = f"{label}_{count}{ext}"
            else:
                filename = f"{label}{ext}"

            try:
                response = self.minio.get_file_stream(af.object_name)
                file_bytes = response.read()
                response.close()
                response.release_conn()
                zf.writestr(f"{base_path}/{_sanitize_filename(filename)}", file_bytes)
            except Exception as e:
                logger.error(f"Failed to fetch file {af.object_name} for app {app.id}: {e}")
                zf.writestr(
                    f"{base_path}/_錯誤_找不到檔案_{_sanitize_filename(label)}.txt",
                    f"檔案下載失敗：{af.original_filename or af.object_name}\n錯誤：{str(e)}",
                )

    def _generate_summary_pdf(
        self,
        app: Application,
        scholarship_name: str,
        academic_year: int,
        semester: Optional[str],
    ) -> bytes:
        """Generate a student summary PDF from the HTML template."""
        student = app.student_data or {}
        submitted = app.submitted_form_data or {}

        # Degree label
        degree_raw = str(student.get("trm_degree", ""))
        degree_label = DEGREE_LABELS.get(degree_raw, degree_raw or "—")

        # Semester label
        semester_map = {"first": "第一學期", "second": "第二學期"}
        semester_label = semester_map.get(semester, "全學年") if semester else "全學年"

        # Form fields
        form_fields = []
        fields_data = submitted.get("fields", {})
        for field_id in sorted(fields_data.keys()):
            field = fields_data[field_id]
            form_fields.append({
                "label": field.get("field_id", field_id),
                "value": field.get("value", ""),
            })

        # Document list
        documents = []
        for doc in submitted.get("documents", []):
            documents.append({
                "name": doc.get("document_type") or doc.get("document_id", "未知文件"),
                "upload_time": doc.get("upload_time", ""),
            })

        # Render HTML
        template = self._jinja_env.get_template("student_summary.html")
        html_content = template.render(
            student=student,
            degree_label=degree_label,
            scholarship_name=scholarship_name,
            academic_year=academic_year,
            semester_label=semester_label,
            export_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
            form_fields=form_fields,
            documents=documents,
        )

        # Generate PDF
        pdf = weasyprint.HTML(string=html_content).write_pdf()
        return pdf
