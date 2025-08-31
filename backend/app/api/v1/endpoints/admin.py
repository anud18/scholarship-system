"""
Administration API endpoints
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, status, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update, delete, or_, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

logger = logging.getLogger(__name__)

from app.db.deps import get_db
from app.schemas.common import MessageResponse, PaginatedResponse, SystemSettingSchema, EmailTemplateSchema, ApiResponse
from app.schemas.application import ApplicationListResponse, ApplicationResponse, ProfessorAssignmentRequest
from app.schemas.scholarship import (
    ScholarshipSubTypeConfigCreate, ScholarshipSubTypeConfigUpdate, ScholarshipSubTypeConfigResponse,
    ScholarshipRuleCreate, ScholarshipRuleUpdate, ScholarshipRuleResponse, ScholarshipRuleFilter,
    RuleCopyRequest, RuleTemplateRequest, ApplyTemplateRequest, BulkRuleOperation
)
from app.schemas.notification import NotificationResponse, NotificationCreate, NotificationUpdate
from app.core.security import require_admin, get_current_user, check_scholarship_permission
from app.models.user import User, UserRole
from app.models.application import Application, ApplicationStatus
# Student model removed - student data now fetched from external API
from app.models.notification import Notification
from app.services.system_setting_service import SystemSettingService, EmailTemplateService
from app.models.scholarship import ScholarshipType, ScholarshipStatus, ScholarshipSubTypeConfig, ScholarshipSubType, ScholarshipRule
from app.models.enums import Semester
from app.models.user import AdminScholarship
from app.services.application_service import ApplicationService

router = APIRouter()


@router.get("/applications", response_model=PaginatedResponse[ApplicationListResponse])
async def get_all_applications(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by student name or ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all applications with pagination (admin only)"""
    
    # Build query with joins and load configurations
    stmt = select(Application, User, ScholarshipType).options(
        selectinload(Application.scholarship_configuration)
    ).join(
        User, Application.user_id == User.id
    ).outerjoin(
        ScholarshipType, Application.scholarship_type_id == ScholarshipType.id
    )
    
    # Apply filters
    if status:
        stmt = stmt.where(Application.status == status)
    else:
        # Default: exclude draft applications for admin view
        stmt = stmt.where(Application.status != ApplicationStatus.DRAFT.value)
    
    if search:
        stmt = stmt.where(
            (User.name.icontains(search)) |
            (User.nycu_id.icontains(search)) |
            (User.email.icontains(search))
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
            "academic_year": app.academic_year or str(datetime.now().year),
            "semester": app.semester or "1",
            "student_data": app.student_data or {},
            "submitted_form_data": app.submitted_form_data or {},
            "agree_terms": app.agree_terms or False,
            "professor_id": app.professor_id,
            "reviewer_id": app.reviewer_id,
            "final_approver_id": app.final_approver_id,
            "review_score": app.review_score,
            "review_comments": app.review_comments,
            "rejection_reason": app.rejection_reason,
            "submitted_at": app.submitted_at,
            "reviewed_at": app.reviewed_at,
            "approved_at": app.approved_at,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
            "meta_data": app.meta_data,
            # Additional fields for display - get from student_data first, fallback to user
            "student_name": (app.student_data.get('cname') if app.student_data else None) or (user.name if user else None),
            "student_no": (app.student_data.get('stdNo') if app.student_data else None) or getattr(user, 'nycu_id', None),
            "days_waiting": None,
            # Include scholarship configuration for professor review settings
            "scholarship_configuration": {
                "requires_professor_recommendation": app.scholarship_configuration.requires_professor_recommendation if app.scholarship_configuration else False,
                "requires_college_review": app.scholarship_configuration.requires_college_review if app.scholarship_configuration else False,
                "config_name": app.scholarship_configuration.config_name if app.scholarship_configuration else None
            } if app.scholarship_configuration else None
        }
        
        # Calculate days waiting
        if app.submitted_at:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            submitted_time = app.submitted_at
            
            if submitted_time.tzinfo is None:
                submitted_time = submitted_time.replace(tzinfo=timezone.utc)
            
            days_diff = (now - submitted_time).days
            app_data["days_waiting"] = max(0, days_diff)
        
        application_list.append(ApplicationListResponse.model_validate(app_data))
    
    return PaginatedResponse(
        items=application_list,
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size
    )


@router.get("/dashboard/stats", response_model=ApiResponse[Dict[str, Any]])
async def get_dashboard_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard statistics for admin"""
    
    # Get user's scholarship permissions
    allowed_scholarship_ids = []
    if current_user.role == UserRole.SUPER_ADMIN:
        # Super admin can see all applications
        pass
    elif current_user.role in [UserRole.ADMIN, UserRole.COLLEGE]:
        # Get user's scholarship permissions
        permission_stmt = select(AdminScholarship.scholarship_id).where(
            AdminScholarship.admin_id == current_user.id
        )
        permission_result = await db.execute(permission_stmt)
        allowed_scholarship_ids = [row[0] for row in permission_result.fetchall()]
    
    # Total users
    stmt = select(func.count(User.id))
    result = await db.execute(stmt)
    total_users = result.scalar()
    
    # Total applications (filtered by permissions)
    stmt = select(func.count(Application.id))
    if current_user.role in [UserRole.ADMIN, UserRole.COLLEGE] and allowed_scholarship_ids:
        stmt = stmt.where(Application.scholarship_type_id.in_(allowed_scholarship_ids))
    result = await db.execute(stmt)
    total_applications = result.scalar()
    
    # Applications by status (filtered by permissions)
    stmt = select(
        Application.status,
        func.count(Application.id)
    ).group_by(Application.status)
    if current_user.role in [UserRole.ADMIN, UserRole.COLLEGE] and allowed_scholarship_ids:
        stmt = stmt.where(Application.scholarship_type_id.in_(allowed_scholarship_ids))
    result = await db.execute(stmt)
    status_counts = {row[0]: row[1] for row in result.fetchall()}
    
    # Pending review count
    pending_review = status_counts.get(ApplicationStatus.SUBMITTED.value, 0) + \
                    status_counts.get(ApplicationStatus.UNDER_REVIEW.value, 0)
    
    # Approved this month (filtered by permissions)
    from datetime import datetime, timedelta
    this_month = datetime.now().replace(day=1)
    stmt = select(func.count(Application.id)).where(
        Application.status == ApplicationStatus.APPROVED.value,
        Application.approved_at >= this_month
    )
    if current_user.role in [UserRole.ADMIN, UserRole.COLLEGE] and allowed_scholarship_ids:
        stmt = stmt.where(Application.scholarship_type_id.in_(allowed_scholarship_ids))
    result = await db.execute(stmt)
    approved_this_month = result.scalar() or 0
    
    # Calculate average processing time (filtered by permissions)
    from sqlalchemy import case
    stmt = select(
        func.avg(
            case(
                (Application.approved_at.isnot(None), 
                 func.extract('epoch', Application.approved_at - Application.submitted_at) / 86400),
                (Application.reviewed_at.isnot(None),
                 func.extract('epoch', Application.reviewed_at - Application.submitted_at) / 86400),
                else_=None
            )
        )
    ).where(
        Application.submitted_at.isnot(None),
        Application.status.in_([ApplicationStatus.APPROVED.value, ApplicationStatus.REJECTED.value])
    )
    if current_user.role in [UserRole.ADMIN, UserRole.COLLEGE] and allowed_scholarship_ids:
        stmt = stmt.where(Application.scholarship_type_id.in_(allowed_scholarship_ids))
    result = await db.execute(stmt)
    avg_days = result.scalar()
    avg_processing_time = f"{avg_days:.1f}天" if avg_days else "N/A"
    
    return ApiResponse(
        success=True,
        message="Dashboard statistics retrieved successfully",
        data={
            "total_applications": total_applications,
            "pending_review": pending_review,
            "approved": approved_this_month,
            "rejected": status_counts.get(ApplicationStatus.REJECTED.value, 0),
            "avg_processing_time": avg_processing_time
        }
    )


@router.get("/system/health", response_model=ApiResponse[Dict[str, Any]])
async def get_system_health(
    current_user: User = Depends(require_admin)
):
    """Get system health status"""
    return ApiResponse(
        success=True,
        message="System health status retrieved successfully",
        data={
            "status": "healthy",
            "database": "connected",
            "redis": "connected",
            "storage": "available",
            "timestamp": "2025-06-15T10:30:00Z"
        }
    )


@router.get("/system-setting", response_model=ApiResponse[SystemSettingSchema])
async def get_system_setting(
    key: str = Query(..., description="Setting key"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get system setting by key (admin only)"""
    setting = await SystemSettingService.get_setting(db, key)
    if not setting:
        return ApiResponse(
            success=True,
            message="System setting retrieved successfully",
            data=SystemSettingSchema(
                key=key,
                value=""
            )
        )
    return ApiResponse(
        success=True,
        message="System setting retrieved successfully",
        data=SystemSettingSchema.model_validate(setting)
    )


