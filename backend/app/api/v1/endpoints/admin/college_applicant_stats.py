"""
Admin 統計各學院學生申請人數 Excel export.

GET /admin/scholarships/{scholarship_identifier}/college-applicant-stats/export

Counts the applications the 審核管理 page lists (everything except draft and
deleted) for one scholarship and academic year, per college × funding agency.
"""

import logging
from typing import Optional
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.endpoints.college_review._helpers import normalize_semester_value
from app.core.security import require_admin
from app.db.deps import get_db
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.services.college_applicant_stats_export_service import (
    REPORT_NAME,
    ApplicantRecord,
    build_stats_columns,
    build_workbook,
    tally_college_counts,
)
from app.utils.academic_period import format_academic_period
from app.utils.application_helpers import get_academy_code_from_data
from app.utils.export_download import XLSX_MEDIA_TYPE, sanitise_filename_part

logger = logging.getLogger(__name__)

router = APIRouter()

# Same exclusion as the 審核管理 list (GET /admin/scholarships/{id}/applications).
_EXCLUDED_STATUSES = (ApplicationStatus.draft.value, ApplicationStatus.deleted.value)


async def _load_scholarship(db: AsyncSession, identifier: str) -> ScholarshipType:
    stmt = select(ScholarshipType).options(selectinload(ScholarshipType.sub_type_configs))
    if identifier.isdigit():
        stmt = stmt.where(ScholarshipType.id == int(identifier))
    else:
        stmt = stmt.where(ScholarshipType.code == identifier)
    scholarship = (await db.execute(stmt)).scalar_one_or_none()
    if scholarship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到此獎學金類型")
    return scholarship


def _period_label(academic_year: int, semester: Optional[str]) -> str:
    if semester is None:
        return f"{academic_year}學年度"
    return format_academic_period(academic_year, semester)


@router.get("/scholarships/{scholarship_identifier}/college-applicant-stats/export")
async def export_college_applicant_stats(
    scholarship_identifier: str = Path(..., pattern=r"^(\d+|[a-z_]{1,50})$"),
    academic_year: int = Query(..., ge=1, le=999, description="ROC academic year"),
    semester: Optional[str] = Query(
        None,
        pattern=r"^(first|second|yearly)$",
        description="first / second / yearly; omit to include every semester of the year",
    ),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Download 統計各學院學生申請人數 (.xlsx) for one scholarship and academic year."""
    scholarship = await _load_scholarship(db, scholarship_identifier)

    # Only the three fields the tally reads — skip submitted_form_data & co.
    stmt = select(Application.user_id, Application.student_data, Application.scholarship_subtype_list).where(
        Application.scholarship_type_id == scholarship.id,
        Application.academic_year == academic_year,
        Application.deleted_at.is_(None),
        Application.status.notin_(_EXCLUDED_STATUSES),
    )
    normalised_semester = normalize_semester_value(semester)
    if semester is not None:
        # "yearly" normalises to None ⇒ year-based scholarships store NULL.
        stmt = stmt.where(
            Application.semester.is_(None)
            if normalised_semester is None
            else Application.semester == normalised_semester
        )
    records = [
        ApplicantRecord(
            user_id=user_id,
            academy_code=get_academy_code_from_data(student_data or {}),
            sub_type_codes=tuple(sub_types or ()),
        )
        for user_id, student_data, sub_types in (await db.execute(stmt)).all()
    ]
    columns = build_stats_columns(
        [(c.sub_type_code, c.name) for c in scholarship.get_active_sub_type_configs()],
        records,
        known_names={c.sub_type_code: c.name for c in scholarship.sub_type_configs},
    )
    rows = tally_college_counts(records, columns)

    period = _period_label(academic_year, normalised_semester)
    scholarship_name = scholarship.name or scholarship.code
    payload = build_workbook(title=f"{period}{scholarship_name} {REPORT_NAME}", columns=columns, rows=rows)
    filename = f"{sanitise_filename_part(f'{period}{scholarship_name}')}_{REPORT_NAME}.xlsx"

    logger.info(
        "college-applicant-stats export issued: scholarship=%s year=%s semester=%s applications=%d",
        scholarship.code,
        academic_year,
        semester,
        len(records),
        extra={"actor_user_id": current_user.id},
    )

    return StreamingResponse(
        iter([payload]),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote(filename, safe='')}",
            "Content-Length": str(len(payload)),
        },
    )
