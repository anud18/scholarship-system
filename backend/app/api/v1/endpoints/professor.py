"""
Professor review management API endpoints
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.security import require_professor
from app.db.deps import get_db
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.review import ReviewItemResponse, ReviewResponse, ReviewSubmitRequest
from app.services.application_service import ApplicationService
from app.services.review_service import ReviewService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/applications")
async def get_professor_applications(
    request: Request,
    status_filter: Optional[str] = Query(None, description="Filter by review status: pending, completed, all"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db),
):
    """Get applications requiring professor review with pagination"""
    logger.info("Professor {current_user.id} requesting applications for review (page {page}, size {size})")

    try:
        service = ApplicationService(db)
        applications, total_count = await service.get_professor_applications_paginated(
            professor_id=current_user.id,
            status_filter=status_filter,
            page=page,
            size=size,
        )

        # Calculate pagination metadata
        total_pages = (total_count + size - 1) // size  # Ceiling division

        logger.info(
            f"Found {len(applications)} applications (page {page}/{total_pages}, total: {total_count}) for professor {current_user.id}"
        )

        response_data = PaginatedResponse(
            items=applications,
            total=total_count,
            page=page,
            size=size,
            pages=total_pages,
        )
        return {
            "success": True,
            "message": "查詢成功",
            "data": response_data.model_dump(),
        }

    except Exception as e:
        logger.error(f"Error fetching professor applications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching applications",
        )


@router.get("/applications/{application_id}/review")
async def get_professor_review(
    request: Request,
    application_id: int = Path(..., description="Application ID"),
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db),
):
    """Get existing professor review for an application using unified review system"""
    logger.info(f"Professor {current_user.id} requesting review for application {application_id}")

    try:
        review_service = ReviewService(db)
        review = await review_service.get_review_by_application_and_reviewer(
            application_id=application_id, reviewer_id=current_user.id
        )

        if not review:
            # Return null for no review found - frontend should handle this
            return {
                "success": True,
                "message": "查詢成功",
                "data": None,
            }

        # Return new format response directly
        review_response = ReviewResponse(
            id=review.id,
            application_id=review.application_id,
            reviewer_id=review.reviewer_id,
            recommendation=review.recommendation,
            comments=review.comments,
            reviewed_at=review.reviewed_at,
            created_at=review.created_at,
            items=[
                ReviewItemResponse(
                    id=item.id,
                    review_id=item.review_id,
                    sub_type_code=item.sub_type_code,
                    recommendation=item.recommendation,
                    comments=item.comments,
                    created_at=item.created_at,
                )
                for item in review.items
            ],
        )

        return {
            "success": True,
            "message": "查詢成功",
            "data": review_response.model_dump(),
        }

    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professor review not found")
    except Exception as e:
        logger.error(f"Error fetching professor review: {str(e)}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching review",
        )


@router.post("/applications/{application_id}/review")
async def submit_professor_review(
    request: Request,
    review_data: ReviewSubmitRequest,
    application_id: int = Path(..., description="Application ID"),
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db),
):
    """Submit professor review for an application using unified review system"""
    logger.info(f"Professor {current_user.id} submitting review for application {application_id}")

    try:
        service = ApplicationService(db)
        review_service = ReviewService(db)

        # Verify the professor has access to this application
        application = await service.get_application_by_id(application_id, current_user)
        if not application:
            raise NotFoundError("Application not found")

        # Check if professor can submit a review (with time restrictions)
        from app.core.config import settings

        if not settings.bypass_time_restrictions and not await service.can_professor_submit_review(
            application_id, current_user.id
        ):
            raise AuthorizationError("Professor not authorized to submit review at this time or for this application")

        # Create review using unified ReviewService - use new format directly
        items_data = [item.model_dump() for item in review_data.items]
        review = await review_service.create_review(
            application_id=application_id,
            reviewer_id=current_user.id,
            items=items_data,
        )

        # Return new format response directly
        review_response = ReviewResponse(
            id=review.id,
            application_id=review.application_id,
            reviewer_id=review.reviewer_id,
            recommendation=review.recommendation,
            comments=review.comments,
            reviewed_at=review.reviewed_at,
            created_at=review.created_at,
            items=[
                ReviewItemResponse(
                    id=item.id,
                    review_id=item.review_id,
                    sub_type_code=item.sub_type_code,
                    recommendation=item.recommendation,
                    comments=item.comments,
                    created_at=item.created_at,
                )
                for item in review.items
            ],
        )

        logger.info(f"Professor {current_user.id} successfully submitted review for application {application_id}")
        return {
            "success": True,
            "message": "審核提交成功",
            "data": review_response.model_dump(),
        }

    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Error submitting professor review: {str(e)}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while submitting review",
        )


@router.put("/applications/{application_id}/review/{review_id}")
async def update_professor_review(
    request: Request,
    review_data: ReviewSubmitRequest,
    application_id: int = Path(..., description="Application ID"),
    review_id: int = Path(..., description="Review ID"),
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing professor review using unified review system"""
    logger.info(f"Professor {current_user.id} updating review {review_id} for application {application_id}")

    try:
        review_service = ReviewService(db)

        # Verify ownership of the review
        existing_review = await review_service.get_review_by_id(review_id)
        if not existing_review:
            raise NotFoundError("Professor review not found")

        # Verify the professor owns this review
        if existing_review.reviewer_id != current_user.id:
            raise AuthorizationError("Professor not authorized to update this review")

        # Verify the review belongs to the specified application
        if existing_review.application_id != application_id:
            raise AuthorizationError("Review does not belong to the specified application")

        # Update review using unified ReviewService - use new format directly
        items_data = [item.model_dump() for item in review_data.items]
        review = await review_service.update_review(
            review_id=review_id,
            items=items_data,
        )

        # Return new format response directly
        review_response = ReviewResponse(
            id=review.id,
            application_id=review.application_id,
            reviewer_id=review.reviewer_id,
            recommendation=review.recommendation,
            comments=review.comments,
            reviewed_at=review.reviewed_at,
            created_at=review.created_at,
            items=[
                ReviewItemResponse(
                    id=item.id,
                    review_id=item.review_id,
                    sub_type_code=item.sub_type_code,
                    recommendation=item.recommendation,
                    comments=item.comments,
                    created_at=item.created_at,
                )
                for item in review.items
            ],
        )

        logger.info(f"Professor {current_user.id} successfully updated review {review_id}")
        return {
            "success": True,
            "message": "審核更新成功",
            "data": review_response.model_dump(),
        }

    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    except Exception as e:
        logger.error(f"Error updating professor review: {str(e)}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while updating review",
        )


