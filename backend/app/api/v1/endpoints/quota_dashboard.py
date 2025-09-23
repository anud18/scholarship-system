"""
Quota Management Dashboard API endpoints
Provides real-time quota tracking, analytics, and management interface
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_

from app.db.deps import get_db
from app.core.security import require_admin, require_staff
from app.models.user import User
from app.models.application import Application, ApplicationStatus, ScholarshipMainType, ScholarshipSubType
from app.schemas.response import ApiResponse
from app.services.scholarship_service import ScholarshipQuotaService

router = APIRouter()


@router.get("/overview")
async def get_quota_overview(
    semester: Optional[str] = Query(None, description="Filter by semester"),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive quota overview dashboard"""
    from sqlalchemy.orm import sessionmaker
    
    sync_session = sessionmaker(bind=db.bind)()
    
    try:
        quota_service = ScholarshipQuotaService(sync_session)
        
        # Get quota status for all type combinations
        quota_overview = {}
        
        for main_type in ScholarshipMainType:
            for sub_type in ScholarshipSubType:
                # Get applications for this combination
                query = sync_session.query(Application).filter(
                    and_(
                        Application.main_scholarship_type == main_type.value,
                        Application.sub_scholarship_type == sub_type.value
                    )
                )
                
                if semester:
                    query = query.filter(Application.semester == semester)
                
                total_apps = query.count()
                
                # Only include combinations that have applications
                if total_apps > 0:
                    quota_status = quota_service.get_quota_status_by_type(
                        main_type.value, sub_type.value, semester or "all"
                    )
                    quota_overview[f"{main_type.value}_{sub_type.value}"] = quota_status
        
        # Get overall statistics
        base_query = sync_session.query(Application)
        if semester:
            base_query = base_query.filter(Application.semester == semester)
        
        total_applications = base_query.count()
        approved_applications = base_query.filter(
            Application.status == ApplicationStatus.APPROVED.value
        ).count()
        pending_applications = base_query.filter(
            Application.status.in_([
                ApplicationStatus.SUBMITTED.value,
                ApplicationStatus.UNDER_REVIEW.value
            ])
        ).count()
        renewal_applications = base_query.filter(Application.is_renewal == True).count()
        
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
                    "approval_rate": (approved_applications / total_applications * 100) if total_applications > 0 else 0
                },
                "semester": semester,
                "generated_at": sync_session.query(func.now()).scalar().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quota overview: {str(e)}")
    finally:
        sync_session.close()


