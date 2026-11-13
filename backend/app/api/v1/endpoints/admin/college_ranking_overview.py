"""
Admin 各學院排名繳交總覽.

GET /admin/scholarships/{scholarship_identifier}/college-ranking-overview

Lists, for one scholarship and period, every college's ranking status
(尚未建立排名 / 草稿 / 草稿已匯入 / 已確認) with the last Excel import of each
ranking. Each ranking is downloaded through the existing
GET /college-review/rankings/{id}/export-excel, which admins may call for any college.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.admin._helpers import load_scholarship_by_identifier
from app.core.security import require_admin
from app.db.deps import get_db
from app.models.user import User
from app.services.college_ranking_overview_service import CollegeRankingOverviewService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/scholarships/{scholarship_identifier}/college-ranking-overview")
async def get_college_ranking_overview(
    scholarship_identifier: str = Path(..., pattern=r"^(\d+|[a-z_]{1,50})$"),
    academic_year: int = Query(..., ge=1, le=999, description="ROC academic year"),
    semester: Optional[str] = Query(
        None,
        pattern=r"^(first|second|yearly)$",
        description="first / second / yearly; omit for a year-based scholarship",
    ),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Ranking status of every college for one scholarship and period."""
    scholarship = await load_scholarship_by_identifier(db, scholarship_identifier)

    overview = await CollegeRankingOverviewService(db).build_overview(
        scholarship_type_id=scholarship.id, academic_year=academic_year, semester=semester
    )

    return {
        "success": True,
        "message": "各學院排名繳交總覽查詢成功",
        "data": {
            "scholarship": {"id": scholarship.id, "code": scholarship.code, "name": scholarship.name},
            "academic_year": academic_year,
            "semester": semester,
            **overview,
        },
    }
