"""
Embedded Summary Tables (申請總表) for the export package.

Builds the 學生資料彙整表 Excel workbooks embedded inside the /export-package
ZIP: one college-level table at the ZIP root plus one per-department table
inside each department folder.

Applications are NOT re-queried here — they are the exact same dept_groups
ExportPackageService already assembled, so every table's rows match the
student folders sitting next to it in the ZIP.

Reuses CollegeRankingExportService.build_workbook (pure xlsx render) and
load_export_aux_data (dynamic fields / sub-type labels / bank account /
advisor names).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.college_review._helpers import load_export_aux_data
from app.models.application import Application
from app.models.scholarship import ScholarshipType
from app.services.college_ranking_export_service import (
    CollegeRankingExportService,
    ExportRow,
)

# NOTE: imported at top is safe — export_package_service has no top-level
# import of this module (it imports build_embedded_summary_tables lazily
# inside generate_export_zip), so there is no import cycle.
from app.services.export_package_service import _sanitize_filename

logger = logging.getLogger(__name__)


def _sort_key(a: Application):
    """Sort key: renewal applications first, then by student code (blanks last)."""
    code = ((a.student_data or {}).get("std_stdcode") or "").strip()
    renewal_group = 0 if getattr(a, "is_renewal", False) else 1  # 0=renewal first, 1=new
    return (renewal_group, not code, code, a.id)


def _dept_name_from_apps(apps: List[Application]) -> str:
    """Department display name taken from the first application's student_data."""
    for a in apps:
        name = (a.student_data or {}).get("trm_depname")
        if name:
            return str(name)
    return "未知系所"


async def build_embedded_summary_tables(
    db: AsyncSession,
    scholarship_type: ScholarshipType,
    dept_groups: Dict[str, List[Application]],
    college_name: Optional[str],
    academic_year: int,
) -> Dict[str, bytes]:
    """Return { zip_inner_path : xlsx_bytes } for the college-level table
    (ZIP root) plus one table per department folder.

    The same dept_groups assembled by ExportPackageService is used directly,
    guaranteeing each table's rows match the student folders next to it.
    """
    all_apps = [app for apps in dept_groups.values() for app in apps]

    dynamic_fields, sub_type_labels, account_by_user, advisor_by_user = await load_export_aux_data(
        db,
        scholarship_type=scholarship_type,
        applications=all_apps,
    )

    scholarship_name = scholarship_type.name or "獎學金"
    service = CollegeRankingExportService()
    sheet_name = f"{academic_year}學年"
    base_name = f"{academic_year}學年度{scholarship_name}學生資料彙整表"
    result: Dict[str, bytes] = {}

    def _rows(apps: List[Application]) -> List[ExportRow]:
        ordered = sorted(apps, key=_sort_key)
        return [
            ExportRow(
                rank_position=None,  # 學院初審會議之學院排序 left blank (ranking not done yet)
                application=app,
                bank_account=account_by_user.get(app.user_id),
                advisor_names=advisor_by_user.get(app.user_id),
            )
            for app in ordered
        ]

    async def _emit(rows: List[ExportRow], scope: str, ok_key: str, err_key: str, err_prefix: str) -> None:
        """Render one workbook into result[ok_key]; on failure write a placeholder at err_key.

        One bad table must not abort the whole ZIP.
        """
        try:
            result[ok_key] = await asyncio.to_thread(
                service.build_workbook,
                rows=rows,
                dynamic_fields=dynamic_fields,
                sub_type_labels=sub_type_labels,
                title=f"{base_name} - {scope}",
                sheet_name=sheet_name,
            )
        except Exception as e:
            logger.exception("summary table build failed: %s", scope)
            result[err_key] = f"{err_prefix}：{e}".encode("utf-8")

    # Single pass: build each department's table and accumulate the college-level rows
    # (department-grouped, sorted within each group) so rows are sorted/built only once.
    college_rows: List[ExportRow] = []
    for dept_folder, apps in sorted(dept_groups.items()):
        dept_rows = _rows(apps)
        college_rows.extend(dept_rows)
        dept_name = _dept_name_from_apps(apps)
        dept_fname = _sanitize_filename(f"{base_name}_{dept_name}.xlsx")
        await _emit(
            dept_rows,
            dept_name,
            f"{dept_folder}/{dept_fname}",
            f"{dept_folder}/_錯誤_總表生成失敗.txt",
            "系總表生成失敗",
        )

    college_label = college_name or "全校"
    await _emit(
        college_rows,
        college_label,
        _sanitize_filename(f"{base_name}_{college_label}.xlsx"),
        "_錯誤_學院總表生成失敗.txt",
        "學院總表生成失敗",
    )

    return result
