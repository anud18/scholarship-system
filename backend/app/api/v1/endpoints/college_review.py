"""
College Review API Endpoints

This module provides API endpoints for college-level review operations including:
- Application review and scoring
- Ranking management
- Quota distribution
- Review statistics and reporting
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, validator

from app.db.deps import get_db
from app.core.security import require_college, require_admin, get_current_user
from app.models.user import User, UserRole
from app.models.college_review import CollegeReview, CollegeRanking, QuotaDistribution
from app.models.application import Application
from app.schemas.response import ApiResponse
from app.services.college_review_service import CollegeReviewService, QuotaDistributionService
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)


# Pydantic schemas for request/response
class CollegeReviewCreate(BaseModel):
    """Schema for creating a college review"""
    academic_score: Optional[float] = Field(None, ge=0, le=100, description="Academic performance score (0-100)")
    professor_review_score: Optional[float] = Field(None, ge=0, le=100, description="Professor review score (0-100)")
    college_criteria_score: Optional[float] = Field(None, ge=0, le=100, description="College-specific criteria score (0-100)")
    special_circumstances_score: Optional[float] = Field(None, ge=0, le=100, description="Special circumstances score (0-100)")
    review_comments: Optional[str] = Field(None, max_length=2000, description="Detailed review comments")
    recommendation: str = Field(..., description="Review recommendation", pattern="^(approve|reject|conditional)$")
    decision_reason: Optional[str] = Field(None, max_length=1000, description="Reason for the recommendation")
    is_priority: Optional[bool] = Field(False, description="Mark as priority application")
    needs_special_attention: Optional[bool] = Field(False, description="Flag for special review")
    scoring_weights: Optional[Dict[str, float]] = Field(None, description="Custom scoring weights")
    
    @validator('academic_score', 'professor_review_score', 'college_criteria_score', 'special_circumstances_score')
    def validate_scores(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError('Score must be between 0 and 100')
        return v
    
    @validator('scoring_weights')
    def validate_scoring_weights(cls, v):
        if v is not None:
            # Ensure all weight values are between 0 and 1
            for key, weight in v.items():
                if not isinstance(weight, (int, float)) or weight < 0 or weight > 1:
                    raise ValueError(f'Weight for {key} must be between 0 and 1')
            # Ensure weights sum to approximately 1.0
            total_weight = sum(v.values())
            if abs(total_weight - 1.0) > 0.01:  # Allow small floating point errors
                raise ValueError('Scoring weights must sum to 1.0')
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
    
    @validator('academic_score', 'professor_review_score', 'college_criteria_score', 'special_circumstances_score')
    def validate_scores(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError('Score must be between 0 and 100')
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


@router.get("/applications", response_model=ApiResponse[List[Dict[str, Any]]])
async def get_applications_for_review(
    scholarship_type_id: Optional[int] = Query(None, description="Filter by scholarship type"),
    sub_type: Optional[str] = Query(None, description="Filter by sub-type"),
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db)
):
    """Get applications that are ready for college review"""
    
    # Additional authorization check
    if not current_user.is_college() and current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="College role required for application review access"
        )
    
    try:
        service = CollegeReviewService(db)
        applications = await service.get_applications_for_review(
            scholarship_type_id=scholarship_type_id,
            sub_type=sub_type,
            reviewer_id=current_user.id,
            academic_year=academic_year,
            semester=semester
        )
        
        # Filter sensitive student data - only return necessary fields
        filtered_applications = []
        for app in applications:
            filtered_app = {
                "id": app.get("id"),
                "app_id": app.get("app_id"),
                "status": app.get("status"),
                "scholarship_type": app.get("scholarship_type"),
                "sub_type": app.get("sub_type"),
                "created_at": app.get("created_at"),
                "submitted_at": app.get("submitted_at"),
                # Only include essential student info
                "student_info": {
                    "name": app.get("student_data", {}).get("cname", "N/A"),
                    "student_no": app.get("student_data", {}).get("stdNo", "N/A"),
                    "department": app.get("student_data", {}).get("department", "N/A")
                } if app.get("student_data") else None
            }
            filtered_applications.append(filtered_app)
        
        return ApiResponse(
            success=True,
            message="Applications for review retrieved successfully",
            data=filtered_applications
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid request parameters for college applications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request parameters: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to retrieve applications for review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve applications for review"
        )


@router.post("/applications/{application_id}/review", response_model=ApiResponse[CollegeReviewResponse])
async def create_college_review(
    application_id: int,
    review_data: CollegeReviewCreate,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db)
):
    """Create or update a college review for an application"""
    
    # Additional authorization check
    if not current_user.is_college() and current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="College role required for application review"
        )
    
    # Validate application_id
    if application_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid application ID"
        )
    
    try:
        service = CollegeReviewService(db)
        college_review = await service.create_or_update_review(
            application_id=application_id,
            reviewer_id=current_user.id,
            review_data=review_data.dict(exclude_unset=True)
        )
        
        return ApiResponse(
            success=True,
            message="College review created successfully",
            data=CollegeReviewResponse.from_orm(college_review)
        )
    
    except ValueError as e:
        logger.warning(f"Invalid review data for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid review data: {str(e)}"
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for college review creation by user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to review this application"
        )
    except Exception as e:
        logger.error(f"Failed to create college review for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create college review"
        )


@router.put("/reviews/{review_id}", response_model=ApiResponse[CollegeReviewResponse])
async def update_college_review(
    review_id: int,
    review_data: CollegeReviewUpdate,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing college review"""
    
    try:
        # Get existing review
        stmt = select(CollegeReview).where(CollegeReview.id == review_id)
        result = await db.execute(stmt)
        college_review = result.scalar_one_or_none()
        
        if not college_review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="College review not found"
            )
        
        # Check permissions
        if college_review.reviewer_id != current_user.id and current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this review"
            )
        
        # Update review
        service = CollegeReviewService(db)
        updated_review = await service.create_or_update_review(
            application_id=college_review.application_id,
            reviewer_id=college_review.reviewer_id,
            review_data=review_data.dict(exclude_unset=True)
        )
        
        return ApiResponse(
            success=True,
            message="College review updated successfully",
            data=CollegeReviewResponse.from_orm(updated_review)
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid review data for review {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid review data: {str(e)}"
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for review update by user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this review"
        )
    except Exception as e:
        logger.error(f"Failed to update college review {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update college review"
        )


@router.get("/rankings", response_model=ApiResponse[List[Dict[str, Any]]])
async def get_rankings(
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db)
):
    """Get all rankings for the current user or all if admin"""
    
    try:
        # Build base query
        stmt = select(CollegeRanking)
        
        # Apply filters
        if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
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
            rankings_data.append({
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
                "finalized_at": ranking.finalized_at.isoformat() if ranking.finalized_at else None
            })
        
        return ApiResponse(
            success=True,
            message=f"Retrieved {len(rankings_data)} rankings successfully",
            data=rankings_data
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve rankings: {str(e)}"
        )


