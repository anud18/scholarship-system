"""
Quota dashboard endpoints - REFACTORED to use configuration-driven quotas

Major changes from original:
- Removed dependency on ScholarshipMainType enum
- Using new QuotaService from app.services.quota_service
- Using scholarship_type_id instead of main_type parameter
- All quotas now come from ScholarshipConfiguration table
"""

import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin, require_staff
from app.db.deps import get_db
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipStatus, ScholarshipType
from app.models.user import User
from app.schemas.response import ApiResponse
from app.services.quota_service import QuotaService

router = APIRouter()


@router.get("/overview")
async def get_quota_overview(
    academic_year: int = Query(..., description="Academic year (e.g., 113)"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    Get comprehensive quota overview dashboard

    BREAKING CHANGE: Now requires academic_year parameter instead of using main_type
    """
    quota_service = QuotaService(db)

    # Get all active scholarship types
    scholarship_types_result = await db.execute(
        select(ScholarshipType).where(ScholarshipType.status == ScholarshipStatus.active.value)
    )
    scholarship_types = scholarship_types_result.scalars().all()

    quota_overview = {}

    for scholarship_type in scholarship_types:
        # Get distinct sub-types for this scholarship type
        distinct_sub_types_result = await db.execute(
            select(Application.sub_scholarship_type)
            .distinct()
            .where(
                and_(
                    Application.scholarship_type_id == scholarship_type.id,
                    Application.sub_scholarship_type.isnot(None),
                )
            )
        )
        sub_type_values = distinct_sub_types_result.scalars().all() or ["general"]

        for sub_type in sub_type_values:
            # Get quota status from configuration
            quota_status = await quota_service.get_quota_status(scholarship_type.id, sub_type, academic_year, semester)

            key = f"{scholarship_type.code}_{sub_type}"
            quota_overview[key] = quota_status

    # Get overall statistics
    conditions = [Application.academic_year == academic_year]
    if semester:
        conditions.append(Application.semester == semester)

    total_apps_result = await db.execute(select(func.count(Application.id)).where(and_(*conditions)))
    total_applications = total_apps_result.scalar() or 0

    approved_result = await db.execute(
        select(func.count(Application.id)).where(
            and_(*conditions, Application.status == ApplicationStatus.approved.value)
        )
    )
    approved_applications = approved_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count(Application.id)).where(
            and_(
                *conditions,
                Application.status.in_(
                    [
                        ApplicationStatus.submitted.value,
                        ApplicationStatus.under_review.value,
                    ]
                ),
            )
        )
    )
    pending_applications = pending_result.scalar() or 0

    renewal_result = await db.execute(
        select(func.count(Application.id)).where(and_(*conditions, Application.is_renewal.is_(True)))
    )
    renewal_applications = renewal_result.scalar() or 0

    return ApiResponse(
        success=True,
        message="Quota overview retrieved successfully",
        data={
            "overview": quota_overview,
            "global_stats": {
                "total_applications": total_applications,
                "approved_applications": approved_applications,
                "pending_applications": pending_applications,
                "renewal_applications": renewal_applications,
                "approval_rate": (approved_applications / total_applications * 100) if total_applications > 0 else 0,
            },
            "academic_year": academic_year,
            "semester": semester,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/detailed/{scholarship_type_id}/{sub_type}")
async def get_detailed_quota_status(
    scholarship_type_id: int,
    sub_type: str,
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed quota status for specific scholarship type and sub-type

    BREAKING CHANGE: Uses scholarship_type_id instead of main_type parameter
    """
    quota_service = QuotaService(db)

    # Get scholarship type info
    scholarship_type_result = await db.execute(select(ScholarshipType).where(ScholarshipType.id == scholarship_type_id))
    scholarship_type = scholarship_type_result.scalar_one_or_none()

    if not scholarship_type:
        raise HTTPException(status_code=404, detail="Scholarship type not found")

    # Get quota status
    quota_status = await quota_service.get_quota_status(scholarship_type_id, sub_type, academic_year, semester)

    # Get applications list
    conditions = [
        Application.scholarship_type_id == scholarship_type_id,
        Application.sub_scholarship_type == sub_type,
        Application.academic_year == academic_year,
    ]
    if semester:
        conditions.append(Application.semester == semester)

    applications_result = await db.execute(
        select(Application).where(and_(*conditions)).order_by(Application.submitted_at.desc()).limit(100)
    )
    applications = applications_result.scalars().all()

    return ApiResponse(
        success=True,
        message="Detailed quota status retrieved successfully",
        data={
            "scholarship_type": {
                "id": scholarship_type.id,
                "code": scholarship_type.code,
                "name": scholarship_type.name,
            },
            "quota_status": quota_status,
            "recent_applications": [
                {
                    "id": app.id,
                    "app_id": app.app_id,
                    "status": app.status,
                    "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
                }
                for app in applications[:10]  # Return top 10
            ],
            "total_applications_shown": min(len(applications), 10),
        },
    )


# Note: Other endpoints (trends, adjust, alerts, export) need similar refactoring
# For now, marking them as deprecated or requiring update


@router.get("/trends")
async def get_quota_trends(
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    TODO: This endpoint needs to be refactored to use new QuotaService
    """
    raise HTTPException(
        status_code=501,
        detail="This endpoint is being refactored to use configuration-driven quotas. Please use /overview instead.",
    )


@router.post("/adjust")
async def adjust_quota_limits(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    TODO: Quota adjustment should be done through ScholarshipConfiguration management endpoints
    """
    raise HTTPException(
        status_code=501,
        detail="Quota adjustment is now done through /api/v1/admin/scholarship-configurations. This endpoint is deprecated.",
    )


@router.get("/alerts")
async def get_quota_alerts(
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Get quota-related alerts (near full, exhausted quotas)"""
    quota_service = QuotaService(db)

    # Get all active scholarship types
    scholarship_types_result = await db.execute(
        select(ScholarshipType).where(ScholarshipType.status == ScholarshipStatus.active.value)
    )
    scholarship_types = scholarship_types_result.scalars().all()

    alerts = []
    now = datetime.now(timezone.utc)

    for scholarship_type in scholarship_types:
        # Get distinct sub-types
        distinct_sub_types_result = await db.execute(
            select(Application.sub_scholarship_type)
            .distinct()
            .where(
                and_(
                    Application.scholarship_type_id == scholarship_type.id,
                    Application.sub_scholarship_type.isnot(None),
                )
            )
        )
        sub_type_values = distinct_sub_types_result.scalars().all() or ["general"]

        for sub_type in sub_type_values:
            quota_status = await quota_service.get_quota_status(scholarship_type.id, sub_type, academic_year, semester)

            if quota_status.get("total_used", 0) > 0:  # Only check active combinations
                usage_percent = quota_status.get("usage_percent", 0)

                if usage_percent >= 100:
                    alerts.append(
                        {
                            "id": f"quota_exhausted_{scholarship_type.code}_{sub_type}",
                            "type": "quota_exhausted",
                            "severity": "critical",
                            "title": f"Quota Exhausted: {scholarship_type.name} - {sub_type}",
                            "message": f"Quota fully utilized ({quota_status.get('total_used')}/{quota_status.get('total_quota')})",
                            "data": quota_status,
                            "created_at": now.isoformat(),
                        }
                    )
                elif usage_percent >= 90:
                    alerts.append(
                        {
                            "id": f"quota_nearly_full_{scholarship_type.code}_{sub_type}",
                            "type": "quota_warning",
                            "severity": "high",
                            "title": f"Quota Nearly Full: {scholarship_type.name} - {sub_type}",
                            "message": f"Quota {usage_percent:.1f}% utilized ({quota_status.get('total_used')}/{quota_status.get('total_quota')})",
                            "data": quota_status,
                            "created_at": now.isoformat(),
                        }
                    )

    return ApiResponse(
        success=True,
        message=f"Found {len(alerts)} quota alerts",
        data={"alerts": alerts, "academic_year": academic_year, "semester": semester},
    )


@router.get("/export")
async def export_quota_data(
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None),
    format: str = Query("json", regex="^(json|csv)$"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export quota data in JSON or CSV format"""
    quota_service = QuotaService(db)

    # Get all active scholarship types
    scholarship_types_result = await db.execute(
        select(ScholarshipType).where(ScholarshipType.status == ScholarshipStatus.active.value)
    )
    scholarship_types = scholarship_types_result.scalars().all()

    export_data = []

    for scholarship_type in scholarship_types:
        # Get distinct sub-types
        distinct_sub_types_result = await db.execute(
            select(Application.sub_scholarship_type)
            .distinct()
            .where(
                and_(
                    Application.scholarship_type_id == scholarship_type.id,
                    Application.sub_scholarship_type.isnot(None),
                )
            )
        )
        sub_type_values = distinct_sub_types_result.scalars().all() or ["general"]

        for sub_type in sub_type_values:
            quota_status = await quota_service.get_quota_status(scholarship_type.id, sub_type, academic_year, semester)

            if quota_status.get("total_used", 0) > 0:  # Only include active combinations
                export_record = {
                    "scholarship_type_id": scholarship_type.id,
                    "scholarship_code": scholarship_type.code,
                    "scholarship_name": scholarship_type.name,
                    "sub_type": sub_type,
                    "academic_year": academic_year,
                    "semester": semester or "all",
                    "total_quota": quota_status.get("total_quota", 0),
                    "total_used": quota_status.get("total_used", 0),
                    "total_available": quota_status.get("total_available", 0),
                    "pending": quota_status.get("pending", 0),
                    "usage_percent": quota_status.get("usage_percent", 0),
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "exported_by": current_user.username,
                }
                export_data.append(export_record)

    if format.lower() == "csv":
        # Generate CSV
        output = io.StringIO()
        if export_data:
            import csv

            writer = csv.DictWriter(output, fieldnames=export_data[0].keys())
            writer.writeheader()
            writer.writerows(export_data)

        from fastapi.responses import Response

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=quota_export_{academic_year}_{semester or 'all'}.csv"
            },
        )
    else:
        # Return JSON
        return ApiResponse(
            success=True,
            message=f"Exported {len(export_data)} quota records",
            data={"records": export_data, "count": len(export_data)},
        )
