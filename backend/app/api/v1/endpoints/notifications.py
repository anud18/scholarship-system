"""
Notification endpoints for managing user notifications and system announcements
"""

from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete
from sqlalchemy import func as sa_func
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.notification import Notification, NotificationPriority, NotificationType
from app.models.user import User
from app.schemas.notification import NotificationCreate, NotificationResponse
from app.schemas.response import ApiResponse
from app.services.notification_service import NotificationService

func: Any = sa_func

router = APIRouter()


@router.get("", response_model=ApiResponse[List[NotificationResponse]])
async def getUserNotifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="跳過的通知數量"),
    limit: int = Query(20, ge=1, le=100, description="返回的通知數量"),
    unread_only: bool = Query(False, description="只返回未讀通知"),
    notification_type: Optional[str] = Query(None, description="通知類型篩選"),
):
    """
    獲取使用者的通知列表
    包含個人通知和系統公告，按用戶分別記錄已讀狀態
    """
    try:
        service = NotificationService(db)
        notifications_data = await service.getUserNotifications(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
            unread_only=unread_only,
            notification_type=notification_type,
        )

        return ApiResponse(success=True, message="通知列表獲取成功", data=notifications_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取通知失敗: {str(e)}")


@router.get("/unread-count", response_model=ApiResponse[int])
async def getUnreadNotificationCount(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    獲取使用者未讀通知數量
    按用戶分別計算未讀狀態
    """
    try:
        service = NotificationService(db)
        count = await service.getUnreadNotificationCount(current_user.id)

        return ApiResponse(success=True, message="未讀通知數量獲取成功", data=count)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取未讀通知數量失敗: {str(e)}")


@router.patch("/{notification_id}/read", response_model=ApiResponse[dict])
async def markNotificationAsRead(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    標記通知為已讀
    支援個人通知和系統公告的分別已讀狀態
    """
    try:
        service = NotificationService(db)
        success = await service.markNotificationAsRead(notification_id, current_user.id)

        if not success:
            raise HTTPException(status_code=404, detail="通知不存在")

        return ApiResponse(success=True, message="通知已標記為已讀", data={"notification_id": notification_id})

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"標記通知為已讀失敗: {str(e)}")


@router.patch("/mark-all-read", response_model=ApiResponse[dict])
async def markAllNotificationsAsRead(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    標記所有通知為已讀
    支援個人通知和系統公告的分別已讀狀態
    """
    try:
        service = NotificationService(db)
        updated_count = await service.markAllNotificationsAsRead(current_user.id)

        return ApiResponse(
            success=True,
            message=f"已標記 {updated_count} 條通知為已讀",
            data={"updated_count": updated_count},
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"標記所有通知為已讀失敗: {str(e)}")


@router.patch("/{notification_id}/dismiss", response_model=ApiResponse[dict])
async def dismissNotification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    關閉/隱藏通知
    """
    try:
        # 查詢通知
        stmt = select(Notification).where(
            and_(
                Notification.id == notification_id,
                or_(
                    Notification.user_id == current_user.id,
                    Notification.user_id.is_(None),
                ),
            )
        )

        result = await db.execute(stmt)
        notification = result.scalar_one_or_none()

        if not notification:
            raise HTTPException(status_code=404, detail="通知不存在")

        # 關閉通知
        notification.dismiss()
        await db.commit()

        return ApiResponse(success=True, message="通知已關閉", data={"notification_id": notification_id})

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"關閉通知失敗: {str(e)}")


@router.get("/{notification_id}", response_model=ApiResponse[NotificationResponse])
async def getNotificationDetail(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    獲取通知詳情
    """
    try:
        stmt = select(Notification).where(
            and_(
                Notification.id == notification_id,
                or_(
                    Notification.user_id == current_user.id,
                    Notification.user_id.is_(None),
                ),
            )
        )

        result = await db.execute(stmt)
        notification = result.scalar_one_or_none()

        if not notification:
            raise HTTPException(status_code=404, detail="通知不存在")

        notification_data = {
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
            "metadata": notification.meta_data,
        }

        return ApiResponse(success=True, message="通知詳情獲取成功", data=notification_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取通知詳情失敗: {str(e)}")


@router.post(
    "/admin/create-system-announcement",
    response_model=ApiResponse[NotificationResponse],
)
async def createSystemAnnouncement(
    notification_data: NotificationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    創建系統公告（僅管理員可用）
    """
    # 檢查管理員權限
    if not current_user.is_admin() and not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="需要管理員權限")

    try:
        notification_service = NotificationService(db)

        notification = await notification_service.createSystemAnnouncement(
            title=notification_data.title,
            title_en=notification_data.title_en,
            message=notification_data.message,
            message_en=notification_data.message_en,
            notification_type=notification_data.notification_type,
            priority=notification_data.priority,
            action_url=notification_data.action_url,
            expires_at=notification_data.expires_at,
            metadata=notification_data.metadata,
        )

        notification_response = {
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
            "metadata": notification.meta_data,
        }

        return ApiResponse(success=True, message="系統公告創建成功", data=notification_response)

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"創建系統公告失敗: {str(e)}")


