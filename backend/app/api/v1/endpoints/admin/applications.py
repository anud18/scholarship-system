"""
Admin Applications Management API Endpoints

Handles application-related operations including:
- Application listing and searching
- Historical applications
- Application status updates
- Professor assignment
- Bulk operations
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.security import require_admin
from app.db.deps import get_db
from app.models.application import Application, ApplicationStatus
from app.models.enums import Semester
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.schemas.application import (
    ApplicationListResponse,
    ApplicationStatusUpdate,
    BulkApproveRequest,
    HistoricalApplicationResponse,
    ProfessorAssignmentRequest,
)
from app.schemas.common import PaginatedResponse
from app.services.application_service import ApplicationService
from app.services.bulk_approval_service import BulkApprovalService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/applications")
async def get_all_applications(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by student name or ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all applications with pagination (admin only)"""

    # Build query with joins and load configurations
    stmt = (
        select(Application, User, ScholarshipType)
        .options(selectinload(Application.scholarship_configuration))
        .join(User, Application.user_id == User.id)
        .outerjoin(ScholarshipType, Application.scholarship_type_id == ScholarshipType.id)
    )

    # Apply filters
    if status:
        stmt = stmt.where(Application.status == status)
    else:
        # Default: exclude draft applications for admin view
        stmt = stmt.where(Application.status != ApplicationStatus.draft.value)

    if search:
        stmt = stmt.where(
            (User.name.icontains(search)) | (User.nycu_id.icontains(search)) | (User.email.icontains(search))
        )

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size).order_by(Application.created_at.desc())

    # Execute query
    result = await db.execute(stmt)
    application_tuples = result.fetchall()

    # Convert to response format
    application_list = []
    for app_tuple in application_tuples:
        app, user, scholarship_type = app_tuple

        # Create response data with proper field mapping
        app_data = {
            "id": app.id,
            "app_id": app.app_id,
            "user_id": app.user_id,
            # "student_id": app.student_id,  # Removed - student data now from external API
            "scholarship_type": scholarship_type.code if scholarship_type else "unknown",
            "scholarship_type_id": app.scholarship_type_id or (scholarship_type.id if scholarship_type else None),
            "scholarship_type_zh": scholarship_type.name if scholarship_type else "Unknown Scholarship",
            "scholarship_subtype_list": app.scholarship_subtype_list or [],
            "status": app.status,
            "status_name": app.status_name,
            "academic_year": app.academic_year or str(datetime.now().year - 1911),  # Convert to ROC year
            "semester": app.semester.value if app.semester else "1",
            "student_data": app.student_data or {},
            "submitted_form_data": app.submitted_form_data or {},
            "agree_terms": app.agree_terms or False,
            "professor_id": app.professor_id,
            "reviewer_id": app.reviewer_id,
            "final_approver_id": app.final_approver_id,
            "submitted_at": app.submitted_at,
            "reviewed_at": app.reviewed_at,
            "approved_at": app.approved_at,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
            "meta_data": app.meta_data,
            # Additional fields for display - get from student_data first, fallback to user
            "student_name": (app.student_data.get("std_cname") if app.student_data else None)
            or (user.name if user else None),
            "student_no": (app.student_data.get("std_stdcode") if app.student_data else None)
            or getattr(user, "nycu_id", None),
            "student_email": (app.student_data.get("com_email") if app.student_data else None)
            or (user.email if user else None),
            "days_waiting": None,
            # Include scholarship configuration for professor review settings
            "scholarship_configuration": (
                {
                    "requires_professor_recommendation": (
                        app.scholarship_configuration.requires_professor_recommendation
                        if app.scholarship_configuration
                        else False
                    ),
                    "requires_college_review": (
                        app.scholarship_configuration.requires_college_review
                        if app.scholarship_configuration
                        else False
                    ),
                    "config_name": app.scholarship_configuration.config_name if app.scholarship_configuration else None,
                }
                if app.scholarship_configuration
                else None
            ),
        }

        # Calculate days waiting
        if app.submitted_at:
            now = datetime.now(timezone.utc)
            submitted_time = app.submitted_at

            if submitted_time.tzinfo is None:
                submitted_time = submitted_time.replace(tzinfo=timezone.utc)

            days_diff = (now - submitted_time).days
            app_data["days_waiting"] = max(0, days_diff)

        application_list.append(ApplicationListResponse.model_validate(app_data))

    response_data = PaginatedResponse(
        items=application_list, total=total, page=page, size=size, pages=(total + size - 1) // size
    )

    return {
        "success": True,
        "message": "Applications retrieved successfully",
        "data": response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict(),
    }


