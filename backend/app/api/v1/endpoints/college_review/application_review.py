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
from app.core.security import require_college
from app.db.deps import get_db
from app.models.application import Application
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
from app.utils.i18n import ScholarshipI18n

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

        # Create StudentService instance for dynamic student data fetching
        student_service = StudentService()

        # Collect all unique department codes for batch query
        department_codes = set()
        for app in applications:
            student_data = app.get("student_data", {}) if isinstance(app.get("student_data"), dict) else {}
            if student_data:
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

            # Build map with department name and academy information from relationship
            department_map = {
                dept.code: {
                    "name": dept.name,
                    "academy_code": dept.academy_code,
                    "academy_name": dept.academy.name if dept.academy else None,
                }
                for dept in departments
            }

        for app in applications:
            # Extract only necessary fields to minimize data exposure
            student_data = app.get("student_data", {}) if isinstance(app.get("student_data"), dict) else {}

            # Check if student_data is empty or missing critical fields
            # If so, try to fetch from external API using application's student_id
            if (
                not student_data
                or (
                    not student_data.get("nycu_id")
                    and not student_data.get("std_stdcode")
                    and not student_data.get("name")
                    and not student_data.get("std_cname")
                )
            ) and app.get("student_id"):
                # Only fetch if API is available
                if student_service.is_api_available():
                    try:
                        logger.info(
                            f"Fetching student data from API for student_id: {app.get('student_id')} (application {app.get('id')})"
                        )
                        fetched_data = await student_service.get_student_basic_info(app.get("student_id"))

                        if fetched_data:
                            logger.info(f"Successfully fetched student data for {app.get('student_id')}")
                            student_data = fetched_data

                            # Optionally update database with fetched data for future requests
                            try:
                                app_stmt = select(Application).where(Application.id == app.get("id"))
                                app_result = await db.execute(app_stmt)
                                app_obj = app_result.scalar_one_or_none()

                                if app_obj:
                                    app_obj.student_data = fetched_data
                                    await db.commit()
                                    logger.info(f"Updated application {app.get('id')} with fetched student data")
                            except Exception as db_err:
                                logger.warning(
                                    f"Failed to update application {app.get('id')} with student data: {str(db_err)}"
                                )
                        else:
                            logger.warning(f"No student data found in API for {app.get('student_id')}")
                    except Exception as e:
                        logger.warning(f"Failed to fetch student data for {app.get('student_id')}: {str(e)}")
                else:
                    logger.debug(f"Student API not available, using existing data for application {app.get('id')}")

            # Extract student info with fallback for both old and new field names
            student_id = (
                (student_data.get("nycu_id") or student_data.get("std_stdcode") or "未提供學號") if student_data else "N/A"
            )

            student_name = (
                (student_data.get("name") or student_data.get("std_cname") or student_data.get("std_ename") or "未提供姓名")
                if student_data
                else "未提供學生資料"
            )

            student_termcount = (
                (student_data.get("term_count") or student_data.get("std_termcount") or "N/A")
                if student_data
                else "N/A"
            )

            department_code = (
                (student_data.get("dept_code") or student_data.get("std_depno") or "N/A") if student_data else "N/A"
            )

            # Get department info from database (includes academy via Department.academy relationship)
            dept_info = department_map.get(department_code) if department_code and department_code != "N/A" else None

            # Extract department name
            department_name = student_data.get("dep_depname") or (  # Prioritize API returned Chinese name
                dept_info["name"] if dept_info else None
            )  # Then lookup from database

            # Extract academy code and name from Department.academy relationship
            academy_code = dept_info["academy_code"] if dept_info else None
            academy_name = student_data.get("aca_cname") or (  # Prioritize API returned Chinese name
                dept_info["academy_name"] if dept_info else None
            )  # Then lookup from Department.academy

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
                "student_id": student_id,
                "student_name": student_name,
                "student_termcount": student_termcount,
                "department_code": department_code,
                "department_name": department_name,
                "academy_code": academy_code,
                "academy_name": academy_name,
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
    current_user: User = Depends(require_college),
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

        basic_info = StudentPreviewBasic(
            student_id=student_id,
            student_name=student_data.get("std_cname") or student_data.get("std_ename") or student_id,
            department_name=department_name,
            academy_name=academy_name,
            term_count=student_data.get("std_termcount"),
            degree=degree_text,
            enrollyear=student_data.get("std_enrollyear"),
            sex=student_data.get("std_sex"),
        )

        # Get recent term data (last 2-3 terms)
        recent_terms = []
        if academic_year:
            # Try to fetch term data for recent semesters
            for year in range(academic_year, max(academic_year - 2, 110), -1):
                for term in ["2", "1"]:  # Second semester first, then first semester
                    try:
                        term_data = await student_service.get_student_term_info(student_id, str(year), term)

                        if term_data:
                            # Extract relevant term information
                            recent_terms.append(
                                StudentTermData(
                                    academic_year=str(year),
                                    term=term,
                                    gpa=term_data.get("trm_gpa"),
                                    credits=term_data.get("trm_credittaken"),
                                    rank=term_data.get("trm_rank"),
                                )
                            )

                            # Stop after getting 3 terms
                            if len(recent_terms) >= 3:
                                break
                    except Exception as term_err:
                        logger.debug(f"Could not fetch term data for {student_id} {year}-{term}: {str(term_err)}")
                        continue

                if len(recent_terms) >= 3:
                    break

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
