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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, validator
from sqlalchemy import and_, select
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiting import professor_rate_limit  # Reuse existing rate limiter
from app.core.security import require_admin, require_college
from app.db.deps import get_db
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeReview
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

logger = logging.getLogger(__name__)


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
    recommendation: str = Field(
        ...,
        description="Review recommendation",
        pattern="^(approve|reject|conditional)$",
    )
    decision_reason: Optional[str] = Field(None, max_length=1000, description="Reason for the recommendation")
    is_priority: Optional[bool] = Field(False, description="Mark as priority application")
    needs_special_attention: Optional[bool] = Field(False, description="Flag for special review")
    scoring_weights: Optional[Dict[str, float]] = Field(None, description="Custom scoring weights")

    @validator(
        "academic_score",
        "professor_review_score",
        "college_criteria_score",
        "special_circumstances_score",
    )
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

    @validator(
        "academic_score",
        "professor_review_score",
        "college_criteria_score",
        "special_circumstances_score",
    )
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


router = APIRouter()


# Helper functions for granular authorization checks
async def _check_scholarship_permission(user: User, scholarship_type_id: int, db: AsyncSession) -> bool:
    """Check if user has permission for specific scholarship type"""
    if user.role in [UserRole.admin, UserRole.super_admin]:
        return True

    # Check if user is assigned to this scholarship type
    from app.models.user import AdminScholarship

    stmt = select(AdminScholarship).where(
        and_(
            AdminScholarship.user_id == user.id,
            AdminScholarship.scholarship_type_id == scholarship_type_id,
        )
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


@router.get("/applications", response_model=ApiResponse[List[Dict[str, Any]]])
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
            success=True,
            message="Applications for review retrieved successfully",
            data=filtered_applications,
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid request parameters for college applications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request parameters: {str(e)}",
        )
    except ReviewPermissionError as e:
        logger.warning(f"Permission denied for college applications access: {str(e)}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        logger.error(f"Invalid parameters for applications query: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid query parameters: {str(e)}",
        )
    except DatabaseError as e:
        logger.error(f"Database error retrieving applications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable",
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving applications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving applications",
        )


@router.post(
    "/applications/{application_id}/review",
    response_model=ApiResponse[CollegeReviewResponse],
)
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
            application_id=application_id,
            reviewer_id=current_user.id,
            review_data=review_data.dict(exclude_unset=True),
        )

        return ApiResponse(
            success=True,
            message="College review created successfully",
            data=CollegeReviewResponse.from_orm(college_review),
        )

    except ValueError as e:
        logger.warning(f"Invalid review data for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid review data: {str(e)}",
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for college review creation by user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to review this application",
        )
    except ValueError as e:
        logger.error(f"Invalid review data for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid review data: {str(e)}",
        )
    except IntegrityError as e:
        logger.error(f"Database integrity error creating review for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Review creation conflicts with existing data",
        )
    except DatabaseError as e:
        logger.error(f"Database error creating review for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable",
        )
    except Exception as e:
        logger.error(f"Unexpected error creating college review for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the review",
        )


@router.put("/reviews/{review_id}", response_model=ApiResponse[CollegeReviewResponse])
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
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this review",
            )

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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid review data: {str(e)}",
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for review update by user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this review",
        )
    except ValueError as e:
        logger.error(f"Invalid review data for update {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid review data: {str(e)}",
        )
    except IntegrityError as e:
        logger.error(f"Database integrity error updating review {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Review update conflicts with existing data",
        )
    except DatabaseError as e:
        logger.error(f"Database error updating review {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable",
        )
    except Exception as e:
        logger.error(f"Unexpected error updating college review {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while updating the review",
        )


@router.get("/rankings", response_model=ApiResponse[List[Dict[str, Any]]])
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
            # Normalize semester for PostgreSQL enum compatibility
            normalized_semester = None
            if semester.lower() == "first":
                normalized_semester = "FIRST"
            elif semester.lower() == "second":
                normalized_semester = "SECOND"
            else:
                normalized_semester = semester
            stmt = stmt.where(CollegeRanking.semester == normalized_semester)

        # Execute query
        result = await db.execute(stmt)
        rankings = result.scalars().all()

        # Format response
        rankings_data = []
        for ranking in rankings:
            rankings_data.append(
                {
                    "id": ranking.id,
                    "ranking_name": ranking.ranking_name,
                    "sub_type_code": ranking.sub_type_code,
                    "academic_year": ranking.academic_year,
                    "semester": ranking.semester,
                    "total_applications": ranking.total_applications,
                    "total_quota": ranking.total_quota,
                    "allocated_count": ranking.allocated_count,
                    "is_finalized": ranking.is_finalized,
                    "ranking_status": ranking.ranking_status,
                    "distribution_executed": ranking.distribution_executed,
                    "created_at": ranking.created_at.isoformat(),
                    "finalized_at": ranking.finalized_at.isoformat() if ranking.finalized_at else None,
                }
            )

        return ApiResponse(
            success=True,
            message=f"Retrieved {len(rankings_data)} rankings successfully",
            data=rankings_data,
        )

    except ValueError as e:
        logger.warning(f"Invalid query parameters for rankings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid query parameters: {str(e)}",
        )
    except CollegeReviewError as e:
        logger.error(f"College review error retrieving rankings: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving rankings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve rankings",
        )


