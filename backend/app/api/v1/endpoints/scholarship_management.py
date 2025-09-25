"""
Enhanced scholarship management API endpoints for Issue #10
Provides comprehensive scholarship application management with priority processing and quota management
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin, require_staff, require_student
from app.db.deps import get_db
from app.models.application import Application, ApplicationStatus, ScholarshipMainType, ScholarshipSubType
from app.models.user import User
from app.schemas.response import ApiResponse

from app.services.scholarship_service import ScholarshipApplicationService, ScholarshipQuotaService

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
                "priority_score": application.priority_score,
                "main_type": application.main_scholarship_type,
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
                    "scholarship_type": app.scholarship_type,
                    "main_type": app.main_scholarship_type,
                    "sub_type": app.sub_scholarship_type,
                    "priority_score": app.priority_score,
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


# Quota Management Endpoints


@router.get("/quota/status")
async def get_quota_status(
    main_type: str = Query(..., description="Main scholarship type"),
    sub_type: str = Query(..., description="Sub scholarship type"),
    semester: str = Query(..., description="Semester"),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Get quota status for a scholarship type combination"""
    from sqlalchemy.orm import sessionmaker

    # Validate enum values
    try:
        main_type_enum = ScholarshipMainType(main_type)
        sub_type_enum = ScholarshipSubType(sub_type)
        main_type_value = main_type_enum.value
        sub_type_value = sub_type_enum.value
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid scholarship type: {str(e)}")

    sync_session = sessionmaker(bind=db.bind)()

    try:
        service = ScholarshipQuotaService(sync_session)
        quota_status = service.get_quota_status_by_type(main_type_value, sub_type_value, semester)

        return ApiResponse(
            success=True,
            message="Quota status retrieved successfully",
            data=quota_status,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quota status: {str(e)}")
    finally:
        sync_session.close()


@router.post("/quota/process-by-priority")
async def process_applications_by_priority(
    main_type: str = Body(...),
    sub_type: str = Body(...),
    semester: str = Body(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Process applications by priority within quota limits"""
    from sqlalchemy.orm import sessionmaker

    # Validate enum values
    try:
        main_type_enum = ScholarshipMainType(main_type)
        sub_type_enum = ScholarshipSubType(sub_type)
        main_type_value = main_type_enum.value
        sub_type_value = sub_type_enum.value
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid scholarship type: {str(e)}")

    sync_session = sessionmaker(bind=db.bind)()

    try:
        service = ScholarshipQuotaService(sync_session)
        result = service.process_applications_by_priority(main_type_value, sub_type_value, semester)

        return ApiResponse(success=True, message="Applications processed successfully", data=result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process applications: {str(e)}")
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
    semester: Optional[str] = Query(None),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive scholarship management dashboard data"""
    from sqlalchemy import and_, func
    from sqlalchemy.orm import sessionmaker

    sync_session = sessionmaker(bind=db.bind)()

    try:
        # Get overall statistics
        query = sync_session.query(Application)
        if semester:
            query = query.filter(Application.semester == semester)

        total_applications = query.count()
        renewal_applications = query.filter(Application.is_renewal.is_(True)).count()
        new_applications = total_applications - renewal_applications

        # Status breakdown
        status_breakdown = {}
        for status in ApplicationStatus:
            count = query.filter(Application.status == status.value).count()
            status_breakdown[status.value] = count

        # Type breakdown
        type_breakdown = {}
        for main_type in ScholarshipMainType:
            for sub_type in ScholarshipSubType:
                count = query.filter(
                    and_(
                        Application.main_scholarship_type == main_type.value,
                        Application.sub_scholarship_type == sub_type.value,
                    )
                ).count()
                if count > 0:
                    type_breakdown[f"{main_type.value}_{sub_type.value}"] = count

        # Priority score statistics
        priority_stats = (
            sync_session.query(
                func.avg(Application.priority_score),
                func.min(Application.priority_score),
                func.max(Application.priority_score),
            )
            .filter(Application.priority_score.isnot(None))
            .first()
        )

        return ApiResponse(
            success=True,
            message="Dashboard data retrieved successfully",
            data={
                "summary": {
                    "total_applications": total_applications,
                    "renewal_applications": renewal_applications,
                    "new_applications": new_applications,
                    "semester": semester,
                },
                "status_breakdown": status_breakdown,
                "type_breakdown": type_breakdown,
                "priority_stats": {
                    "average": float(priority_stats[0]) if priority_stats[0] else 0,
                    "minimum": priority_stats[1] if priority_stats[1] else 0,
                    "maximum": priority_stats[2] if priority_stats[2] else 0,
                },
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard data: {str(e)}")
    finally:
        sync_session.close()


@router.get("/types/available")
async def get_available_scholarship_types(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Get available scholarship main and sub types"""
    main_types = [{"value": t.value, "name": t.value.replace("_", " ").title()} for t in ScholarshipMainType]
    sub_types = [{"value": t.value, "name": t.value.replace("_", " ").title()} for t in ScholarshipSubType]

    return ApiResponse(
        success=True,
        message="Available scholarship types retrieved",
        data={"main_types": main_types, "sub_types": sub_types},
    )


# Development and Testing Endpoints


@router.post("/dev/simulate-priority-processing")
async def simulate_priority_processing(
    semester: str = Body(...),
    main_type: str = Body(...),
    sub_type: str = Body(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Simulate priority processing for testing (dev only)"""
    from app.core.config import settings

    if not settings.debug:
        raise HTTPException(status_code=403, detail="Only available in development mode")

    from sqlalchemy.orm import sessionmaker

    sync_session = sessionmaker(bind=db.bind)()

    try:
        # Get applications for simulation
        query = sync_session.query(Application).filter(
            and_(
                Application.semester == semester,
                Application.main_scholarship_type == main_type,
                Application.sub_scholarship_type == sub_type,
                Application.status.in_(
                    [
                        ApplicationStatus.SUBMITTED.value,
                        ApplicationStatus.UNDER_REVIEW.value,
                    ]
                ),
            )
        )

        applications = query.all()

        # Simulate processing
        simulation_results = []
        for app in applications:
            priority_score = app.calculate_priority_score()
            simulation_results.append(
                {
                    "app_id": app.app_id,
                    "student_id": app.student_id,
                    "is_renewal": app.is_renewal,
                    "original_priority": app.priority_score,
                    "calculated_priority": priority_score,
                    "submission_date": app.submitted_at.isoformat() if app.submitted_at else None,
                }
            )

        # Sort by priority
        simulation_results.sort(key=lambda x: x["calculated_priority"], reverse=True)

        return ApiResponse(
            success=True,
            message=f"Simulated processing for {len(simulation_results)} applications",
            data={
                "simulation_results": simulation_results,
                "parameters": {
                    "semester": semester,
                    "main_type": main_type,
                    "sub_type": sub_type,
                },
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")
    finally:
        sync_session.close()
