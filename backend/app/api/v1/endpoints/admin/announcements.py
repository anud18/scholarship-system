"""
Admin Announcements Management API Endpoints

Handles system announcement operations including:
- Listing announcements
- Creating new announcements
- Updating announcements
- Deleting announcements
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.notification import NotificationCreate, NotificationResponse, NotificationUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/announcements")
async def get_all_announcements(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all system announcements with pagination (admin only)"""

    # Build query for system announcements
    stmt = select(Notification).where(Notification.user_id.is_(None), Notification.related_resource_type == "system")

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
            "id": ann.id,
            "title": ann.title,
            "title_en": ann.title_en,
            "message": ann.message,
            "message_en": ann.message_en,
            "notification_type": ann.notification_type.value
            if hasattr(ann.notification_type, "value")
            else str(ann.notification_type),
            "priority": ann.priority.value if hasattr(ann.priority, "value") else str(ann.priority),
            "related_resource_type": ann.related_resource_type,
            "related_resource_id": ann.related_resource_id,
            "action_url": ann.action_url,
            "is_read": ann.is_read,
            "is_dismissed": ann.is_dismissed,
            "scheduled_at": ann.scheduled_at,
            "expires_at": ann.expires_at,
            "read_at": ann.read_at,
            "created_at": ann.created_at,
            "meta_data": ann.meta_data if isinstance(ann.meta_data, (dict, type(None))) else None,
        }
        response_items.append(NotificationResponse.model_validate(ann_dict))

    # 計算總頁數
    pages = (total + size - 1) // size if total > 0 else 1

    return {
        "success": True,
        "message": "系統公告列表獲取成功",
        "data": {"items": response_items, "total": total, "page": page, "size": size, "pages": pages},
    }


@router.post("/announcements", status_code=status.HTTP_201_CREATED)
async def create_announcement(
    announcement_data: NotificationCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
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
        related_resource_type="system",
        related_resource_id=None,
        action_url=announcement_data.action_url,
        is_read=False,
        is_dismissed=False,
        send_email=False,
        email_sent=False,
        expires_at=announcement_data.expires_at,
        meta_data=announcement_data.metadata,
    )

    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)

    # 修正 meta_data 字段以確保序列化正常
    announcement_dict = {
        "id": announcement.id,
        "title": announcement.title,
        "title_en": announcement.title_en,
        "message": announcement.message,
        "message_en": announcement.message_en,
        "notification_type": announcement.notification_type.value
        if hasattr(announcement.notification_type, "value")
        else str(announcement.notification_type),
        "priority": announcement.priority.value
        if hasattr(announcement.priority, "value")
        else str(announcement.priority),
        "related_resource_type": announcement.related_resource_type,
        "related_resource_id": announcement.related_resource_id,
        "action_url": announcement.action_url,
        "is_read": announcement.is_read,
        "is_dismissed": announcement.is_dismissed,
        "scheduled_at": announcement.scheduled_at,
        "expires_at": announcement.expires_at,
        "read_at": announcement.read_at,
        "created_at": announcement.created_at,
        "meta_data": announcement.meta_data if isinstance(announcement.meta_data, (dict, type(None))) else None,
    }

    return {
        "success": True,
        "message": "System announcement created successfully",
        "data": NotificationResponse.model_validate(announcement_dict),
    }


@router.get("/announcements/{id}")
async def get_announcement(id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Get specific system announcement (admin only)"""

    stmt = select(Notification).where(
        Notification.id == id,
        Notification.user_id.is_(None),
        Notification.related_resource_type == "system",
    )

    result = await db.execute(stmt)
    announcement = result.scalar_one_or_none()

    if not announcement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System announcement not found")

    # 修正 meta_data 字段以確保序列化正常
    announcement_dict = {
        "id": announcement.id,
        "title": announcement.title,
        "title_en": announcement.title_en,
        "message": announcement.message,
        "message_en": announcement.message_en,
        "notification_type": announcement.notification_type.value
        if hasattr(announcement.notification_type, "value")
        else str(announcement.notification_type),
        "priority": announcement.priority.value
        if hasattr(announcement.priority, "value")
        else str(announcement.priority),
        "related_resource_type": announcement.related_resource_type,
        "related_resource_id": announcement.related_resource_id,
        "action_url": announcement.action_url,
        "is_read": announcement.is_read,
        "is_dismissed": announcement.is_dismissed,
        "scheduled_at": announcement.scheduled_at,
        "expires_at": announcement.expires_at,
        "read_at": announcement.read_at,
        "created_at": announcement.created_at,
        "meta_data": announcement.meta_data if isinstance(announcement.meta_data, (dict, type(None))) else None,
    }

    return {
        "success": True,
        "message": "System announcement retrieved successfully",
        "data": NotificationResponse.model_validate(announcement_dict),
    }


@router.put("/announcements/{id}")
async def update_announcement(
    id: int,
    announcement_data: NotificationUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update system announcement (admin only)"""

    # Check if announcement exists
    stmt = select(Notification).where(
        Notification.id == id,
        Notification.user_id.is_(None),
        Notification.related_resource_type == "system",
    )

    result = await db.execute(stmt)
    announcement = result.scalar_one_or_none()

    if not announcement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System announcement not found")

    # Update only fields defined in the Pydantic schema to prevent mass assignment
    # This automatically stays in sync with schema changes
    allowed_fields = set(announcement_data.model_fields.keys())

    update_data = announcement_data.dict(exclude_unset=True)
    if update_data:
        for field, value in update_data.items():
            if field in allowed_fields:
                if field == "metadata":
                    setattr(announcement, "meta_data", value)
                elif hasattr(announcement, field):
                    setattr(announcement, field, value)

    await db.commit()
    await db.refresh(announcement)

    # 修正 meta_data 字段以確保序列化正常
    announcement_dict = {
        "id": announcement.id,
        "title": announcement.title,
        "title_en": announcement.title_en,
        "message": announcement.message,
        "message_en": announcement.message_en,
        "notification_type": announcement.notification_type.value
        if hasattr(announcement.notification_type, "value")
        else str(announcement.notification_type),
        "priority": announcement.priority.value
        if hasattr(announcement.priority, "value")
        else str(announcement.priority),
        "related_resource_type": announcement.related_resource_type,
        "related_resource_id": announcement.related_resource_id,
        "action_url": announcement.action_url,
        "is_read": announcement.is_read,
        "is_dismissed": announcement.is_dismissed,
        "scheduled_at": announcement.scheduled_at,
        "expires_at": announcement.expires_at,
        "read_at": announcement.read_at,
        "created_at": announcement.created_at,
        "meta_data": announcement.meta_data if isinstance(announcement.meta_data, (dict, type(None))) else None,
    }

    return {
        "success": True,
        "message": "System announcement updated successfully",
        "data": NotificationResponse.model_validate(announcement_dict),
    }


@router.delete("/announcements/{id}")
async def delete_announcement(id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Delete system announcement (admin only)"""

    # Check if announcement exists
    stmt = select(Notification).where(
        Notification.id == id,
        Notification.user_id.is_(None),
        Notification.related_resource_type == "system",
    )

    result = await db.execute(stmt)
    announcement = result.scalar_one_or_none()

    if not announcement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System announcement not found")

    # Delete announcement
    await db.delete(announcement)
    await db.commit()

    return {"success": True, "message": "系統公告已成功刪除", "data": None}