@router.post("/admin/create-test-notifications", response_model=ApiResponse[dict])
async def createTestNotifications(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    創建測試通知（僅管理員可用，用於演示）
    """
    # 檢查管理員權限
    if not current_user.is_admin() and not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="需要管理員權限")

    try:
        notification_service = NotificationService(db)
        created_notifications = []

        # 創建系統公告
        system_announcement = await notification_service.createSystemAnnouncement(
            title="系統維護通知",
            title_en="System Maintenance Notice",
            message="系統將於今晚23:00-01:00進行維護，期間可能無法正常使用。造成不便敬請見諒。",
            message_en="The system will undergo maintenance from 23:00-01:00 tonight. Service may be unavailable during this time. We apologize for any inconvenience.",
            notification_type=NotificationType.warning.value,
            priority=NotificationPriority.high.value,
        )
        created_notifications.append(system_announcement.id)

        # 創建個人通知（給當前用戶）
        personal_notification = await notification_service.createUserNotification(
            user_id=current_user.id,
            title="歡迎使用獎學金管理系統",
            title_en="Welcome to Scholarship Management System",
            message="歡迎使用獎學金申請與審核系統！您可以在此查看申請狀態、上傳文件並接收重要通知。",
            message_en="Welcome to the Scholarship Application and Review System! You can view application status, upload documents, and receive important notifications here.",
            notification_type=NotificationType.info.value,
            priority=NotificationPriority.normal.value,
            action_url="/dashboard",
        )
        created_notifications.append(personal_notification.id)

        # 創建緊急通知
        urgent_notification = await notification_service.createSystemAnnouncement(
            title="重要：申請截止日期提醒",
            title_en="Important: Application Deadline Reminder",
            message="2024春季獎學金申請將於本月底截止，請尚未提交申請的同學把握時間完成申請程序。",
            message_en="The 2024 Spring Scholarship application deadline is at the end of this month. Students who have not yet submitted their applications should complete the process soon.",
            notification_type=NotificationType.reminder.value,
            priority=NotificationPriority.URGENT.value,
            action_url="/scholarships",
        )
        created_notifications.append(urgent_notification.id)

        return ApiResponse(
            success=True,
            message=f"成功創建 {len(created_notifications)} 條測試通知",
            data={
                "created_count": len(created_notifications),
                "notification_ids": created_notifications,
            },
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"創建測試通知失敗: {str(e)}")


# === Admin Announcement Management Endpoints === #


@router.get("/admin/announcements", response_model=ApiResponse[dict])
async def getAllAnnouncements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="頁碼"),
    size: int = Query(10, ge=1, le=100, description="每頁數量"),
    notification_type: Optional[str] = Query(None, description="通知類型篩選"),
    priority: Optional[str] = Query(None, description="優先級篩選"),
):
    """
    獲取所有系統公告（分頁）
    """
    # 檢查管理員權限
    if not current_user.is_admin() and not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="需要管理員權限")

    try:
        # 構建查詢條件
        conditions = [Notification.user_id.is_(None)]  # 只查詢系統公告

        if notification_type:
            conditions.append(Notification.notification_type == notification_type)
        if priority:
            conditions.append(Notification.priority == priority)

        # 查詢總數
        count_stmt = select(func.count(Notification.id)).where(and_(*conditions))
        count_result = await db.execute(count_stmt)
        total = count_result.scalar()

        # 查詢數據
        offset = (page - 1) * size
        stmt = (
            select(Notification)
            .where(and_(*conditions))
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(size)
        )

        result = await db.execute(stmt)
        notifications = result.scalars().all()

        # 轉換為響應格式
        items = []
        for notification in notifications:
            notification_data = {
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
                "metadata": notification.meta_data,
            }
            items.append(notification_data)

        return ApiResponse(
            success=True,
            message="系統公告列表獲取成功",
            data={"items": items, "total": total, "page": page, "size": size},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取系統公告列表失敗: {str(e)}")


@router.get(
    "/admin/announcements/{announcement_id}",
    response_model=ApiResponse[NotificationResponse],
)
async def getAnnouncement(
    announcement_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    獲取特定系統公告詳情
    """
    # 檢查管理員權限
    if not current_user.is_admin() and not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="需要管理員權限")

    try:
        stmt = select(Notification).where(
            and_(
                Notification.id == announcement_id,
                Notification.user_id.is_(None),  # 只查詢系統公告
            )
        )

        result = await db.execute(stmt)
        notification = result.scalar_one_or_none()

        if not notification:
            raise HTTPException(status_code=404, detail="系統公告不存在")

        notification_data = {
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
            "metadata": notification.meta_data,
        }

        return ApiResponse(success=True, message="系統公告詳情獲取成功", data=notification_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取系統公告詳情失敗: {str(e)}")


@router.post("/admin/announcements", response_model=ApiResponse[NotificationResponse])
async def createAnnouncement(
    notification_data: NotificationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    創建系統公告
    """
    # 檢查管理員權限
    if not current_user.is_admin() and not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="需要管理員權限")

    try:
        notification_service = NotificationService(db)

        notification = await notification_service.createSystemAnnouncement(
            title=notification_data.title,
            title_en=notification_data.title_en,
            message=notification_data.message,
            message_en=notification_data.message_en,
            notification_type=notification_data.notification_type,
            priority=notification_data.priority,
            action_url=notification_data.action_url,
            expires_at=notification_data.expires_at,
            metadata=notification_data.metadata,
        )

        notification_response = {
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
            "metadata": notification.meta_data,
        }

        return ApiResponse(success=True, message="系統公告創建成功", data=notification_response)

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"創建系統公告失敗: {str(e)}")


@router.put(
    "/admin/announcements/{announcement_id}",
    response_model=ApiResponse[NotificationResponse],
)
async def updateAnnouncement(
    announcement_id: int,
    notification_data: NotificationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    更新系統公告
    """
    # 檢查管理員權限
    if not current_user.is_admin() and not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="需要管理員權限")

    try:
        stmt = select(Notification).where(
            and_(
                Notification.id == announcement_id,
                Notification.user_id.is_(None),  # 只允許更新系統公告
            )
        )

        result = await db.execute(stmt)
        notification = result.scalar_one_or_none()

        if not notification:
            raise HTTPException(status_code=404, detail="系統公告不存在")

        # 更新公告數據
        if notification_data.title is not None:
            notification.title = notification_data.title
        if notification_data.title_en is not None:
            notification.title_en = notification_data.title_en
        if notification_data.message is not None:
            notification.message = notification_data.message
        if notification_data.message_en is not None:
            notification.message_en = notification_data.message_en
        if notification_data.notification_type is not None:
            notification.notification_type = notification_data.notification_type
        if notification_data.priority is not None:
            notification.priority = notification_data.priority
        if notification_data.action_url is not None:
            notification.action_url = notification_data.action_url
        if notification_data.expires_at is not None:
            notification.expires_at = notification_data.expires_at
        if notification_data.metadata is not None:
            notification.meta_data = notification_data.metadata

        notification.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(notification)

        notification_response = {
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
            "metadata": notification.meta_data,
        }

        return ApiResponse(success=True, message="系統公告更新成功", data=notification_response)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"更新系統公告失敗: {str(e)}")


@router.delete("/admin/announcements/{announcement_id}", response_model=ApiResponse[dict])
async def deleteAnnouncement(
    announcement_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    刪除系統公告
    """
    # 檢查管理員權限
    if not current_user.is_admin() and not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="需要管理員權限")

    try:
        stmt = select(Notification).where(
            and_(
                Notification.id == announcement_id,
                Notification.user_id.is_(None),  # 只允許刪除系統公告
            )
        )

        result = await db.execute(stmt)
        notification = result.scalar_one_or_none()

        if not notification:
            raise HTTPException(status_code=404, detail="系統公告不存在")

        # 同時刪除相關的已讀記錄
        from app.models.notification import NotificationRead

        read_stmt = delete(NotificationRead).where(NotificationRead.notification_id == announcement_id)
        await db.execute(read_stmt)

        # 刪除公告
        delete_stmt = delete(Notification).where(Notification.id == announcement_id)
        await db.execute(delete_stmt)

        await db.commit()

        return ApiResponse(success=True, message="系統公告刪除成功", data={"message": "系統公告已成功刪除"})

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"刪除系統公告失敗: {str(e)}")
