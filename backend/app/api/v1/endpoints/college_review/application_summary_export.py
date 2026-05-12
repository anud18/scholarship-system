"""
Application Summary (申請總表) Excel Export Endpoints

Two endpoints, both under /api/v1/college-review/applications/:
- GET /department-summary-export       → single department .xlsx
- GET /department-summary-export-bulk  → multi-department .zip

Reuses CollegeRankingExportService with ExportRow.rank_position=None so the
學院初審會議之學院排序 column renders empty cells.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from typing import Optional
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import require_college
from app.db.deps import get_db
from app.models.application import Application
from app.models.scholarship import ScholarshipType
from app.models.student import Department
from app.models.user import User, UserRole
from app.services.college_ranking_export_service import (
    CollegeRankingExportService,
    ExportRow,
)

from ._helpers import load_export_aux_data, normalize_semester_value

logger = logging.getLogger(__name__)

router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ZIP_MEDIA_TYPE = "application/zip"

# Characters not allowed in cross-platform filenames
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|]')


def _sanitise_filename_part(value: str) -> str:
    return _UNSAFE_FILENAME_RE.sub("_", value).strip() or "untitled"


@router.get("/applications/department-summary-export")
async def export_department_summary_single(
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None, description="first / second / yearly / null"),
    department_code: str = Query(..., min_length=1, description="Department code (Department.code)"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Generate the 申請總表 Excel for one department."""

    normalised_semester = normalize_semester_value(semester)

    # Resolve department row + auth check
    dept = (
        await db.execute(select(Department).where(Department.code == department_code))
    ).scalar_one_or_none()
    if dept is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到系所代碼 {department_code}",
        )

    if current_user.role not in (UserRole.admin, UserRole.super_admin):
        user_college = (current_user.college_code or "").strip()
        dept_academy = (dept.academy_code or "").strip()
        if not user_college or not dept_academy or user_college != dept_academy:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="無權限匯出此系所之資料",
            )

    # Load scholarship type (with sub_type_configs)
    stype = (
        await db.execute(
            select(ScholarshipType)
            .where(ScholarshipType.id == scholarship_type_id)
            .options(selectinload(ScholarshipType.sub_type_configs))
        )
    ).scalar_one_or_none()
    if stype is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到獎學金類型 ID={scholarship_type_id}",
        )

    # Load applications. student_data is plain JSON (not JSONB) so filter by
    # std_depno in Python rather than via SQL JSON-path. Typical N is < 1k per
    # (scholarship_type, year, semester) so this is fine.
    stmt = select(Application).where(
        Application.scholarship_type_id == scholarship_type_id,
        Application.academic_year == academic_year,
        Application.deleted_at.is_(None),
        Application.status != "deleted",
    )
    if normalised_semester is None:
        stmt = stmt.where(Application.semester.is_(None))
    else:
        stmt = stmt.where(Application.semester == normalised_semester)

    raw_apps = list((await db.execute(stmt)).scalars().all())
    apps = [
        a for a in raw_apps
        if ((a.student_data or {}).get("std_depno") or "").strip() == department_code
    ]
    apps.sort(key=lambda a: ((a.student_data or {}).get("std_stdcode") or "", a.id))

    # Aux data
    dynamic_fields, sub_type_labels, account_by_user, advisor_by_user = await load_export_aux_data(
        db, scholarship_type=stype, applications=apps,
    )

    # Build rows with rank_position=None — empty cell in column 2
    export_rows = [
        ExportRow(
            rank_position=None,
            application=app,
            bank_account=account_by_user.get(app.user_id),
            advisor_names=advisor_by_user.get(app.user_id),
        )
        for app in apps
    ]

    scholarship_name = stype.name or "獎學金"
    dept_name = dept.name or department_code
    title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {dept_name}"
    sheet_name = f"{academic_year}學年"
    base_filename = (
        f"{academic_year}學年度{scholarship_name}學生資料彙整表"
        f"_{_sanitise_filename_part(dept_name)}.xlsx"
    )
    encoded = _url_quote(base_filename, safe="")

    service = CollegeRankingExportService()
    payload = service.build_workbook(
        rows=export_rows,
        dynamic_fields=dynamic_fields,
        sub_type_labels=sub_type_labels,
        title=title,
        sheet_name=sheet_name,
    )

    return StreamingResponse(
        iter([payload]),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Content-Length": str(len(payload)),
        },
    )


