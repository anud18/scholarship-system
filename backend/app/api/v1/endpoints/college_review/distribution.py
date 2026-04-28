"""
Distribution & Quota Management API Endpoints

Handles:
- Distribution details retrieval
- Quota status monitoring
- Roster status checking
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import require_college
from app.db.deps import get_db
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.schemas.response import ApiResponse
from app.services.college_review_service import (
    CollegeReviewError,
    CollegeReviewService,
)

from ._helpers import normalize_semester_value

logger = logging.getLogger(__name__)

router = APIRouter()


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
        logger.warning(f"Invalid quota status parameters: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid parameters: {str(e)}")
    except CollegeReviewError as e:
        logger.error(f"College review error retrieving quota status: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving quota status: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve quota status")


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
        service = CollegeReviewService(db)
        roster_status = await service.check_ranking_roster_status(ranking_id)

        return ApiResponse(success=True, message="Roster status retrieved successfully", data=roster_status)

    except Exception as e:
        logger.error(f"Error retrieving roster status for ranking {ranking_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve roster status"
        )


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
        logger.error(f"Error retrieving distribution details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve distribution details: {str(e)}",
        )