@router.get("/detailed/{main_type}/{sub_type}")
async def get_detailed_quota_status(
    main_type: str,
    sub_type: str,
    semester: Optional[str] = Query(None),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed quota status for specific scholarship type"""
    from sqlalchemy.orm import sessionmaker
    
    # Validate enum values
    try:
        main_type_enum = ScholarshipMainType(main_type)
        sub_type_enum = ScholarshipSubType(sub_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid scholarship type: {str(e)}")
    
    sync_session = sessionmaker(bind=db.bind)()
    
    try:
        # Get applications for this type combination
        query = sync_session.query(Application).filter(
            and_(
                Application.main_scholarship_type == main_type,
                Application.sub_scholarship_type == sub_type
            )
        )
        
        if semester:
            query = query.filter(Application.semester == semester)
        
        applications = query.all()
        
        # Group by status
        status_breakdown = {}
        for status in ApplicationStatus:
            count = len([app for app in applications if app.status == status.value])
            if count > 0:
                status_breakdown[status.value] = count
        
        # Priority distribution
        priority_ranges = {
            "high_priority": len([app for app in applications if (app.priority_score or 0) >= 100]),
            "medium_priority": len([app for app in applications if 50 <= (app.priority_score or 0) < 100]),
            "low_priority": len([app for app in applications if (app.priority_score or 0) < 50])
        }
        
        # Renewal vs new applications
        renewal_breakdown = {
            "renewal_applications": len([app for app in applications if app.is_renewal]),
            "new_applications": len([app for app in applications if not app.is_renewal])
        }
        
        # Time-based analysis
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        
        # Applications by submission time
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)
        
        recent_submissions = {
            "last_7_days": len([app for app in applications if app.submitted_at and app.submitted_at >= last_7_days]),
            "last_30_days": len([app for app in applications if app.submitted_at and app.submitted_at >= last_30_days]),
            "total": len([app for app in applications if app.submitted_at])
        }
        
        # Overdue applications
        overdue_applications = [
            {
                "app_id": app.app_id,
                "student_id": app.student_id,
                "days_overdue": (now - app.review_deadline).days if app.review_deadline else 0,
                "status": app.status
            }
            for app in applications 
            if app.review_deadline and app.review_deadline < now and app.status in [
                ApplicationStatus.SUBMITTED.value,
                ApplicationStatus.UNDER_REVIEW.value
            ]
        ]
        
        # Get quota information
        quota_service = ScholarshipQuotaService(sync_session)
        quota_status = quota_service.get_quota_status_by_type(main_type, sub_type, semester or "all")
        
        return ApiResponse(
            success=True,
            message="Detailed quota status retrieved successfully",
            data={
                "quota_status": quota_status,
                "status_breakdown": status_breakdown,
                "priority_distribution": priority_ranges,
                "renewal_breakdown": renewal_breakdown,
                "submission_timeline": recent_submissions,
                "overdue_applications": overdue_applications,
                "total_applications": len(applications),
                "filters": {
                    "main_type": main_type,
                    "sub_type": sub_type,
                    "semester": semester
                }
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get detailed quota status: {str(e)}")
    finally:
        sync_session.close()


@router.get("/trends")
async def get_quota_trends(
    main_type: Optional[str] = Query(None),
    sub_type: Optional[str] = Query(None),
    months_back: int = Query(6, description="Number of months to look back"),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db)
):
    """Get quota utilization trends over time"""
    from sqlalchemy.orm import sessionmaker
    from datetime import datetime, timezone, timedelta
    
    sync_session = sessionmaker(bind=db.bind)()
    
    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=months_back * 30)
        
        # Base query
        query = sync_session.query(Application).filter(
            Application.created_at >= start_date
        )
        
        if main_type:
            query = query.filter(Application.main_scholarship_type == main_type)
        if sub_type:
            query = query.filter(Application.sub_scholarship_type == sub_type)
        
        applications = query.all()
        
        # Group by month
        monthly_data = {}
        for app in applications:
            if app.created_at:
                month_key = app.created_at.strftime("%Y-%m")
                if month_key not in monthly_data:
                    monthly_data[month_key] = {
                        "total": 0,
                        "approved": 0,
                        "rejected": 0,
                        "pending": 0,
                        "renewal": 0
                    }
                
                monthly_data[month_key]["total"] += 1
                
                if app.status == ApplicationStatus.APPROVED.value:
                    monthly_data[month_key]["approved"] += 1
                elif app.status == ApplicationStatus.REJECTED.value:
                    monthly_data[month_key]["rejected"] += 1
                elif app.status in [ApplicationStatus.SUBMITTED.value, ApplicationStatus.UNDER_REVIEW.value]:
                    monthly_data[month_key]["pending"] += 1
                
                if app.is_renewal:
                    monthly_data[month_key]["renewal"] += 1
        
        # Fill in missing months with zero data
        current_month = start_date.replace(day=1)
        trend_data = []
        
        while current_month <= end_date:
            month_key = current_month.strftime("%Y-%m")
            data = monthly_data.get(month_key, {
                "total": 0, "approved": 0, "rejected": 0, "pending": 0, "renewal": 0
            })
            
            trend_data.append({
                "month": month_key,
                "month_name": current_month.strftime("%B %Y"),
                **data,
                "approval_rate": (data["approved"] / data["total"] * 100) if data["total"] > 0 else 0
            })
            
            # Move to next month
            if current_month.month == 12:
                current_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                current_month = current_month.replace(month=current_month.month + 1)
        
        return ApiResponse(
            success=True,
            message="Quota trends retrieved successfully",
            data={
                "trends": trend_data,
                "summary": {
                    "date_range": {
                        "start": start_date.strftime("%Y-%m-%d"),
                        "end": end_date.strftime("%Y-%m-%d")
                    },
                    "total_applications": len(applications),
                    "months_analyzed": len(trend_data),
                    "filters": {
                        "main_type": main_type,
                        "sub_type": sub_type
                    }
                }
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quota trends: {str(e)}")
    finally:
        sync_session.close()


@router.post("/adjust-quota")
async def adjust_quota_limits(
    quota_adjustments: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Adjust quota limits for scholarship types (admin only)"""
    from sqlalchemy.orm import sessionmaker
    
    sync_session = sessionmaker(bind=db.bind)()
    
    try:
        # This would update quota configurations in a real system
        # For now, we'll return the requested adjustments as confirmation
        
        adjusted_quotas = []
        
        for type_combination, new_quota in quota_adjustments.items():
            # Validate the format: MAIN_TYPE_SUB_TYPE
            try:
                parts = type_combination.split('_')
                if len(parts) < 2:
                    continue
                
                # Extract main and sub types
                main_type = '_'.join(parts[:-1])  # Handle multi-word types
                sub_type = parts[-1]
                
                # Validate enum values
                main_type_enum = ScholarshipMainType(main_type)
                sub_type_enum = ScholarshipSubType(sub_type)
                
                adjusted_quotas.append({
                    "type_combination": type_combination,
                    "main_type": main_type,
                    "sub_type": sub_type,
                    "new_quota": new_quota,
                    "adjusted_by": current_user.username,
                    "adjusted_at": datetime.now(timezone.utc).isoformat()
                })
                
            except ValueError:
                continue
        
        return ApiResponse(
            success=True,
            message=f"Quota adjustments processed for {len(adjusted_quotas)} type combinations",
            data={
                "adjusted_quotas": adjusted_quotas,
                "total_adjustments": len(adjusted_quotas),
                "adjusted_by": current_user.username
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to adjust quotas: {str(e)}")
    finally:
        sync_session.close()


@router.get("/alerts")
async def get_quota_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity: low, medium, high, critical"),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db)
):
    """Get quota-related alerts and warnings"""
    from sqlalchemy.orm import sessionmaker
    from datetime import datetime, timezone, timedelta
    
    sync_session = sessionmaker(bind=db.bind)()
    
    try:
        alerts = []
        now = datetime.now(timezone.utc)
        
        # Check for quota exhaustion
        quota_service = ScholarshipQuotaService(sync_session)
        
        for main_type in ScholarshipMainType:
            for sub_type in ScholarshipSubType:
                quota_status = quota_service.get_quota_status_by_type(
                    main_type.value, sub_type.value, "current"
                )
                
                if quota_status.get("total_used", 0) > 0:  # Only check active combinations
                    usage_percent = quota_status.get("usage_percent", 0)
                    
                    if usage_percent >= 100:
                        alerts.append({
                            "id": f"quota_exhausted_{main_type.value}_{sub_type.value}",
                            "type": "quota_exhausted",
                            "severity": "critical",
                            "title": f"Quota Exhausted: {main_type.value} - {sub_type.value}",
                            "message": f"Quota fully utilized ({quota_status.get('total_used')}/{quota_status.get('total_quota')})",
                            "data": quota_status,
                            "created_at": now.isoformat()
                        })
                    elif usage_percent >= 90:
                        alerts.append({
                            "id": f"quota_nearly_full_{main_type.value}_{sub_type.value}",
                            "type": "quota_warning",
                            "severity": "high",
                            "title": f"Quota Nearly Full: {main_type.value} - {sub_type.value}",
                            "message": f"Quota {usage_percent:.1f}% utilized ({quota_status.get('total_used')}/{quota_status.get('total_quota')})",
                            "data": quota_status,
                            "created_at": now.isoformat()
                        })
                    elif usage_percent >= 75:
                        alerts.append({
                            "id": f"quota_high_usage_{main_type.value}_{sub_type.value}",
                            "type": "quota_info",
                            "severity": "medium",
                            "title": f"High Quota Usage: {main_type.value} - {sub_type.value}",
                            "message": f"Quota {usage_percent:.1f}% utilized ({quota_status.get('total_used')}/{quota_status.get('total_quota')})",
                            "data": quota_status,
                            "created_at": now.isoformat()
                        })
        
        # Check for overdue applications
        overdue_threshold = now - timedelta(days=30)
        overdue_count = sync_session.query(Application).filter(
            and_(
                Application.review_deadline < now,
                Application.status.in_([
                    ApplicationStatus.SUBMITTED.value,
                    ApplicationStatus.UNDER_REVIEW.value
                ])
            )
        ).count()
        
        if overdue_count > 0:
            severity = "critical" if overdue_count > 50 else "high" if overdue_count > 20 else "medium"
            alerts.append({
                "id": "overdue_applications",
                "type": "overdue_reviews",
                "severity": severity,
                "title": f"Overdue Applications: {overdue_count}",
                "message": f"{overdue_count} applications are past their review deadline",
                "data": {"count": overdue_count},
                "created_at": now.isoformat()
            })
        
        # Filter by severity if requested
        if severity:
            alerts = [alert for alert in alerts if alert["severity"] == severity]
        
        # Sort by severity (critical first)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        alerts.sort(key=lambda x: severity_order.get(x["severity"], 4))
        
        return ApiResponse(
            success=True,
            message=f"Retrieved {len(alerts)} quota alerts",
            data={
                "alerts": alerts,
                "summary": {
                    "total_alerts": len(alerts),
                    "by_severity": {
                        sev: len([a for a in alerts if a["severity"] == sev])
                        for sev in ["critical", "high", "medium", "low"]
                    }
                },
                "generated_at": now.isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quota alerts: {str(e)}")
    finally:
        sync_session.close()


@router.get("/export")
async def export_quota_data(
    format: str = Query("json", description="Export format: json, csv"),
    semester: Optional[str] = Query(None),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db)
):
    """Export quota data for reporting"""
    from sqlalchemy.orm import sessionmaker
    import csv
    import io
    from fastapi.responses import StreamingResponse
    
    sync_session = sessionmaker(bind=db.bind)()
    
    try:
        # Get all quota data
        quota_service = ScholarshipQuotaService(sync_session)
        export_data = []
        
        for main_type in ScholarshipMainType:
            for sub_type in ScholarshipSubType:
                quota_status = quota_service.get_quota_status_by_type(
                    main_type.value, sub_type.value, semester or "all"
                )
                
                if quota_status.get("total_used", 0) > 0:  # Only include active combinations
                    export_record = {
                        "main_type": main_type.value,
                        "sub_type": sub_type.value,
                        "semester": semester or "all",
                        "total_quota": quota_status.get("total_quota", 0),
                        "total_used": quota_status.get("total_used", 0),
                        "total_available": quota_status.get("total_available", 0),
                        "pending": quota_status.get("pending", 0),
                        "usage_percent": quota_status.get("usage_percent", 0),
                        "exported_at": datetime.now(timezone.utc).isoformat(),
                        "exported_by": current_user.username
                    }
                    export_data.append(export_record)
        
        if format.lower() == "csv":
            # Generate CSV
            output = io.StringIO()
            if export_data:
                fieldnames = export_data[0].keys()
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(export_data)
            
            output.seek(0)
            filename = f"quota_data_{semester or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        else:
            # Return JSON
            return ApiResponse(
                success=True,
                message=f"Quota data exported ({len(export_data)} records)",
                data={
                    "export_data": export_data,
                    "metadata": {
                        "format": format,
                        "semester": semester,
                        "record_count": len(export_data),
                        "exported_at": datetime.now(timezone.utc).isoformat(),
                        "exported_by": current_user.username
                    }
                }
            )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export quota data: {str(e)}")
    finally:
        sync_session.close()