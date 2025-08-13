"""
Professor review management API endpoints
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.db.deps import get_db
from app.schemas.application import (
    ApplicationResponse, ProfessorReviewCreate, ProfessorReviewResponse
)
from app.schemas.common import MessageResponse
from app.services.application_service import ApplicationService
from app.core.security import get_current_user, require_professor
from app.models.user import User
from app.core.exceptions import NotFoundError, AuthorizationError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/applications", response_model=List[ApplicationResponse])
async def get_professor_applications(
    status_filter: Optional[str] = Query(None, description="Filter by review status: pending, completed, all"),
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db)
):
    """Get applications requiring professor review"""
    logger.info(f"Professor {current_user.id} requesting applications for review")
    
    try:
        service = ApplicationService(db)
        applications = await service.get_professor_pending_applications(
            professor_id=current_user.id,
            status_filter=status_filter
        )
        
        logger.info(f"Found {len(applications)} applications for professor {current_user.id}")
        return applications
        
    except Exception as e:
        logger.error(f"Error fetching professor applications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch applications: {str(e)}"
        )


@router.get("/applications/{application_id}/review", response_model=ProfessorReviewResponse)
async def get_professor_review(
    application_id: int = Path(..., description="Application ID"),
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db)
):
    """Get existing professor review for an application"""
    logger.info(f"Professor {current_user.id} requesting review for application {application_id}")
    
    try:
        service = ApplicationService(db)
        review = await service.get_professor_review(
            application_id=application_id,
            professor_id=current_user.id
        )
        
        if not review:
            raise NotFoundError("Professor review not found")
            
        return review
        
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Professor review not found"
        )
    except Exception as e:
        logger.error(f"Error fetching professor review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch review: {str(e)}"
        )


@router.post("/applications/{application_id}/review", response_model=ProfessorReviewResponse)
async def submit_professor_review(
    review_data: ProfessorReviewCreate,
    application_id: int = Path(..., description="Application ID"),
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db)
):
    """Submit professor review for an application"""
    logger.info(f"Professor {current_user.id} submitting review for application {application_id}")
    
    try:
        service = ApplicationService(db)
        
        # Verify the professor has access to this application
        application = await service.get_application(application_id)
        if not application:
            raise NotFoundError("Application not found")
            
        # Check if professor is authorized for this application
        # This could be based on student-professor relationships or scholarship configuration
        if not await service.can_professor_review_application(application_id, current_user.id):
            raise AuthorizationError("Professor not authorized to review this application")
            
        # Submit the review
        review = await service.submit_professor_review(
            application_id=application_id,
            professor_id=current_user.id,
            review_data=review_data.dict()
        )
        
        logger.info(f"Professor {current_user.id} successfully submitted review for application {application_id}")
        return review
        
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error submitting professor review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit review: {str(e)}"
        )


@router.put("/applications/{application_id}/review/{review_id}", response_model=ProfessorReviewResponse)
async def update_professor_review(
    review_data: ProfessorReviewCreate,
    application_id: int = Path(..., description="Application ID"),
    review_id: int = Path(..., description="Review ID"),
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing professor review"""
    logger.info(f"Professor {current_user.id} updating review {review_id} for application {application_id}")
    
    try:
        service = ApplicationService(db)
        
        # Verify ownership of the review
        existing_review = await service.get_professor_review(application_id, current_user.id)
        if not existing_review or existing_review.id != review_id:
            raise AuthorizationError("Professor not authorized to update this review")
            
        # Update the review
        review = await service.update_professor_review(
            review_id=review_id,
            review_data=review_data.dict()
        )
        
        logger.info(f"Professor {current_user.id} successfully updated review {review_id}")
        return review
        
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating professor review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update review: {str(e)}"
        )


@router.get("/applications/{application_id}/sub-types", response_model=List[dict])
async def get_application_sub_types(
    application_id: int = Path(..., description="Application ID"),
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db)
):
    """Get available sub-types for an application (config-driven)"""
    logger.info(f"Professor {current_user.id} requesting sub-types for application {application_id}")
    
    try:
        service = ApplicationService(db)
        sub_types = await service.get_application_available_sub_types(application_id)
        
        logger.info(f"Found {len(sub_types)} sub-types for application {application_id}")
        return sub_types
        
    except Exception as e:
        logger.error(f"Error fetching application sub-types: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sub-types: {str(e)}"
        )


@router.get("/stats", response_model=dict)
async def get_professor_review_stats(
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db)
):
    """Get basic review statistics for the professor (minimal dashboard data)"""
    logger.info(f"Professor {current_user.id} requesting review statistics")
    
    try:
        service = ApplicationService(db)
        stats = await service.get_professor_review_stats(current_user.id)
        
        return {
            "pending_reviews": stats.get("pending_reviews", 0),
            "completed_reviews": stats.get("completed_reviews", 0),
            "overdue_reviews": stats.get("overdue_reviews", 0)
        }
        
    except Exception as e:
        logger.error(f"Error fetching professor stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch statistics: {str(e)}"
        )