@router.put("/system-setting", response_model=ApiResponse[SystemSettingSchema])
async def set_system_setting(
    data: SystemSettingSchema,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update system setting (admin only)"""
    setting = await SystemSettingService.set_setting(
        db,
        key=data.key,
        value=data.value
    )
    return ApiResponse(
        success=True,
        message="System setting updated successfully",
        data=SystemSettingSchema.model_validate(setting)
    )


@router.get("/email-template")
async def get_email_template(
    key: str = Query(..., description="Template key"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get email template by key (admin only)"""
    template = await EmailTemplateService.get_template(db, key)
    if not template:
        template_data = EmailTemplateSchema(
            key=key,
            subject_template="",
            body_template="",
            cc=None,
            bcc=None,
            updated_at=None
        )
    else:
        template_data = EmailTemplateSchema.model_validate(template)
    
    return {
        "success": True,
        "message": "Email template retrieved successfully",
        "data": template_data
    }


@router.put("/email-template")
async def update_email_template(
    template: EmailTemplateSchema,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update email template (admin only)"""
    updated_template = await EmailTemplateService.set_template(
        db,
        template.key,
        template.subject_template,
        template.body_template,
        template.cc,
        template.bcc
    )
    
    return {
        "success": True,
        "message": "Email template updated successfully",
        "data": EmailTemplateSchema.model_validate(updated_template)
    }


@router.get("/recent-applications", response_model=ApiResponse[List[ApplicationListResponse]])
async def get_recent_applications(
    limit: int = Query(5, ge=1, le=20, description="Number of recent applications"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get recent applications for admin dashboard"""
    
    # Get user's scholarship permissions
    allowed_scholarship_ids = []
    if current_user.role == UserRole.SUPER_ADMIN:
        # Super admin can see all applications
        pass
    elif current_user.role in [UserRole.ADMIN, UserRole.COLLEGE]:
        # Get user's scholarship permissions
        permission_stmt = select(AdminScholarship.scholarship_id).where(
            AdminScholarship.admin_id == current_user.id
        )
        permission_result = await db.execute(permission_stmt)
        allowed_scholarship_ids = [row[0] for row in permission_result.fetchall()]
        
        # If no permissions assigned, return empty list
        if not allowed_scholarship_ids:
            return ApiResponse(
                success=True,
                message="No scholarship permissions assigned",
                data=[]
            )
    
    # Build query with joins and load configurations
    stmt = select(Application, User, ScholarshipType).options(
        selectinload(Application.scholarship_configuration)
    ).join(
        User, Application.user_id == User.id
    ).outerjoin(
        ScholarshipType, Application.scholarship_type_id == ScholarshipType.id
    ).where(
        Application.status != ApplicationStatus.DRAFT.value
    )
    
    # Apply scholarship permission filtering
    if current_user.role in [UserRole.ADMIN, UserRole.COLLEGE] and allowed_scholarship_ids:
        stmt = stmt.where(Application.scholarship_type_id.in_(allowed_scholarship_ids))
    
    stmt = stmt.order_by(desc(Application.created_at)).limit(limit)
    
    result = await db.execute(stmt)
    application_tuples = result.fetchall()
    
    # Add Chinese scholarship type names
    scholarship_type_zh = {
        "undergraduate_freshman": "學士班新生獎學金",
        "phd_nstc": "國科會博士生獎學金", 
        "phd_moe": "教育部博士生獎學金",
        "direct_phd": "逕博獎學金"
    }
    
    response_list = []
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
            "scholarship_type_zh": scholarship_type_zh.get(
                scholarship_type.code if scholarship_type else "unknown", 
                scholarship_type.code if scholarship_type else "unknown"
            ),
            "scholarship_subtype_list": app.scholarship_subtype_list or [],
            "status": app.status,
            "status_name": app.status_name,
            "academic_year": app.academic_year or str(datetime.now().year),
            "semester": app.semester or "1",
            "student_data": app.student_data or {},
            "submitted_form_data": app.submitted_form_data or {},
            "agree_terms": app.agree_terms or False,
            "professor_id": app.professor_id,
            "reviewer_id": app.reviewer_id,
            "final_approver_id": app.final_approver_id,
            "review_score": app.review_score,
            "review_comments": app.review_comments,
            "rejection_reason": app.rejection_reason,
            "submitted_at": app.submitted_at,
            "reviewed_at": app.reviewed_at,
            "approved_at": app.approved_at,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
            "meta_data": app.meta_data,
            # Additional fields for display - get from student_data first, fallback to user
            "student_name": (app.student_data.get('cname') if app.student_data else None) or (user.name if user else None),
            "student_no": (app.student_data.get('stdNo') if app.student_data else None) or getattr(user, 'nycu_id', None),
            "days_waiting": None,
            # Include scholarship configuration for professor review settings
            "scholarship_configuration": {
                "requires_professor_recommendation": app.scholarship_configuration.requires_professor_recommendation if app.scholarship_configuration else False,
                "requires_college_review": app.scholarship_configuration.requires_college_review if app.scholarship_configuration else False,
                "config_name": app.scholarship_configuration.config_name if app.scholarship_configuration else None
            } if app.scholarship_configuration else None
        }
        
        # Calculate days waiting
        if app.submitted_at:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            submitted_time = app.submitted_at
            
            if submitted_time.tzinfo is None:
                submitted_time = submitted_time.replace(tzinfo=timezone.utc)
            
            days_diff = (now - submitted_time).days
            app_data["days_waiting"] = max(0, days_diff)
        
        response_list.append(ApplicationListResponse.model_validate(app_data))
    
    return ApiResponse(
        success=True,
        message="Recent applications retrieved successfully",
        data=response_list
    )


@router.get("/system-announcements", response_model=ApiResponse[List[NotificationResponse]])
async def get_system_announcements(
    limit: int = Query(5, ge=1, le=20, description="Number of announcements"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get system announcements for admin dashboard"""
    
    # Get system-wide notifications (user_id is null for system announcements)
    # or notifications specifically for admins
    stmt = select(Notification).where(
        (Notification.user_id.is_(None)) |
        (Notification.user_id == current_user.id)
    ).where(
        Notification.is_dismissed == False,
        Notification.related_resource_type == 'system'
    ).order_by(desc(Notification.created_at)).limit(limit)
    
    result = await db.execute(stmt)
    notifications = result.scalars().all()
    
    # 修正 meta_data 字段以確保序列化正常
    response_list = []
    for notification in notifications:
        # 創建字典副本以修正 meta_data 字段
        notification_dict = {
            'id': notification.id,
            'title': notification.title,
            'title_en': notification.title_en,
            'message': notification.message,
            'message_en': notification.message_en,
            'notification_type': notification.notification_type.value if hasattr(notification.notification_type, 'value') else str(notification.notification_type),
            'priority': notification.priority.value if hasattr(notification.priority, 'value') else str(notification.priority),
            'related_resource_type': notification.related_resource_type,
            'related_resource_id': notification.related_resource_id,
            'action_url': notification.action_url,
            'is_read': notification.is_read,
            'is_dismissed': notification.is_dismissed,
            'scheduled_at': notification.scheduled_at,
            'expires_at': notification.expires_at,
            'read_at': notification.read_at,
            'created_at': notification.created_at,
            'meta_data': notification.meta_data if isinstance(notification.meta_data, (dict, type(None))) else None
        }
        response_list.append(NotificationResponse.model_validate(notification_dict))
    
    return ApiResponse(
        success=True,
        message="System announcements retrieved successfully",
        data=response_list
    )


# === 系統公告 CRUD === #

@router.get("/announcements", response_model=ApiResponse[dict])
async def get_all_announcements(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all system announcements with pagination (admin only)"""
    
    # Build query for system announcements
    stmt = select(Notification).where(
        Notification.user_id.is_(None),
        Notification.related_resource_type == 'system'
    )
    
    # Apply filters
    if notification_type:
        stmt = stmt.where(Notification.notification_type == notification_type)
    if priority:
        stmt = stmt.where(Notification.priority == priority)
    
    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    result = await db.execute(count_stmt)
    total = result.scalar() or 0
    
    # Apply pagination and ordering
    stmt = stmt.order_by(desc(Notification.created_at))
    stmt = stmt.offset((page - 1) * size).limit(size)
    
    # Execute query
    result = await db.execute(stmt)
    announcements = result.scalars().all()
    
    # 修正 meta_data 字段以確保序列化正常
    response_items = []
    for ann in announcements:
        # 創建字典副本以修正 meta_data 字段
        ann_dict = {
            'id': ann.id,
            'title': ann.title,
            'title_en': ann.title_en,
            'message': ann.message,
            'message_en': ann.message_en,
            'notification_type': ann.notification_type.value if hasattr(ann.notification_type, 'value') else str(ann.notification_type),
            'priority': ann.priority.value if hasattr(ann.priority, 'value') else str(ann.priority),
            'related_resource_type': ann.related_resource_type,
            'related_resource_id': ann.related_resource_id,
            'action_url': ann.action_url,
            'is_read': ann.is_read,
            'is_dismissed': ann.is_dismissed,
            'scheduled_at': ann.scheduled_at,
            'expires_at': ann.expires_at,
            'read_at': ann.read_at,
            'created_at': ann.created_at,
            'meta_data': ann.meta_data if isinstance(ann.meta_data, (dict, type(None))) else None
        }
        response_items.append(NotificationResponse.model_validate(ann_dict))
    
    # 計算總頁數
    pages = (total + size - 1) // size if total > 0 else 1
    
    return ApiResponse(
        success=True,
        message="系統公告列表獲取成功",
        data={
            "items": response_items,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages
        }
    )


@router.post("/announcements", response_model=ApiResponse[NotificationResponse], status_code=status.HTTP_201_CREATED)
async def create_announcement(
    announcement_data: NotificationCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create new system announcement (admin only)"""
    
    # Create announcement with system announcement properties
    announcement = Notification(
        user_id=None,  # System announcement
        title=announcement_data.title,
        title_en=announcement_data.title_en,
        message=announcement_data.message,
        message_en=announcement_data.message_en,
        notification_type=announcement_data.notification_type,
        priority=announcement_data.priority,
        related_resource_type='system',
        related_resource_id=None,
        action_url=announcement_data.action_url,
        is_read=False,
        is_dismissed=False,
        send_email=False,
        email_sent=False,
        expires_at=announcement_data.expires_at,
        meta_data=announcement_data.metadata
    )
    
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)
    
    # 修正 meta_data 字段以確保序列化正常
    announcement_dict = {
        'id': announcement.id,
        'title': announcement.title,
        'title_en': announcement.title_en,
        'message': announcement.message,
        'message_en': announcement.message_en,
        'notification_type': announcement.notification_type.value if hasattr(announcement.notification_type, 'value') else str(announcement.notification_type),
        'priority': announcement.priority.value if hasattr(announcement.priority, 'value') else str(announcement.priority),
        'related_resource_type': announcement.related_resource_type,
        'related_resource_id': announcement.related_resource_id,
        'action_url': announcement.action_url,
        'is_read': announcement.is_read,
        'is_dismissed': announcement.is_dismissed,
        'scheduled_at': announcement.scheduled_at,
        'expires_at': announcement.expires_at,
        'read_at': announcement.read_at,
        'created_at': announcement.created_at,
        'meta_data': announcement.meta_data if isinstance(announcement.meta_data, (dict, type(None))) else None
    }
    
    return ApiResponse(
        success=True,
        message="System announcement created successfully",
        data=NotificationResponse.model_validate(announcement_dict)
    )


@router.get("/announcements/{announcement_id}", response_model=ApiResponse[NotificationResponse])
async def get_announcement(
    announcement_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get specific system announcement (admin only)"""
    
    stmt = select(Notification).where(
        Notification.id == announcement_id,
        Notification.user_id.is_(None),
        Notification.related_resource_type == 'system'
    )
    
    result = await db.execute(stmt)
    announcement = result.scalar_one_or_none()
    
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System announcement not found"
        )
    
    # 修正 meta_data 字段以確保序列化正常
    announcement_dict = {
        'id': announcement.id,
        'title': announcement.title,
        'title_en': announcement.title_en,
        'message': announcement.message,
        'message_en': announcement.message_en,
        'notification_type': announcement.notification_type.value if hasattr(announcement.notification_type, 'value') else str(announcement.notification_type),
        'priority': announcement.priority.value if hasattr(announcement.priority, 'value') else str(announcement.priority),
        'related_resource_type': announcement.related_resource_type,
        'related_resource_id': announcement.related_resource_id,
        'action_url': announcement.action_url,
        'is_read': announcement.is_read,
        'is_dismissed': announcement.is_dismissed,
        'scheduled_at': announcement.scheduled_at,
        'expires_at': announcement.expires_at,
        'read_at': announcement.read_at,
        'created_at': announcement.created_at,
        'meta_data': announcement.meta_data if isinstance(announcement.meta_data, (dict, type(None))) else None
    }
    
    return ApiResponse(
        success=True,
        message="System announcement retrieved successfully",
        data=NotificationResponse.model_validate(announcement_dict)
    )


@router.put("/announcements/{announcement_id}", response_model=ApiResponse[NotificationResponse])
async def update_announcement(
    announcement_id: int,
    announcement_data: NotificationUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update system announcement (admin only)"""
    
    # Check if announcement exists
    stmt = select(Notification).where(
        Notification.id == announcement_id,
        Notification.user_id.is_(None),
        Notification.related_resource_type == 'system'
    )
    
    result = await db.execute(stmt)
    announcement = result.scalar_one_or_none()
    
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System announcement not found"
        )
    
    # Update only fields defined in the Pydantic schema to prevent mass assignment
    # This automatically stays in sync with schema changes
    allowed_fields = set(announcement_data.model_fields.keys())
    
    update_data = announcement_data.dict(exclude_unset=True)
    if update_data:
        for field, value in update_data.items():
            if field in allowed_fields:
                if field == 'metadata':
                    setattr(announcement, 'meta_data', value)
                elif hasattr(announcement, field):
                    setattr(announcement, field, value)
    
    await db.commit()
    await db.refresh(announcement)
    
    # 修正 meta_data 字段以確保序列化正常
    announcement_dict = {
        'id': announcement.id,
        'title': announcement.title,
        'title_en': announcement.title_en,
        'message': announcement.message,
        'message_en': announcement.message_en,
        'notification_type': announcement.notification_type.value if hasattr(announcement.notification_type, 'value') else str(announcement.notification_type),
        'priority': announcement.priority.value if hasattr(announcement.priority, 'value') else str(announcement.priority),
        'related_resource_type': announcement.related_resource_type,
        'related_resource_id': announcement.related_resource_id,
        'action_url': announcement.action_url,
        'is_read': announcement.is_read,
        'is_dismissed': announcement.is_dismissed,
        'scheduled_at': announcement.scheduled_at,
        'expires_at': announcement.expires_at,
        'read_at': announcement.read_at,
        'created_at': announcement.created_at,
        'meta_data': announcement.meta_data if isinstance(announcement.meta_data, (dict, type(None))) else None
    }
    
    return ApiResponse(
        success=True,
        message="System announcement updated successfully",
        data=NotificationResponse.model_validate(announcement_dict)
    )


@router.delete("/announcements/{announcement_id}", response_model=ApiResponse[MessageResponse])
async def delete_announcement(
    announcement_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete system announcement (admin only)"""
    
    # Check if announcement exists
    stmt = select(Notification).where(
        Notification.id == announcement_id,
        Notification.user_id.is_(None),
        Notification.related_resource_type == 'system'
    )
    
    result = await db.execute(stmt)
    announcement = result.scalar_one_or_none()
    
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System announcement not found"
        )
    
    # Delete announcement
    await db.delete(announcement)
    await db.commit()
    
    return ApiResponse(
        success=True,
        message="系統公告已成功刪除",
        data=MessageResponse(message="系統公告已成功刪除")
    )


@router.get("/scholarships/stats", response_model=ApiResponse[Dict[str, Any]])
async def get_scholarship_statistics(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get scholarship-specific statistics for admin dashboard"""
    
    # Get user's scholarship permissions
    allowed_scholarship_ids = []
    if current_user.role == UserRole.SUPER_ADMIN:
        # Super admin can see all scholarships
        pass
    elif current_user.role in [UserRole.ADMIN, UserRole.COLLEGE]:
        # Get user's scholarship permissions
        permission_stmt = select(AdminScholarship.scholarship_id).where(
            AdminScholarship.admin_id == current_user.id
        )
        permission_result = await db.execute(permission_stmt)
        allowed_scholarship_ids = [row[0] for row in permission_result.fetchall()]
    
    # Get all scholarship types (filtered by permissions)
    stmt = select(ScholarshipType).where(ScholarshipType.status == ScholarshipStatus.ACTIVE.value)
    if current_user.role in [UserRole.ADMIN, UserRole.COLLEGE] and allowed_scholarship_ids:
        stmt = stmt.where(ScholarshipType.id.in_(allowed_scholarship_ids))
    result = await db.execute(stmt)
    scholarships = result.scalars().all()
    
    scholarship_stats = {}
    
    for scholarship in scholarships:
        # Get applications for this scholarship type
        stmt = select(Application).where(Application.scholarship_type_id == scholarship.id)
        result = await db.execute(stmt)
        applications = result.scalars().all()
        
        # Calculate statistics
        total_applications = len(applications)
        pending_review = len([app for app in applications if app.status in [
            ApplicationStatus.SUBMITTED.value,
            ApplicationStatus.UNDER_REVIEW.value,
            ApplicationStatus.PENDING_RECOMMENDATION.value
        ]])
        
        # Calculate average wait time for completed applications
        completed_apps = [app for app in applications if app.status in [
            ApplicationStatus.APPROVED.value,
            ApplicationStatus.REJECTED.value
        ] and app.submitted_at and app.reviewed_at]
        
        avg_wait_days = 0
        if completed_apps:
            total_days = sum([
                (app.reviewed_at - app.submitted_at).days 
                for app in completed_apps
            ])
            avg_wait_days = round(total_days / len(completed_apps), 1)
        
        # Get sub-types if they exist
        sub_types = scholarship.sub_type_list or []
        
        scholarship_stats[scholarship.code] = {
            "id": scholarship.id,
            "name": scholarship.name,
            "name_en": scholarship.name_en,
            "total_applications": total_applications,
            "pending_review": pending_review,
            "avg_wait_days": avg_wait_days,
            "sub_types": sub_types,
            "has_sub_types": len(sub_types) > 0 and "general" not in sub_types
        }
    
    return ApiResponse(
        success=True,
        message="Scholarship statistics retrieved successfully",
        data=scholarship_stats
    )


@router.get("/scholarships/{scholarship_code}/applications", response_model=ApiResponse[List[ApplicationListResponse]])
async def get_applications_by_scholarship(
    scholarship_code: str,
    sub_type: Optional[str] = Query(None, description="Filter by sub-type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get applications for a specific scholarship type"""
    
    # Verify scholarship exists
    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_code)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()
    
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    
    # Build query with joins and load files, configurations, and professor
    stmt = select(Application, User).options(
        selectinload(Application.files),
        selectinload(Application.scholarship_configuration),
        selectinload(Application.professor)
    ).join(
        User, Application.user_id == User.id
    ).where(Application.scholarship_type_id == scholarship.id)
    
    # Default: exclude draft applications for admin view
    if status:
        stmt = stmt.where(Application.status == status)
    else:
        stmt = stmt.where(Application.status != ApplicationStatus.DRAFT.value)
    
    if sub_type:
        # Filter by sub-type in scholarship_subtype_list
        stmt = stmt.where(Application.scholarship_subtype_list.contains([sub_type]))
    
    stmt = stmt.order_by(desc(Application.submitted_at))
    result = await db.execute(stmt)
    application_tuples = result.fetchall()
    
    # Convert to response format
    response_list = []
    for app_tuple in application_tuples:
        app, user = app_tuple
        
        # Process submitted_form_data to include file URLs
        processed_form_data = app.submitted_form_data or {}
        if processed_form_data and app.files:
            # Generate file access token
            from app.core.config import settings
            from app.core.security import create_access_token
            
            token_data = {"sub": str(current_user.id)}
            access_token = create_access_token(token_data)
            
            # Update documents in submitted_form_data with file URLs
            if 'documents' in processed_form_data:
                existing_docs = processed_form_data['documents']
                for existing_doc in existing_docs:
                    # Find matching file record
                    matching_file = next((f for f in app.files if f.file_type == existing_doc.get('document_id')), None)
                    if matching_file:
                        # Update existing file information with URLs
                        base_url = f"{settings.base_url}{settings.api_v1_str}"
                        existing_doc.update({
                            "file_id": matching_file.id,
                            "filename": matching_file.filename,
                            "original_filename": matching_file.original_filename,
                            "file_size": matching_file.file_size,
                            "mime_type": matching_file.mime_type or matching_file.content_type,
                            "file_path": f"{base_url}/files/applications/{app.id}/files/{matching_file.id}?token={access_token}",
                            "download_url": f"{base_url}/files/applications/{app.id}/files/{matching_file.id}/download?token={access_token}",
                            "is_verified": matching_file.is_verified,
                            "object_name": matching_file.object_name
                        })
        
        # Create response data with proper field mapping
        app_data = {
            "id": app.id,
            "app_id": app.app_id,
            "user_id": app.user_id,
            # "student_id": app.student_id,  # Removed - student data now from external API
            "scholarship_type": scholarship.code,
            "scholarship_type_id": app.scholarship_type_id or scholarship.id,
            "scholarship_type_zh": scholarship.name,
            "scholarship_name": app.scholarship_configuration.config_name if app.scholarship_configuration else None,
            "amount": app.scholarship_configuration.amount if app.scholarship_configuration else None,
            "currency": app.scholarship_configuration.currency if app.scholarship_configuration else "TWD",
            "scholarship_subtype_list": app.scholarship_subtype_list or [],
            "status": app.status,
            "status_name": app.status_name,
            "academic_year": app.academic_year or str(datetime.now().year),
            "semester": app.semester or "1",
            "student_data": app.student_data or {},
            "submitted_form_data": processed_form_data,
            "agree_terms": app.agree_terms or False,
            "professor_id": app.professor_id,
            "professor": {
                "id": app.professor.id,
                "name": app.professor.name,
                "nycu_id": app.professor.nycu_id,
                "email": app.professor.email
            } if app.professor else ({
                "id": app.professor_id,
                "name": f"[教授不存在] ID: {app.professor_id}",
                "nycu_id": None,
                "email": None,
                "error": True
            } if app.professor_id else None),
            "reviewer_id": app.reviewer_id,
            "final_approver_id": app.final_approver_id,
            "review_score": app.review_score,
            "review_comments": app.review_comments,
            "rejection_reason": app.rejection_reason,
            "submitted_at": app.submitted_at,
            "reviewed_at": app.reviewed_at,
            "approved_at": app.approved_at,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
            "meta_data": app.meta_data,
            # Additional fields for display - get from student_data first, fallback to user
            "student_name": (app.student_data.get('cname') if app.student_data else None) or (user.name if user else None),
            "student_no": (app.student_data.get('stdNo') if app.student_data else None) or getattr(user, 'nycu_id', None),
            "days_waiting": None,
            # Include scholarship configuration for professor review settings
            "scholarship_configuration": {
                "requires_professor_recommendation": app.scholarship_configuration.requires_professor_recommendation if app.scholarship_configuration else False,
                "requires_college_review": app.scholarship_configuration.requires_college_review if app.scholarship_configuration else False,
                "config_name": app.scholarship_configuration.config_name if app.scholarship_configuration else None
            } if app.scholarship_configuration else None
        }
        
        # Calculate days waiting
        if app.submitted_at:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            submitted_time = app.submitted_at
            
            if submitted_time.tzinfo is None:
                submitted_time = submitted_time.replace(tzinfo=timezone.utc)
            
            days_diff = (now - submitted_time).days
            app_data["days_waiting"] = max(0, days_diff)
        
        response_list.append(ApplicationListResponse.model_validate(app_data))
    
    return ApiResponse(
        success=True,
        message=f"Applications for scholarship {scholarship_code} retrieved successfully",
        data=response_list
    )


@router.get("/scholarships/{scholarship_code}/sub-types", response_model=ApiResponse[List[Dict[str, Any]]])
async def get_scholarship_sub_types(
    scholarship_code: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get sub-types for a specific scholarship"""
    
    # Get scholarship
    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_code)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()
    
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    
    sub_types = scholarship.sub_type_list or []
    
    # Return sub-types with statistics
    sub_type_stats = []
    for sub_type in sub_types:
        # Get applications for this sub-type
        stmt = select(Application).where(
            Application.scholarship_type_id == scholarship.id,
            Application.scholarship_subtype_list.contains([sub_type])
        )
        result = await db.execute(stmt)
        applications = result.scalars().all()
        
        total_applications = len(applications)
        pending_review = len([app for app in applications if app.status in [
            ApplicationStatus.SUBMITTED.value,
            ApplicationStatus.UNDER_REVIEW.value,
            ApplicationStatus.PENDING_RECOMMENDATION.value
        ]])
        
        # Calculate average wait time
        completed_apps = [app for app in applications if app.status in [
            ApplicationStatus.APPROVED.value,
            ApplicationStatus.REJECTED.value
        ] and app.submitted_at and app.reviewed_at]
        
        avg_wait_days = 0
        if completed_apps:
            total_days = sum([
                (app.reviewed_at - app.submitted_at).days 
                for app in completed_apps
            ])
            avg_wait_days = round(total_days / len(completed_apps), 1)
        
        sub_type_stats.append({
            "sub_type": sub_type,
            "total_applications": total_applications,
            "pending_review": pending_review,
            "avg_wait_days": avg_wait_days
        })
    
    return ApiResponse(
        success=True,
        message=f"Sub-type statistics for scholarship {scholarship_code} retrieved successfully",
        data=sub_type_stats
    )


@router.get("/scholarships/sub-type-translations", response_model=ApiResponse[Dict[str, Dict[str, str]]])
async def get_sub_type_translations(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get sub-type name translations for all supported languages from database"""
    
    # Get all active scholarship types with their sub-type configurations
    stmt = select(ScholarshipType).options(
        selectinload(ScholarshipType.sub_type_configs)
    ).where(ScholarshipType.status == ScholarshipStatus.ACTIVE.value)
    result = await db.execute(stmt)
    scholarships = result.scalars().all()
    
    # Build translations from database
    translations = {"zh": {}, "en": {}}
    
    for scholarship in scholarships:
        # Get sub-type translations for this scholarship
        scholarship_translations = scholarship.get_sub_type_translations()
        
        # Merge into global translations
        for lang in ["zh", "en"]:
            translations[lang].update(scholarship_translations[lang])
    
    return ApiResponse(
        success=True,
        message="Sub-type translations retrieved successfully from database",
        data=translations
    )


# === 子類型配置管理 API === #

@router.get("/scholarships/{scholarship_id}/sub-type-configs", response_model=ApiResponse[List[ScholarshipSubTypeConfigResponse]])
async def get_scholarship_sub_type_configs(
    scholarship_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get sub-type configurations for a specific scholarship"""
    
    # Get scholarship with sub-type configurations
    stmt = select(ScholarshipType).options(
        selectinload(ScholarshipType.sub_type_configs)
    ).where(ScholarshipType.id == scholarship_id)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()
    
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    
    # Get sub-type configurations
    configs = []
    
    # 獲取已配置的子類型
    for config in scholarship.get_active_sub_type_configs():
        config_dict = {
            "id": config.id,
            "scholarship_type_id": config.scholarship_type_id,
            "sub_type_code": config.sub_type_code,
            "name": config.name,
            "name_en": config.name_en,
            "description": config.description,
            "description_en": config.description_en,
            "amount": config.amount,
            "currency": config.currency,
            "display_order": config.display_order,
            "is_active": config.is_active,
            "effective_amount": config.effective_amount,
            "created_at": config.created_at,
            "updated_at": config.updated_at
        }
        configs.append(ScholarshipSubTypeConfigResponse.model_validate(config_dict))
    
    # 為 general 子類型添加預設配置（如果沒有配置且在子類型列表中）
    if ScholarshipSubType.GENERAL.value in scholarship.sub_type_list:
        general_config = scholarship.get_sub_type_config(ScholarshipSubType.GENERAL.value)
        if not general_config:
            # 創建預設的 general 配置
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            
            config_dict = {
                "id": 0,  # 虛擬 ID
                "scholarship_type_id": scholarship.id,
                "sub_type_code": ScholarshipSubType.GENERAL.value,
                "name": "一般獎學金",
                "name_en": "General Scholarship",
                "description": "一般獎學金",
                "description_en": "General Scholarship",
                "amount": None,
                "currency": scholarship.currency,
                "display_order": 0,
                "is_active": True,
                "effective_amount": scholarship.amount,
                "created_at": now,
                "updated_at": now
            }
            configs.append(ScholarshipSubTypeConfigResponse.model_validate(config_dict))
    
    return ApiResponse(
        success=True,
        message="Sub-type configurations retrieved successfully",
        data=configs
    )


@router.post("/scholarships/{scholarship_id}/sub-type-configs", response_model=ApiResponse[ScholarshipSubTypeConfigResponse])
async def create_sub_type_config(
    scholarship_id: int,
    config_data: ScholarshipSubTypeConfigCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create new sub-type configuration for a scholarship"""
    
    # Get scholarship with sub-type configurations
    stmt = select(ScholarshipType).options(
        selectinload(ScholarshipType.sub_type_configs)
    ).where(ScholarshipType.id == scholarship_id)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()
    
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    
    # Validate sub_type_code
    if config_data.sub_type_code not in scholarship.sub_type_list:
        raise HTTPException(status_code=400, detail="Invalid sub_type_code for this scholarship")
    
    # Prevent creating general sub-type configurations
    if config_data.sub_type_code == ScholarshipSubType.GENERAL.value:
        raise HTTPException(status_code=400, detail="Cannot create configuration for 'general' sub-type. It uses default values.")
    
    # Check if config already exists
    existing = await db.execute(
        select(ScholarshipSubTypeConfig).where(
            ScholarshipSubTypeConfig.scholarship_type_id == scholarship_id,
            ScholarshipSubTypeConfig.sub_type_code == config_data.sub_type_code
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Sub-type configuration already exists")
    
    # Create new config
    config = ScholarshipSubTypeConfig(
        scholarship_type_id=scholarship_id,
        created_by=current_user.id,
        updated_by=current_user.id,
        **config_data.model_dump()
    )
    
    db.add(config)
    await db.commit()
    await db.refresh(config)
    
    config_dict = {
        "id": config.id,
        "scholarship_type_id": config.scholarship_type_id,
        "sub_type_code": config.sub_type_code,
        "name": config.name,
        "name_en": config.name_en,
        "description": config.description,
        "description_en": config.description_en,
        "amount": config.amount,
        "currency": config.currency,
        "display_order": config.display_order,
        "is_active": config.is_active,
        "effective_amount": config.effective_amount,
        "created_at": config.created_at,
        "updated_at": config.updated_at
    }
    
    return ApiResponse(
        success=True,
        message="Sub-type configuration created successfully",
        data=ScholarshipSubTypeConfigResponse.model_validate(config_dict)
    )


@router.put("/scholarships/sub-type-configs/{config_id}", response_model=ApiResponse[ScholarshipSubTypeConfigResponse])
async def update_sub_type_config(
    config_id: int,
    config_data: ScholarshipSubTypeConfigUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update sub-type configuration"""
    
    # Get config
    stmt = select(ScholarshipSubTypeConfig).where(ScholarshipSubTypeConfig.id == config_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Sub-type configuration not found")
    
    # Update only fields defined in the Pydantic schema to prevent mass assignment
    # This automatically stays in sync with schema changes
    allowed_fields = set(config_data.model_fields.keys())
    
    update_data = config_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in allowed_fields and hasattr(config, field):
            setattr(config, field, value)
    
    config.updated_by = current_user.id
    await db.commit()
    await db.refresh(config)
    
    config_dict = {
        "id": config.id,
        "scholarship_type_id": config.scholarship_type_id,
        "sub_type_code": config.sub_type_code,
        "name": config.name,
        "name_en": config.name_en,
        "description": config.description,
        "description_en": config.description_en,
        "amount": config.amount,
        "currency": config.currency,
        "display_order": config.display_order,
        "is_active": config.is_active,
        "effective_amount": config.effective_amount,
        "created_at": config.created_at,
        "updated_at": config.updated_at
    }
    
    return ApiResponse(
        success=True,
        message="Sub-type configuration updated successfully",
        data=ScholarshipSubTypeConfigResponse.model_validate(config_dict)
    )


@router.delete("/scholarships/sub-type-configs/{config_id}", response_model=ApiResponse[MessageResponse])
async def delete_sub_type_config(
    config_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete sub-type configuration (soft delete by setting is_active=False)"""
    
    # Get config
    stmt = select(ScholarshipSubTypeConfig).where(ScholarshipSubTypeConfig.id == config_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sub-type configuration not found"
        )
    
    # Soft delete
    config.is_active = False
    config.updated_by = current_user.id
    await db.commit()
    
    return ApiResponse(
        success=True,
        message="Sub-type configuration deleted successfully",
        data=MessageResponse(message="Sub-type configuration deleted successfully")
    ) 


# === 獎學金權限管理相關 API === #

@router.get("/scholarship-permissions", response_model=ApiResponse[List[Dict[str, Any]]])
async def get_scholarship_permissions(
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get scholarship permissions (admin only)"""
    
    
    # Special handling for super_admin when filtering by user_id
    if user_id:
        # Check if the filtered user is a super_admin
        target_user_stmt = select(User).where(User.id == user_id)
        target_user_result = await db.execute(target_user_stmt)
        target_user = target_user_result.scalar_one_or_none()
        
        if target_user and target_user.role == UserRole.SUPER_ADMIN:
            # Super admin has access to all scholarships
            from app.models.scholarship import ScholarshipType
            all_scholarships_stmt = select(ScholarshipType)
            all_scholarships_result = await db.execute(all_scholarships_stmt)
            all_scholarships = all_scholarships_result.scalars().all()
            
            permission_list = []
            for idx, scholarship in enumerate(all_scholarships):
                permission_list.append({
                    "id": -(idx + 1),  # Negative ID to indicate virtual permission
                    "user_id": user_id,
                    "scholarship_id": scholarship.id,
                    "scholarship_name": scholarship.name,
                    "scholarship_name_en": scholarship.name_en,
                    "comment": "Super admin has automatic access to all scholarships",
                    "created_at": target_user.created_at.isoformat(),
                    "updated_at": target_user.updated_at.isoformat()
                })
            
            return ApiResponse(
                success=True,
                message=f"Retrieved {len(permission_list)} scholarship permissions (super admin has access to all)",
                data=permission_list
            )
    
    # Build query for regular permissions
    stmt = select(AdminScholarship).options(
        selectinload(AdminScholarship.admin),
        selectinload(AdminScholarship.scholarship)
    )
    
    if user_id:
        stmt = stmt.where(AdminScholarship.admin_id == user_id)
    
    result = await db.execute(stmt)
    permissions = result.scalars().all()
    
    
    # Convert to response format
    permission_list = []
    for permission in permissions:
        permission_list.append({
            "id": permission.id,
            "user_id": permission.admin_id,
            "scholarship_id": permission.scholarship_id,
            "scholarship_name": permission.scholarship.name,
            "scholarship_name_en": permission.scholarship.name_en,
            "comment": "",  # AdminScholarship doesn't have comment field
            "created_at": permission.assigned_at.isoformat(),
            "updated_at": permission.assigned_at.isoformat()
        })
    
    # If no user_id filter and current user is SUPER_ADMIN, also include virtual permissions for all scholarships
    if not user_id and current_user.role == UserRole.SUPER_ADMIN:
        from app.models.scholarship import ScholarshipType
        all_scholarships_stmt = select(ScholarshipType)
        all_scholarships_result = await db.execute(all_scholarships_stmt)
        all_scholarships = all_scholarships_result.scalars().all()
        
        # Add virtual permissions for scholarships not already in the list
        existing_scholarship_ids = {perm["scholarship_id"] for perm in permission_list}
        
        for idx, scholarship in enumerate(all_scholarships):
            if scholarship.id not in existing_scholarship_ids:
                permission_list.append({
                    "id": -(idx + 1000),  # Negative ID to indicate virtual permission
                    "user_id": current_user.id,
                    "scholarship_id": scholarship.id,
                    "scholarship_name": scholarship.name,
                    "scholarship_name_en": scholarship.name_en,
                    "comment": "Super admin has automatic access to all scholarships",
                    "created_at": current_user.created_at.isoformat(),
                    "updated_at": current_user.updated_at.isoformat()
                })
        
    
    
    return ApiResponse(
        success=True,
        message=f"Retrieved {len(permission_list)} scholarship permissions",
        data=permission_list
    )


@router.get("/scholarship-permissions/current-user", response_model=ApiResponse[List[Dict[str, Any]]])
async def get_current_user_scholarship_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's scholarship permissions"""
    
    # Only admin and college roles can have scholarship permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.COLLEGE, UserRole.SUPER_ADMIN]:
        return ApiResponse(
            success=True,
            message="User role does not require scholarship permissions",
            data=[]
        )
    
    # Super admin has access to all scholarships (no specific permissions needed)
    if current_user.role == UserRole.SUPER_ADMIN:
        return ApiResponse(
            success=True,
            message="Super admin has access to all scholarships",
            data=[]
        )
    
    # Get permissions for admin/college users
    stmt = select(AdminScholarship).options(
        selectinload(AdminScholarship.scholarship)
    ).where(AdminScholarship.admin_id == current_user.id)
    
    result = await db.execute(stmt)
    permissions = result.scalars().all()
    
    # Convert to response format
    permission_list = []
    for permission in permissions:
        permission_list.append({
            "id": permission.id,
            "user_id": permission.admin_id,
            "scholarship_id": permission.scholarship_id,
            "scholarship_name": permission.scholarship.name,
            "scholarship_name_en": permission.scholarship.name_en,
            "comment": "",
            "created_at": permission.assigned_at.isoformat(),
            "updated_at": permission.assigned_at.isoformat()
        })
    
    return ApiResponse(
        success=True,
        message=f"Retrieved {len(permission_list)} scholarship permissions for current user",
        data=permission_list
    )


@router.post("/scholarship-permissions", response_model=ApiResponse[Dict[str, Any]])
async def create_scholarship_permission(
    permission_data: Dict[str, Any],
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create new scholarship permission (admin can only assign scholarships they have permission for)"""
    
    
    user_id = permission_data.get("user_id")
    scholarship_id = permission_data.get("scholarship_id")
    comment = permission_data.get("comment", "")
    
    
    if not user_id or not scholarship_id:
        raise HTTPException(status_code=400, detail="user_id and scholarship_id are required")
    
    # Check if admin is trying to modify their own permissions (not allowed)
    if current_user.role == UserRole.ADMIN and user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Admin users cannot modify their own permissions"
        )
    
    # Check if user exists
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if scholarship exists
    scholarship_stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_id)
    scholarship_result = await db.execute(scholarship_stmt)
    scholarship = scholarship_result.scalar_one_or_none()
    
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    
    # Check if current user has permission for this scholarship
    check_scholarship_permission(current_user, scholarship_id)
    
    # Check if permission already exists
    existing_stmt = select(AdminScholarship).where(
        AdminScholarship.admin_id == user_id,
        AdminScholarship.scholarship_id == scholarship_id
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=409, detail="Permission already exists")
    
    # Create new permission
    
    new_permission = AdminScholarship(
        admin_id=user_id,
        scholarship_id=scholarship_id
    )
    
    db.add(new_permission)
    await db.commit()
    await db.refresh(new_permission)
    
    
    return ApiResponse(
        success=True,
        message="Scholarship permission created successfully",
        data={
            "id": new_permission.id,
            "user_id": new_permission.admin_id,
            "scholarship_id": new_permission.scholarship_id,
            "scholarship_name": scholarship.name,
            "scholarship_name_en": scholarship.name_en,
            "comment": comment,
            "created_at": new_permission.assigned_at.isoformat(),
            "updated_at": new_permission.assigned_at.isoformat()
        }
    )


@router.put("/scholarship-permissions/{permission_id}", response_model=ApiResponse[Dict[str, Any]])
async def update_scholarship_permission(
    permission_id: int,
    permission_data: Dict[str, Any],
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update scholarship permission (admin only)"""
    
    # Check if permission exists
    stmt = select(AdminScholarship).options(
        selectinload(AdminScholarship.scholarship)
    ).where(AdminScholarship.id == permission_id)
    result = await db.execute(stmt)
    permission = result.scalar_one_or_none()
    
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    
    # Update fields (only comment is updatable in this model)
    # Note: AdminScholarship model doesn't have comment field, so we'll skip updates
    # In a real implementation, you might want to add a comment field to the model
    
    await db.commit()
    await db.refresh(permission)
    
    return ApiResponse(
        success=True,
        message="Scholarship permission updated successfully",
        data={
            "id": permission.id,
            "user_id": permission.admin_id,
            "scholarship_id": permission.scholarship_id,
            "scholarship_name": permission.scholarship.name,
            "scholarship_name_en": permission.scholarship.name_en,
            "comment": "",
            "created_at": permission.assigned_at.isoformat(),
            "updated_at": permission.assigned_at.isoformat()
        }
    )


@router.delete("/scholarship-permissions/{permission_id}", response_model=ApiResponse[Dict[str, str]])
async def delete_scholarship_permission(
    permission_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete scholarship permission (admin can only delete permissions for scholarships they manage, and cannot delete their own permissions)"""
    
    
    # Check if permission exists
    stmt = select(AdminScholarship).options(
        selectinload(AdminScholarship.scholarship)
    ).where(AdminScholarship.id == permission_id)
    result = await db.execute(stmt)
    permission = result.scalar_one_or_none()
    
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    
    
    # Check if admin is trying to delete their own permissions (not allowed)
    if current_user.role == UserRole.ADMIN and permission.admin_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin users cannot delete their own permissions"
        )
    
    # Check if current user has permission for this scholarship
    check_scholarship_permission(current_user, permission.scholarship_id)
    
    # Delete permission
    await db.delete(permission)
    await db.commit()
    
    
    return ApiResponse(
        success=True,
        message="Scholarship permission deleted successfully",
        data={"message": "Permission deleted successfully"}
    )


@router.get("/scholarships/all-for-permissions", response_model=ApiResponse[List[Dict[str, Any]]])
async def get_all_scholarships_for_permissions(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all scholarships for permission management (admin only)"""
    
    # Get all active scholarships
    stmt = select(ScholarshipType).where(
        ScholarshipType.status == ScholarshipStatus.ACTIVE.value
    ).order_by(ScholarshipType.name)
    
    result = await db.execute(stmt)
    scholarships = result.scalars().all()
    
    # Convert to response format
    scholarship_list = []
    for scholarship in scholarships:
        scholarship_list.append({
            "id": scholarship.id,
            "name": scholarship.name,
            "name_en": scholarship.name_en,
            "code": scholarship.code
        })
    
    return ApiResponse(
        success=True,
        message=f"Retrieved {len(scholarship_list)} scholarships for permission management",
        data=scholarship_list
    )


@router.get("/scholarships/my-scholarships", response_model=ApiResponse[List[Dict[str, Any]]])
async def get_my_scholarships(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get scholarships that the current user has permission to manage"""
    
    logger.info(f"get_my_scholarships called by user {current_user.id} role {current_user.role}")
    
    if current_user.is_super_admin():
        # Super admins can see all scholarships
        logger.info("User is super admin, getting all active scholarships")
        stmt = select(ScholarshipType).where(
            ScholarshipType.status == ScholarshipStatus.ACTIVE.value
        ).order_by(ScholarshipType.name)
        
        result = await db.execute(stmt)
        scholarships = result.scalars().all()
        logger.info(f"Found {len(scholarships)} active scholarships for super admin")
    else:
        # Regular admins can only see assigned scholarships
        stmt = select(ScholarshipType).join(
            AdminScholarship, ScholarshipType.id == AdminScholarship.scholarship_id
        ).where(
            AdminScholarship.admin_id == current_user.id,
            ScholarshipType.status == ScholarshipStatus.ACTIVE.value
        ).order_by(ScholarshipType.name)
        
        result = await db.execute(stmt)
        scholarships = result.scalars().all()
    
    # Convert to response format
    scholarship_list = []
    for scholarship in scholarships:
        scholarship_list.append({
            "id": scholarship.id,
            "name": scholarship.name,
            "name_en": scholarship.name_en,
            "code": scholarship.code,
            "category": scholarship.category,  # category is already a string, not an enum
            "application_cycle": scholarship.application_cycle.value if scholarship.application_cycle else None,
            "status": scholarship.status  # status is also a string, not an enum in this model
        })
    
    return ApiResponse(
        success=True,
        message=f"Retrieved {len(scholarship_list)} scholarships for current user",
        data=scholarship_list
    )


# ============================
# Scholarship Rules Management
# ============================

@router.get("/scholarship-rules", response_model=ApiResponse[List[ScholarshipRuleResponse]])
async def get_scholarship_rules(
    scholarship_type_id: Optional[int] = Query(None, description="Filter by scholarship type"),
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    sub_type: Optional[str] = Query(None, description="Filter by sub type"),
    rule_type: Optional[str] = Query(None, description="Filter by rule type"),
    is_template: Optional[bool] = Query(None, description="Filter templates"),
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get scholarship rules with optional filters"""
    
    # Check scholarship permission if specific scholarship type is requested
    if scholarship_type_id:
        check_scholarship_permission(current_user, scholarship_type_id)
    
    # Build query with joins
    stmt = select(ScholarshipRule).options(
        selectinload(ScholarshipRule.scholarship_type),
        selectinload(ScholarshipRule.creator),
        selectinload(ScholarshipRule.updater)
    )
    
    # Apply filters
    if scholarship_type_id:
        stmt = stmt.where(ScholarshipRule.scholarship_type_id == scholarship_type_id)
    elif not current_user.is_super_admin():
        # If no specific scholarship type requested and user is not super admin,
        # only show rules for scholarships they have permission to manage
        admin_scholarship_ids = [admin_scholarship.scholarship_id 
                               for admin_scholarship in current_user.admin_scholarships]
        if admin_scholarship_ids:
            stmt = stmt.where(ScholarshipRule.scholarship_type_id.in_(admin_scholarship_ids))
        else:
            # Admin has no scholarship permissions, return empty result
            return ApiResponse(success=True, message="No scholarship rules found", data=[])
    
    if academic_year:
        stmt = stmt.where(ScholarshipRule.academic_year == academic_year)
    
    if semester:
        semester_enum = Semester.FIRST if semester == "first" else Semester.SECOND if semester == "second" else None
        if semester_enum:
            stmt = stmt.where(ScholarshipRule.semester == semester_enum)
    
    if sub_type:
        stmt = stmt.where(ScholarshipRule.sub_type == sub_type)
    
    if rule_type:
        stmt = stmt.where(ScholarshipRule.rule_type == rule_type)
    
    if is_template is not None:
        stmt = stmt.where(ScholarshipRule.is_template == is_template)
    
    if is_active is not None:
        stmt = stmt.where(ScholarshipRule.is_active == is_active)
    
    if tag:
        stmt = stmt.where(ScholarshipRule.tag.icontains(tag))
    
    # Order by priority and created date
    stmt = stmt.order_by(ScholarshipRule.priority.desc(), ScholarshipRule.created_at.desc())
    
    result = await db.execute(stmt)
    rules = result.scalars().all()
    
    # Convert to response format
    rule_responses = []
    for rule in rules:
        # Ensure all attributes are loaded in the session context
        await db.refresh(rule)
        
        rule_data = ScholarshipRuleResponse.model_validate(rule)
        rule_data.academic_period_label = rule.academic_period_label
        rule_responses.append(rule_data)
    
    return ApiResponse(
        success=True,
        message=f"Retrieved {len(rule_responses)} scholarship rules",
        data=rule_responses
    )


@router.post("/scholarship-rules", response_model=ApiResponse[ScholarshipRuleResponse])
async def create_scholarship_rule(
    rule_data: ScholarshipRuleCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new scholarship rule"""
    
    # Check permission to manage this scholarship
    check_scholarship_permission(current_user, rule_data.scholarship_type_id)
    
    # Verify scholarship type exists
    stmt = select(ScholarshipType).where(ScholarshipType.id == rule_data.scholarship_type_id)
    result = await db.execute(stmt)
    scholarship_type = result.scalar_one_or_none()
    
    if not scholarship_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship type not found"
        )
    
    # Create new rule
    new_rule = ScholarshipRule(
        **rule_data.dict(),
        created_by=current_user.id,
        updated_by=current_user.id
    )
    
    db.add(new_rule)
    await db.commit()
    # Load relationships in a single query
    refreshed_rule_stmt = select(ScholarshipRule).options(
        selectinload(ScholarshipRule.scholarship_type),
        selectinload(ScholarshipRule.creator),
        selectinload(ScholarshipRule.updater)
    ).where(ScholarshipRule.id == new_rule.id)
    
    refreshed_result = await db.execute(refreshed_rule_stmt)
    new_rule = refreshed_result.scalar_one()
    
    rule_response = ScholarshipRuleResponse.model_validate(new_rule)
    rule_response.academic_period_label = new_rule.academic_period_label
    
    return ApiResponse(
        success=True,
        message="Scholarship rule created successfully",
        data=rule_response
    )


@router.get("/scholarship-rules/{rule_id}", response_model=ApiResponse[ScholarshipRuleResponse])
async def get_scholarship_rule(
    rule_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific scholarship rule"""
    
    stmt = select(ScholarshipRule).options(
        selectinload(ScholarshipRule.scholarship_type),
        selectinload(ScholarshipRule.creator),
        selectinload(ScholarshipRule.updater)
    ).where(ScholarshipRule.id == rule_id)
    
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship rule not found"
        )
    
    # Check permission to manage this scholarship
    check_scholarship_permission(current_user, rule.scholarship_type_id)
    
    # Ensure all attributes are loaded in the session context
    await db.refresh(rule)
    
    rule_response = ScholarshipRuleResponse.model_validate(rule)
    rule_response.academic_period_label = rule.academic_period_label
    
    return ApiResponse(
        success=True,
        message="Scholarship rule retrieved successfully",
        data=rule_response
    )


@router.put("/scholarship-rules/{rule_id}", response_model=ApiResponse[ScholarshipRuleResponse])
async def update_scholarship_rule(
    rule_id: int,
    rule_data: ScholarshipRuleUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a scholarship rule"""
    
    # Get existing rule
    stmt = select(ScholarshipRule).where(ScholarshipRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship rule not found"
        )
    
    # Check permission to manage this scholarship
    check_scholarship_permission(current_user, rule.scholarship_type_id)
    
    # Update only fields defined in the Pydantic schema to prevent mass assignment
    # This automatically stays in sync with schema changes
    allowed_fields = set(rule_data.model_fields.keys())
    allowed_fields.add('updated_by')  # Allow system field
    
    update_data = rule_data.dict(exclude_unset=True)
    update_data['updated_by'] = current_user.id
    
    for field, value in update_data.items():
        if field in allowed_fields and hasattr(rule, field):
            setattr(rule, field, value)
    
    await db.commit()
    
    # Load relationships in a single query
    refreshed_rule_stmt = select(ScholarshipRule).options(
        selectinload(ScholarshipRule.scholarship_type),
        selectinload(ScholarshipRule.creator),
        selectinload(ScholarshipRule.updater)
    ).where(ScholarshipRule.id == rule.id)
    
    refreshed_result = await db.execute(refreshed_rule_stmt)
    rule = refreshed_result.scalar_one()
    
    rule_response = ScholarshipRuleResponse.model_validate(rule)
    rule_response.academic_period_label = rule.academic_period_label
    
    return ApiResponse(
        success=True,
        message="Scholarship rule updated successfully",
        data=rule_response
    )


@router.delete("/scholarship-rules/{rule_id}", response_model=ApiResponse[Dict[str, str]])
async def delete_scholarship_rule(
    rule_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a scholarship rule"""
    
    # Get existing rule
    stmt = select(ScholarshipRule).where(ScholarshipRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship rule not found"
        )
    
    # Check permission to manage this scholarship
    check_scholarship_permission(current_user, rule.scholarship_type_id)
    
    await db.delete(rule)
    await db.commit()
    
    return ApiResponse(
        success=True,
        message="Scholarship rule deleted successfully",
        data={"message": "Rule deleted successfully"}
    )


async def _copy_rules_in_batches(
    db: AsyncSession,
    base_stmt: Select,
    copy_request: RuleCopyRequest,
    target_semester_enum,
    current_user: User,
    total_rules: int,
    batch_size: int
) -> ApiResponse[List[ScholarshipRuleResponse]]:
    """Process rule copying in batches to manage memory usage for large datasets"""
    
    all_new_rules = []
    total_skipped = 0
    processed_count = 0
    
    # Optimized duplicate check function
    def rule_exists_in_target(source_rule):
        exists_query = select(1).where(
            ScholarshipRule.academic_year == copy_request.target_academic_year,
            ScholarshipRule.semester == target_semester_enum,
            ScholarshipRule.scholarship_type_id == source_rule.scholarship_type_id,
            ScholarshipRule.rule_name == source_rule.rule_name,
            ScholarshipRule.rule_type == source_rule.rule_type,
            ScholarshipRule.condition_field == source_rule.condition_field,
            ScholarshipRule.operator == source_rule.operator,
            ScholarshipRule.expected_value == source_rule.expected_value,
            ScholarshipRule.sub_type == source_rule.sub_type,
            ScholarshipRule.is_template == False
        ).exists()
        return select(exists_query)
    
    # Process in batches
    offset = 0
    
    while offset < total_rules:
        # Get current batch
        batch_stmt = base_stmt.offset(offset).limit(batch_size)
        batch_result = await db.execute(batch_stmt)
        batch_rules = batch_result.scalars().all()
        
        if not batch_rules:
            break
            
        # Check permissions for batch
        scholarship_type_ids = set(rule.scholarship_type_id for rule in batch_rules)
        for scholarship_type_id in scholarship_type_ids:
            check_scholarship_permission(current_user, scholarship_type_id)
        
        # Process batch
        batch_new_rules = []
        batch_skipped = 0
        
        for source_rule in batch_rules:
            # Check for duplicates if not overwriting
            if not copy_request.overwrite_existing:
                exists_result = await db.execute(rule_exists_in_target(source_rule))
                if exists_result.scalar():
                    batch_skipped += 1
                    continue
            
            # Create copy
            new_rule = source_rule.create_copy_for_period(
                copy_request.target_academic_year,
                target_semester_enum
            )
            new_rule.created_by = current_user.id
            new_rule.updated_by = current_user.id
            batch_new_rules.append(new_rule)
        
        # Bulk insert batch
        if batch_new_rules:
            db.add_all(batch_new_rules)
            await db.commit()
            all_new_rules.extend(batch_new_rules)
        
        total_skipped += batch_skipped
        processed_count += len(batch_rules)
        offset += batch_size
    
    # Load relationships for response
    if all_new_rules:
        rule_ids = [rule.id for rule in all_new_rules]
        refreshed_rules_stmt = select(ScholarshipRule).options(
            selectinload(ScholarshipRule.scholarship_type),
            selectinload(ScholarshipRule.creator),
            selectinload(ScholarshipRule.updater)
        ).where(ScholarshipRule.id.in_(rule_ids))
        
        refreshed_result = await db.execute(refreshed_rules_stmt)
        refreshed_rules = refreshed_result.scalars().all()
        
        rule_responses = []
        for rule in refreshed_rules:
            rule_response = ScholarshipRuleResponse.model_validate(rule)
            rule_response.academic_period_label = rule.academic_period_label
            rule_responses.append(rule_response)
    else:
        rule_responses = []
    
    # Build response message
    if total_skipped > 0:
        message = f"Successfully copied {len(all_new_rules)} rules in batches. Skipped {total_skipped} duplicates."
    else:
        message = f"Successfully copied {len(all_new_rules)} rules in batches."
    
    return ApiResponse(
        success=True,
        message=message,
        data=rule_responses
    )


@router.post("/scholarship-rules/copy", response_model=ApiResponse[List[ScholarshipRuleResponse]])
async def copy_rules_between_periods(
    copy_request: RuleCopyRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Copy rules between academic periods"""
    
    # Build source query
    stmt = select(ScholarshipRule)
    
    # Filter by source period
    if copy_request.source_academic_year:
        stmt = stmt.where(ScholarshipRule.academic_year == copy_request.source_academic_year)
    
    if copy_request.source_semester:
        # source_semester is already a Semester enum from the schema
        stmt = stmt.where(ScholarshipRule.semester == copy_request.source_semester)
    
    # Filter by scholarship types if specified
    if copy_request.scholarship_type_ids:
        stmt = stmt.where(ScholarshipRule.scholarship_type_id.in_(copy_request.scholarship_type_ids))
    
    # Filter by specific rules if specified
    if copy_request.rule_ids:
        stmt = stmt.where(ScholarshipRule.id.in_(copy_request.rule_ids))
    
    # Exclude templates
    stmt = stmt.where(ScholarshipRule.is_template == False)
    
    # Get count first to decide on batch processing approach
    count_stmt = select(func.count(ScholarshipRule.id))
    if copy_request.rule_ids:
        count_stmt = count_stmt.where(ScholarshipRule.id.in_(copy_request.rule_ids))
    else:
        count_stmt = count_stmt.where(
            ScholarshipRule.scholarship_type_id == copy_request.source_scholarship_type_id,
            ScholarshipRule.academic_year == copy_request.source_academic_year
        )
        if copy_request.source_semester:
            count_stmt = count_stmt.where(ScholarshipRule.semester == copy_request.source_semester)
    
    count_stmt = count_stmt.where(ScholarshipRule.is_template == False)
    count_result = await db.execute(count_stmt)
    total_rules = count_result.scalar()
    
    if total_rules == 0:
        return ApiResponse(
            success=True,
            message="No rules found to copy",
            data=[]
        )
    
    # For large datasets (>500 rules), use batch processing to avoid memory issues
    BATCH_SIZE = 500
    use_batch_processing = total_rules > BATCH_SIZE
    
    if use_batch_processing:
        # Process in batches for large datasets
        return await _copy_rules_in_batches(
            db, stmt, copy_request, target_semester_enum, current_user, total_rules, BATCH_SIZE
        )
    else:
        # Process all at once for smaller datasets
        result = await db.execute(stmt)
        source_rules = result.scalars().all()
        
        # Check permissions for all scholarship types involved
        scholarship_type_ids = set(rule.scholarship_type_id for rule in source_rules)
        for scholarship_type_id in scholarship_type_ids:
            check_scholarship_permission(current_user, scholarship_type_id)
    
    # Prepare target semester enum (already an enum from schema)
    target_semester_enum = copy_request.target_semester
    
    # Create copies with bulk duplicate checking for better performance
    new_rules = []
    skipped_rules = 0
    
    # Optimized duplicate check using EXISTS subquery for better performance with large datasets
    def rule_exists_in_target(source_rule):
        """Check if a rule already exists in the target period using EXISTS subquery"""
        exists_query = select(1).where(
            ScholarshipRule.academic_year == copy_request.target_academic_year,
            ScholarshipRule.semester == target_semester_enum,
            ScholarshipRule.scholarship_type_id == source_rule.scholarship_type_id,
            ScholarshipRule.rule_name == source_rule.rule_name,
            ScholarshipRule.rule_type == source_rule.rule_type,
            ScholarshipRule.condition_field == source_rule.condition_field,
            ScholarshipRule.operator == source_rule.operator,
            ScholarshipRule.expected_value == source_rule.expected_value,
            ScholarshipRule.sub_type == source_rule.sub_type,
            ScholarshipRule.is_template == False  # Exclude templates
        ).exists()
        
        return select(exists_query)
    
    for source_rule in source_rules:
        # Check if rule already exists using EXISTS subquery (more memory efficient)
        if not copy_request.overwrite_existing:
            exists_result = await db.execute(rule_exists_in_target(source_rule))
            rule_exists = exists_result.scalar()
            
            if rule_exists:
                # Skip this rule as it already exists
                skipped_rules += 1
                continue
        
        # Create new rule
        new_rule = source_rule.create_copy_for_period(
            copy_request.target_academic_year, 
            target_semester_enum
        )
        new_rule.created_by = current_user.id
        new_rule.updated_by = current_user.id
        new_rules.append(new_rule)
    
    # Add all new rules
    db.add_all(new_rules)
    await db.commit()
    
    # Load all relationships in a single batch query
    if new_rules:
        rule_ids = [rule.id for rule in new_rules]
        refreshed_rules_stmt = select(ScholarshipRule).options(
            selectinload(ScholarshipRule.scholarship_type),
            selectinload(ScholarshipRule.creator),
            selectinload(ScholarshipRule.updater)
        ).where(ScholarshipRule.id.in_(rule_ids))
        
        refreshed_result = await db.execute(refreshed_rules_stmt)
        refreshed_rules = refreshed_result.scalars().all()
        
        # Create response objects
        rule_responses = []
        for rule in refreshed_rules:
            rule_response = ScholarshipRuleResponse.model_validate(rule)
            rule_response.academic_period_label = rule.academic_period_label
            rule_responses.append(rule_response)
    else:
        rule_responses = []
    
    # Build response message
    if skipped_rules > 0:
        message = f"Successfully copied {len(new_rules)} rules to target period. Skipped {skipped_rules} duplicate rules."
    else:
        message = f"Successfully copied {len(new_rules)} rules to target period."
    
    return ApiResponse(
        success=True,
        message=message,
        data=rule_responses
    )


@router.post("/scholarship-rules/bulk-operation", response_model=ApiResponse[Dict[str, Any]])
async def bulk_rule_operation(
    operation_request: BulkRuleOperation,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Perform bulk operations on scholarship rules"""
    
    if not operation_request.rule_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No rule IDs provided"
        )
    
    # Get rules
    stmt = select(ScholarshipRule).where(ScholarshipRule.id.in_(operation_request.rule_ids))
    result = await db.execute(stmt)
    rules = result.scalars().all()
    
    if not rules:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No rules found with the provided IDs"
        )
    
    # Check permissions for all scholarship types involved
    scholarship_type_ids = set(rule.scholarship_type_id for rule in rules)
    for scholarship_type_id in scholarship_type_ids:
        check_scholarship_permission(current_user, scholarship_type_id)
    
    operation_results = {
        "operation": operation_request.operation,
        "affected_rules": len(rules),
        "details": []
    }
    
    if operation_request.operation == "activate":
        for rule in rules:
            rule.is_active = True
            rule.updated_by = current_user.id
        await db.commit()
        operation_results["details"].append(f"Activated {len(rules)} rules")
    
    elif operation_request.operation == "deactivate":
        for rule in rules:
            rule.is_active = False
            rule.updated_by = current_user.id
        await db.commit()
        operation_results["details"].append(f"Deactivated {len(rules)} rules")
    
    elif operation_request.operation == "delete":
        for rule in rules:
            await db.delete(rule)
        await db.commit()
        operation_results["details"].append(f"Deleted {len(rules)} rules")
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported operation: {operation_request.operation}"
        )
    
    return ApiResponse(
        success=True,
        message=f"Bulk operation '{operation_request.operation}' completed successfully",
        data=operation_results
    )


# ============================
# Rule Template Management
# ============================

@router.get("/scholarship-rules/templates", response_model=ApiResponse[List[ScholarshipRuleResponse]])
async def get_rule_templates(
    scholarship_type_id: Optional[int] = Query(None, description="Filter by scholarship type"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all rule templates"""
    
    # Check scholarship permission if specific scholarship type is requested
    if scholarship_type_id:
        check_scholarship_permission(current_user, scholarship_type_id)
    
    stmt = select(ScholarshipRule).options(
        selectinload(ScholarshipRule.scholarship_type),
        selectinload(ScholarshipRule.creator)
    ).where(ScholarshipRule.is_template == True)
    
    if scholarship_type_id:
        stmt = stmt.where(ScholarshipRule.scholarship_type_id == scholarship_type_id)
    elif not current_user.is_super_admin():
        # If no specific scholarship type requested and user is not super admin,
        # only show templates for scholarships they have permission to manage
        admin_scholarship_ids = [admin_scholarship.scholarship_id 
                               for admin_scholarship in current_user.admin_scholarships]
        if admin_scholarship_ids:
            stmt = stmt.where(ScholarshipRule.scholarship_type_id.in_(admin_scholarship_ids))
        else:
            # Admin has no scholarship permissions, return empty result
            return ApiResponse(success=True, message="No rule templates found", data=[])
    
    stmt = stmt.order_by(ScholarshipRule.template_name, ScholarshipRule.priority.desc())
    
    result = await db.execute(stmt)
    templates = result.scalars().all()
    
    template_responses = []
    for template in templates:
        # Ensure all attributes are loaded in the session context
        await db.refresh(template)
        
        template_response = ScholarshipRuleResponse.model_validate(template)
        template_response.academic_period_label = template.academic_period_label
        template_responses.append(template_response)
    
    return ApiResponse(
        success=True,
        message=f"Retrieved {len(template_responses)} rule templates",
        data=template_responses
    )


@router.post("/scholarship-rules/create-template", response_model=ApiResponse[List[ScholarshipRuleResponse]])
async def create_rule_template(
    template_request: RuleTemplateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a rule template from existing rules"""
    
    # Get the source rules
    stmt = select(ScholarshipRule).where(ScholarshipRule.id.in_(template_request.rule_ids))
    result = await db.execute(stmt)
    source_rules = result.scalars().all()
    
    if not source_rules:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No rules found with the provided IDs"
        )
    
    # Check permissions for all scholarship types involved
    scholarship_type_ids = set(rule.scholarship_type_id for rule in source_rules)
    for scholarship_type_id in scholarship_type_ids:
        check_scholarship_permission(current_user, scholarship_type_id)
    
    # Verify all rules belong to the same scholarship type
    if not all(rule.scholarship_type_id == template_request.scholarship_type_id for rule in source_rules):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All rules must belong to the same scholarship type"
        )
    
    # Create template rules
    template_rules = []
    for source_rule in source_rules:
        template_rule = ScholarshipRule(
            scholarship_type_id=source_rule.scholarship_type_id,
            sub_type=source_rule.sub_type,
            academic_year=None,  # Templates don't have academic context
            semester=None,
            is_template=True,
            template_name=template_request.template_name,
            template_description=template_request.template_description,
            rule_name=source_rule.rule_name,
            rule_type=source_rule.rule_type,
            tag=source_rule.tag,
            description=source_rule.description,
            condition_field=source_rule.condition_field,
            operator=source_rule.operator,
            expected_value=source_rule.expected_value,
            message=source_rule.message,
            message_en=source_rule.message_en,
            is_hard_rule=source_rule.is_hard_rule,
            is_warning=source_rule.is_warning,
            priority=source_rule.priority,
            is_active=True,
            created_by=current_user.id,
            updated_by=current_user.id
        )
        template_rules.append(template_rule)
    
    # Add template rules to database
    db.add_all(template_rules)
    await db.commit()
    
    # Load all relationships in a single batch query
    if template_rules:
        rule_ids = [rule.id for rule in template_rules]
        refreshed_rules_stmt = select(ScholarshipRule).options(
            selectinload(ScholarshipRule.scholarship_type),
            selectinload(ScholarshipRule.creator),
            selectinload(ScholarshipRule.updater)
        ).where(ScholarshipRule.id.in_(rule_ids))
        
        refreshed_result = await db.execute(refreshed_rules_stmt)
        refreshed_rules = refreshed_result.scalars().all()
        
        # Create response objects
        template_responses = []
        for rule in refreshed_rules:
            rule_response = ScholarshipRuleResponse.model_validate(rule)
            rule_response.academic_period_label = rule.academic_period_label
            template_responses.append(rule_response)
    else:
        template_responses = []
    
    return ApiResponse(
        success=True,
        message=f"Created template '{template_request.template_name}' with {len(template_rules)} rules",
        data=template_responses
    )


@router.post("/scholarship-rules/apply-template", response_model=ApiResponse[List[ScholarshipRuleResponse]])
async def apply_rule_template(
    template_request: ApplyTemplateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Apply a rule template to create rules for a specific academic period"""
    
    # Get template rules
    stmt = select(ScholarshipRule).where(
        ScholarshipRule.id == template_request.template_id,
        ScholarshipRule.is_template == True
    )
    result = await db.execute(stmt)
    template_rule = result.scalar_one_or_none()
    
    if not template_rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # Check permission to manage the target scholarship
    check_scholarship_permission(current_user, template_request.scholarship_type_id)
    
    # Get all rules with the same template name and scholarship type
    template_stmt = select(ScholarshipRule).where(
        ScholarshipRule.template_name == template_rule.template_name,
        ScholarshipRule.scholarship_type_id == template_request.scholarship_type_id,
        ScholarshipRule.is_template == True
    )
    template_result = await db.execute(template_stmt)
    template_rules = template_result.scalars().all()
    
    # Check for existing rules in the target period if not overwriting
    if not template_request.overwrite_existing:
        target_semester_enum = None
        if template_request.semester:
            target_semester_enum = Semester.FIRST if template_request.semester == "first" else Semester.SECOND
        
        existing_stmt = select(ScholarshipRule).where(
            ScholarshipRule.scholarship_type_id == template_request.scholarship_type_id,
            ScholarshipRule.academic_year == template_request.academic_year,
            ScholarshipRule.semester == target_semester_enum,
            ScholarshipRule.is_template == False
        )
        
        existing_result = await db.execute(existing_stmt)
        existing_rules = existing_result.scalars().all()
        
        if existing_rules:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Rules already exist for the target period. Use overwrite_existing=true to replace them."
            )
    
    # Create rules from template
    new_rules = []
    target_semester_enum = None
    if template_request.semester:
        target_semester_enum = Semester.FIRST if template_request.semester == "first" else Semester.SECOND
    
    for template_rule in template_rules:
        new_rule = ScholarshipRule(
            scholarship_type_id=template_request.scholarship_type_id,
            sub_type=template_rule.sub_type,
            academic_year=template_request.academic_year,
            semester=target_semester_enum,
            is_template=False,
            rule_name=template_rule.rule_name,
            rule_type=template_rule.rule_type,
            tag=template_rule.tag,
            description=template_rule.description,
            condition_field=template_rule.condition_field,
            operator=template_rule.operator,
            expected_value=template_rule.expected_value,
            message=template_rule.message,
            message_en=template_rule.message_en,
            is_hard_rule=template_rule.is_hard_rule,
            is_warning=template_rule.is_warning,
            priority=template_rule.priority,
            is_active=template_rule.is_active,
            created_by=current_user.id,
            updated_by=current_user.id
        )
        new_rules.append(new_rule)
    
    # Add new rules to database
    db.add_all(new_rules)
    await db.commit()
    
    # Load all relationships in a single batch query
    if new_rules:
        rule_ids = [rule.id for rule in new_rules]
        refreshed_rules_stmt = select(ScholarshipRule).options(
            selectinload(ScholarshipRule.scholarship_type),
            selectinload(ScholarshipRule.creator),
            selectinload(ScholarshipRule.updater)
        ).where(ScholarshipRule.id.in_(rule_ids))
        
        refreshed_result = await db.execute(refreshed_rules_stmt)
        refreshed_rules = refreshed_result.scalars().all()
        
        # Create response objects
        rule_responses = []
        for rule in refreshed_rules:
            rule_response = ScholarshipRuleResponse.model_validate(rule)
            rule_response.academic_period_label = rule.academic_period_label
            rule_responses.append(rule_response)
    else:
        rule_responses = []
    
    return ApiResponse(
        success=True,
        message=f"Applied template '{template_rule.template_name}' and created {len(new_rules)} rules",
        data=rule_responses
    )


@router.delete("/scholarship-rules/templates/{template_name}", response_model=ApiResponse[Dict[str, str]])
async def delete_rule_template(
    template_name: str,
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a rule template and all its associated rules"""
    
    # Check permission to manage this scholarship
    check_scholarship_permission(current_user, scholarship_type_id)
    
    # Get template rules
    stmt = select(ScholarshipRule).where(
        ScholarshipRule.template_name == template_name,
        ScholarshipRule.scholarship_type_id == scholarship_type_id,
        ScholarshipRule.is_template == True
    )
    result = await db.execute(stmt)
    template_rules = result.scalars().all()
    
    if not template_rules:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # Delete all template rules
    for rule in template_rules:
        await db.delete(rule)
    
    await db.commit()
    
    return ApiResponse(
        success=True,
        message=f"Deleted template '{template_name}' with {len(template_rules)} rules",
        data={"message": f"Template '{template_name}' deleted successfully"}
    )


@router.get("/scholarships/available-years", response_model=ApiResponse[List[int]])
async def get_available_years(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get available academic years from scholarship rules"""
    
    # Query distinct academic years from scholarship rules
    stmt = select(ScholarshipRule.academic_year).distinct().where(
        ScholarshipRule.academic_year.is_not(None)
    ).order_by(ScholarshipRule.academic_year.desc())
    
    result = await db.execute(stmt)
    years = result.scalars().all()
    
    # If no years found in database, provide default years
    if not years:
        # Current year in Taiwan calendar (民國)
        current_taiwan_year = datetime.now().year - 1911
        years = [current_taiwan_year - 1, current_taiwan_year, current_taiwan_year + 1]
    
    return ApiResponse(
        success=True,
        message=f"Retrieved {len(years)} available years",
        data=list(years)
    )


@router.get("/professors", response_model=ApiResponse[List[Dict[str, Any]]])
async def get_available_professors(
    search: Optional[str] = Query(None, description="Search by name or NYCU ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of available professors for assignment
    - College admins see only professors in their college
    - Admin/Super Admin see all professors
    """
    try:
        service = ApplicationService(db)
        professors = await service.get_available_professors(current_user, search)
        
        return ApiResponse(
            success=True,
            message=f"Retrieved {len(professors)} professors",
            data=professors
        )
        
    except Exception as e:
        logger.error(f"Error fetching professors: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch professors: {str(e)}"
        )


@router.put("/applications/{application_id}/assign-professor", response_model=ApiResponse[ApplicationResponse])
async def assign_professor_to_application(
    application_id: int,
    request: ProfessorAssignmentRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Assign a professor to review an application"""
    try:
        service = ApplicationService(db)
        application = await service.assign_professor(
            application_id=application_id,
            professor_nycu_id=request.professor_nycu_id,
            assigned_by=current_user
        )
        
        # Create a safe response that doesn't trigger lazy loading
        # Extract student info from student_data JSON field
        student_data = application.student_data or {}
        student_id = (student_data.get("std_stdcode") or 
                     student_data.get("student_id") or 
                     student_data.get("stdNo"))
        
        response_data = {
            "id": application.id,
            "app_id": application.app_id,
            "user_id": application.user_id,
            "student_id": student_id,
            "scholarship_type_id": application.scholarship_type_id,
            "scholarship_subtype_list": application.scholarship_subtype_list or [],
            "status": application.status,
            "status_name": getattr(application, 'status_name', application.status),
            "is_renewal": application.is_renewal or False,
            "academic_year": application.academic_year,
            "semester": application.semester,
            "student_data": application.student_data or {},
            "submitted_form_data": application.submitted_form_data or {},
            "agree_terms": application.agree_terms or False,
            "professor_id": application.professor_id,
            "reviewer_id": application.reviewer_id,
            "final_approver_id": application.final_approver_id,
            "review_score": application.review_score,
            "review_comments": application.review_comments,
            "rejection_reason": application.rejection_reason,
            "submitted_at": application.submitted_at.isoformat() if application.submitted_at else None,
            "reviewed_at": application.reviewed_at.isoformat() if application.reviewed_at else None,
            "approved_at": application.approved_at.isoformat() if application.approved_at else None,
            "created_at": application.created_at.isoformat(),
            "updated_at": application.updated_at.isoformat(),
            "meta_data": application.meta_data,
            "reviews": [],  # Empty to avoid lazy loading
            "professor_reviews": []  # Empty to avoid lazy loading
        }
        
        return ApiResponse(
            success=True,
            message=f"Professor {request.professor_nycu_id} assigned to application {application.app_id}",
            data=response_data
        )
        
    except Exception as e:
        logger.error(f"Error assigning professor: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign professor: {str(e)}"
        ) 