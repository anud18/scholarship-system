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

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin, require_staff, require_student
from app.db.deps import get_db
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipStatus, ScholarshipType
from app.models.user import User
from app.schemas.response import ApiResponse
from app.utils.scholarship_helpers import get_distinct_sub_types

logger = logging.getLogger(__name__)

router = APIRouter()

# Application Management Endpoints


@router.post("/applications/create-comprehensive")
async def create_comprehensive_application(
    application_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """[Not implemented - see issue #649] Create a comprehensive scholarship application.

    Calls ``ScholarshipApplicationService.create_application`` which has been
    commented out (see ``app/services/scholarship_service.py:385``) with the
    note that application creation moved to ``ApplicationService`` with
    external API integration. The new signature is incompatible with this
    endpoint's renewal-aware contract, so callers must migrate to
    ``POST /api/v1/applications/`` and the renewal flow on
    ``ApplicationService`` instead. Returns 501 until a migration plan is
    decided (tracked in issue #649).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="The comprehensive create endpoint is not currently implemented (tracked in issue #649). Use POST /api/v1/applications/ instead.",
    )


@router.post("/applications/{application_id}/submit-comprehensive")
async def submit_comprehensive_application(
    application_id: int = Path(...),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """[Not implemented - see issue #651] Submit application with comprehensive workflow management.

    Calls ``ScholarshipApplicationService.submit_application`` (async) on a
    synchronously-constructed session, without ``await``. The service body
    uses ``await self.db.execute(...)`` / ``await self.db.commit()`` which
    fails against a sync session, and the missing ``await`` would yield a
    coroutine that cannot be tuple-unpacked into ``(success, message)``.
    Returns 501 until the service interface is reconciled with the endpoint
    (tracked in issue #651). Use ``POST /api/v1/applications/{id}/submit``
    on ``ApplicationService`` instead.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="The comprehensive submit endpoint is not currently implemented (tracked in issue #651). Use POST /api/v1/applications/{id}/submit instead.",
    )


@router.get("/applications/by-priority")
async def get_applications_by_priority(
    scholarship_type_id: Optional[int] = Query(None),
    semester: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """[Not implemented - see issue #651] Get applications ordered by priority score.

    Calls ``ScholarshipApplicationService.get_applications_by_priority`` (async)
    on a synchronously-constructed session, without ``await``. The service body
    uses ``await self.db.execute(...)`` which fails against a sync session, and
    the missing ``await`` would yield a coroutine that cannot be iterated.
    Returns 501 until the service interface is reconciled with the endpoint
    (tracked in issue #651).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="The applications-by-priority endpoint is not currently implemented (tracked in issue #651).",
    )


# Renewal Processing Endpoints


@router.post("/renewals/process-priority")
async def process_renewal_applications(
    semester: str = Body(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """[Not implemented - see issue #651] Process renewal applications with priority.

    Calls ``ScholarshipApplicationService.process_renewal_applications_first``
    (async) on a synchronously-constructed session, without ``await``. The
    service body uses ``await self.db.execute(...)`` which fails against a
    sync session, and the missing ``await`` would yield a coroutine that is
    serialized in place of the expected result dict. Returns 501 until the
    service interface is reconciled with the endpoint (tracked in issue #651).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="The renewal-priority processing endpoint is not currently implemented (tracked in issue #651).",
    )


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
        logger.exception(
            "Failed to get scholarship dashboard data",
            extra={
                "academic_year": academic_year,
                "semester": semester,
                "actor_user_id": current_user.id,
            },
        )
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard data: {str(e)}") from e


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

    logger.info(
        "Priority-processing simulated for %d applications by admin user_id=%s "
        "(AY=%d semester=%s scholarship_type_id=%d sub_type=%s)",
        len(simulation_results),
        current_user.id,
        academic_year,
        semester,
        scholarship_type_id,
        sub_type,
        extra={
            "application_count": len(simulation_results),
            "academic_year": academic_year,
            "semester": semester,
            "scholarship_type_id": scholarship_type_id,
            "sub_type": sub_type,
            "actor_user_id": current_user.id,
        },
    )

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
