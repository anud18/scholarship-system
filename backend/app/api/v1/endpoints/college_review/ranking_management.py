"""
Ranking Management API Endpoints

Handles:
- Creating and retrieving rankings
- Updating ranking metadata and order
- Finalizing/unfinalizing rankings
- Deleting rankings
- Importing ranking data from Excel
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rate_limiting import professor_rate_limit
from app.core.security import require_college
from app.db.deps import get_db
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import ScholarshipConfiguration
from app.models.student import Department
from app.models.user import User, UserRole
from app.schemas.college_review import RankingImportItem, RankingOrderUpdate, RankingUpdate
from app.schemas.response import ApiResponse
from app.services.college_review_service import (
    CollegeReviewError,
    CollegeReviewService,
    InvalidRankingDataError,
    RankingModificationError,
    RankingNotFoundError,
)

from ._helpers import normalize_semester_value

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/rankings")
async def get_rankings(
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Get all rankings for the current user or all if admin"""

    try:
        # Build base query
        stmt = select(CollegeRanking)

        # Apply filters
        if current_user.role not in [UserRole.admin, UserRole.super_admin]:
            # Regular college users can only see their own rankings
            stmt = stmt.where(CollegeRanking.created_by == current_user.id)

        if academic_year:
            stmt = stmt.where(CollegeRanking.academic_year == academic_year)
        if semester:
            semester_str = str(semester).strip()
            semester_lower = semester_str.lower()
            if semester_lower.startswith("semester."):
                semester_lower = semester_lower.split(".", 1)[1]

            if semester_lower in {"yearly"}:
                stmt = stmt.where(or_(CollegeRanking.semester.is_(None), CollegeRanking.semester == "yearly"))
            else:
                stmt = stmt.where(CollegeRanking.semester == semester_lower)

        # Execute query
        result = await db.execute(stmt)
        rankings = result.scalars().all()

        # Preload scholarship configurations per (type, year, semester) to avoid N+1 queries
        config_cache: Dict[Tuple[int, int, Optional[str]], Optional[ScholarshipConfiguration]] = {}
        user_college_code = current_user.college_code

        async def get_config_for_ranking(ranking: CollegeRanking) -> Optional[ScholarshipConfiguration]:
            normalized_semester = normalize_semester_value(ranking.semester)
            cache_key = (ranking.scholarship_type_id, ranking.academic_year, normalized_semester)
            if cache_key in config_cache:
                return config_cache[cache_key]

            config_stmt = select(ScholarshipConfiguration).where(
                and_(
                    ScholarshipConfiguration.scholarship_type_id == ranking.scholarship_type_id,
                    ScholarshipConfiguration.academic_year == ranking.academic_year,
                    ScholarshipConfiguration.is_active.is_(True),
                )
            )

            if normalized_semester:
                config_stmt = config_stmt.where(ScholarshipConfiguration.semester == normalized_semester)
            else:
                config_stmt = config_stmt.where(ScholarshipConfiguration.semester.is_(None))

            config_result = await db.execute(config_stmt)
            config_cache[cache_key] = config_result.scalar_one_or_none()
            return config_cache[cache_key]

        # Format response
        rankings_data = []
        for ranking in rankings:
            college_quota: Optional[int] = None

            if user_college_code:
                config = await get_config_for_ranking(ranking)
                if config and config.has_college_quota and config.quotas:
                    if ranking.sub_type_code == "default":
                        # Sum all quotas for this college across sub-types
                        college_quota = config.get_college_total_quota(user_college_code) or None
                    else:
                        quota_value: Optional[int] = None
                        possible_keys: List[str] = []
                        if ranking.sub_type_code:
                            possible_keys.extend(
                                [
                                    ranking.sub_type_code,
                                    ranking.sub_type_code.lower(),
                                    ranking.sub_type_code.upper(),
                                ]
                            )

                        # Preserve order while de-duplicating
                        seen_keys = set()
                        ordered_keys = []
                        for key in possible_keys:
                            if key not in seen_keys:
                                seen_keys.add(key)
                                ordered_keys.append(key)

                        for key in ordered_keys:
                            sub_quota_map = config.quotas.get(key)
                            if isinstance(sub_quota_map, dict) and user_college_code in sub_quota_map:
                                quota_value = sub_quota_map[user_college_code]
                                break

                        college_quota = quota_value if quota_value is not None else None

            normalized_ranking_semester = normalize_semester_value(ranking.semester)

            rankings_data.append(
                {
                    "id": ranking.id,
                    "ranking_name": ranking.ranking_name,
                    "scholarship_type_id": ranking.scholarship_type_id,
                    "sub_type_code": ranking.sub_type_code,
                    "academic_year": ranking.academic_year,
                    "semester": normalized_ranking_semester,
                    "total_applications": ranking.total_applications,
                    "total_quota": ranking.total_quota,
                    "college_quota": college_quota,
                    "allocated_count": ranking.allocated_count,
                    "is_finalized": ranking.is_finalized,
                    "ranking_status": ranking.ranking_status,
                    "distribution_executed": ranking.distribution_executed,
                    "created_at": ranking.created_at.isoformat(),
                    "finalized_at": ranking.finalized_at.isoformat() if ranking.finalized_at else None,
                }
            )

        return ApiResponse(
            success=True, message=f"Retrieved {len(rankings_data)} rankings successfully", data=rankings_data
        )

    except ValueError as e:
        logger.warning(f"Invalid query parameters for rankings: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid query parameters: {str(e)}")
    except CollegeReviewError as e:
        logger.error(f"College review error retrieving rankings: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving rankings: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve rankings")


