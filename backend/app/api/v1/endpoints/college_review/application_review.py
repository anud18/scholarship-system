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
from sqlalchemy import select
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rate_limiting import professor_rate_limit
from app.core.security import require_college, require_roles
from app.db.deps import get_db
from app.models.audit_log import AuditAction
from app.models.college_review import CollegeReview
from app.models.student import Department
from app.models.user import User, UserRole
from app.schemas.college_review import (
    CollegeReviewCreate,
    CollegeReviewResponse,
    CollegeReviewUpdate,
    StudentPreviewBasic,
    StudentPreviewResponse,
    StudentTermData,
)
from app.schemas.response import ApiResponse
from app.services.application_audit_service import ApplicationAuditService
from app.services.college_review_service import CollegeReviewService, ReviewPermissionError
from app.services.student_service import StudentService

from ._helpers import (
    _check_academic_year_permission,
    _check_application_review_permission,
    _check_scholarship_permission,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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

        # Log the college review operation
        audit_service = ApplicationAuditService(db)
        await audit_service.log_application_operation(
            application_id=application_id,
            action=AuditAction.college_review,
            user=current_user,
            request=request,
            description=f"College review created with recommendation: {review_data.recommendation}",
            new_values={
                "recommendation": review_data.recommendation,
                "academic_score": review_data.academic_score,
                "professor_review_score": review_data.professor_review_score,
                "college_criteria_score": review_data.college_criteria_score,
                "special_circumstances_score": review_data.special_circumstances_score,
                "decision_reason": review_data.decision_reason,
                "is_priority": review_data.is_priority,
            },
            status="success",
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

        # Capture old values for audit log
        old_values = {
            "recommendation": college_review.recommendation,
            "academic_score": college_review.academic_score,
            "professor_review_score": college_review.professor_review_score,
            "college_criteria_score": college_review.college_criteria_score,
            "special_circumstances_score": college_review.special_circumstances_score,
            "decision_reason": college_review.decision_reason,
            "is_priority": college_review.is_priority,
        }

        # Update review
        service = CollegeReviewService(db)
        updated_review = await service.create_or_update_review(
            application_id=college_review.application_id,
            reviewer_id=college_review.reviewer_id,
            review_data=review_data.dict(exclude_unset=True),
        )

        # Log the college review update operation
        audit_service = ApplicationAuditService(db)
        new_values = {
            "recommendation": updated_review.recommendation,
            "academic_score": updated_review.academic_score,
            "professor_review_score": updated_review.professor_review_score,
            "college_criteria_score": updated_review.college_criteria_score,
            "special_circumstances_score": updated_review.special_circumstances_score,
            "decision_reason": updated_review.decision_reason,
            "is_priority": updated_review.is_priority,
        }

        # Build description highlighting the key changes
        description_parts = ["College review updated"]
        if old_values["recommendation"] != new_values["recommendation"]:
            description_parts.append(f"recommendation: {old_values['recommendation']} → {new_values['recommendation']}")

        await audit_service.log_application_operation(
            application_id=college_review.application_id,
            action=AuditAction.college_review_update,
            user=current_user,
            request=None,
            description="; ".join(description_parts),
            old_values=old_values,
            new_values=new_values,
            status="success",
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


@router.get("/students/{student_id}/preview")
@professor_rate_limit(requests=100, window_seconds=600)  # 100 requests per 10 minutes
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

        # Get department and academy info
        dept_code = student_data.get("std_depno") or student_data.get("dept_code")
        department_name = None
        academy_name = None

        if dept_code:
            dept_stmt = select(Department).options(selectinload(Department.academy)).where(Department.code == dept_code)
            dept_result = await db.execute(dept_stmt)
            dept = dept_result.scalar_one_or_none()

            if dept:
                department_name = dept.name
                if dept.academy:
                    academy_name = dept.academy.name

        # Fallback to API data if database doesn't have department info
        if not department_name:
            department_name = student_data.get("dep_depname")
        if not academy_name:
            academy_name = student_data.get("aca_cname")

        # Map degree code to readable text
        degree_map = {
            "1": "博士",
            "2": "碩士",
            "3": "學士",
        }
        degree_code = student_data.get("std_degree", "3")
        degree_text = degree_map.get(degree_code, "學士")

        # Convert integer values to strings for Pydantic validation
        enrollyear_value = student_data.get("std_enrollyear")
        sex_value = student_data.get("std_sex")

        basic_info = StudentPreviewBasic(
            student_id=student_id,
            student_name=student_data.get("std_cname") or student_data.get("std_ename") or student_id,
            department_name=department_name,
            academy_name=academy_name,
            term_count=student_data.get("std_termcount"),
            degree=degree_text,
            enrollyear=str(enrollyear_value) if enrollyear_value is not None else None,
            sex=str(sex_value) if sex_value is not None else None,
        )

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

        preview_response = StudentPreviewResponse(
            basic=basic_info,
            recent_terms=recent_terms,
        )

        return ApiResponse(
            success=True,
            message="Student preview retrieved successfully",
            data=preview_response.model_dump(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving student preview for {student_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve student preview: {str(e)}"
        )
