"""
Enhanced scholarship management API endpoints - REFACTORED
Provides comprehensive scholarship application management with priority processing

Major changes:
- Removed ScholarshipMainType enum dependency
- Removed ScholarshipQuotaService (replaced by QuotaService)
- main_scholarship_type field removed from all responses
- Quota endpoints deprecated (use quota_dashboard endpoints instead)
- Dashboard and types endpoints now use ScholarshipType table
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin, require_staff, require_student
from app.db.deps import get_db
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipStatus, ScholarshipType
from app.models.user import User
from app.schemas.response import ApiResponse
from app.services.scholarship_service import ScholarshipApplicationService
from app.utils.scholarship_helpers import get_distinct_sub_types

router = APIRouter()

# Application Management Endpoints


@router.post("/applications/create-comprehensive")
async def create_comprehensive_application(
    application_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Create a comprehensive scholarship application with all new features"""
    from sqlalchemy.orm import sessionmaker

    from app.services.application_service import get_student_data_from_user

    # Convert AsyncSession to regular Session for our service
    sync_session = sessionmaker(bind=db.bind)()

    try:
        student = await get_student_data_from_user(current_user)
        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found")

        service = ScholarshipApplicationService(sync_session)

        application, message = service.create_application(
            user_id=current_user.id,
            student_id=current_user.id,
            scholarship_type_id=application_data["scholarship_type_id"],
            scholarship_type_code=application_data["scholarship_type_code"],
            semester=application_data["semester"],
            academic_year=application_data["academic_year"],
            application_data=application_data.get("form_data", {}),
            is_renewal=application_data.get("is_renewal", False),
            previous_application_id=application_data.get("previous_application_id"),
        )

        return ApiResponse(
            success=True,
            message=message,
            data={
                "application_id": application.id,
                "app_id": application.app_id,
                "scholarship_type_id": application.scholarship_type_id,
                "sub_type": application.sub_scholarship_type,
                "is_renewal": application.is_renewal,
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Application creation failed: {str(e)}")
    finally:
        sync_session.close()


@router.post("/applications/{application_id}/submit-comprehensive")
async def submit_comprehensive_application(
    application_id: int = Path(...),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Submit application with comprehensive workflow management"""
    from sqlalchemy.orm import sessionmaker

    sync_session = sessionmaker(bind=db.bind)()

    try:
        service = ScholarshipApplicationService(sync_session)
        success, message = service.submit_application(application_id)

        if not success:
            raise HTTPException(status_code=400, detail=message)

        return ApiResponse(success=True, message=message, data={"application_id": application_id})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Submission failed: {str(e)}")
    finally:
        sync_session.close()


@router.get("/applications/by-priority")
async def get_applications_by_priority(
    scholarship_type_id: Optional[int] = Query(None),
    semester: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Get applications ordered by priority score"""
    from sqlalchemy.orm import sessionmaker

    sync_session = sessionmaker(bind=db.bind)()

    try:
        service = ScholarshipApplicationService(sync_session)

        # Convert string status to enum if provided
        status_enum = None
        if status:
            try:
                status_enum = ApplicationStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        applications = service.get_applications_by_priority(
            scholarship_type_id=scholarship_type_id,
            semester=semester,
            status=status_enum,
            limit=limit,
        )

        application_data = []
        for app in applications:
            application_data.append(
                {
                    "id": app.id,
                    "app_id": app.app_id,
                    "student_id": app.student_id,
                    "scholarship_type_id": app.scholarship_type_id,
                    "sub_type": app.sub_scholarship_type,
                    "is_renewal": app.is_renewal,
                    "status": app.status,
                    "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
                    "review_deadline": app.review_deadline.isoformat() if app.review_deadline else None,
                    "is_overdue": app.is_overdue,
                }
            )

        return ApiResponse(
            success=True,
            message=f"Retrieved {len(applications)} applications",
            data={
                "applications": application_data,
                "total": len(applications),
                "filters": {
                    "scholarship_type_id": scholarship_type_id,
                    "semester": semester,
                    "status": status,
                },
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve applications: {str(e)}")
    finally:
        sync_session.close()


# Renewal Processing Endpoints


@router.post("/renewals/process-priority")
async def process_renewal_applications(
    semester: str = Body(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Process renewal applications with priority"""
    from sqlalchemy.orm import sessionmaker

    sync_session = sessionmaker(bind=db.bind)()

    try:
        service = ScholarshipApplicationService(sync_session)
        result = service.process_renewal_applications_first(semester)

        return ApiResponse(
            success=True,
            message="Renewal applications processed successfully",
            data=result,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process renewals: {str(e)}")
    finally:
        sync_session.close()


# Analytics and Dashboard Endpoints


@router.get("/analytics/dashboard")
async def get_scholarship_dashboard(
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive scholarship management dashboard data"""
    try:
        # Build base query filter
        conditions = [Application.academic_year == academic_year]
        if semester:
            conditions.append(Application.semester == semester)

        # Get overall statistics
        total_result = await db.execute(select(func.count(Application.id)).where(and_(*conditions)))
        total_applications = total_result.scalar() or 0

        renewal_result = await db.execute(
            select(func.count(Application.id)).where(and_(*conditions, Application.is_renewal.is_(True)))
        )
        renewal_applications = renewal_result.scalar() or 0
        new_applications = total_applications - renewal_applications

        # Status breakdown
        status_breakdown = {}
        for status in ApplicationStatus:
            status_result = await db.execute(
                select(func.count(Application.id)).where(and_(*conditions, Application.status == status.value))
            )
            count = status_result.scalar() or 0
            status_breakdown[status.value] = count

        # Get all active scholarship types
        scholarship_types_result = await db.execute(
            select(ScholarshipType).where(ScholarshipType.status == ScholarshipStatus.active.value)
        )
        scholarship_types = scholarship_types_result.scalars().all()

        # Get distinct sub-types for filtering
        sub_types = await get_distinct_sub_types(db, academic_year=academic_year, semester=semester)

        # Type breakdown by scholarship_type_id and sub_type
        type_breakdown = {}
        for scholarship_type in scholarship_types:
            for sub_type in sub_types:
                count_result = await db.execute(
                    select(func.count(Application.id)).where(
                        and_(
                            *conditions,
                            Application.scholarship_type_id == scholarship_type.id,
                            Application.sub_scholarship_type == sub_type,
                        )
                    )
                )
                count = count_result.scalar() or 0
                if count > 0:
                    key = f"{scholarship_type.code}_{sub_type}"
                    type_breakdown[key] = count

        return ApiResponse(
            success=True,
            message="Dashboard data retrieved successfully",
            data={
                "summary": {
                    "total_applications": total_applications,
                    "renewal_applications": renewal_applications,
                    "new_applications": new_applications,
                    "academic_year": academic_year,
                    "semester": semester,
                },
                "status_breakdown": status_breakdown,
                "type_breakdown": type_breakdown,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard data: {str(e)}")


@router.get("/types/available")
async def get_available_scholarship_types(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Get available scholarship types from configuration"""
    # Get all active scholarship types from database
    scholarship_types_result = await db.execute(
        select(ScholarshipType).where(ScholarshipType.status == ScholarshipStatus.active.value)
    )
    scholarship_types = scholarship_types_result.scalars().all()

    types_list = [
        {
            "id": st.id,
            "code": st.code,
            "name": st.name,
            "description": st.description,
        }
        for st in scholarship_types
    ]

    # Get distinct sub-types from applications (configuration-driven)
    sub_types = await get_distinct_sub_types(db)

    sub_types_list = [{"value": st, "name": st.replace("_", " ").title()} for st in sub_types]

    return ApiResponse(
        success=True,
        message="Available scholarship types retrieved",
        data={
            "scholarship_types": types_list,
            "sub_types": sub_types_list,
        },
    )


# Development and Testing Endpoints


@router.post("/dev/simulate-priority-processing")
async def simulate_priority_processing(
    academic_year: int = Body(...),
    semester: str = Body(...),
    scholarship_type_id: int = Body(...),
    sub_type: str = Body(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Simulate priority processing for testing (dev only)"""
    from app.core.config import settings

    if not settings.debug:
        raise HTTPException(status_code=403, detail="Only available in development mode")

    # Get applications for simulation
    applications_result = await db.execute(
        select(Application).where(
            and_(
                Application.academic_year == academic_year,
                Application.semester == semester,
                Application.scholarship_type_id == scholarship_type_id,
                Application.sub_scholarship_type == sub_type,
                Application.status.in_(
                    [
                        ApplicationStatus.submitted.value,
                        ApplicationStatus.under_review.value,
                    ]
                ),
            )
        )
    )
    applications = applications_result.scalars().all()

    # Simulate processing
    simulation_results = []
    for app in applications:
        simulation_results.append(
            {
                "app_id": app.app_id,
                "user_id": app.user_id,
                "is_renewal": app.is_renewal,
                "submission_date": app.submitted_at.isoformat() if app.submitted_at else None,
                "status": app.status,
            }
        )

    # Sort by submission date (renewal applications first)
    simulation_results.sort(key=lambda x: (not x["is_renewal"], x["submission_date"] or ""))

    return ApiResponse(
        success=True,
        message=f"Simulated processing for {len(simulation_results)} applications",
        data={
            "simulation_results": simulation_results,
            "parameters": {
                "academic_year": academic_year,
                "semester": semester,
                "scholarship_type_id": scholarship_type_id,
                "sub_type": sub_type,
            },
        },
    )
