"""
Admin 統計各學院學生申請人數 Excel export.

GET /admin/scholarships/{scholarship_identifier}/college-applicant-stats/export

Counts the applications the 審核管理 page lists (everything except draft and
deleted) for one scholarship and academic year, per college × funding agency.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.endpoints.college_review._helpers import normalize_semester_value
from app.core.security import require_admin
from app.db.deps import get_db
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.services.college_stats_export_service import (
    APPLICANT_COUNT_LABEL,
    APPLICANT_REPORT_NAME,
    StatsRecord,
    build_workbook,
    scholarship_stats_columns,
    stats_period_label,
    tally_college_counts,
)
from app.services.stats_applicant_source import load_applicant_rows
from app.utils.application_helpers import get_academy_code_from_data
from app.utils.export_download import sanitise_filename_part, xlsx_attachment_response

logger = logging.getLogger(__name__)

router = APIRouter()


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

    applicants = await load_applicant_rows(
        db, scholarship_type_id=scholarship.id, academic_year=academic_year, semester=semester
    )
    records = [
        StatsRecord(
            user_id=row.user_id,
            academy_code=get_academy_code_from_data(row.student_data or {}),
            sub_type_codes=tuple(row.sub_type_codes),
        )
        for row in applicants
    ]
    columns = scholarship_stats_columns(scholarship, records, single_column_label=APPLICANT_COUNT_LABEL)
    rows = tally_college_counts(records, columns)

    period = stats_period_label(academic_year, normalize_semester_value(semester))
    scholarship_name = scholarship.name or scholarship.code
    payload = build_workbook(
        title=f"{period}{scholarship_name} {APPLICANT_REPORT_NAME}",
        columns=columns,
        rows=rows,
        sheet_name=APPLICANT_REPORT_NAME,
    )
    filename = f"{sanitise_filename_part(f'{period}{scholarship_name}')}_{APPLICANT_REPORT_NAME}.xlsx"

    logger.info(
        "college-applicant-stats export issued: scholarship=%s year=%s semester=%s applications=%d",
        scholarship.code,
        academic_year,
        semester,
        len(records),
        extra={"actor_user_id": current_user.id},
    )

    return xlsx_attachment_response(payload, filename)
