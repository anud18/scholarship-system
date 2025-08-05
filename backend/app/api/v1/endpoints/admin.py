"""
Administration API endpoints
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, status, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update, delete
from sqlalchemy.orm import selectinload

from app.db.deps import get_db
from app.schemas.common import MessageResponse, PaginatedResponse, SystemSettingSchema, EmailTemplateSchema, ApiResponse
from app.schemas.application import ApplicationListResponse
from app.schemas.scholarship import ScholarshipSubTypeConfigCreate, ScholarshipSubTypeConfigUpdate, ScholarshipSubTypeConfigResponse
from app.schemas.notification import NotificationResponse, NotificationCreate, NotificationUpdate
from app.core.security import require_admin, get_current_user
from app.models.user import User, UserRole
from app.models.application import Application, ApplicationStatus
# Student model removed - student data now fetched from external API
from app.models.notification import Notification
from app.services.system_setting_service import SystemSettingService, EmailTemplateService
from app.models.scholarship import ScholarshipType, ScholarshipStatus, ScholarshipSubTypeConfig, ScholarshipSubType
from app.models.user import AdminScholarship

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
    
    # Build query with joins
    stmt = select(Application, User, ScholarshipType).join(
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
            # Additional fields for display
            "student_name": user.name if user else None,
            "student_no": getattr(user, 'nycu_id', None),
            "days_waiting": None
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
    
    # Build query with joins
    stmt = select(Application, User, ScholarshipType).join(
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
            # Additional fields for display
            "student_name": user.name if user else None,
            "student_no": getattr(user, 'nycu_id', None),
            "days_waiting": None
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
            'notification_type': notification.notification_type,
            'priority': notification.priority,
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
            'notification_type': ann.notification_type,
            'priority': ann.priority,
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
        'notification_type': announcement.notification_type,
        'priority': announcement.priority,
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
        'notification_type': announcement.notification_type,
        'priority': announcement.priority,
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
    
    # Update fields
    update_data = announcement_data.dict(exclude_unset=True)
    if update_data:
        for field, value in update_data.items():
            if field == 'metadata':
                setattr(announcement, 'meta_data', value)
            else:
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
        'notification_type': announcement.notification_type,
        'priority': announcement.priority,
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
    
    # Build query with joins and load files
    stmt = select(Application, User).options(
        selectinload(Application.files)
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
                        base_url = f"http://localhost:8000{settings.api_v1_str}"
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
            "scholarship_subtype_list": app.scholarship_subtype_list or [],
            "status": app.status,
            "status_name": app.status_name,
            "academic_year": app.academic_year or str(datetime.now().year),
            "semester": app.semester or "1",
            "student_data": app.student_data or {},
            "submitted_form_data": processed_form_data,
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
            # Additional fields for display
            "student_name": user.name if user else None,
            "student_no": getattr(user, 'nycu_id', None),
            "days_waiting": None
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
    
    # Update fields
    update_data = config_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
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
    
    print(f"DEBUG: get_scholarship_permissions called by user {current_user.id} ({current_user.role})")
    
    # Special handling for super_admin when filtering by user_id
    if user_id:
        # Check if the filtered user is a super_admin
        target_user_stmt = select(User).where(User.id == user_id)
        target_user_result = await db.execute(target_user_stmt)
        target_user = target_user_result.scalar_one_or_none()
        
        if target_user and target_user.role == UserRole.SUPER_ADMIN:
            print(f"DEBUG: Target user {user_id} is SUPER_ADMIN, returning all scholarships")
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
            
            print(f"DEBUG: Returning {len(permission_list)} virtual permissions for super_admin")
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
        print(f"DEBUG: Filtering by user_id: {user_id}")
    
    result = await db.execute(stmt)
    permissions = result.scalars().all()
    
    print(f"DEBUG: Found {len(permissions)} permissions in database")
    for perm in permissions:
        print(f"DEBUG: Permission - ID: {perm.id}, Admin: {perm.admin_id}, Scholarship: {perm.scholarship_id}")
    
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
        print(f"DEBUG: Current user is SUPER_ADMIN with no filter, adding virtual permissions")
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
        
        print(f"DEBUG: Added virtual permissions, total now: {len(permission_list)}")
    
    print(f"DEBUG: Returning {len(permission_list)} permissions")
    
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
    
    print(f"DEBUG: Received permission_data: {permission_data}")
    
    user_id = permission_data.get("user_id")
    scholarship_id = permission_data.get("scholarship_id")
    comment = permission_data.get("comment", "")
    
    print(f"DEBUG: user_id={user_id}, scholarship_id={scholarship_id}, comment={comment}")
    
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
    
    # Check if current user has permission for this scholarship (admin role only)
    if current_user.role == UserRole.ADMIN:
        permission_check_stmt = select(AdminScholarship).where(
            AdminScholarship.admin_id == current_user.id,
            AdminScholarship.scholarship_id == scholarship_id
        )
        permission_check_result = await db.execute(permission_check_stmt)
        has_permission = permission_check_result.scalar_one_or_none()
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to assign this scholarship"
            )
    
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
    print(f"DEBUG: Creating AdminScholarship with admin_id={user_id}, scholarship_id={scholarship_id}")
    
    new_permission = AdminScholarship(
        admin_id=user_id,
        scholarship_id=scholarship_id
    )
    
    db.add(new_permission)
    await db.commit()
    await db.refresh(new_permission)
    
    print(f"DEBUG: Successfully created permission with id={new_permission.id}")
    
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
    
    print(f"DEBUG: Attempting to delete permission {permission_id}")
    
    # Check if permission exists
    stmt = select(AdminScholarship).options(
        selectinload(AdminScholarship.scholarship)
    ).where(AdminScholarship.id == permission_id)
    result = await db.execute(stmt)
    permission = result.scalar_one_or_none()
    
    if not permission:
        print(f"DEBUG: Permission {permission_id} not found")
        raise HTTPException(status_code=404, detail="Permission not found")
    
    print(f"DEBUG: Found permission {permission_id} for admin {permission.admin_id}, scholarship {permission.scholarship_id}")
    
    # Check if admin is trying to delete their own permissions (not allowed)
    if current_user.role == UserRole.ADMIN and permission.admin_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin users cannot delete their own permissions"
        )
    
    # Check if current user has permission for this scholarship (admin role only)
    if current_user.role == UserRole.ADMIN:
        permission_check_stmt = select(AdminScholarship).where(
            AdminScholarship.admin_id == current_user.id,
            AdminScholarship.scholarship_id == permission.scholarship_id
        )
        permission_check_result = await db.execute(permission_check_stmt)
        has_permission = permission_check_result.scalar_one_or_none()
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to manage this scholarship"
            )
    
    # Delete permission
    await db.delete(permission)
    await db.commit()
    
    print(f"DEBUG: Successfully deleted permission {permission_id}")
    
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