@router.post("/rankings", response_model=ApiResponse[Dict[str, Any]])
async def create_ranking(
    scholarship_type_id: int = Body(..., description="Scholarship type ID"),
    sub_type_code: str = Body(..., description="Sub-type code"),
    academic_year: int = Body(..., description="Academic year"),
    semester: Optional[str] = Body(None, description="Semester"),
    ranking_name: Optional[str] = Body(None, description="Custom ranking name"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ranking for a scholarship sub-type"""

    try:
        # Normalize semester values for PostgreSQL enum compatibility
        # Frontend may send 'first'/'second' or 'FIRST'/'SECOND', but DB expects enum names
        normalized_semester = None
        if semester:
            if semester.lower() == "first":
                normalized_semester = "FIRST"
            elif semester.lower() == "second":
                normalized_semester = "SECOND"
            else:
                normalized_semester = semester  # Keep as-is if it's already correct

        service = CollegeReviewService(db)
        ranking = await service.create_ranking(
            scholarship_type_id=scholarship_type_id,
            sub_type_code=sub_type_code,
            academic_year=academic_year,
            semester=normalized_semester,
            creator_id=current_user.id,
            ranking_name=ranking_name,
        )

        return ApiResponse(
            success=True,
            message="Ranking created successfully",
            data={
                "id": ranking.id,
                "ranking_name": ranking.ranking_name,
                "total_applications": ranking.total_applications,
                "total_quota": ranking.total_quota,
                "sub_type_code": ranking.sub_type_code,
                "academic_year": ranking.academic_year,
                "semester": ranking.semester,
                "created_at": ranking.created_at.isoformat(),
            },
        )

    except ValueError as e:
        logger.warning(f"Invalid ranking creation data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ranking data: {str(e)}",
        )
    except CollegeReviewError as e:
        logger.error(f"College review error creating ranking: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating ranking: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ranking",
        )


@router.get("/rankings/{ranking_id}", response_model=ApiResponse[Dict[str, Any]])
@professor_rate_limit(requests=200, window_seconds=600)  # 200 requests per 10 minutes
async def get_ranking(
    request: Request,
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Get a ranking with all its items"""

    try:
        service = CollegeReviewService(db)
        ranking = await service.get_ranking(ranking_id)

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Format ranking items
        items = []
        for item in sorted(ranking.items, key=lambda x: x.rank_position):
            items.append(
                {
                    "id": item.id,
                    "rank_position": item.rank_position,
                    "is_allocated": item.is_allocated,
                    "status": item.status,
                    "total_score": float(item.total_score) if item.total_score else None,
                    # Lightweight DTO with minimal student exposure
                    "application": {
                        "id": item.application.id,
                        "app_id": item.application.app_id,
                        "status": item.application.status,
                        "scholarship_type": item.application.main_scholarship_type,
                        "sub_type": item.application.sub_scholarship_type,
                        # Minimal student info - only what's needed for ranking display
                        "student_info": {
                            "display_name": (
                                item.application.student_data.get("cname", "學生")
                                if item.application.student_data and isinstance(item.application.student_data, dict)
                                else "學生"
                            ),
                            "student_id_masked": (
                                f"{item.application.student_data.get('stdNo', 'N/A')[:3]}***"
                                if item.application.student_data
                                and isinstance(item.application.student_data, dict)
                                and item.application.student_data.get("stdNo")
                                else "N/A"
                            ),  # Partially mask student ID for privacy
                            "dept_code": (
                                item.application.student_data.get("deptCode", "N/A")[:3]
                                if item.application.student_data and isinstance(item.application.student_data, dict)
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
                "sub_type_code": ranking.sub_type_code,
                "academic_year": ranking.academic_year,
                "semester": ranking.semester,
                "total_applications": ranking.total_applications,
                "total_quota": ranking.total_quota,
                "allocated_count": ranking.allocated_count,
                "is_finalized": ranking.is_finalized,
                "ranking_status": ranking.ranking_status,
                "distribution_executed": ranking.distribution_executed,
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve ranking",
        )


@router.put("/rankings/{ranking_id}/order", response_model=ApiResponse[Dict[str, Any]])
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ranking order",
        )


@router.post("/rankings/{ranking_id}/distribute", response_model=ApiResponse[Dict[str, Any]])
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute distribution",
        )


@router.post("/rankings/{ranking_id}/finalize", response_model=ApiResponse[Dict[str, Any]])
async def finalize_ranking(
    ranking_id: int,
    current_user: User = Depends(require_admin),  # Only admin can finalize rankings
    db: AsyncSession = Depends(get_db),
):
    """Finalize a ranking (makes it read-only)"""

    try:
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize ranking",
        )


@router.get("/quota-status", response_model=ApiResponse[Dict[str, Any]])
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
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
        )

        return ApiResponse(
            success=True,
            message="Quota status retrieved successfully",
            data=quota_status,
        )

    except ValueError as e:
        logger.warning(f"Invalid quota status parameters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid parameters: {str(e)}",
        )
    except CollegeReviewError as e:
        logger.error(f"College review error retrieving quota status: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving quota status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve quota status",
        )


@router.get("/statistics", response_model=ApiResponse[Dict[str, Any]])
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
                join(
                    CollegeReview,
                    Application,
                    CollegeReview.application_id == Application.id,
                )
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

        return ApiResponse(
            success=True,
            message="College review statistics retrieved successfully",
            data=statistics,
        )

    except ValueError as e:
        logger.warning(f"Invalid statistics parameters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid parameters: {str(e)}",
        )
    except CollegeReviewError as e:
        logger.error(f"College review error retrieving statistics: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics",
        )


@router.get("/available-combinations", response_model=ApiResponse[Dict[str, Any]])
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
                ScholarshipConfiguration.is_active == True,
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
                if hasattr(config.semester, "value"):
                    semesters_set.add(config.semester.value)
                else:
                    semesters_set.add(str(config.semester))
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

        return ApiResponse(
            success=True,
            message="Available combinations retrieved successfully",
            data=response_data,
        )

    except Exception as e:
        logger.error(f"Error retrieving available combinations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available combinations from database",
        )