@router.get("/applications/{application_id}/sub-types")
async def get_application_sub_types(
    request: Request,
    application_id: int = Path(..., description="Application ID"),
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db),
):
    """Get available sub-types for an application (config-driven)"""
    logger.info("Professor {current_user.id} requesting sub-types for application {application_id}")

    try:
        service = ApplicationService(db)
        sub_types = await service.get_application_available_sub_types(application_id)

        logger.info("Found {len(sub_types)} sub-types for application {application_id}")
        return {
            "success": True,
            "message": "查詢成功",
            "data": sub_types,
        }

    except Exception as e:
        logger.error(f"Error fetching application sub-types: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching sub-types",
        )


@router.get("/stats")
async def get_professor_review_stats(
    request: Request,
    current_user: User = Depends(require_professor),
    db: AsyncSession = Depends(get_db),
):
    """Get basic review statistics for the professor (minimal dashboard data)"""
    logger.info("Professor {current_user.id} requesting review statistics")

    try:
        service = ApplicationService(db)
        stats = await service.get_professor_review_stats(current_user.id)

        stats_data = {
            "pending_reviews": stats.get("pending_reviews", 0),
            "completed_reviews": stats.get("completed_reviews", 0),
            "overdue_reviews": stats.get("overdue_reviews", 0),
        }
        return {
            "success": True,
            "message": "查詢成功",
            "data": stats_data,
        }

    except Exception as e:
        logger.error(f"Error fetching professor stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching statistics",
        )
