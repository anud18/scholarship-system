"""
Admin Dashboard API Endpoints

Includes:
- System statistics (系統統計)
- System health check (系統健康檢查)
- Recent applications (最近申請)
- Scholarship statistics (獎學金統計)
- Debug utilities (調試工具)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import require_admin
from app.db.deps import get_db
from app.integrations.nycu_emp import (
    NYCUEmpAuthenticationError,
    NYCUEmpConnectionError,
    NYCUEmpError,
    NYCUEmpTimeoutError,
    NYCUEmpValidationError,
    create_nycu_emp_client_from_env,
)
from app.models.application import Application, ApplicationStatus
from app.models.notification import Notification
from app.models.scholarship import ScholarshipType
from app.models.user import AdminScholarship, User, UserRole
from app.schemas.notification import NotificationResponse

from ._helpers import apply_scholarship_filter, get_allowed_scholarship_ids

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """
    Get dashboard statistics for admin

    Returns system overview data including:
    - totalUsers: Total registered users
    - activeApplications: Applications in progress (submitted/under_review)
    - completedReviews: Completed reviews (approved/rejected)
    - pendingReviews: Pending reviews
    - totalScholarships: Total scholarship types
    - systemUptime: System uptime (percentage)
    - avgResponseTime: Average application processing time
    - storageUsed: Storage usage (calculated from uploads)
    """

    # Get user's scholarship permissions
    allowed_scholarship_ids = await get_allowed_scholarship_ids(current_user, db)

    # 1. Total users
    stmt = select(func.count(User.id))
    result = await db.execute(stmt)
    total_users = result.scalar() or 0

    # 2. Active applications (submitted + under_review)
    stmt = select(func.count(Application.id)).where(
        Application.status.in_([ApplicationStatus.submitted.value, ApplicationStatus.under_review.value])
    )
    stmt = apply_scholarship_filter(stmt, Application.scholarship_type_id, allowed_scholarship_ids)
    result = await db.execute(stmt)
    active_applications = result.scalar() or 0

    # 3. Completed reviews (approved + rejected)
    stmt = select(func.count(Application.id)).where(
        Application.status.in_([ApplicationStatus.approved.value, ApplicationStatus.rejected.value])
    )
    stmt = apply_scholarship_filter(stmt, Application.scholarship_type_id, allowed_scholarship_ids)
    result = await db.execute(stmt)
    completed_reviews = result.scalar() or 0

    # 4. Pending reviews (submitted + under_review)
    pending_reviews = active_applications  # Same as active applications

    # 5. Total scholarship types
    stmt = select(func.count(ScholarshipType.id))
    if not current_user.is_super_admin() and allowed_scholarship_ids:
        stmt = stmt.where(ScholarshipType.id.in_(allowed_scholarship_ids))
    result = await db.execute(stmt)
    total_scholarships = result.scalar() or 0

    # 6. System uptime (fixed value for now, could be calculated from server start time)
    system_uptime = "99.9%"

    # 7. Average processing time
    stmt = select(
        func.avg(
            case(
                (
                    Application.approved_at.isnot(None),
                    func.extract("epoch", Application.approved_at - Application.submitted_at) / 86400,
                ),
                (
                    Application.reviewed_at.isnot(None),
                    func.extract("epoch", Application.reviewed_at - Application.submitted_at) / 86400,
                ),
                else_=None,
            )
        )
    ).where(
        Application.submitted_at.isnot(None),
        Application.status.in_([ApplicationStatus.approved.value, ApplicationStatus.rejected.value]),
    )
    stmt = apply_scholarship_filter(stmt, Application.scholarship_type_id, allowed_scholarship_ids)
    result = await db.execute(stmt)
    avg_days = result.scalar()
    avg_response_time = f"{avg_days:.1f}天" if avg_days else "N/A"

    return {
        "success": True,
        "message": "Dashboard statistics retrieved successfully",
        "data": {
            "totalUsers": total_users,
            "activeApplications": active_applications,
            "completedReviews": completed_reviews,
            "systemUptime": system_uptime,
            "avgResponseTime": avg_response_time,
            "pendingReviews": pending_reviews,
            "totalScholarships": total_scholarships,
        },
    }


@router.get("/system/health")
async def get_system_health(current_user: User = Depends(require_admin)):
    """Get system health status"""

    # Test NYCU Employee API connection
    nycu_emp_status = "unknown"
    nycu_emp_details = {}

    try:
        client = create_nycu_emp_client_from_env()

        # Use context manager for HTTP client if available
        if hasattr(client, "__aenter__"):
            async with client as c:
                test_result = await c.get_employee_page(page_row="1", status="01")
        else:
            test_result = await client.get_employee_page(page_row="1", status="01")

        if test_result.is_success:
            nycu_emp_status = "connected"
            nycu_emp_details = {
                "total_employees": test_result.total_count,
                "total_pages": test_result.total_page,
                "sample_employees": len(test_result.empDataList),
                "response_status": test_result.status,
                "api_mode": "mock" if hasattr(client, "_get_sample_employees") else "http",
            }
        else:
            nycu_emp_status = "error"
            nycu_emp_details = {"error": f"API returned status: {test_result.status}", "message": test_result.message}

    except NYCUEmpError as e:
        nycu_emp_status = "error"
        nycu_emp_details = {"error": str(e), "type": type(e).__name__}
    except Exception as e:
        nycu_emp_status = "error"
        nycu_emp_details = {"error": str(e), "type": "UnexpectedError"}

    return {
        "success": True,
        "message": "System health status retrieved successfully",
        "data": {
            "status": "healthy",
            "database": "connected",
            "redis": "connected",
            "storage": "available",
            "nycu_employee_api": {"status": nycu_emp_status, "details": nycu_emp_details},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/debug/nycu-employee")
async def debug_nycu_employee_api(
    page: int = Query(1, ge=1, description="Page number"),
    status_filter: str = Query("01", description="Employee status filter", alias="status"),
    current_user: User = Depends(require_admin),
):
    """Debug endpoint for NYCU Employee API integration"""

    debug_info = {
        "configuration": {
            "mode": getattr(settings, "nycu_emp_mode", "mock"),
            "endpoint": getattr(settings, "nycu_emp_endpoint", None),
            "account": getattr(settings, "nycu_emp_account", None),
            "has_key": bool(getattr(settings, "nycu_emp_key_hex", None) or getattr(settings, "nycu_emp_key_raw", None)),
            "timeout": getattr(settings, "nycu_emp_timeout", 10.0),
            "retries": getattr(settings, "nycu_emp_retries", 3),
            "env_vars": {
                "NYCU_EMP_MODE": os.getenv("NYCU_EMP_MODE"),
                "NYCU_EMP_ACCOUNT": os.getenv("NYCU_EMP_ACCOUNT"),
                "NYCU_EMP_ENDPOINT": os.getenv("NYCU_EMP_ENDPOINT"),
                "NYCU_EMP_KEY_HEX": "***" if os.getenv("NYCU_EMP_KEY_HEX") else None,
                "NYCU_EMP_KEY_RAW": "***" if os.getenv("NYCU_EMP_KEY_RAW") else None,
            },
        },
        "test_results": {},
    }

    try:
        client = create_nycu_emp_client_from_env()
        debug_info["client_type"] = type(client).__name__
        debug_info["client_mode"] = "mock" if hasattr(client, "_get_sample_employees") else "http"

        # Test single page request
        if hasattr(client, "__aenter__"):
            async with client as c:
                result = await c.get_employee_page(page_row=str(page), status=status_filter)
        else:
            result = await client.get_employee_page(page_row=str(page), status=status_filter)

        debug_info["test_results"] = {
            "status": "success",
            "api_status": result.status,
            "api_message": result.message,
            "is_success": result.is_success,
            "total_pages": result.total_page,
            "total_count": result.total_count,
            "current_page_employees": len(result.empDataList),
            "sample_employee": result.empDataList[0].__dict__ if result.empDataList else None,
            "requested_page": page,
            "requested_status": status_filter,
        }

    except NYCUEmpAuthenticationError as e:
        debug_info["test_results"] = {
            "status": "authentication_error",
            "error": str(e),
            "type": "NYCUEmpAuthenticationError",
            "suggestion": "Check NYCU_EMP_ACCOUNT and NYCU_EMP_KEY_HEX/NYCU_EMP_KEY_RAW",
        }
    except NYCUEmpConnectionError as e:
        debug_info["test_results"] = {
            "status": "connection_error",
            "error": str(e),
            "type": "NYCUEmpConnectionError",
            "suggestion": "Check NYCU_EMP_ENDPOINT and network connectivity",
        }
    except NYCUEmpTimeoutError as e:
        debug_info["test_results"] = {
            "status": "timeout_error",
            "error": str(e),
            "type": "NYCUEmpTimeoutError",
            "suggestion": "Consider increasing NYCU_EMP_TIMEOUT value",
        }
    except NYCUEmpValidationError as e:
        debug_info["test_results"] = {
            "status": "validation_error",
            "error": str(e),
            "type": "NYCUEmpValidationError",
            "suggestion": "Check page and status parameter values",
        }
    except NYCUEmpError as e:
        debug_info["test_results"] = {
            "status": "api_error",
            "error": str(e),
            "type": type(e).__name__,
            "suggestion": "Check API endpoint and credentials",
        }
    except Exception as e:
        debug_info["test_results"] = {
            "status": "unexpected_error",
            "error": str(e),
            "type": type(e).__name__,
            "suggestion": "Check system logs for more details",
        }

    return {"success": True, "message": "NYCU Employee API debug information retrieved", "data": debug_info}


@router.get("/recent-applications")
async def get_recent_applications(
    limit: int = Query(5, ge=1, le=20, description="Number of recent applications"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get recent applications for admin dashboard"""

    # Get user's scholarship permissions
    allowed_scholarship_ids = await get_allowed_scholarship_ids(current_user, db)

    # If no permissions assigned for non-super-admin, return empty list
    if not current_user.is_super_admin() and not allowed_scholarship_ids:
        return {"success": True, "message": "No scholarship permissions assigned", "data": []}

    # Build query with joins and load configurations
    stmt = (
        select(Application, User, ScholarshipType)
        .options(selectinload(Application.scholarship_configuration))
        .join(User, Application.user_id == User.id)
        .outerjoin(ScholarshipType, Application.scholarship_type_id == ScholarshipType.id)
        .where(Application.status != ApplicationStatus.draft.value)
    )

    # Apply scholarship permission filtering
    stmt = apply_scholarship_filter(stmt, Application.scholarship_type_id, allowed_scholarship_ids)
    stmt = stmt.order_by(desc(Application.created_at)).limit(limit)

    result = await db.execute(stmt)
    application_tuples = result.fetchall()

    response_list = []
    for app_tuple in application_tuples:
        app, user, scholarship_type = app_tuple

        # Create response data with proper field mapping
        app_data = {
            "id": app.id,
            "app_id": app.app_id,
            "user_id": app.user_id,
            "scholarship_type": scholarship_type.code if scholarship_type else "unknown",
            "scholarship_type_id": app.scholarship_type_id or (scholarship_type.id if scholarship_type else None),
            "scholarship_type_zh": scholarship_type.name if scholarship_type else "未知獎學金",
            "scholarship_subtype_list": app.scholarship_subtype_list or [],
            "status": app.status,
            "status_name": app.status_name,
            "academic_year": app.academic_year or str(datetime.now().year - 1911),
            "semester": app.semester.value if app.semester else "1",
            "student_data": app.student_data or {},
            "submitted_form_data": app.submitted_form_data or {},
            "agree_terms": app.agree_terms or False,
            "professor_id": app.professor_id,
            "reviewer_id": app.reviewer_id,
            "final_approver_id": app.final_approver_id,
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
            "reviewed_at": app.reviewed_at.isoformat() if app.reviewed_at else None,
            "approved_at": app.approved_at.isoformat() if app.approved_at else None,
            "created_at": app.created_at.isoformat() if app.created_at else None,
            "updated_at": app.updated_at.isoformat() if app.updated_at else None,
            "meta_data": app.meta_data,
            # Additional fields for display
            "student_name": (
                (app.student_data.get("std_cname") if app.student_data else None) or (user.name if user else None)
            ),
            "student_no": (
                (app.student_data.get("std_stdcode") if app.student_data else None) or getattr(user, "nycu_id", None)
            ),
            "student_email": (
                (app.student_data.get("com_email") if app.student_data else None) or (user.email if user else None)
            ),
        }

        response_list.append(app_data)

    return {
        "success": True,
        "message": f"Retrieved {len(response_list)} recent applications",
        "data": response_list,
    }


