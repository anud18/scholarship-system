"""
Application Review API Endpoints

Handles:
- Retrieving applications for review
- Creating and updating college reviews
- Student preview functionality
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import DatabaseError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_college, require_roles
from app.db.deps import get_db

# Note: CollegeReview model removed - replaced by unified ApplicationReview system
# from app.models.college_review import CollegeReview
from app.models.user import User, UserRole
from app.schemas.college_review import StudentTermData
from app.schemas.response import ApiResponse
from app.services.college_review_service import CollegeReviewService, ReviewPermissionError
from app.services.student_service import StudentService

from ._helpers import _check_academic_year_permission, _check_scholarship_permission

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/applications")
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
        # Get college code for filtering (None for super_admin to see all)
        college_code = current_user.college_code if current_user.role == UserRole.college else None

        # Get raw applications from service
        service = CollegeReviewService(db)
        applications = await service.get_applications_for_review(
            scholarship_type_id=scholarship_type_id,
            scholarship_type=scholarship_type,
            sub_type=sub_type,
            reviewer_id=current_user.id,
            academic_year=academic_year,
            semester=semester,
            college_code=college_code,
        )

        # Enrich applications with student data and scholarship period info (parallel processing)
        from app.services.application_enricher_service import ApplicationEnricherService

        enricher = ApplicationEnricherService(db)
        enriched_applications = await enricher.enrich_applications_for_review(applications)

        return ApiResponse(
            success=True, message="Applications for review retrieved successfully", data=enriched_applications
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid request parameters for college applications: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid request parameters: {str(e)}")
    except ReviewPermissionError as e:
        logger.warning(f"Permission denied for college applications access: {str(e)}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
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


# NOTE: Review endpoints moved to /api/v1/reviews/* for multi-role support
# See backend/app/api/v1/endpoints/reviews.py:
# - POST /api/v1/reviews/applications/{id}/review (submit review)
# - GET /api/v1/reviews/applications/{id}/review (get user's review)
# - GET /api/v1/reviews/applications/{id}/sub-types (get reviewable sub-types)


# REMOVED: PUT /reviews/{review_id} endpoint
# This endpoint was removed as part of CollegeReview table removal (Phase 3).
# The CollegeReview model and create_or_update_review() service method no longer exist.
# Use the unified review system at /api/v1/reviews/* instead for all review operations.


@router.get("/students/{student_id}/preview")
async def get_student_preview(
    request: Request,
    student_id: str,
    academic_year: Optional[int] = Query(None, description="Current academic year for term data"),
    current_user: User = Depends(require_roles(UserRole.college, UserRole.admin, UserRole.super_admin)),
    db: AsyncSession = Depends(get_db),
):
    """
    Get student preview information for college review

    Returns basic student information and recent term data.
    College users can only preview students in applications they manage.
    """

    try:
        logger.info(f"User {current_user.id} requesting preview for student {student_id}")

        # Initialize student service
        student_service = StudentService()

        # Get student basic info from API
        student_data = await student_service.get_student_basic_info(student_id)

        if not student_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student {student_id} not found")

        # Get recent term data from current academic year back to enrollment year
        recent_terms = []
        if academic_year:
            enroll_year = int(
                student_data.get("std_enrollyear", academic_year)
            )  # Get enrollment year, fallback to current academic_year

            # Loop from current academic year down to enrollment year
            for year in range(academic_year, enroll_year - 1, -1):
                for term in ["2", "1"]:  # Second semester first, then first semester
                    try:
                        term_data = await student_service.get_student_term_info(student_id, str(year), term)

                        if term_data:
                            # Extract ALL available term information from external API
                            recent_terms.append(
                                StudentTermData(
                                    # Basic term info
                                    academic_year=str(year),
                                    term=term,
                                    term_count=term_data.get("trm_termcount"),
                                    # Academic performance
                                    gpa=term_data.get("trm_ascore_gpa"),  # API only provides ascore_gpa
                                    ascore_gpa=term_data.get("trm_ascore_gpa"),
                                    # Rankings
                                    placings=term_data.get("trm_placings"),
                                    placings_rate=term_data.get("trm_placingsrate"),
                                    dept_placing=term_data.get("trm_depplacing"),
                                    dept_placing_rate=term_data.get("trm_depplacingrate"),
                                    # Student status
                                    studying_status=term_data.get("trm_studystatus"),
                                    degree=term_data.get("trm_degree"),
                                    # Academic organization
                                    academy_no=term_data.get("trm_academyno"),
                                    academy_name=term_data.get("trm_academyname"),
                                    dept_no=term_data.get("trm_depno"),
                                    dept_name=term_data.get("trm_depname"),
                                )
                            )
                    except Exception as term_err:
                        logger.debug(f"Could not fetch term data for {student_id} {year}-{term}: {str(term_err)}")
                        continue

        return ApiResponse(
            success=True,
            message="Student preview retrieved successfully",
            data={
                "basic": student_data,
                "recent_terms": [term.model_dump() for term in recent_terms],
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving student preview for {student_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve student preview: {str(e)}"
        )
