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
from typing import Literal, Optional
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import require_scholarship_manager
from app.db.deps import get_db
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipType
from app.models.student import Department
from app.models.user import User, UserRole
from app.services.college_ranking_export_service import (
    CollegeRankingExportService,
    ExportRow,
)

# Re-exported so existing callers/tests can keep importing _sort_key from this
# module; the single definition now lives in the service layer.
from app.services.export_summary_tables import _sort_key

from ._helpers import (
    _check_academic_year_permission,
    _check_scholarship_permission,
    load_export_aux_data,
    normalize_semester_value,
)

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
    department_code: str = Query(
        ...,
        min_length=1,
        description="Department code(s) — Department.code; comma-separated to bundle a name group",
    ),
    current_user: User = Depends(require_scholarship_manager),
    db: AsyncSession = Depends(get_db),
):
    """Generate the 申請總表 Excel for one department."""

    normalised_semester = normalize_semester_value(semester)

    log_extra = {
        "actor_user_id": current_user.id,
        "actor_role": (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)),
        "scholarship_type_id": scholarship_type_id,
        "academic_year": academic_year,
        "semester": normalised_semester,
        "department_code": department_code,
        "scope": "single",
    }

    if not await _check_scholarship_permission(current_user, scholarship_type_id, db):
        logger.warning("department-summary-export denied: scholarship permission missing", extra=log_extra)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限存取此獎學金類型")
    if not await _check_academic_year_permission(current_user, academic_year, db):
        logger.warning("department-summary-export denied: academic-year permission missing", extra=log_extra)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限存取此學年度")

    # Resolve department rows + auth check. department_code may be a comma-separated
    # group of codes sharing a display name (e.g. 資訊工程學系 = 117/217/317/1550); the
    # export then bundles every code in the group into one workbook.
    requested_codes = [c.strip() for c in department_code.split(",") if c.strip()]
    if not requested_codes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未提供系所代碼")

    depts = list((await db.execute(select(Department).where(Department.code.in_(requested_codes)))).scalars().all())
    found_codes = {d.code for d in depts}
    missing = [c for c in requested_codes if c not in found_codes]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到系所代碼 {', '.join(missing)}",
        )

    if current_user.role not in (UserRole.admin, UserRole.super_admin):
        user_college = (current_user.college_code or "").strip()
        for dept in depts:
            dept_academy = (dept.academy_code or "").strip()
            if not user_college or not dept_academy or user_college != dept_academy:
                logger.warning(
                    "department-summary-export denied: cross-college export attempt",
                    extra={**log_extra, "user_college": user_college, "dept_academy": dept_academy},
                )
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
        Application.status != ApplicationStatus.deleted.value,
    )
    if normalised_semester is None:
        stmt = stmt.where(Application.semester.is_(None))
    else:
        stmt = stmt.where(Application.semester == normalised_semester)

    raw_apps = list((await db.execute(stmt)).scalars().all())
    apps = [a for a in raw_apps if ((a.student_data or {}).get("std_depno") or "").strip() in found_codes]
    apps.sort(key=_sort_key)

    # Aux data
    dynamic_fields, sub_type_labels, account_by_user, advisor_by_user = await load_export_aux_data(
        db,
        scholarship_type=stype,
        applications=apps,
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
    name_by_code = {d.code: d.name for d in depts}
    dept_name = name_by_code.get(requested_codes[0]) or requested_codes[0]
    title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {dept_name}"
    sheet_name = f"{academic_year}學年"
    base_filename = (
        f"{academic_year}學年度{scholarship_name}學生資料彙整表" f"_{_sanitise_filename_part(dept_name)}.xlsx"
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

    logger.info(
        "department-summary-export issued (single): dept=%s row_count=%d size_bytes=%d",
        department_code,
        len(export_rows),
        len(payload),
        extra={
            "actor_user_id": current_user.id,
            **log_extra,
            "dept_name": dept_name,
            "row_count": len(export_rows),
            "size_bytes": len(payload),
            "export_filename": base_filename,
        },
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
    scope: Literal["college", "all"] = Query(...),
    academy_code: Optional[str] = Query(
        None,
        description="Academy (學院) code to export when scope='college'; admins may pick any college",
    ),
    current_user: User = Depends(require_scholarship_manager),
    db: AsyncSession = Depends(get_db),
):
    """Generate a ZIP archive containing one 申請總表 xlsx per department."""

    normalised_semester = normalize_semester_value(semester)

    log_extra = {
        "actor_user_id": current_user.id,
        "actor_role": (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)),
        "scholarship_type_id": scholarship_type_id,
        "academic_year": academic_year,
        "semester": normalised_semester,
        "scope": scope,
    }

    if not await _check_scholarship_permission(current_user, scholarship_type_id, db):
        logger.warning("department-summary-export-bulk denied: scholarship permission missing", extra=log_extra)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限存取此獎學金類型")
    if not await _check_academic_year_permission(current_user, academic_year, db):
        logger.warning("department-summary-export-bulk denied: academic-year permission missing", extra=log_extra)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限存取此學年度")

    is_admin = current_user.role in (UserRole.admin, UserRole.super_admin)

    if scope == "all" and not is_admin:
        logger.warning(
            "department-summary-export-bulk denied: non-admin requested 'all' scope",
            extra=log_extra,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="學院使用者僅能匯出本學院資料",
        )

    if scope == "college":
        # Admins may target any academy via academy_code; a college user is
        # always pinned to their own college_code and cannot cross-export.
        requested_academy = (academy_code or "").strip()
        if is_admin:
            college_code = requested_academy or (current_user.college_code or "").strip()
        else:
            college_code = (current_user.college_code or "").strip()
            if requested_academy and requested_academy != college_code:
                logger.warning(
                    "department-summary-export-bulk denied: cross-college academy_code",
                    extra={**log_extra, "requested_academy": requested_academy, "user_college": college_code},
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="無權限匯出此學院之資料",
                )
        if not college_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="未設定學院，無法使用本學院範圍",
            )
        dept_rows = (
            (await db.execute(select(Department).where(Department.academy_code == college_code))).scalars().all()
        )
        target_dept_codes = [d.code for d in dept_rows if d.code]
        resolved_college_code = college_code
    else:  # scope == "all"
        target_dept_codes = None  # no dept filter
        resolved_college_code = None

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
        Application.status != ApplicationStatus.deleted.value,
    )
    if normalised_semester is None:
        stmt = stmt.where(Application.semester.is_(None))
    else:
        stmt = stmt.where(Application.semester == normalised_semester)

    raw_apps = list((await db.execute(stmt)).scalars().all())
    if target_dept_codes is not None:
        allowed = set(target_dept_codes)
        apps = [a for a in raw_apps if ((a.student_data or {}).get("std_depno") or "").strip() in allowed]
    else:
        apps = raw_apps

    if not apps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到符合條件的申請資料",
        )

    apps.sort(key=_sort_key)

    # Group by std_depno
    groups: dict[str, list[Application]] = {}
    for app in apps:
        dept_code = ((app.student_data or {}).get("std_depno") or "").strip() or "未知"
        groups.setdefault(dept_code, []).append(app)

    # Department name lookup
    dept_codes = list(groups.keys())
    dept_name_rows = (await db.execute(select(Department).where(Department.code.in_(dept_codes)))).scalars().all()
    name_by_code = {d.code: d.name for d in dept_name_rows}

    # Aux data — loaded once over the union of applicants
    dynamic_fields, sub_type_labels, account_by_user, advisor_by_user = await load_export_aux_data(
        db,
        scholarship_type=stype,
        applications=apps,
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
                f"_{_sanitise_filename_part(dept_name)}_{_sanitise_filename_part(dept_code)}.xlsx"
            )
            zf.writestr(inner_name, xlsx_bytes)

    payload = buf.getvalue()

    scope_label = resolved_college_code if scope == "college" else "全部"
    base_filename = (
        f"{academic_year}學年度{scholarship_name}學生資料彙整表"
        f"_{_sanitise_filename_part(scope_label or '全部')}.zip"
    )
    encoded = _url_quote(base_filename, safe="")

    logger.info(
        "department-summary-export-bulk issued: scope=%s departments=%d row_count=%d size_bytes=%d",
        scope,
        len(groups),
        len(apps),
        len(payload),
        extra={
            "actor_user_id": current_user.id,
            **log_extra,
            "departments_count": len(groups),
            "row_count": len(apps),
            "size_bytes": len(payload),
            "export_filename": base_filename,
        },
    )

    return StreamingResponse(
        iter([payload]),
        media_type=ZIP_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Content-Length": str(len(payload)),
        },
    )