@router.get("/applications/department-summary-export-bulk")
async def export_department_summary_bulk(
    scholarship_type_id: int = Query(...),
    academic_year: int = Query(...),
    semester: Optional[str] = Query(None),
    scope: str = Query(..., pattern="^(college|all)$"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Generate a ZIP archive containing one 申請總表 xlsx per department."""

    normalised_semester = normalize_semester_value(semester)
    is_admin = current_user.role in (UserRole.admin, UserRole.super_admin)

    if scope == "all" and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="學院使用者僅能匯出本學院資料",
        )

    if scope == "college":
        college_code = (current_user.college_code or "").strip()
        if not college_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="未設定學院，無法使用本學院範圍",
            )
        dept_rows = (
            await db.execute(
                select(Department).where(Department.academy_code == college_code)
            )
        ).scalars().all()
        target_dept_codes = [d.code for d in dept_rows if d.code]
    else:  # scope == "all"
        target_dept_codes = None  # no dept filter

    # Load scholarship type
    stype = (
        await db.execute(
            select(ScholarshipType)
            .where(ScholarshipType.id == scholarship_type_id)
            .options(selectinload(ScholarshipType.sub_type_configs))
        )
    ).scalar_one_or_none()
    if stype is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到獎學金類型 ID={scholarship_type_id}",
        )

    # Empty target list for college scope → no matches
    if target_dept_codes is not None and not target_dept_codes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到符合條件的申請資料",
        )

    # Load applications
    stmt = select(Application).where(
        Application.scholarship_type_id == scholarship_type_id,
        Application.academic_year == academic_year,
        Application.deleted_at.is_(None),
        Application.status != "deleted",
    )
    if normalised_semester is None:
        stmt = stmt.where(Application.semester.is_(None))
    else:
        stmt = stmt.where(Application.semester == normalised_semester)

    raw_apps = list((await db.execute(stmt)).scalars().all())
    if target_dept_codes is not None:
        allowed = set(target_dept_codes)
        apps = [
            a for a in raw_apps
            if ((a.student_data or {}).get("std_depno") or "").strip() in allowed
        ]
    else:
        apps = raw_apps

    if not apps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到符合條件的申請資料",
        )

    apps.sort(key=lambda a: ((a.student_data or {}).get("std_stdcode") or "", a.id))

    # Group by std_depno
    groups: dict[str, list] = {}
    for app in apps:
        dept_code = ((app.student_data or {}).get("std_depno") or "").strip() or "未知"
        groups.setdefault(dept_code, []).append(app)

    # Department name lookup
    dept_codes = list(groups.keys())
    dept_name_rows = (
        await db.execute(select(Department).where(Department.code.in_(dept_codes)))
    ).scalars().all()
    name_by_code = {d.code: d.name for d in dept_name_rows}

    # Aux data — loaded once over the union of applicants
    dynamic_fields, sub_type_labels, account_by_user, advisor_by_user = await load_export_aux_data(
        db, scholarship_type=stype, applications=apps,
    )

    scholarship_name = stype.name or "獎學金"
    service = CollegeRankingExportService()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dept_code, dept_apps in groups.items():
            dept_name = name_by_code.get(dept_code) or dept_code
            export_rows = [
                ExportRow(
                    rank_position=None,
                    application=app,
                    bank_account=account_by_user.get(app.user_id),
                    advisor_names=advisor_by_user.get(app.user_id),
                )
                for app in dept_apps
            ]
            title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {dept_name}"
            sheet_name = f"{academic_year}學年"
            xlsx_bytes = service.build_workbook(
                rows=export_rows,
                dynamic_fields=dynamic_fields,
                sub_type_labels=sub_type_labels,
                title=title,
                sheet_name=sheet_name,
            )
            inner_name = (
                f"{academic_year}學年度{scholarship_name}學生資料彙整表"
                f"_{_sanitise_filename_part(dept_name)}.xlsx"
            )
            zf.writestr(inner_name, xlsx_bytes)

    payload = buf.getvalue()

    scope_label = current_user.college_code if scope == "college" else "全部"
    base_filename = (
        f"{academic_year}學年度{scholarship_name}學生資料彙整表"
        f"_{_sanitise_filename_part(scope_label or '全部')}.zip"
    )
    encoded = _url_quote(base_filename, safe="")

    return StreamingResponse(
        iter([payload]),
        media_type=ZIP_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Content-Length": str(len(payload)),
        },
    )
