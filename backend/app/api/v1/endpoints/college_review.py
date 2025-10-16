"""
College Review API Endpoints

This module provides API endpoints for college-level review operations including:
- Application review and scoring
- Ranking management
- Quota distribution
- Review statistics and reporting
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, validator
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiting import professor_rate_limit  # Reuse existing rate limiter
from app.core.security import require_admin, require_college
from app.db.deps import get_db
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeReview
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole
from app.schemas.response import ApiResponse
from app.services.college_review_service import (
    CollegeReviewError,
    CollegeReviewService,
    InvalidRankingDataError,
    RankingModificationError,
    RankingNotFoundError,
    ReviewPermissionError,
)
from app.services.matrix_distribution import MatrixDistributionService

logger = logging.getLogger(__name__)


def normalize_semester_value(value: Optional[Any]) -> Optional[str]:
    """Normalize semester representations (None/yearly/enum) to canonical values."""
    if value is None:
        return None

    candidate = value.value if hasattr(value, "value") else str(value).strip()
    candidate_lower = candidate.lower()

    if candidate_lower.startswith("semester."):
        candidate_lower = candidate_lower.split(".", 1)[1]

    if candidate_lower in {"", "none", "yearly"}:
        return None

    return candidate_lower


# Pydantic schemas for request/response
class CollegeReviewCreate(BaseModel):
    """Schema for creating a college review"""

    academic_score: Optional[float] = Field(None, ge=0, le=100, description="Academic performance score (0-100)")
    professor_review_score: Optional[float] = Field(None, ge=0, le=100, description="Professor review score (0-100)")
    college_criteria_score: Optional[float] = Field(
        None, ge=0, le=100, description="College-specific criteria score (0-100)"
    )
    special_circumstances_score: Optional[float] = Field(
        None, ge=0, le=100, description="Special circumstances score (0-100)"
    )
    review_comments: Optional[str] = Field(None, max_length=2000, description="Detailed review comments")
    recommendation: str = Field(..., description="Review recommendation", pattern="^(approve|reject|conditional)$")
    decision_reason: Optional[str] = Field(None, max_length=1000, description="Reason for the recommendation")
    is_priority: Optional[bool] = Field(False, description="Mark as priority application")
    needs_special_attention: Optional[bool] = Field(False, description="Flag for special review")
    scoring_weights: Optional[Dict[str, float]] = Field(None, description="Custom scoring weights")

    @validator("academic_score", "professor_review_score", "college_criteria_score", "special_circumstances_score")
    def validate_scores(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError("Score must be between 0 and 100")
        return v

    @validator("scoring_weights")
    def validate_scoring_weights(cls, v):
        if v is not None:
            # Ensure all weight values are between 0 and 1
            for key, weight in v.items():
                if not isinstance(weight, (int, float)) or weight < 0 or weight > 1:
                    raise ValueError(f"Weight for {key} must be between 0 and 1")
            # Ensure weights sum to approximately 1.0
            total_weight = sum(v.values())
            if abs(total_weight - 1.0) > 0.01:  # Allow small floating point errors
                raise ValueError("Scoring weights must sum to 1.0")
        return v


class CollegeReviewUpdate(BaseModel):
    """Schema for updating a college review"""

    academic_score: Optional[float] = Field(None, ge=0, le=100)
    professor_review_score: Optional[float] = Field(None, ge=0, le=100)
    college_criteria_score: Optional[float] = Field(None, ge=0, le=100)
    special_circumstances_score: Optional[float] = Field(None, ge=0, le=100)
    review_comments: Optional[str] = Field(None, max_length=2000)
    recommendation: Optional[str] = Field(None, pattern="^(approve|reject|conditional)$")
    decision_reason: Optional[str] = Field(None, max_length=1000)
    is_priority: Optional[bool] = None
    needs_special_attention: Optional[bool] = None

    @validator("academic_score", "professor_review_score", "college_criteria_score", "special_circumstances_score")
    def validate_scores(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError("Score must be between 0 and 100")
        return v


class CollegeReviewResponse(BaseModel):
    """Schema for college review response"""

    id: int
    application_id: int
    reviewer_id: int
    ranking_score: Optional[float]
    academic_score: Optional[float]
    professor_review_score: Optional[float]
    college_criteria_score: Optional[float]
    special_circumstances_score: Optional[float]
    review_comments: Optional[str]
    recommendation: str
    decision_reason: Optional[str]
    preliminary_rank: Optional[int]
    final_rank: Optional[int]
    review_status: str
    is_priority: bool
    needs_special_attention: bool
    reviewed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class RankingOrderUpdate(BaseModel):
    """Schema for updating ranking order"""

    item_id: int
    position: int


class QuotaDistributionRequest(BaseModel):
    """Schema for quota distribution request"""

    distribution_rules: Optional[Dict[str, Any]] = Field(None, description="Custom distribution rules")


class RankingUpdate(BaseModel):
    """Schema for updating ranking metadata"""

    ranking_name: str = Field(..., min_length=1, max_length=200, description="New ranking name")


router = APIRouter()


# Helper functions for granular authorization checks
async def _check_scholarship_permission(user: User, scholarship_type_id: int, db: AsyncSession) -> bool:
    """Check if user has permission for specific scholarship type"""
    if user.role in [UserRole.admin, UserRole.super_admin]:
        return True

    # Check if user is assigned to this scholarship type
    from app.models.user import AdminScholarship

    stmt = select(AdminScholarship).where(
        and_(AdminScholarship.admin_id == user.id, AdminScholarship.scholarship_id == scholarship_type_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _check_academic_year_permission(user: User, academic_year: int, db: AsyncSession) -> bool:
    """Check if user has permission for specific academic year"""
    if user.role in [UserRole.admin, UserRole.super_admin]:
        return True

    # College users can only access current and previous academic year
    current_year = datetime.now().year - 1911  # ROC year
    allowed_years = [current_year - 1, current_year, current_year + 1]
    return academic_year in allowed_years


async def _check_application_review_permission(user: User, application_id: int, db: AsyncSession) -> bool:
    """Check if user can review specific application"""
    if user.role in [UserRole.admin, UserRole.super_admin]:
        return True

    # Get application details to check permissions
    stmt = select(Application).where(Application.id == application_id)
    result = await db.execute(stmt)
    application = result.scalar_one_or_none()

    if not application:
        return False

    # Check scholarship type permission
    if application.scholarship_type_id:
        return await _check_scholarship_permission(user, application.scholarship_type_id, db)

    # Check academic year permission
    if application.academic_year:
        return await _check_academic_year_permission(user, application.academic_year, db)

    return True  # Default allow if no specific restrictions


@router.get("/applications")
@professor_rate_limit(requests=150, window_seconds=600)  # 150 requests per 10 minutes
async def get_applications_for_review(
    request: Request,
    scholarship_type_id: Optional[int] = Query(None, description="Filter by scholarship type ID"),
    scholarship_type: Optional[str] = Query(None, description="Filter by scholarship type code"),
    sub_type: Optional[str] = Query(None, description="Filter by sub-type"),
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Get applications that are ready for college review"""

    # Granular authorization checks
    if not current_user.is_college() and not current_user.is_admin() and not current_user.is_super_admin():
        raise ReviewPermissionError("College role required for application review access")

    # Additional checks for specific operations
    if scholarship_type_id and not await _check_scholarship_permission(current_user, scholarship_type_id, db):
        raise ReviewPermissionError(f"User {current_user.id} not authorized for scholarship type {scholarship_type_id}")

    if academic_year and not await _check_academic_year_permission(current_user, academic_year, db):
        raise ReviewPermissionError(f"User {current_user.id} not authorized for academic year {academic_year}")

    try:
        service = CollegeReviewService(db)
        applications = await service.get_applications_for_review(
            scholarship_type_id=scholarship_type_id,
            scholarship_type=scholarship_type,
            sub_type=sub_type,
            reviewer_id=current_user.id,
            academic_year=academic_year,
            semester=semester,
        )

        # Create lightweight DTOs with field-level filtering for security
        filtered_applications = []
        # Import i18n utilities
        from app.utils.i18n import ScholarshipI18n

        for app in applications:
            # Extract only necessary fields to minimize data exposure
            student_data = app.get("student_data", {}) if isinstance(app.get("student_data"), dict) else {}

            filtered_app = {
                "id": app.get("id"),
                "app_id": app.get("app_id"),
                "status": app.get("status"),
                "status_zh": ScholarshipI18n.get_application_status_text(app.get("status", "")),
                "scholarship_type": app.get("scholarship_type"),
                "scholarship_type_zh": app.get("scholarship_type_zh", app.get("scholarship_type")),
                "sub_type": app.get("sub_type"),
                "academic_year": app.get("academic_year"),
                "semester": app.get("semester"),
                "is_renewal": app.get("is_renewal", False),
                "created_at": app.get("created_at"),
                "submitted_at": app.get("submitted_at"),
                # Student info in flat format for frontend compatibility
                "student_id": student_data.get("std_stdcode", "未提供學號") if student_data else "N/A",
                "student_name": student_data.get("std_cname", "未提供姓名") if student_data else "未提供學生資料",
                "student_termcount": student_data.get("std_termcount", "N/A") if student_data else "N/A",
                "department_code": student_data.get("std_depno", "N/A") if student_data else "N/A",
                # Add review status for UI purposes
                "review_status": {
                    "has_professor_review": len(app.get("professor_reviews", [])) > 0,
                    "professor_review_count": len(app.get("professor_reviews", [])),
                    "files_count": len(app.get("files", [])),
                },
            }
            filtered_applications.append(filtered_app)

        return ApiResponse(
            success=True, message="Applications for review retrieved successfully", data=filtered_applications
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid request parameters for college applications: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid request parameters: {str(e)}")
    except ReviewPermissionError as e:
        logger.warning(f"Permission denied for college applications access: {str(e)}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        logger.error(f"Invalid parameters for applications query: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid query parameters: {str(e)}")
    except DatabaseError as e:
        logger.error(f"Database error retrieving applications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving applications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving applications",
        )


@router.post("/applications/{application_id}/review")
@professor_rate_limit(requests=50, window_seconds=600)  # 50 review submissions per 10 minutes
async def create_college_review(
    request: Request,
    application_id: int,
    review_data: CollegeReviewCreate,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a college review for an application"""

    # Granular authorization checks for review creation
    if not current_user.is_college() and not current_user.is_admin() and not current_user.is_super_admin():
        raise ReviewPermissionError("College role required for application review")

    # Check if user can review this specific application
    if not await _check_application_review_permission(current_user, application_id, db):
        raise ReviewPermissionError(f"User {current_user.id} not authorized to review application {application_id}")

    # Validate application_id
    if application_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid application ID")

    try:
        service = CollegeReviewService(db)
        college_review = await service.create_or_update_review(
            application_id=application_id, reviewer_id=current_user.id, review_data=review_data.dict(exclude_unset=True)
        )

        return ApiResponse(
            success=True,
            message="College review created successfully",
            data=CollegeReviewResponse.from_orm(college_review),
        )

    except ValueError as e:
        logger.warning(f"Invalid review data for application {application_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid review data: {str(e)}")
    except PermissionError as e:
        logger.warning(f"Permission denied for college review creation by user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to review this application")
    except ValueError as e:
        logger.error(f"Invalid review data for application {application_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid review data: {str(e)}")
    except IntegrityError as e:
        logger.error(f"Database integrity error creating review for application {application_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Review creation conflicts with existing data")
    except DatabaseError as e:
        logger.error(f"Database error creating review for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected error creating college review for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the review",
        )


@router.put("/reviews/{review_id}")
async def update_college_review(
    review_id: int,
    review_data: CollegeReviewUpdate,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing college review"""

    try:
        # Get existing review
        stmt = select(CollegeReview).where(CollegeReview.id == review_id)
        result = await db.execute(stmt)
        college_review = result.scalar_one_or_none()

        if not college_review:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="College review not found")

        # Check permissions
        if college_review.reviewer_id != current_user.id and current_user.role not in [
            UserRole.admin,
            UserRole.super_admin,
        ]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this review")

        # Update review
        service = CollegeReviewService(db)
        updated_review = await service.create_or_update_review(
            application_id=college_review.application_id,
            reviewer_id=college_review.reviewer_id,
            review_data=review_data.dict(exclude_unset=True),
        )

        return ApiResponse(
            success=True,
            message="College review updated successfully",
            data=CollegeReviewResponse.from_orm(updated_review),
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid review data for review {review_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid review data: {str(e)}")
    except PermissionError as e:
        logger.warning(f"Permission denied for review update by user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this review")
    except ValueError as e:
        logger.error(f"Invalid review data for update {review_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid review data: {str(e)}")
    except IntegrityError as e:
        logger.error(f"Database integrity error updating review {review_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Review update conflicts with existing data")
    except DatabaseError as e:
        logger.error(f"Database error updating review {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected error updating college review {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while updating the review",
        )


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

        # Format ranking items
        items = []
        for item in sorted(ranking.items, key=lambda x: x.rank_position):
            student_data = (
                item.application.student_data
                if item.application.student_data and isinstance(item.application.student_data, dict)
                else {}
            )
            student_name_raw = (
                student_data.get("std_cname") or student_data.get("std_ename") or student_data.get("student_name")
            )
            student_name = str(student_name_raw) if student_name_raw else "學生"

            student_id_raw = student_data.get("std_stdcode") or student_data.get("student_id")
            student_id = str(student_id_raw) if student_id_raw is not None else None

            items.append(
                {
                    "id": item.id,
                    "rank_position": item.rank_position,
                    "is_allocated": item.is_allocated,
                    "status": item.status,
                    "total_score": float(item.total_score) if item.total_score else None,
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
                            ),  # Partially mask student ID for privacy
                            "dept_code": (
                                student_data.get("std_depno", "N/A")[:3]
                                if isinstance(student_data.get("std_depno"), str)
                                else "N/A"
                            ),  # Use department code instead of full name
                        },
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
                "total_applications": ranking.total_applications,
                "total_quota": ranking.total_quota,
                "college_quota": college_quota,  # College-specific quota
                "college_quota_breakdown": college_quota_breakdown,  # Quota breakdown by sub-type
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


@router.post("/rankings/{ranking_id}/distribute")
async def execute_quota_distribution(
    ranking_id: int,
    distribution_request: QuotaDistributionRequest,
    current_user: User = Depends(require_admin),  # Only admin can execute distribution
    db: AsyncSession = Depends(get_db),
):
    """Execute quota-based distribution for a ranking"""

    try:
        service = CollegeReviewService(db)
        distribution = await service.execute_quota_distribution(
            ranking_id=ranking_id,
            executor_id=current_user.id,
            distribution_rules=distribution_request.distribution_rules,
        )

        return ApiResponse(
            success=True,
            message="Quota distribution executed successfully",
            data={
                "id": distribution.id,
                "distribution_name": distribution.distribution_name,
                "total_applications": distribution.total_applications,
                "total_quota": distribution.total_quota,
                "total_allocated": distribution.total_allocated,
                "success_rate": distribution.success_rate,
                "distribution_summary": distribution.distribution_summary,
                "executed_at": distribution.executed_at.isoformat(),
            },
        )

    except RankingNotFoundError as e:
        logger.warning(f"Ranking not found for distribution: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RankingModificationError as e:
        logger.warning(f"Cannot execute distribution: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CollegeReviewError as e:
        logger.error(f"College review error during distribution: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error executing distribution: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to execute distribution")


@router.post("/rankings/{ranking_id}/finalize")
async def finalize_ranking(
    ranking_id: int,
    current_user: User = Depends(require_college),  # College users can finalize their own rankings
    db: AsyncSession = Depends(get_db),
):
    """Finalize a ranking (makes it read-only)"""

    try:
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

        service = CollegeReviewService(db)
        ranking = await service.finalize_ranking(ranking_id=ranking_id, finalizer_id=current_user.id)

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


@router.get("/quota-status")
async def get_quota_status(
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None, description="Semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Get quota status for a scholarship type"""

    try:
        service = CollegeReviewService(db)
        quota_status = await service.get_quota_status(
            scholarship_type_id=scholarship_type_id, academic_year=academic_year, semester=semester
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


@router.get("/statistics")
async def get_college_review_statistics(
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Get college review statistics"""

    try:
        # Build statistics query
        base_query = select(CollegeReview)

        if current_user.role not in [UserRole.admin, UserRole.super_admin]:
            # Non-admin users can only see their own reviews
            base_query = base_query.where(CollegeReview.reviewer_id == current_user.id)

        # Apply filters
        if academic_year or semester:
            from sqlalchemy.orm import join

            base_query = base_query.select_from(
                join(CollegeReview, Application, CollegeReview.application_id == Application.id)
            )

            if academic_year:
                base_query = base_query.where(Application.academic_year == academic_year)
            if semester:
                base_query = base_query.where(Application.semester == semester)

        # Execute query and calculate statistics
        result = await db.execute(base_query)
        reviews = result.scalars().all()

        total_reviews = len(reviews)
        approved_count = len([r for r in reviews if r.recommendation == "approve"])
        rejected_count = len([r for r in reviews if r.recommendation == "reject"])
        conditional_count = len([r for r in reviews if r.recommendation == "conditional"])

        avg_ranking_score = (
            sum(r.ranking_score for r in reviews if r.ranking_score) / len([r for r in reviews if r.ranking_score])
            if reviews
            else 0
        )

        statistics = {
            "total_reviews": total_reviews,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "conditional_count": conditional_count,
            "approval_rate": (approved_count / total_reviews * 100) if total_reviews > 0 else 0,
            "average_ranking_score": round(avg_ranking_score, 2),
            "breakdown_by_recommendation": {
                "approve": approved_count,
                "reject": rejected_count,
                "conditional": conditional_count,
            },
        }

        return ApiResponse(success=True, message="College review statistics retrieved successfully", data=statistics)

    except ValueError as e:
        logger.warning(f"Invalid statistics parameters: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid parameters: {str(e)}")
    except CollegeReviewError as e:
        logger.error(f"College review error retrieving statistics: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving statistics: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve statistics")


@router.get("/available-combinations")
async def get_available_combinations(current_user: User = Depends(require_college), db: AsyncSession = Depends(get_db)):
    """Get available combinations of scholarship types, academic years, and semesters from configurations"""

    try:
        logger.info("College user requesting available combinations from configurations")

        # Import models
        from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
        from app.models.user import AdminScholarship

        # Get scholarship IDs that the user has permission to access
        permission_query = select(AdminScholarship.scholarship_id).where(AdminScholarship.admin_id == current_user.id)
        permission_result = await db.execute(permission_query)
        allowed_scholarship_ids = [row[0] for row in permission_result.fetchall()]

        logger.info(f"User {current_user.id} has permission for scholarships: {allowed_scholarship_ids}")

        # If user has specific permissions, filter by those
        # If user has no permissions set (empty list), show all (for backward compatibility or super admin)
        if allowed_scholarship_ids:
            scholarship_query = select(ScholarshipType).where(
                ScholarshipType.status == "active", ScholarshipType.id.in_(allowed_scholarship_ids)
            )
        else:
            # No specific permissions - could mean all or none depending on your business logic
            # For college users without permissions, show no scholarships
            logger.warning(f"College user {current_user.id} has no scholarship permissions set")
            scholarship_query = select(ScholarshipType).where(ScholarshipType.id == -1)  # No results

        scholarship_result = await db.execute(scholarship_query)
        scholarship_types_objs = scholarship_result.scalars().all()

        scholarship_types = [
            {
                "code": st.code,
                "name": st.name,
                "name_en": st.name_en if st.name_en else st.name,
            }
            for st in scholarship_types_objs
        ]
        logger.info(f"Returning {len(scholarship_types)} scholarship types for user {current_user.id}")

        # Query distinct academic years and semesters from active configurations
        # Filter by scholarship permissions
        if allowed_scholarship_ids:
            config_query = select(ScholarshipConfiguration).where(
                ScholarshipConfiguration.is_active,
                ScholarshipConfiguration.scholarship_type_id.in_(allowed_scholarship_ids),
            )
        else:
            config_query = select(ScholarshipConfiguration).where(ScholarshipConfiguration.id == -1)  # No results

        config_result = await db.execute(config_query)
        configs = config_result.scalars().all()

        # Collect unique academic years and semesters from configurations
        academic_years_set = set()
        semesters_set = set()
        has_yearly_scholarships = False

        for config in configs:
            if config.academic_year:
                academic_years_set.add(config.academic_year)

            if config.semester:
                # Semester is an enum, get its value
                raw_value = config.semester.value if hasattr(config.semester, "value") else str(config.semester)
                value_lower = raw_value.lower()
                if value_lower in {"yearly"}:
                    has_yearly_scholarships = True
                else:
                    semesters_set.add(value_lower.upper())
            else:
                # No semester means yearly scholarship
                has_yearly_scholarships = True

        academic_years = sorted(list(academic_years_set))
        semester_strings = sorted(list(semesters_set))

        # Add a special "YEARLY" option if there are yearly scholarships
        if has_yearly_scholarships:
            semester_strings.append("YEARLY")

        response_data = {
            "scholarship_types": scholarship_types,
            "academic_years": academic_years,
            "semesters": sorted(list(set(semester_strings))),  # Remove duplicates and sort
        }

        logger.info(
            f"Retrieved {len(scholarship_types)} scholarship types, {len(academic_years)} years, {len(semester_strings)} semesters"
        )

        return ApiResponse(success=True, message="Available combinations retrieved successfully", data=response_data)

    except Exception as e:
        logger.error(f"Error retrieving available combinations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available combinations from database",
        )


# Matrix Distribution Endpoints


class RankingImportItem(BaseModel):
    """Schema for importing ranking data from Excel"""

    student_id: str = Field(..., description="Student ID (學號)")
    student_name: str = Field(..., description="Student name (姓名)")
    rank_position: int = Field(..., ge=1, description="Ranking position (排名)")


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
        from sqlalchemy.orm import selectinload

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


@router.post("/rankings/{ranking_id}/execute-matrix-distribution")
async def execute_matrix_distribution(
    ranking_id: int,
    current_user: User = Depends(require_college),  # College users can execute distribution
    db: AsyncSession = Depends(get_db),
):
    """
    Execute matrix-based quota distribution for a ranking

    This uses the matrix distribution algorithm which:
    - Processes sub-types in fixed priority order
    - Allocates students to sub-type × college matrix quotas
    - Tracks admitted (正取) and backup (備取) positions
    - Checks eligibility rules before allocation
    """

    try:
        logger.info(f"User {current_user.id} executing matrix distribution for ranking_id={ranking_id}")

        # Create matrix distribution service
        matrix_service = MatrixDistributionService(db)

        # Execute distribution
        distribution_result = await matrix_service.execute_matrix_distribution(
            ranking_id=ranking_id, executor_id=current_user.id
        )

        return ApiResponse(
            success=True,
            message="Matrix distribution executed successfully",
            data=distribution_result,
        )

    except ValueError as e:
        logger.warning(f"Invalid matrix distribution request: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing matrix distribution: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to execute matrix distribution: {str(e)}"
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
        from sqlalchemy.orm import selectinload

        from app.models.college_review import CollegeRankingItem
        from app.models.scholarship import ScholarshipConfiguration

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

            student_id = app.student_data.get("std_stdcode", "N/A")
            student_name = app.student_data.get("std_cname", "N/A")
            college_code = (
                app.student_data.get("college_code")
                or app.student_data.get("std_college")
                or app.student_data.get("academy_code")
                or "N/A"
            )

            sub_type = item.allocated_sub_type or "unallocated"
            item_status = item.status

            student_info = {
                "rank_position": item.rank_position,
                "student_id": student_id,
                "student_name": student_name,
                "application_id": app.id,
                "app_id": app.app_id,
            }

            if item_status == "rejected" or not item.allocated_sub_type:
                rejected_students.append(
                    {
                        "rank_position": item.rank_position,
                        "student_id": student_id,
                        "student_name": student_name,
                        "application_id": app.id,
                        "reason": item.allocation_reason or "No suitable sub-type or quota exceeded",
                    }
                )
                continue

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

            if item_status == "allocated" and item.is_allocated:
                college_entry["admitted"].append(student_info)
                college_entry["admitted_count"] += 1
                entry["admitted_total"] += 1
                admitted_total_counter += 1
            elif item_status == "waitlisted":
                student_info["backup_position"] = item.backup_position
                college_entry["backup"].append(student_info)
                college_entry["backup_count"] += 1
                entry["backup_total"] += 1

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


@router.get("/sub-type-translations")
async def get_sub_type_translations(
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """
    Get sub-type name translations for all supported languages from database

    Returns a dictionary with Chinese and English translations for all active sub-type configurations
    """

    try:
        from sqlalchemy.orm import selectinload

        from app.models.scholarship import ScholarshipStatus, ScholarshipType

        # Get all active scholarship types with their sub-type configurations
        stmt = (
            select(ScholarshipType)
            .options(selectinload(ScholarshipType.sub_type_configs))
            .where(ScholarshipType.status == ScholarshipStatus.active.value)
        )
        result = await db.execute(stmt)
        scholarships = result.scalars().all()

        # Build translations from database
        translations = {"zh": {}, "en": {}}

        for scholarship in scholarships:
            # Get sub-type configurations for this scholarship
            for config in scholarship.sub_type_configs:
                if config.is_active:
                    # Add Chinese translation
                    translations["zh"][config.sub_type_code] = config.name
                    # Add English translation
                    translations["en"][config.sub_type_code] = config.name_en if config.name_en else config.name

        return ApiResponse(
            success=True,
            message="Sub-type translations retrieved successfully from database",
            data=translations,
        )

    except Exception as e:
        logger.error(f"Error retrieving sub-type translations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve sub-type translations: {str(e)}",
        )


@router.delete("/rankings/{ranking_id}")
async def delete_ranking(
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a ranking

    Only the creator or admin can delete a ranking.
    Cannot delete finalized rankings.
    """

    try:
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

        # Delete ranking items first (cascade should handle this, but being explicit)
        from app.models.college_review import CollegeRankingItem

        delete_items_stmt = select(CollegeRankingItem).where(CollegeRankingItem.ranking_id == ranking_id)
        items_result = await db.execute(delete_items_stmt)
        items = items_result.scalars().all()

        for item in items:
            await db.delete(item)

        # Delete the ranking
        await db.delete(ranking)
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


@router.get("/managed-college")
async def get_managed_college(
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the college that the current college user has management permission for

    Uses the college_code field directly from the User model, which should be set
    when college users are created or assigned to colleges.
    """

    try:
        from app.models.student import Academy
        from app.models.user import AdminScholarship

        logger.info(f"User {current_user.id} requesting managed college information")

        # Check if user has college_code set
        if not current_user.college_code:
            logger.warning(f"College user {current_user.id} has no college_code assigned")
            return ApiResponse(success=True, message="No college assigned to this user", data=None)

        # Get college information from Academy table
        academy_stmt = select(Academy).where(Academy.code == current_user.college_code)
        academy_result = await db.execute(academy_stmt)
        academy = academy_result.scalar_one_or_none()

        if not academy:
            logger.error(f"College code {current_user.college_code} not found in Academy table")
            return ApiResponse(
                success=True, message=f"College information not found for code: {current_user.college_code}", data=None
            )

        # Get scholarship count for this user
        admin_scholarships_stmt = select(AdminScholarship).where(AdminScholarship.admin_id == current_user.id)
        admin_scholarships_result = await db.execute(admin_scholarships_stmt)
        admin_scholarships = admin_scholarships_result.scalars().all()

        # Return managed college information
        managed_college_data = {
            "code": academy.code,
            "name": academy.name,
            "name_en": academy.name_en or academy.name,
            "scholarship_count": len(admin_scholarships),
        }

        logger.info(f"User {current_user.id} manages college: {academy.code} ({academy.name})")

        return ApiResponse(success=True, message="Managed college retrieved successfully", data=managed_college_data)

    except Exception as e:
        logger.error(f"Error retrieving managed college for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve managed college: {str(e)}"
        )
