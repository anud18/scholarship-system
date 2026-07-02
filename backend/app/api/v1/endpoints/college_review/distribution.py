"""
Distribution & Quota Management API Endpoints

Handles:
- Distribution details retrieval
- Quota status monitoring
- Roster status checking
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from app.core.security import require_college
from app.db.deps import get_db
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.schemas.response import ApiResponse
from app.utils.application_helpers import (
    get_college_code_from_data,
    get_nycu_id_from_data,
    get_student_name_from_data,
)
from app.services.college_review_service import (
    CollegeReviewError,
    CollegeReviewService,
)

from ._helpers import assert_can_manage_ranking, normalize_semester_value

logger = logging.getLogger(__name__)

router = APIRouter()


def _assert_ranking_visible_or_404(ranking, current_user: User) -> None:
    """Authorize ranking access for read endpoints, translating a cross-college
    403 into a 404.

    ``assert_can_manage_ranking`` raises 403 for a college that doesn't own the
    ranking. On these read-by-id endpoints that turns the endpoint into an
    enumeration oracle (403 = "exists but not your college" vs 404 = "no such
    ranking"). Collapsing both to 404 removes that signal (#1081-C/D).
    """
    try:
        assert_can_manage_ranking(ranking, current_user)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found") from exc
        raise


@router.get("/quota-status")
async def get_quota_status(
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None, description="Semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Get quota status for a scholarship type

    Returns quota status including college-specific quota if user has college_code
    """

    try:
        service = CollegeReviewService(db)
        quota_status = await service.get_quota_status(
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
            college_code=current_user.college_code,  # Pass college_code to calculate college quota
        )

        return ApiResponse(success=True, message="Quota status retrieved successfully", data=quota_status)

    except ValueError as e:
        logger.warning("Invalid quota status parameters", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parameters") from e
    except CollegeReviewError as e:
        logger.exception("College review error retrieving quota status")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except Exception as e:
        logger.exception("Unexpected error retrieving quota status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve quota status"
        ) from e


@router.get("/rankings/{ranking_id}/roster-status")
async def get_ranking_roster_status(
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """
    Get roster status for a ranking
    查詢排名的造冊狀態和進展
    """
    try:
        # SECURITY (#1081-D): same missing-scope root cause as distribution-details.
        # Load the ranking's owning college_code and authorize before returning its
        # roster metadata, so a college can't read another college's ranking by id.
        ranking_stmt = (
            select(CollegeRanking)
            .options(load_only(CollegeRanking.id, CollegeRanking.college_code))
            .where(CollegeRanking.id == ranking_id)
        )
        ranking = (await db.execute(ranking_stmt)).scalar_one_or_none()
        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")
        _assert_ranking_visible_or_404(ranking, current_user)

        service = CollegeReviewService(db)
        roster_status = await service.check_ranking_roster_status(ranking_id)

        return ApiResponse(success=True, message="Roster status retrieved successfully", data=roster_status)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving roster status for ranking {ranking_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve roster status"
        ) from e


@router.get("/rankings/{ranking_id}/distribution-details")
async def get_distribution_details(
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed distribution results for a ranking

    Returns allocation details by sub-type and college including:
    - Admitted students (正取)
    - Backup students (備取) with positions
    - Rejected students
    """

    try:
        # Get ranking with items
        stmt = (
            select(CollegeRanking)
            .options(
                selectinload(CollegeRanking.items).selectinload(CollegeRankingItem.application),
                selectinload(CollegeRanking.scholarship_type).selectinload(ScholarshipType.sub_type_configs),
            )
            .where(CollegeRanking.id == ranking_id)
        )
        result = await db.execute(stmt)
        ranking = result.scalar_one_or_none()

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # SECURITY (#1081-C): rankings are single-college and this response carries
        # applicant PII, ranks and rejection reasons. Without scoping, a College-A
        # account could read College-B's data by enumerating ranking_id. Cross-college
        # access collapses to 404 (not 403) so it isn't an existence oracle.
        _assert_ranking_visible_or_404(ranking, current_user)

        sub_type_metadata_map: Dict[str, Dict[str, str]] = {}
        if ranking.scholarship_type and getattr(ranking.scholarship_type, "sub_type_configs", None):
            for config in ranking.scholarship_type.sub_type_configs:
                if not config.sub_type_code:
                    continue
                label = config.name or config.sub_type_code
                label_en = config.name_en or label
                sub_type_metadata_map[config.sub_type_code] = {
                    "code": config.sub_type_code,
                    "label": label,
                    "label_en": label_en,
                }

        if ranking.sub_type_code and ranking.sub_type_code not in sub_type_metadata_map:
            fallback_label = ranking.sub_type_code
            sub_type_metadata_map[ranking.sub_type_code] = {
                "code": ranking.sub_type_code,
                "label": fallback_label,
                "label_en": fallback_label,
            }

        def _meta_for_sub_type(code: Optional[str]) -> Dict[str, str]:
            if not code:
                code = "unallocated"
            if code in sub_type_metadata_map:
                return sub_type_metadata_map[code]
            sub_type_metadata_map[code] = {
                "code": code,
                "label": code,
                "label_en": code,
            }
            return sub_type_metadata_map[code]

        def _normalize_quota_value(value: Any) -> int:
            if isinstance(value, (int, float)):
                return int(value)
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0

        normalized_ranking_semester = normalize_semester_value(ranking.semester)
        config_stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == ranking.scholarship_type_id,
                ScholarshipConfiguration.academic_year == ranking.academic_year,
                ScholarshipConfiguration.is_active.is_(True),
            )
        )
        if normalized_ranking_semester:
            config_stmt = config_stmt.where(ScholarshipConfiguration.semester == normalized_ranking_semester)
        else:
            config_stmt = config_stmt.where(ScholarshipConfiguration.semester.is_(None))

        config_result = await db.execute(config_stmt)
        config = config_result.scalar_one_or_none()
        quota_matrix = config.quotas if config and config.quotas else {}

        def initialize_summary_from_quota() -> Dict[str, Dict[str, Any]]:
            summary: Dict[str, Dict[str, Any]] = {}
            for sub_type_code, college_quotas in quota_matrix.items():
                if not isinstance(college_quotas, dict):
                    continue
                meta = _meta_for_sub_type(sub_type_code)
                total_quota = 0
                colleges: Dict[str, Dict[str, Any]] = {}
                for college_code, quota in college_quotas.items():
                    quota_value = _normalize_quota_value(quota)
                    total_quota += quota_value
                    colleges[college_code] = {
                        "quota": quota_value,
                        "admitted_count": 0,
                        "backup_count": 0,
                        "admitted": [],
                        "backup": [],
                    }
                summary[sub_type_code] = {
                    "code": meta["code"],
                    "label": meta["label"],
                    "label_en": meta["label_en"],
                    "total_quota": total_quota,
                    "admitted_total": 0,
                    "backup_total": 0,
                    "colleges": colleges,
                }
            return summary

        def ensure_summary_entry(code: str) -> Dict[str, Any]:
            if code not in distribution_summary:
                meta = _meta_for_sub_type(code)
                distribution_summary[code] = {
                    "code": meta["code"],
                    "label": meta["label"],
                    "label_en": meta["label_en"],
                    "total_quota": 0,
                    "admitted_total": 0,
                    "backup_total": 0,
                    "colleges": {},
                }
            return distribution_summary[code]

        distribution_summary: Dict[str, Dict[str, Any]] = initialize_summary_from_quota()
        rejected_students: List[Dict[str, Any]] = []

        if not ranking.distribution_executed:
            return ApiResponse(
                success=True,
                message="Distribution has not been executed yet",
                data={
                    "ranking_id": ranking_id,
                    "ranking_name": ranking.ranking_name,
                    "distribution_executed": False,
                    "total_allocated": ranking.allocated_count,
                    "total_applications": ranking.total_applications,
                    "distribution_summary": distribution_summary,
                    "rejected": rejected_students,
                    "sub_type_metadata": list(sub_type_metadata_map.values()),
                },
            )

        admitted_total_counter = 0

        for item in ranking.items:
            app = item.application
            if not app or not app.student_data:
                continue

            # Skip deleted applications
            if app.status == "deleted" or app.deleted_at is not None:
                continue

            student_id = app.student_data.get("std_stdcode") or app.student_data.get("nycu_id") or "N/A"
            student_name = app.student_data.get("std_cname") or app.student_data.get("name") or "N/A"
            # std_academyno is the correct field from API, prioritize it
            college_code = (
                app.student_data.get("std_academyno")
                or app.student_data.get("academy_code")
                or app.student_data.get("college_code")
                or app.student_data.get("std_college")
                or "N/A"
            )

            student_info = {
                "rank_position": item.rank_position,
                "student_id": student_id,
                "student_name": student_name,
                "application_id": app.id,
                "app_id": app.app_id,
                "is_renewal": app.is_renewal,
                "renewal_year": app.renewal_year,
            }

            # 優先處理被駁回的學生（管理員駁回 status='rejected'，或學院 N college_rejected=True）
            if item.status == "rejected" or getattr(item, "college_rejected", False):
                if item.status == "rejected":
                    rejection_reason = item.allocation_reason or "申請已被駁回"
                else:
                    rejection_reason = "學院標記不予分配 (N)"
                rejected_students.append(
                    {
                        "rank_position": item.rank_position,
                        "student_id": student_id,
                        "student_name": student_name,
                        "application_id": app.id,
                        "reason": rejection_reason,
                    }
                )
                continue  # 跳過正取/備取處理

            # Handle primary allocation (正取)
            if item.is_allocated and item.allocated_sub_type:
                sub_type = item.allocated_sub_type
                entry = ensure_summary_entry(sub_type)
                colleges = entry.setdefault("colleges", {})

                if college_code not in colleges:
                    quota_value = 0
                    if sub_type in quota_matrix and isinstance(quota_matrix[sub_type], dict):
                        quota_value = _normalize_quota_value(quota_matrix[sub_type].get(college_code))
                    colleges[college_code] = {
                        "quota": quota_value,
                        "admitted_count": 0,
                        "backup_count": 0,
                        "admitted": [],
                        "backup": [],
                    }

                college_entry = colleges[college_code]
                college_entry["admitted"].append(student_info)
                college_entry["admitted_count"] += 1
                entry["admitted_total"] += 1
                admitted_total_counter += 1
            # Handle backup allocations (備取) from backup_allocations array
            # Use independent if (not elif) to allow both primary and backup allocations to be shown
            if (
                item.backup_allocations
                and isinstance(item.backup_allocations, list)
                and len(item.backup_allocations) > 0
            ):
                for backup_alloc in item.backup_allocations:
                    if not isinstance(backup_alloc, dict):
                        continue

                    sub_type = backup_alloc.get("sub_type")
                    backup_college = backup_alloc.get("college")
                    backup_position = backup_alloc.get("backup_position")

                    if not sub_type:
                        continue

                    entry = ensure_summary_entry(sub_type)
                    colleges = entry.setdefault("colleges", {})

                    if backup_college not in colleges:
                        quota_value = 0
                        if sub_type in quota_matrix and isinstance(quota_matrix[sub_type], dict):
                            quota_value = _normalize_quota_value(quota_matrix[sub_type].get(backup_college))
                        colleges[backup_college] = {
                            "quota": quota_value,
                            "admitted_count": 0,
                            "backup_count": 0,
                            "admitted": [],
                            "backup": [],
                        }

                    college_entry = colleges[backup_college]
                    backup_student_info = student_info.copy()
                    backup_student_info["backup_position"] = backup_position
                    college_entry["backup"].append(backup_student_info)
                    college_entry["backup_count"] += 1
                    entry["backup_total"] += 1

            # Handle rejected students (no allocation or backup)
            # Only process as rejected if student has neither primary allocation nor any backup allocations
            if not item.is_allocated and (not item.backup_allocations or len(item.backup_allocations) == 0):
                rejection_reason = item.allocation_reason or "未獲分配（原因未記錄）"
                rejected_students.append(
                    {
                        "rank_position": item.rank_position,
                        "student_id": student_id,
                        "student_name": student_name,
                        "application_id": app.id,
                        "reason": rejection_reason,
                    }
                )

        return ApiResponse(
            success=True,
            message="Distribution details retrieved successfully",
            data={
                "ranking_id": ranking_id,
                "ranking_name": ranking.ranking_name,
                "distribution_executed": ranking.distribution_executed,
                "total_allocated": ranking.allocated_count or admitted_total_counter,
                "total_applications": ranking.total_applications,
                "distribution_summary": distribution_summary,
                "rejected": rejected_students,
                "sub_type_metadata": list(sub_type_metadata_map.values()),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error retrieving distribution details")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve distribution details",
        ) from e


@router.get("/distribution-results")
async def get_college_distribution_results(
    scholarship_type_id: int,
    academic_year: int,
    semester: Optional[str] = None,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """College-facing: this college's own students' distribution outcomes by sub-type.

    Gated by ScholarshipConfiguration.allow_college_view_distribution (admin toggle).
    Scoped to the caller's college_code. Allocation outcome only — no payment PII,
    no allocation-year labels (outcomes for one sub-type are merged across years).
    """
    # Permission first, then read the flag (don't leak flag state to a college
    # with no binding) — same ordering discipline as ranking_management.py.
    college_code = current_user.college_code
    if not college_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="使用者未綁定學院")

    normalized_semester = normalize_semester_value(semester)

    config_stmt = select(ScholarshipConfiguration).where(
        and_(
            ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
            ScholarshipConfiguration.academic_year == academic_year,
            ScholarshipConfiguration.is_active.is_(True),
        )
    )
    if normalized_semester:
        config_stmt = config_stmt.where(ScholarshipConfiguration.semester == normalized_semester)
    else:
        config_stmt = config_stmt.where(ScholarshipConfiguration.semester.is_(None))
    config = (await db.execute(config_stmt)).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到對應的獎學金配置")

    if not config.allow_college_view_distribution:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="分發結果尚未開放查看")

    # Rankings for this (type, year, semester)
    ranking_stmt = select(CollegeRanking).where(
        and_(
            CollegeRanking.scholarship_type_id == scholarship_type_id,
            CollegeRanking.academic_year == academic_year,
        )
    )
    if normalized_semester:
        ranking_stmt = ranking_stmt.where(CollegeRanking.semester == normalized_semester)
    else:
        ranking_stmt = ranking_stmt.where(CollegeRanking.semester.is_(None))
    rankings = (await db.execute(ranking_stmt)).scalars().all()
    ranking_ids = [r.id for r in rankings]
    ranking_sub_type = {r.id: r.sub_type_code for r in rankings}
    distribution_executed = any(r.distribution_executed for r in rankings)

    if not ranking_ids or not distribution_executed:
        return ApiResponse(
            success=True,
            message="尚未分發",
            data={"distribution_executed": distribution_executed, "sub_types": []},
        )

    # Sub-type label metadata (deferred until we know there are distributed results to label)
    st_stmt = (
        select(ScholarshipType)
        .options(selectinload(ScholarshipType.sub_type_configs))
        .where(ScholarshipType.id == scholarship_type_id)
    )
    scholarship_type = (await db.execute(st_stmt)).scalar_one_or_none()
    label_map: Dict[str, Dict[str, str]] = {}
    if scholarship_type and getattr(scholarship_type, "sub_type_configs", None):
        for sc in scholarship_type.sub_type_configs:
            if sc.sub_type_code:
                label_map[sc.sub_type_code] = {
                    "label": sc.name or sc.sub_type_code,
                    "label_en": sc.name_en or sc.name or sc.sub_type_code,
                }

    # Only student_data + deleted_at are read below; avoid hydrating the full Application row.
    items_stmt = (
        select(CollegeRankingItem)
        .options(
            selectinload(CollegeRankingItem.application).load_only(Application.student_data, Application.deleted_at)
        )
        .where(CollegeRankingItem.ranking_id.in_(ranking_ids))
    )
    items = (await db.execute(items_stmt)).scalars().all()

    groups: Dict[str, Dict[str, list]] = defaultdict(lambda: {"admitted": [], "backup": [], "rejected": []})

    for item in items:
        appn = item.application
        if not appn or not appn.student_data:
            continue
        if appn.deleted_at is not None:
            continue
        sd = appn.student_data
        # College scoping (Python-side; student_data is encrypted JSON, the academy code is plaintext).
        # Reuse the canonical student_data accessors so key-alias changes stay in one place.
        if get_college_code_from_data(sd) != college_code:
            continue
        student = {
            "student_number": get_nycu_id_from_data(sd) or "N/A",
            "student_name": get_student_name_from_data(sd),
        }
        fallback_code = ranking_sub_type.get(item.ranking_id) or "unallocated"

        handled = False
        if item.is_allocated and item.allocated_sub_type:
            groups[item.allocated_sub_type]["admitted"].append({**student, "rank_position": item.rank_position})
            handled = True
        if item.backup_allocations and isinstance(item.backup_allocations, list):
            for ba in item.backup_allocations:
                if not isinstance(ba, dict):
                    continue
                st_code = ba.get("sub_type")
                if not st_code:
                    continue
                groups[st_code]["backup"].append({**student, "backup_position": ba.get("backup_position")})
                handled = True
        if not handled:
            groups[fallback_code]["rejected"].append(student)

    sub_types = []
    for code in sorted(groups.keys()):
        m = label_map.get(code, {"label": code, "label_en": code})
        g = groups[code]
        sub_types.append(
            {
                "code": code,
                "label": m["label"],
                "label_en": m["label_en"],
                "admitted": sorted(g["admitted"], key=lambda s: s.get("rank_position") or 0),
                "backup": sorted(g["backup"], key=lambda s: s.get("backup_position") or 0),
                "rejected": g["rejected"],
            }
        )

    return ApiResponse(
        success=True,
        message="分發結果",
        data={"distribution_executed": True, "sub_types": sub_types},
    )