@router.post("/rankings", response_model=ApiResponse[Dict[str, Any]])
async def create_ranking(
    scholarship_type_id: int = Body(..., description="Scholarship type ID"),
    sub_type_code: str = Body(..., description="Sub-type code"),
    academic_year: int = Body(..., description="Academic year"),
    semester: Optional[str] = Body(None, description="Semester"),
    ranking_name: Optional[str] = Body(None, description="Custom ranking name"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db)
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
            ranking_name=ranking_name
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
                "created_at": ranking.created_at.isoformat()
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create ranking: {str(e)}"
        )


@router.get("/rankings/{ranking_id}", response_model=ApiResponse[Dict[str, Any]])
async def get_ranking(
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db)
):
    """Get a ranking with all its items"""
    
    try:
        service = CollegeReviewService(db)
        ranking = await service.get_ranking(ranking_id)
        
        if not ranking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ranking not found"
            )
        
        # Format ranking items
        items = []
        for item in sorted(ranking.items, key=lambda x: x.rank_position):
            items.append({
                "id": item.id,
                "rank_position": item.rank_position,
                "is_allocated": item.is_allocated,
                "status": item.status,
                "total_score": float(item.total_score) if item.total_score else None,
                "application": {
                    "id": item.application.id,
                    "app_id": item.application.app_id,
                    # Only expose essential student information
                    "student_name": item.application.student_data.get('cname', 'N/A') if item.application.student_data else 'N/A',
                    "student_no": item.application.student_data.get('stdNo', 'N/A') if item.application.student_data else 'N/A',
                    "department": item.application.student_data.get('department', 'N/A') if item.application.student_data else 'N/A',
                    "scholarship_type": item.application.main_scholarship_type,
                    "sub_type": item.application.sub_scholarship_type,
                    "status": item.application.status
                }
            })
        
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
                "created_at": ranking.created_at.isoformat()
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve ranking: {str(e)}"
        )