@router.post("/rankings")
async def create_ranking(
    scholarship_type_id: int = Body(..., description="Scholarship type ID"),
    sub_type_code: str = Body(..., description="Sub-type code"),
    academic_year: int = Body(..., description="Academic year"),
    semester: Optional[str] = Body(None, description="Semester"),
    ranking_name: Optional[str] = Body(None, description="Custom ranking name"),
    force_new: bool = Body(False, description="Create a new ranking even if an unfinished one already exists"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ranking for a scholarship sub-type"""

    try:
        service = CollegeReviewService(db)
        ranking = await service.create_ranking(
            scholarship_type_id=scholarship_type_id,
            sub_type_code=sub_type_code,
            academic_year=academic_year,
            semester=semester,
            creator_id=current_user.id,
            ranking_name=ranking_name,
            force_new=force_new,
        )

        return ApiResponse(
            success=True,
            message="Ranking created successfully",
            data={
                "id": ranking.id,
                "ranking_name": ranking.ranking_name,
                "scholarship_type_id": ranking.scholarship_type_id,
                "total_applications": ranking.total_applications,
                "total_quota": ranking.total_quota,
                "sub_type_code": ranking.sub_type_code,
                "academic_year": ranking.academic_year,
                "semester": normalize_semester_value(ranking.semester),
                "created_at": ranking.created_at.isoformat(),
            },
        )

    except ValueError as e:
        logger.warning(f"Invalid ranking creation data: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid ranking data: {str(e)}")
    except CollegeReviewError as e:
        logger.error(f"College review error creating ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create ranking")


@router.get("/rankings/{ranking_id}")
@professor_rate_limit(requests=200, window_seconds=600)  # 200 requests per 10 minutes
async def get_ranking(
    request: Request, ranking_id: int, current_user: User = Depends(require_college), db: AsyncSession = Depends(get_db)
):
    """Get a ranking with all its items"""

    try:
        service = CollegeReviewService(db)
        ranking = await service.get_ranking(ranking_id)

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Build sub-type metadata for UI display
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

        # Calculate college-specific quota from matrix
        college_quota: Optional[int] = None
        college_quota_breakdown: Dict[str, Dict[str, Any]] = {}
        user_college_code = current_user.college_code

        normalized_ranking_semester = normalize_semester_value(ranking.semester)

        if user_college_code:
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

            if config and config.has_college_quota and isinstance(config.quotas, dict):

                def _record_quota(sub_type_code: str, quota_value: Any) -> None:
                    meta = _meta_for_sub_type(sub_type_code)
                    try:
                        numeric_quota = int(quota_value)
                    except (TypeError, ValueError):
                        try:
                            numeric_quota = int(float(quota_value))
                        except (TypeError, ValueError):
                            numeric_quota = 0
                    college_quota_breakdown[sub_type_code] = {
                        "code": meta["code"],
                        "label": meta["label"],
                        "label_en": meta["label_en"],
                        "quota": numeric_quota,
                    }
                    return numeric_quota

                if ranking.sub_type_code == "default":
                    subtotal = 0
                    for sub_type_code, college_quotas in config.quotas.items():
                        if not isinstance(college_quotas, dict):
                            continue
                        if user_college_code not in college_quotas:
                            continue
                        subtotal += _record_quota(sub_type_code, college_quotas[user_college_code])
                    if subtotal > 0:
                        college_quota = subtotal
                else:
                    possible_keys: List[str] = []
                    if ranking.sub_type_code:
                        possible_keys.extend(
                            [
                                ranking.sub_type_code,
                                ranking.sub_type_code.lower(),
                                ranking.sub_type_code.upper(),
                            ]
                        )

                    seen_keys = set()
                    ordered_keys = []
                    for key in possible_keys:
                        if key not in seen_keys:
                            seen_keys.add(key)
                            ordered_keys.append(key)

                    for key in ordered_keys:
                        sub_quota_map = config.quotas.get(key)
                        if isinstance(sub_quota_map, dict) and user_college_code in sub_quota_map:
                            numeric_quota = _record_quota(ranking.sub_type_code, sub_quota_map[user_college_code])
                            college_quota = numeric_quota
                            break

        # Collect all unique department codes for batch query
        department_codes = set()
        for item in ranking.items:
            if item.application and item.application.student_data:
                student_data = item.application.student_data
                if isinstance(student_data, dict):
                    dept_code = student_data.get("std_depno") or student_data.get("dept_code")
                    if dept_code:
                        department_codes.add(dept_code)

        # Query all departments with academy relationship to avoid N+1 queries
        department_map = {}
        if department_codes:
            dept_stmt = (
                select(Department)
                .options(selectinload(Department.academy))
                .where(Department.code.in_(department_codes))
            )
            dept_result = await db.execute(dept_stmt)
            departments = dept_result.scalars().all()

            # Build map with department name and academy information
            department_map = {
                dept.code: {
                    "name": dept.name,
                    "academy_code": dept.academy_code,
                    "academy_name": dept.academy.name if dept.academy else None,
                }
                for dept in departments
            }

        # Format ranking items
        items = []
        for item in sorted(ranking.items, key=lambda x: x.rank_position):
            # Skip deleted applications
            if item.application and (item.application.status == "deleted" or item.application.deleted_at is not None):
                continue

            student_data = (
                item.application.student_data
                if item.application.student_data and isinstance(item.application.student_data, dict)
                else {}
            )
            student_name_raw = (
                student_data.get("std_cname")
                or student_data.get("std_ename")
                or student_data.get("name")
                or student_data.get("student_name")
            )
            student_name = str(student_name_raw) if student_name_raw else "學生"

            student_id_raw = (
                student_data.get("std_stdcode") or student_data.get("nycu_id") or student_data.get("student_id")
            )
            student_id = str(student_id_raw) if student_id_raw is not None else None

            # Extract department and academy information
            department_code = student_data.get("dept_code") or student_data.get("std_depno") or "N/A"

            # Get department info from database
            dept_info = department_map.get(department_code) if department_code and department_code != "N/A" else None

            # Extract department name
            department_name = student_data.get("dep_depname") or (dept_info["name"] if dept_info else None)

            # Extract academy code and name from Department.academy relationship
            academy_code = dept_info["academy_code"] if dept_info else None
            academy_name = student_data.get("aca_cname") or (dept_info["academy_name"] if dept_info else None)

            items.append(
                {
                    "id": item.id,
                    "rank_position": item.rank_position,
                    "display_rank": len(items) + 1,  # Dynamic display rank (skips deleted applications)
                    "is_allocated": item.is_allocated,
                    "status": item.status,
                    "student_name": student_name,
                    "student_id": student_id,
                    # Lightweight DTO with minimal student exposure
                    "application": {
                        "id": item.application.id,
                        "app_id": item.application.app_id,
                        "status": item.application.status,
                        "scholarship_type": item.application.main_scholarship_type,
                        "sub_type": item.application.sub_scholarship_type,
                        # Eligible sub-types that student applied for
                        "eligible_subtypes": (
                            item.application.scholarship_subtype_list
                            if item.application.scholarship_subtype_list
                            else []
                        ),
                        # Minimal student info - only what's needed for ranking display
                        "student_info": {
                            "display_name": student_name,
                            "student_id": student_id,
                            "student_id_masked": (
                                f"{student_id[:3]}***" if student_id and isinstance(student_id, str) else "N/A"
                            ),
                            "dept_code": (
                                student_data.get("std_depno", "N/A")[:3]
                                if isinstance(student_data.get("std_depno"), str)
                                else "N/A"
                            ),
                            "term_count": student_data.get("term_count") or student_data.get("std_termcount"),
                        },
                        # Add academy and department information
                        "department_code": department_code,
                        "department_name": department_name,
                        "academy_code": academy_code,
                        "academy_name": academy_name,
                    },
                }
            )

        return ApiResponse(
            success=True,
            message="Ranking retrieved successfully",
            data={
                "id": ranking.id,
                "ranking_name": ranking.ranking_name,
                "scholarship_type_id": ranking.scholarship_type_id,
                "sub_type_code": ranking.sub_type_code,
                "academic_year": ranking.academic_year,
                "semester": normalized_ranking_semester,
                "total_applications": len(items),
                "total_quota": ranking.total_quota,
                "college_quota": college_quota,
                "college_quota_breakdown": college_quota_breakdown,
                "allocated_count": ranking.allocated_count,
                "is_finalized": ranking.is_finalized,
                "ranking_status": ranking.ranking_status,
                "distribution_executed": ranking.distribution_executed,
                "sub_type_metadata": list(sub_type_metadata_map.values()),
                "items": items,
                "created_at": ranking.created_at.isoformat(),
            },
        )

    except HTTPException:
        raise
    except RankingNotFoundError as e:
        logger.warning(f"Ranking not found: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CollegeReviewError as e:
        logger.error(f"College review error retrieving ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve ranking")


@router.put("/rankings/{ranking_id}")
async def update_ranking(
    ranking_id: int,
    ranking_update: RankingUpdate,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Update ranking metadata (name, etc.)"""

    try:
        # Get ranking
        stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id)
        result = await db.execute(stmt)
        ranking = result.scalar_one_or_none()

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Check permissions - only creator or admin can update
        if ranking.created_by != current_user.id and current_user.role not in [UserRole.admin, UserRole.super_admin]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the ranking creator or admin can update this ranking",
            )

        # Check if ranking is finalized - cannot update finalized rankings
        if ranking.is_finalized:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot update finalized ranking")

        # Update ranking name
        ranking.ranking_name = ranking_update.ranking_name
        await db.commit()
        await db.refresh(ranking)

        return ApiResponse(
            success=True,
            message="Ranking updated successfully",
            data={
                "id": ranking.id,
                "ranking_name": ranking.ranking_name,
                "updated_at": ranking.updated_at.isoformat(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update ranking")


@router.put("/rankings/{ranking_id}/order")
@professor_rate_limit(requests=30, window_seconds=600)  # 30 ranking updates per 10 minutes
async def update_ranking_order(
    request: Request,
    ranking_id: int,
    new_order: List[RankingOrderUpdate],
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Update the ranking order of applications"""

    try:
        service = CollegeReviewService(db)
        ranking = await service.update_ranking_order(
            ranking_id=ranking_id, new_order=[item.dict() for item in new_order]
        )

        return ApiResponse(
            success=True,
            message="Ranking order updated successfully",
            data={"id": ranking.id, "updated_at": ranking.updated_at.isoformat()},
        )

    except RankingNotFoundError as e:
        logger.warning(f"Ranking not found for order update: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RankingModificationError as e:
        logger.warning(f"Cannot modify ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidRankingDataError as e:
        logger.warning(f"Invalid ranking data: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except CollegeReviewError as e:
        logger.error(f"College review error during ranking update: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error updating ranking order: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update ranking order")


@router.post("/rankings/{ranking_id}/finalize")
async def finalize_ranking(
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Finalize a ranking (makes it read-only)"""

    try:
        from app.models.audit_log import AuditAction, AuditLog

        # Get ranking to check ownership
        stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id)
        result = await db.execute(stmt)
        ranking_check = result.scalar_one_or_none()

        if not ranking_check:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Check permissions - only creator or admin can finalize
        if ranking_check.created_by != current_user.id and current_user.role not in [
            UserRole.admin,
            UserRole.super_admin,
        ]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the ranking creator or admin can finalize this ranking",
            )

        # Capture old state for audit log
        old_values = {
            "is_finalized": ranking_check.is_finalized,
            "ranking_status": ranking_check.ranking_status,
        }

        service = CollegeReviewService(db)
        ranking = await service.finalize_ranking(ranking_id=ranking_id, finalizer_id=current_user.id)

        # Log the finalize ranking operation
        new_values = {
            "is_finalized": ranking.is_finalized,
            "ranking_status": ranking.ranking_status,
            "finalized_at": ranking.finalized_at.isoformat() if ranking.finalized_at else None,
        }

        # Extract request metadata
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None

        audit_log = AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.finalize_ranking.value,
            resource_type="ranking",
            resource_id=str(ranking.id),
            description=f"Finalized ranking: {ranking.ranking_name}",
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            status="success",
        )
        db.add(audit_log)
        await db.commit()

        return ApiResponse(
            success=True,
            message="Ranking finalized successfully",
            data={
                "id": ranking.id,
                "is_finalized": ranking.is_finalized,
                "finalized_at": ranking.finalized_at.isoformat(),
                "ranking_status": ranking.ranking_status,
            },
        )

    except RankingNotFoundError as e:
        logger.warning(f"Ranking not found for finalization: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RankingModificationError as e:
        logger.warning(f"Cannot finalize ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CollegeReviewError as e:
        logger.error(f"College review error during finalization: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error finalizing ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to finalize ranking")


@router.post("/rankings/{ranking_id}/unfinalize")
async def unfinalize_ranking(
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Unfinalize a ranking (makes it editable again)"""

    try:
        from app.models.audit_log import AuditAction, AuditLog

        # Get ranking to check ownership
        stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id)
        result = await db.execute(stmt)
        ranking_check = result.scalar_one_or_none()

        if not ranking_check:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Check permissions - only creator or admin can unfinalize
        if ranking_check.created_by != current_user.id and current_user.role not in [
            UserRole.admin,
            UserRole.super_admin,
        ]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the ranking creator or admin can unfinalize this ranking",
            )

        # Capture old state for audit log
        old_values = {
            "is_finalized": ranking_check.is_finalized,
            "ranking_status": ranking_check.ranking_status,
        }

        service = CollegeReviewService(db)
        ranking = await service.unfinalize_ranking(ranking_id=ranking_id)

        # Log the unfinalize ranking operation
        new_values = {
            "is_finalized": ranking.is_finalized,
            "ranking_status": ranking.ranking_status,
        }

        # Extract request metadata
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None

        audit_log = AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.unfinalize_ranking.value,
            resource_type="ranking",
            resource_id=str(ranking.id),
            description=f"Unfinalized ranking: {ranking.ranking_name}",
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            status="success",
        )
        db.add(audit_log)
        await db.commit()

        return ApiResponse(
            success=True,
            message="Ranking unfinalized successfully",
            data={
                "id": ranking.id,
                "is_finalized": ranking.is_finalized,
                "ranking_status": ranking.ranking_status,
            },
        )

    except RankingNotFoundError as e:
        logger.warning(f"Ranking not found for unfinalization: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RankingModificationError as e:
        logger.warning(f"Cannot unfinalize ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CollegeReviewError as e:
        logger.error(f"College review error during unfinalization: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error unfinalizing ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to unfinalize ranking")


@router.delete("/rankings/{ranking_id}")
async def delete_ranking(
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Delete a ranking

    Only the creator or admin can delete a ranking.
    Cannot delete finalized rankings.
    """

    try:
        from app.models.audit_log import AuditAction, AuditLog

        # Get ranking
        stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id)
        result = await db.execute(stmt)
        ranking = result.scalar_one_or_none()

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Check permissions - only creator or admin can delete
        if ranking.created_by != current_user.id and current_user.role not in [UserRole.admin, UserRole.super_admin]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the ranking creator or admin can delete this ranking",
            )

        # Check if ranking is finalized - cannot delete finalized rankings
        if ranking.is_finalized:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete finalized ranking. Please unfinalize it first.",
            )

        # Capture ranking information for audit log before deletion
        old_values = {
            "ranking_name": ranking.ranking_name,
            "scholarship_type_id": ranking.scholarship_type_id,
            "sub_type_code": ranking.sub_type_code,
            "academic_year": ranking.academic_year,
            "semester": ranking.semester,
            "total_applications": ranking.total_applications,
            "is_finalized": ranking.is_finalized,
            "ranking_status": ranking.ranking_status,
        }

        # Delete ranking items first (cascade should handle this, but being explicit)
        delete_items_stmt = select(CollegeRankingItem).where(CollegeRankingItem.ranking_id == ranking_id)
        items_result = await db.execute(delete_items_stmt)
        items = items_result.scalars().all()

        for item in items:
            await db.delete(item)

        # Delete the ranking
        await db.delete(ranking)

        # Log the delete ranking operation before committing
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None

        audit_log = AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.delete_ranking.value,
            resource_type="ranking",
            resource_id=str(ranking_id),
            description=f"Deleted ranking: {ranking.ranking_name}",
            old_values=old_values,
            ip_address=ip_address,
            user_agent=user_agent,
            status="success",
        )
        db.add(audit_log)
        await db.commit()

        return ApiResponse(
            success=True,
            message=f"Ranking '{ranking.ranking_name}' deleted successfully",
            data={"ranking_id": ranking_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting ranking {ranking_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete ranking: {str(e)}"
        )


@router.post("/rankings/{ranking_id}/import-excel")
async def import_ranking_from_excel(
    ranking_id: int,
    import_data: List[RankingImportItem],
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """
    Import ranking data from Excel

    Expected Excel columns: 學號, 姓名, 排名
    This endpoint updates the rank_position of existing ranking items based on student IDs
    """

    try:
        logger.info(f"User {current_user.id} importing {len(import_data)} rankings for ranking_id={ranking_id}")

        # Get ranking
        stmt = (
            select(CollegeRanking)
            .options(selectinload(CollegeRanking.items).selectinload("application"))
            .where(CollegeRanking.id == ranking_id)
        )
        result = await db.execute(stmt)
        ranking = result.scalar_one_or_none()

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Check if ranking can be modified
        if ranking.is_finalized:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot modify finalized ranking")

        # Build a map of student_id -> import_item
        import_map = {item.student_id: item for item in import_data}

        # Update ranking items
        updated_count = 0
        not_found = []

        for rank_item in ranking.items:
            app = rank_item.application
            if not app or not app.student_data:
                continue

            student_id = app.student_data.get("std_stdcode") or app.student_data.get("student_id")
            if not student_id:
                continue

            if student_id in import_map:
                import_item = import_map[student_id]
                rank_item.rank_position = import_item.rank_position
                updated_count += 1
            else:
                not_found.append(student_id)

        # Update ranking metadata
        ranking.total_applications = len(ranking.items)

        await db.flush()

        return ApiResponse(
            success=True,
            message=f"Ranking import successful. Updated {updated_count} students.",
            data={
                "ranking_id": ranking_id,
                "updated_count": updated_count,
                "total_imported": len(import_data),
                "not_found_in_ranking": not_found if len(not_found) < 20 else f"{len(not_found)} students not found",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing ranking data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to import ranking data: {str(e)}"
        )
