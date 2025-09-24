"""
Facebook-style notification API endpoints demonstration
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import require_admin
from app.models.notification import (
    NotificationChannel,
    NotificationPriority,
    NotificationType,
)
from app.models.user import User
from app.services.notification_service import NotificationService

router = APIRouter()


class CreateNotificationRequest(BaseModel):
    user_id: Optional[int] = None
    notification_type: str
    data: Dict[str, Any]
    channels: Optional[List[str]] = None
    priority: str = "normal"
    href: Optional[str] = None
    group_key: Optional[str] = None


class BatchNotificationRequest(BaseModel):
    user_ids: List[int]
    notification_type: str
    data: Dict[str, Any]
    batch_size: int = 100
    delay_minutes: int = 5


class PreferenceUpdateRequest(BaseModel):
    notification_type: str
    in_app_enabled: bool = True
    email_enabled: bool = True
    sms_enabled: bool = False
    push_enabled: bool = False
    frequency: str = "immediate"


@router.post("/notifications/create")
async def create_facebook_style_notification(
    request: CreateNotificationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a Facebook-style notification with enhanced features"""
    service = NotificationService(db)

    # Convert channels
    channels = []
    if request.channels:
        for channel_str in request.channels:
            try:
                channels.append(NotificationChannel(channel_str))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid channel: {channel_str}",
                )

    try:
        notification = await service.create_notification(
            user_id=request.user_id,
            notification_type=NotificationType(request.notification_type),
            data=request.data,
            channels=channels or None,
            priority=NotificationPriority(request.priority),
            href=request.href,
            group_key=request.group_key,
        )

        return {
            "success": True,
            "notification": notification.to_dict(),
            "message": "Facebook-style notification created successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/notifications/batch")
async def create_batch_notifications(
    request: BatchNotificationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create batched notifications for multiple users"""
    service = NotificationService(db)

    try:
        batch_id = await service.create_batched_notification(
            user_ids=request.user_ids,
            notification_type=NotificationType(request.notification_type),
            data=request.data,
            batch_size=request.batch_size,
            delay_minutes=request.delay_minutes,
        )

        return {
            "success": True,
            "batch_id": batch_id,
            "user_count": len(request.user_ids),
            "message": "Batch notifications queued successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/notifications/aggregated/{group_key}")
async def get_aggregated_notifications(
    group_key: str,
    max_age_hours: int = 24,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get Facebook-style aggregated notifications"""
    service = NotificationService(db)

    aggregated = await service.aggregate_notifications(
        user_id=current_user.id, group_key=group_key, max_age_hours=max_age_hours
    )

    return {
        "success": True,
        "aggregated_notification": aggregated,
        "group_key": group_key,
    }


@router.post("/notifications/preferences")
async def update_notification_preferences(
    request: PreferenceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update user notification preferences"""
    service = NotificationService(db)

    preferences = {
        "in_app_enabled": request.in_app_enabled,
        "email_enabled": request.email_enabled,
        "sms_enabled": request.sms_enabled,
        "push_enabled": request.push_enabled,
        "frequency": request.frequency,
    }

    try:
        updated_pref = await service.set_user_preferences(
            user_id=current_user.id,
            notification_type=NotificationType(request.notification_type),
            preferences=preferences,
        )

        return {
            "success": True,
            "preferences": {
                "notification_type": updated_pref.notification_type.value,
                "in_app_enabled": updated_pref.in_app_enabled,
                "email_enabled": updated_pref.email_enabled,
                "sms_enabled": updated_pref.sms_enabled,
                "push_enabled": updated_pref.push_enabled,
                "frequency": updated_pref.frequency.value,
            },
            "message": "Preferences updated successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/notifications/analytics")
async def get_notification_analytics(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get Facebook-style notification analytics"""
    service = NotificationService(db)

    analytics = await service.get_notification_analytics(
        user_id=current_user.id, days=days
    )

    return {"success": True, "analytics": analytics}


@router.post("/scholarships/notify-new")
async def notify_new_scholarship_demo(
    scholarship_data: Dict[str, Any],
    user_ids: List[int],
    use_batching: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Demo: Notify users about new scholarship opportunities"""
    service = NotificationService(db)

    result = await service.notify_new_scholarship_available(
        user_ids=user_ids, scholarship_data=scholarship_data, use_batching=use_batching
    )

    if isinstance(result, str):
        # Batched
        return {
            "success": True,
            "batch_id": result,
            "message": f"Batched notifications queued for {len(user_ids)} users",
        }
    else:
        # Individual notifications
        return {
            "success": True,
            "notifications_created": len(result),
            "message": f"Individual notifications sent to {len(user_ids)} users",
        }


@router.post("/applications/batch-status-updates")
async def batch_application_status_updates_demo(
    application_updates: List[Dict[str, Any]],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Demo: Send batched application status updates"""
    service = NotificationService(db)

    result = await service.notify_application_batch_updates(application_updates)

    return {
        "success": True,
        "statistics": result,
        "message": "Batch application status updates processed",
    }


@router.post("/queue/process")
async def process_notification_queue_demo(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """Demo: Process notification queue (normally a background task)"""
    service = NotificationService(db)

    result = await service.process_notification_queue()

    return {
        "success": True,
        "processing_result": result,
        "message": "Notification queue processed",
    }