@router.put("/rankings/{ranking_id}/order", response_model=ApiResponse[Dict[str, Any]])
async def update_ranking_order(
    ranking_id: int,
    new_order: List[RankingOrderUpdate],
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db)
):
    """Update the ranking order of applications"""
    
    try:
        service = CollegeReviewService(db)
        ranking = await service.update_ranking_order(
            ranking_id=ranking_id,
            new_order=[item.dict() for item in new_order]
        )
        
        return ApiResponse(
            success=True,
            message="Ranking order updated successfully",
            data={
                "id": ranking.id,
                "updated_at": ranking.updated_at.isoformat()
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update ranking order: {str(e)}"
        )


@router.post("/rankings/{ranking_id}/distribute", response_model=ApiResponse[Dict[str, Any]])
async def execute_quota_distribution(
    ranking_id: int,
    distribution_request: QuotaDistributionRequest,
    current_user: User = Depends(require_admin),  # Only admin can execute distribution
    db: AsyncSession = Depends(get_db)
):
    """Execute quota-based distribution for a ranking"""
    
    try:
        service = CollegeReviewService(db)
        distribution = await service.execute_quota_distribution(
            ranking_id=ranking_id,
            executor_id=current_user.id,
            distribution_rules=distribution_request.distribution_rules
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
                "executed_at": distribution.executed_at.isoformat()
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute distribution: {str(e)}"
        )


@router.post("/rankings/{ranking_id}/finalize", response_model=ApiResponse[Dict[str, Any]])
async def finalize_ranking(
    ranking_id: int,
    current_user: User = Depends(require_admin),  # Only admin can finalize rankings
    db: AsyncSession = Depends(get_db)
):
    """Finalize a ranking (makes it read-only)"""
    
    try:
        service = CollegeReviewService(db)
        ranking = await service.finalize_ranking(
            ranking_id=ranking_id,
            finalizer_id=current_user.id
        )
        
        return ApiResponse(
            success=True,
            message="Ranking finalized successfully",
            data={
                "id": ranking.id,
                "is_finalized": ranking.is_finalized,
                "finalized_at": ranking.finalized_at.isoformat(),
                "ranking_status": ranking.ranking_status
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to finalize ranking: {str(e)}"
        )


@router.get("/quota-status", response_model=ApiResponse[Dict[str, Any]])
async def get_quota_status(
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None, description="Semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db)
):
    """Get quota status for a scholarship type"""
    
    try:
        service = CollegeReviewService(db)
        quota_status = await service.get_quota_status(
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester
        )
        
        return ApiResponse(
            success=True,
            message="Quota status retrieved successfully",
            data=quota_status
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve quota status: {str(e)}"
        )


@router.get("/statistics", response_model=ApiResponse[Dict[str, Any]])
async def get_college_review_statistics(
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db)
):
    """Get college review statistics"""
    
    try:
        # Build statistics query
        base_query = select(CollegeReview)
        
        if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
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
        approved_count = len([r for r in reviews if r.recommendation == 'approve'])
        rejected_count = len([r for r in reviews if r.recommendation == 'reject'])
        conditional_count = len([r for r in reviews if r.recommendation == 'conditional'])
        
        avg_ranking_score = sum(r.ranking_score for r in reviews if r.ranking_score) / len([r for r in reviews if r.ranking_score]) if reviews else 0
        
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
                "conditional": conditional_count
            }
        }
        
        return ApiResponse(
            success=True,
            message="College review statistics retrieved successfully",
            data=statistics
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statistics: {str(e)}"
        )