@router.get("/applications/history")
async def get_historical_applications(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    status: Optional[str] = Query(None, description="Filter by status"),
    scholarship_type: Optional[str] = Query(None, description="Filter by scholarship type"),
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    search: Optional[str] = Query(None, description="Search by student name or ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get historical applications with advanced filtering (admin only)"""

    # Build base query with joins
    stmt = (
        select(
            Application,
            User.name.label("student_name"),
            User.nycu_id.label("student_nycu_id"),
            User.email.label("student_email"),
            ScholarshipType.name.label("scholarship_name"),
            ScholarshipType.code.label("scholarship_type_code"),
        )
        .join(User, Application.user_id == User.id)
        .outerjoin(ScholarshipType, Application.scholarship_type_id == ScholarshipType.id)
    )

    # Create aliases for joined tables
    from sqlalchemy import alias

    professor_user = alias(User, "professor_user")
    reviewer_user = alias(User, "reviewer_user")

    # Add professor and reviewer information
    stmt = (
        stmt.outerjoin(professor_user, Application.professor_id == professor_user.c.id)
        .outerjoin(reviewer_user, Application.reviewer_id == reviewer_user.c.id)
        .add_columns(professor_user.c.name.label("professor_name"), reviewer_user.c.name.label("reviewer_name"))
    )

    # Apply filters
    if status:
        stmt = stmt.where(Application.status == status)

    if scholarship_type:
        stmt = stmt.where(ScholarshipType.code == scholarship_type)

    if academic_year:
        stmt = stmt.where(Application.academic_year == academic_year)

    if semester and semester != "all":
        if semester == "first":
            stmt = stmt.where(Application.semester == Semester.first)
        elif semester == "second":
            stmt = stmt.where(Application.semester == Semester.second)
        elif semester == "yearly":
            stmt = stmt.where(Application.semester == Semester.yearly)

    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.name.ilike(search_term),
                User.nycu_id.ilike(search_term),
                User.email.ilike(search_term),
                Application.app_id.ilike(search_term),
                ScholarshipType.name.ilike(search_term),
            )
        )

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # Apply pagination and ordering
    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size).order_by(Application.created_at.desc())

    # Execute query
    result = await db.execute(stmt)
    rows = result.fetchall()

    # Convert to response format
    historical_applications = []
    for row in rows:
        app = row.Application

        # Extract student data from JSON if available
        student_data = app.student_data or {}
        student_department = student_data.get("department") or student_data.get("dept_name")

        historical_app = HistoricalApplicationResponse(
            id=app.id,
            app_id=app.app_id,
            status=app.status,
            status_name=HistoricalApplicationResponse.get_status_label(app.status),
            # Student information
            student_name=row.student_name,
            student_id=row.student_nycu_id,
            student_email=row.student_email,
            student_department=student_department,
            # Scholarship information
            scholarship_name=row.scholarship_name,
            scholarship_type_code=row.scholarship_type_code,
            amount=app.amount,
            sub_scholarship_type=app.sub_scholarship_type,
            is_renewal=app.is_renewal,
            # Academic information
            academic_year=app.academic_year,
            semester=app.semester.value if app.semester else None,
            # Important dates
            submitted_at=app.submitted_at,
            reviewed_at=app.reviewed_at,
            approved_at=app.approved_at,
            created_at=app.created_at,
            updated_at=app.updated_at,
            # Review information
            professor_name=getattr(row, "professor_name", None),
            reviewer_name=getattr(row, "reviewer_name", None),
        )

        historical_applications.append(historical_app)

    response_data = PaginatedResponse(
        items=historical_applications, total=total, page=page, size=size, pages=(total + size - 1) // size
    )

    return {
        "success": True,
        "message": "Historical applications retrieved successfully",
        "data": response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict(),
    }


@router.put("/applications/{id}/assign-professor")
async def assign_professor_to_application(
    id: int,
    request: ProfessorAssignmentRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Assign a professor to review an application"""
    try:
        service = ApplicationService(db)
        application = await service.assign_professor(
            application_id=id, professor_nycu_id=request.professor_nycu_id, assigned_by=current_user
        )

        # Create a safe response that doesn't trigger lazy loading
        # Extract student info from student_data JSON field
        student_data = application.student_data or {}
        student_id = student_data.get("std_stdcode") or student_data.get("student_id") or student_data.get("stdNo")

        response_data = {
            "id": application.id,
            "app_id": application.app_id,
            "user_id": application.user_id,
            "student_id": student_id,
            "scholarship_type_id": application.scholarship_type_id,
            "scholarship_subtype_list": application.scholarship_subtype_list or [],
            "status": application.status,
            "status_name": getattr(application, "status_name", application.status),
            "is_renewal": application.is_renewal or False,
            "academic_year": application.academic_year,
            "semester": application.semester.value if application.semester else "1",
            "student_data": application.student_data or {},
            "submitted_form_data": application.submitted_form_data or {},
            "agree_terms": application.agree_terms or False,
            "professor_id": application.professor_id,
            "reviewer_id": application.reviewer_id,
            "final_approver_id": application.final_approver_id,
            "submitted_at": application.submitted_at.isoformat() if application.submitted_at else None,
            "reviewed_at": application.reviewed_at.isoformat() if application.reviewed_at else None,
            "approved_at": application.approved_at.isoformat() if application.approved_at else None,
            "created_at": application.created_at.isoformat(),
            "updated_at": application.updated_at.isoformat(),
            "meta_data": application.meta_data,
            "reviews": [],  # Empty to avoid lazy loading
        }

        return {
            "success": True,
            "message": f"Professor {request.professor_nycu_id} assigned to application {application.app_id}",
            "data": response_data,
        }

    except (NotFoundError, AuthorizationError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if isinstance(e, NotFoundError) else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error assigning professor: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign professor due to a database error.",
        )
    except Exception as e:
        logger.error(f"Unexpected error assigning professor: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign professor due to an unexpected error.",
        )


@router.post("/applications/bulk-approve")
async def bulk_approve_applications_endpoint(
    payload: BulkApproveRequest, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Bulk approve multiple applications."""

    service = BulkApprovalService(db)
    result = await service.bulk_approve_applications(
        application_ids=payload.application_ids,
        approver_user_id=current_user.id,
        approval_notes=payload.comments,
        send_notifications=payload.send_notifications,
    )

    return {"success": True, "message": "Bulk approval processed successfully", "data": result}


@router.patch("/applications/{id}/status")
async def admin_update_application_status(
    id: int,
    status_update: ApplicationStatusUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Update application status (admin version)

    This is a wrapper around the applications endpoint for admin-specific access.
    """
    service = ApplicationService(db)
    result = await service.update_application_status(id, current_user, status_update)
    return {
        "success": True,
        "message": "Application status updated successfully",
        "data": result,
    }