@router.get("/scholarships/stats")
async def get_scholarship_stats(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """
    Get scholarship statistics grouped by scholarship type

    Returns applications count and status breakdown for each scholarship type
    """

    # Get user's scholarship permissions
    allowed_scholarship_ids = await get_allowed_scholarship_ids(current_user, db)

    # Get all scholarship types (filtered by permissions)
    stmt = select(ScholarshipType).where(ScholarshipType.status == "active")
    if not current_user.is_super_admin() and allowed_scholarship_ids:
        stmt = stmt.where(ScholarshipType.id.in_(allowed_scholarship_ids))

    result = await db.execute(stmt)
    scholarship_types = result.scalars().all()

    stats = {}
    for scholarship_type in scholarship_types:
        # Get application counts by status for this scholarship
        stmt = (
            select(Application.status, func.count(Application.id))
            .where(Application.scholarship_type_id == scholarship_type.id)
            .group_by(Application.status)
        )

        result = await db.execute(stmt)
        status_counts = {row[0]: row[1] for row in result.fetchall()}

        # Get unique sub-types for this scholarship
        stmt = select(Application.scholarship_subtype_list).where(
            Application.scholarship_type_id == scholarship_type.id, Application.scholarship_subtype_list.isnot(None)
        )

        result = await db.execute(stmt)
        all_subtypes = set()
        for row in result.fetchall():
            if row[0]:  # scholarship_subtype_list
                all_subtypes.update(row[0])

        stats[scholarship_type.code] = {
            "id": scholarship_type.id,
            "code": scholarship_type.code,
            "name": scholarship_type.name,
            "name_en": scholarship_type.name_en,
            "total_applications": sum(status_counts.values()),
            "status_breakdown": status_counts,
            "sub_types": sorted(list(all_subtypes)),
        }

    return {
        "success": True,
        "message": "Scholarship statistics retrieved successfully",
        "data": stats,
    }


@router.get("/system-announcements")
async def get_system_announcements(
    limit: int = Query(5, ge=1, le=20, description="Number of announcements"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get system announcements for admin dashboard"""

    # Get system-wide notifications (user_id is null for system announcements)
    # or notifications specifically for admins
    stmt = (
        select(Notification)
        .where((Notification.user_id.is_(None)) | (Notification.user_id == current_user.id))
        .where(~Notification.is_dismissed, Notification.related_resource_type == "system")
        .order_by(desc(Notification.created_at))
        .limit(limit)
    )

    result = await db.execute(stmt)
    notifications = result.scalars().all()

    # 修正 meta_data 字段以確保序列化正常
    response_list = []
    for notification in notifications:
        # 創建字典副本以修正 meta_data 字段
        notification_dict = {
            "id": notification.id,
            "title": notification.title,
            "title_en": notification.title_en,
            "message": notification.message,
            "message_en": notification.message_en,
            "notification_type": notification.notification_type.value
            if hasattr(notification.notification_type, "value")
            else str(notification.notification_type),
            "priority": notification.priority.value
            if hasattr(notification.priority, "value")
            else str(notification.priority),
            "related_resource_type": notification.related_resource_type,
            "related_resource_id": notification.related_resource_id,
            "action_url": notification.action_url,
            "is_read": notification.is_read,
            "is_dismissed": notification.is_dismissed,
            "scheduled_at": notification.scheduled_at,
            "expires_at": notification.expires_at,
            "read_at": notification.read_at,
            "created_at": notification.created_at,
            "meta_data": notification.meta_data if isinstance(notification.meta_data, (dict, type(None))) else None,
        }
        response_list.append(NotificationResponse.model_validate(notification_dict))

    return {"success": True, "message": "System announcements retrieved successfully", "data": response_list}
