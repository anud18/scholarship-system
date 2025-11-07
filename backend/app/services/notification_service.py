"""
Facebook-style notification service for creating and managing user notifications
"""

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import and_, desc
from sqlalchemy import func as sa_func
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationPriority,
    NotificationQueue,
    NotificationRead,
    NotificationTemplate,
    NotificationType,
)

func: Any = sa_func

logger = logging.getLogger(__name__)


class NotificationService:
    """Facebook-style notification service with real-time delivery, batching, and preferences"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._websocket_connections: Dict[int, List] = defaultdict(list)  # user_id -> [websocket_connections]
        self._notification_cache: Dict[str, Any] = {}  # Redis-like cache simulation

    # === Facebook-style Enhanced Methods === #

    async def create_notification(
        self,
        user_id: Optional[int],
        notification_type: NotificationType,
        data: Dict[str, Any],
        channels: Optional[List[NotificationChannel]] = None,
        priority: NotificationPriority = NotificationPriority.normal,
        href: Optional[str] = None,
        group_key: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ) -> Notification:
        """
        Create Facebook-style notification with enhanced features

        Args:
            user_id: Target user ID (None for system announcements)
            notification_type: Type of notification
            data: Flexible data payload
            channels: Delivery channels (defaults to user preferences)
            priority: Notification priority
            href: Click-through URL
            group_key: For grouping similar notifications
            scheduled_for: Schedule for later delivery
            expires_at: Expiration time
        """
        # Use template if available
        template = await self._get_notification_template(notification_type)
        if template and template.is_active:
            rendered = template.render(data)
            title = rendered["title"]
            message = rendered["message"]
            href = href or rendered["href"]
        else:
            # Fallback to data fields
            title = data.get("title", f"Notification: {notification_type.value}")
            message = data.get("message", "You have a new notification")

        # Set default channels based on user preferences
        if channels is None:
            channels = await self._get_user_preferred_channels(user_id, notification_type)

        # Create notification with enhanced fields
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            channel=channels[0] if channels else NotificationChannel.in_app,  # Primary channel
            data=data,
            href=href,
            group_key=group_key,
            scheduled_for=scheduled_for,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)

        # Handle real-time delivery if not scheduled
        if not scheduled_for:
            await self._deliver_notification(notification, channels)

        return notification

    async def create_batched_notification(
        self,
        user_ids: List[int],
        notification_type: NotificationType,
        data: Dict[str, Any],
        batch_size: int = 100,
        delay_minutes: int = 5,
    ) -> str:
        """
        Create batched notifications for multiple users (Facebook-style)

        Args:
            user_ids: List of target user IDs
            notification_type: Type of notification
            data: Notification data
            batch_size: Size of each batch
            delay_minutes: Delay between batches

        Returns:
            batch_id: Unique batch identifier
        """
        batch_id = str(uuid.uuid4())
        scheduled_time = datetime.now(timezone.utc)

        # Split users into batches
        for i in range(0, len(user_ids), batch_size):
            batch_users = user_ids[i : i + batch_size]

            # Create queue entry for this batch
            queue_entry = NotificationQueue(
                user_id=batch_users[0],  # Representative user for the batch
                batch_id=batch_id,
                notification_type=notification_type,
                notifications_data={"user_ids": batch_users, "data": data},
                scheduled_for=scheduled_time + timedelta(minutes=delay_minutes * (i // batch_size)),
            )

            self.db.add(queue_entry)

        await self.db.commit()
        return batch_id

    async def add_websocket_connection(self, user_id: int, websocket):
        """Add WebSocket connection for real-time notifications"""
        self._websocket_connections[user_id].append(websocket)

    async def remove_websocket_connection(self, user_id: int, websocket):
        """Remove WebSocket connection"""
        if user_id in self._websocket_connections:
            if websocket in self._websocket_connections[user_id]:
                self._websocket_connections[user_id].remove(websocket)

    async def aggregate_notifications(self, user_id: int, group_key: str, max_age_hours: int = 24) -> Dict[str, Any]:
        """
        Aggregate notifications by group key (Facebook-style)

        Args:
            user_id: User ID
            group_key: Group key for aggregation
            max_age_hours: Maximum age of notifications to aggregate

        Returns:
            Aggregated notification data
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        query = (
            select(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.group_key == group_key,
                    Notification.created_at >= cutoff_time,
                    Notification.is_read.is_(False),
                )
            )
            .order_by(desc(Notification.created_at))
        )

        result = await self.db.execute(query)
        notifications = result.scalars().all()

        if not notifications:
            return {}

        # Group by type and aggregate
        type_counts = defaultdict(int)
        latest_notification = notifications[0]

        for notif in notifications:
            type_counts[notif.notification_type.value] += 1

        return {
            "id": f"agg_{group_key}_{user_id}",
            "type": "aggregated",
            "group_key": group_key,
            "count": len(notifications),
            "type_counts": dict(type_counts),
            "latest": latest_notification.to_dict(),
            "href": latest_notification.effective_href,
            "created_at": latest_notification.created_at.isoformat(),
            "is_aggregated": True,
        }

    async def set_user_preferences(
        self,
        user_id: int,
        notification_type: NotificationType,
        preferences: Dict[str, Any],
    ) -> NotificationPreference:
        """
        Set user notification preferences (Facebook-style granular control)

        Args:
            user_id: User ID
            notification_type: Type of notification
            preferences: Preference settings
        """
        # Check if preference exists
        query = select(NotificationPreference).where(
            and_(
                NotificationPreference.user_id == user_id,
                NotificationPreference.notification_type == notification_type,
            )
        )
        result = await self.db.execute(query)
        existing_pref = result.scalar_one_or_none()

        if existing_pref:
            # Update existing preference
            for key, value in preferences.items():
                if hasattr(existing_pref, key):
                    setattr(existing_pref, key, value)
            existing_pref.updated_at = datetime.now(timezone.utc)
        else:
            # Create new preference
            existing_pref = NotificationPreference(user_id=user_id, notification_type=notification_type, **preferences)
            self.db.add(existing_pref)

        await self.db.commit()
        await self.db.refresh(existing_pref)

        # Update cache
        cache_key = f"pref_{user_id}_{notification_type.value}"
        self._notification_cache[cache_key] = existing_pref

        return existing_pref

    async def process_notification_queue(self) -> Dict[str, int]:
        """
        Process pending notifications in queue (background task)

        Returns:
            Processing statistics
        """
        current_time = datetime.now(timezone.utc)

        # Get pending notifications ready for processing
        query = (
            select(NotificationQueue)
            .where(
                and_(
                    NotificationQueue.status == "pending",
                    NotificationQueue.scheduled_for <= current_time,
                    NotificationQueue.attempts < NotificationQueue.max_attempts,
                )
            )
            .order_by(NotificationQueue.priority, NotificationQueue.scheduled_for)
        )

        result = await self.db.execute(query)
        queue_items = result.scalars().all()

        processed = 0
        failed = 0

        for item in queue_items:
            try:
                item.status = "processing"
                item.attempts += 1
                await self.db.commit()

                # Process the batch
                user_ids = item.notifications_data["user_ids"]
                data = item.notifications_data["data"]

                for user_id in user_ids:
                    await self.create_notification(
                        user_id=user_id,
                        notification_type=item.notification_type,
                        data=data,
                        priority=item.priority,
                    )

                item.status = "sent"
                item.processed_at = current_time
                processed += 1

            except Exception as e:
                item.status = "failed"
                item.error_message = str(e)
                failed += 1

                # Retry logic
                if item.attempts < item.max_attempts:
                    item.status = "pending"
                    item.scheduled_for = current_time + timedelta(minutes=5 * item.attempts)

        await self.db.commit()

        return {"processed": processed, "failed": failed}

    async def _deliver_notification(self, notification: Notification, channels: List[NotificationChannel]):
        """Deliver notification through specified channels"""
        # Real-time WebSocket delivery
        if NotificationChannel.in_app in channels and notification.user_id:
            await self._send_websocket_notification(notification.user_id, notification.to_dict())

        # Email delivery (placeholder)
        if NotificationChannel.email in channels:
            await self._send_email_notification(notification)

        # SMS delivery (placeholder)
        if NotificationChannel.sms in channels:
            await self._send_sms_notification(notification)

        # Push notification delivery (placeholder)
        if NotificationChannel.push in channels:
            await self._send_push_notification(notification)

    async def _send_websocket_notification(self, user_id: int, notification_data: Dict[str, Any]):
        """Send notification via WebSocket to connected clients"""
        if user_id in self._websocket_connections:
            disconnected = []
            for websocket in self._websocket_connections[user_id]:
                try:
                    await websocket.send_text(json.dumps({"type": "notification", "data": notification_data}))
                except Exception:
                    disconnected.append(websocket)

            # Clean up disconnected websockets
            for ws in disconnected:
                self._websocket_connections[user_id].remove(ws)

    async def _send_email_notification(self, notification: Notification):
        """Send notification via email"""
        from app.core.config import settings

        # Check required SMTP configuration (host and from address)
        if not settings.smtp_host or not settings.email_from:
            logger.warning("SMTP basic configuration incomplete (host/from), skipping email notification")
            return

        if not notification.user:
            logger.warning(f"No user found for notification {notification.id}, skipping email")
            return

        if not notification.user.email:
            logger.warning(f"No email found for user {notification.user_id}, skipping email notification")
            return

        try:
            from fastapi_mail import ConnectionConfig, FastMail, MessageSchema

            # Configure email connection
            conf = ConnectionConfig(
                MAIL_USERNAME=settings.smtp_user,
                MAIL_PASSWORD=settings.smtp_password,
                MAIL_FROM=settings.email_from,
                MAIL_FROM_NAME=settings.email_from_name,
                MAIL_PORT=settings.smtp_port,
                MAIL_SERVER=settings.smtp_host,
                MAIL_STARTTLS=settings.smtp_use_tls,
                MAIL_SSL_TLS=False,
                USE_CREDENTIALS=True,
                VALIDATE_CERTS=True,
            )

            # Create email message
            message = MessageSchema(
                subject=notification.title or "NYCU Scholarship System Notification",
                recipients=[notification.user.email],
                body=f"""
                <html>
                <body>
                    <h2>{notification.title or 'Notification'}</h2>
                    <p>{notification.message}</p>

                    <hr>
                    <p style="color: gray; font-size: 12px;">
                        This is an automated message from NYCU Scholarship System.<br>
                        Please do not reply to this email.
                    </p>
                </body>
                </html>
                """,
                subtype="html",
            )

            # Send email
            fm = FastMail(conf)
            await fm.send_message(message)

            logger.info(f"Email notification sent to {notification.user.email} for notification {notification.id}")

        except Exception as e:
            logger.error(f"Failed to send email notification {notification.id}: {str(e)}")
            # Don't raise exception to avoid breaking the notification flow

    async def _send_sms_notification(self, notification: Notification):
        """Send notification via SMS (placeholder implementation)

        This is a placeholder implementation for SMS delivery.
        Can be extended in the future to integrate with SMS providers like Twilio, AWS SNS, etc.
        """
        pass

    async def _send_push_notification(self, notification: Notification):
        """Send push notification (placeholder implementation)

        This is a placeholder implementation for push notifications.
        Can be extended in the future to integrate with push services like FCM, OneSignal, etc.
        """
        pass

    async def _get_notification_template(self, notification_type: NotificationType) -> Optional[NotificationTemplate]:
        """Get notification template for type"""
        query = select(NotificationTemplate).where(
            and_(
                NotificationTemplate.type == notification_type,
                NotificationTemplate.is_active.is_(True),
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_user_preferred_channels(
        self, user_id: Optional[int], notification_type: NotificationType
    ) -> List[NotificationChannel]:
        """Get user's preferred delivery channels"""
        if not user_id:
            return [NotificationChannel.in_app]  # System announcements default to in-app

        # Check cache first
        cache_key = f"pref_{user_id}_{notification_type.value}"
        if cache_key in self._notification_cache:
            pref = self._notification_cache[cache_key]
        else:
            query = select(NotificationPreference).where(
                and_(
                    NotificationPreference.user_id == user_id,
                    NotificationPreference.notification_type == notification_type,
                )
            )
            result = await self.db.execute(query)
            pref = result.scalar_one_or_none()

            if pref:
                self._notification_cache[cache_key] = pref

        if not pref:
            return [NotificationChannel.in_app]  # Default

        channels = []
        if pref.in_app_enabled:
            channels.append(NotificationChannel.in_app)
        if pref.email_enabled:
            channels.append(NotificationChannel.email)
        if pref.sms_enabled:
            channels.append(NotificationChannel.sms)
        if pref.push_enabled:
            channels.append(NotificationChannel.push)

        return channels or [NotificationChannel.in_app]  # Fallback

    # === Legacy Methods (Enhanced for backward compatibility) === #

    async def createUserNotification(
        self,
        user_id: int,
        title: str,
        message: str,
        title_en: Optional[str] = None,
        message_en: Optional[str] = None,
        notification_type: NotificationType = NotificationType.info,
        priority: NotificationPriority = NotificationPriority.normal,
        related_resource_type: Optional[str] = None,
        related_resource_id: Optional[int] = None,
        action_url: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Notification:
        """
        創建個人通知

        Args:
            user_id: 用戶ID
            title: 通知標題
            message: 通知內容
            title_en: 英文標題（可選）
            message_en: 英文內容（可選）
            notification_type: 通知類型
            priority: 優先級
            related_resource_type: 相關資源類型
            related_resource_id: 相關資源ID
            action_url: 行動連結
            expires_at: 過期時間
            metadata: 額外資料

        Returns:
            Notification: 創建的通知對象
        """
        notification = Notification(
            user_id=user_id,
            title=title,
            title_en=title_en,
            message=message,
            message_en=message_en,
            notification_type=notification_type,
            priority=priority,
            related_resource_type=related_resource_type,
            related_resource_id=related_resource_id,
            action_url=action_url,
            expires_at=expires_at,
            meta_data=metadata,
        )

        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)

        return notification

    async def createSystemAnnouncement(
        self,
        title: str,
        message: str,
        title_en: Optional[str] = None,
        message_en: Optional[str] = None,
        notification_type: NotificationType = NotificationType.info,
        priority: NotificationPriority = NotificationPriority.normal,
        action_url: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Notification:
        """
        創建系統公告（所有用戶可見）

        Args:
            title: 公告標題
            message: 公告內容
            title_en: 英文標題（可選）
            message_en: 英文內容（可選）
            notification_type: 通知類型
            priority: 優先級
            action_url: 行動連結
            expires_at: 過期時間
            metadata: 額外資料

        Returns:
            Notification: 創建的通知對象
        """
        notification = Notification(
            user_id=None,  # 系統公告設置為 None
            title=title,
            title_en=title_en,
            message=message,
            message_en=message_en,
            notification_type=notification_type,
            priority=priority,
            related_resource_type="system",
            action_url=action_url,
            expires_at=expires_at,
            meta_data=metadata,
        )

        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)

        return notification

    async def notifyApplicationStatusChange(
        self,
        user_id: int,
        application_id: int,
        new_status: str,
        application_title: str = "獎學金申請",
    ) -> Notification:
        """
        通知申請狀態變更

        Args:
            user_id: 申請人ID
            application_id: 申請ID
            new_status: 新狀態
            application_title: 申請標題

        Returns:
            Notification: 創建的通知對象
        """
        status_messages = {
            "under_review": {
                "zh": f"您的{application_title}正在審核中",
                "en": f"Your {application_title} is under review",
            },
            "approved": {
                "zh": f"恭喜！您的{application_title}已獲得核准",
                "en": f"Congratulations! Your {application_title} has been approved",
            },
            "rejected": {
                "zh": f"很抱歉，您的{application_title}未獲得核准",
                "en": f"We regret to inform you that your {application_title} was not approved",
            },
        }

        message_data = status_messages.get(
            new_status,
            {
                "zh": f"您的{application_title}狀態已更新",
                "en": f"Your {application_title} status has been updated",
            },
        )

        notification_type = NotificationType.success if new_status == "approved" else NotificationType.info
        priority = NotificationPriority.high if new_status in ["approved", "rejected"] else NotificationPriority.normal

        # Enhanced: Use new Facebook-style notification system
        return await self.create_notification(
            user_id=user_id,
            notification_type=notification_type,
            data={
                "title": f"{application_title}狀態更新",
                "title_en": f"{application_title} Status Update",
                "message": message_data["zh"],
                "message_en": message_data["en"],
                "application_id": application_id,
                "status": new_status,
                "application_title": application_title,
            },
            href=f"/applications/{application_id}",
            group_key=f"application_{application_id}",
            priority=priority,
        )

    async def notifyDocumentRequired(
        self,
        user_id: int,
        application_id: int,
        required_documents: List[str],
        deadline: Optional[datetime] = None,
    ) -> Notification:
        """
        通知需要補充文件

        Args:
            user_id: 申請人ID
            application_id: 申請ID
            required_documents: 需要的文件列表
            deadline: 截止時間

        Returns:
            Notification: 創建的通知對象
        """
        doc_list = "、".join(required_documents)
        deadline_text = f"，請於 {deadline.strftime('%Y/%m/%d')} 前上傳" if deadline else ""

        message = f"您的獎學金申請需要補充以下文件：{doc_list}{deadline_text}"
        message_en = f"Your scholarship application requires the following documents: {', '.join(required_documents)}"

        if deadline:
            message_en += f". Please upload by {deadline.strftime('%Y/%m/%d')}"

        return await self.createUserNotification(
            user_id=user_id,
            title="申請文件補充通知",
            title_en="Document Requirement Notification",
            message=message,
            message_en=message_en,
            notification_type=NotificationType.warning,
            priority=NotificationPriority.high,
            related_resource_type="application",
            related_resource_id=application_id,
            action_url=f"/applications/{application_id}/documents",
            expires_at=deadline,
            metadata={
                "application_id": application_id,
                "required_documents": required_documents,
                "deadline": deadline.isoformat() if deadline else None,
            },
        )

    async def notifyDeadlineReminder(
        self,
        user_id: int,
        title: str,
        title_en: Optional[str] = None,
        deadline: datetime = None,
        action_url: Optional[str] = None,
    ) -> Notification:
        """
        發送截止日期提醒

        Args:
            user_id: 用戶ID
            title: 提醒標題
            title_en: 英文標題
            deadline: 截止時間
            action_url: 行動連結

        Returns:
            Notification: 創建的通知對象
        """
        days_left = (deadline - datetime.now()).days if deadline else 0

        if days_left > 1:
            message = f"{title}的截止日期將在 {days_left} 天後到期"
            message_en = f"The deadline for {title_en or title} is in {days_left} days"
        elif days_left == 1:
            message = f"{title}的截止日期將在明天到期"
            message_en = f"The deadline for {title_en or title} is tomorrow"
        else:
            message = f"{title}的截止日期已到期"
            message_en = f"The deadline for {title_en or title} has passed"

        priority = NotificationPriority.urgent if days_left <= 1 else NotificationPriority.high

        return await self.createUserNotification(
            user_id=user_id,
            title=f"截止日期提醒：{title}",
            title_en=f"Deadline Reminder: {title_en or title}",
            message=message,
            message_en=message_en,
            notification_type=NotificationType.reminder,
            priority=priority,
            action_url=action_url,
            expires_at=deadline + timedelta(days=7) if deadline else None,  # 過期後7天自動清理
            metadata={
                "reminder_type": "deadline",
                "deadline": deadline.isoformat() if deadline else None,
                "days_left": days_left,
            },
        )

    async def bulkNotifyUsers(
        self,
        user_ids: List[int],
        title: str,
        message: str,
        title_en: Optional[str] = None,
        message_en: Optional[str] = None,
        notification_type: NotificationType = NotificationType.info,
        priority: NotificationPriority = NotificationPriority.normal,
        action_url: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Notification]:
        """
        批量發送通知給多個用戶

        Args:
            user_ids: 用戶ID列表
            title: 通知標題
            message: 通知內容
            其他參數與 createUserNotification 相同

        Returns:
            List[Notification]: 創建的通知對象列表
        """
        notifications = []

        for user_id in user_ids:
            notification = Notification(
                user_id=user_id,
                title=title,
                title_en=title_en,
                message=message,
                message_en=message_en,
                notification_type=notification_type,
                priority=priority,
                action_url=action_url,
                expires_at=expires_at,
                meta_data=metadata,
            )
            notifications.append(notification)

        self.db.add_all(notifications)
        await self.db.commit()

        # 刷新所有對象
        for notification in notifications:
            await self.db.refresh(notification)

        return notifications

    # === 按用戶已讀狀態管理 === #

    async def getUserNotifications(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        獲取用戶的所有通知（個人通知 + 系統公告）及其已讀狀態

        Args:
            user_id: 用戶ID
            skip: 跳過數量
            limit: 限制數量
            unread_only: 只返回未讀通知
            notification_type: 通知類型過濾

        Returns:
            List[Dict]: 包含通知資料和已讀狀態的字典列表
        """
        from sqlalchemy import and_, desc

        # 構建基礎查詢 - 獲取個人通知和系統公告
        base_query = select(Notification).where(
            or_(
                Notification.user_id == user_id,  # 個人通知
                Notification.user_id.is_(None),  # 系統公告
            )
        )

        # 添加類型過濾
        if notification_type:
            base_query = base_query.where(Notification.notification_type == notification_type)

        # 添加過期過濾
        base_query = base_query.where(
            or_(
                Notification.expires_at.is_(None),
                Notification.expires_at > datetime.now(),
            )
        )

        # 如果只要未讀通知，需要複雜的查詢
        if unread_only:
            # 子查詢：獲取已讀的通知ID
            read_subquery = select(NotificationRead.notification_id).where(NotificationRead.user_id == user_id)

            base_query = base_query.where(
                and_(
                    # 個人通知未讀 OR 系統公告未讀
                    or_(
                        and_(
                            Notification.user_id == user_id,
                            Notification.is_read.is_(False),
                        ),
                        and_(
                            Notification.user_id.is_(None),
                            ~Notification.id.in_(read_subquery),
                        ),
                    )
                )
            )

        # 添加排序和分頁 - simplified to avoid enum comparison issues
        query = base_query.order_by(desc(Notification.created_at)).offset(skip).limit(limit)

        result = await self.db.execute(query)
        notifications = result.scalars().all()

        # 獲取用戶的已讀記錄
        read_query = select(NotificationRead).where(
            and_(
                NotificationRead.user_id == user_id,
                NotificationRead.notification_id.in_([n.id for n in notifications]),
            )
        )
        read_result = await self.db.execute(read_query)
        read_records = {r.notification_id: r for r in read_result.scalars().all()}

        # 組合結果
        result_list = []
        for notification in notifications:
            # 確定已讀狀態
            if notification.user_id == user_id:
                # 個人通知使用原有邏輯
                is_read = notification.is_read
                read_at = notification.read_at
            else:
                # 系統公告使用NotificationRead記錄
                read_record = read_records.get(notification.id)
                is_read = read_record is not None
                read_at = read_record.read_at if read_record else None

            result_list.append(
                {
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
                    "is_read": is_read,
                    "is_dismissed": notification.is_dismissed,
                    "scheduled_at": notification.scheduled_at,
                    "expires_at": notification.expires_at,
                    "read_at": read_at,
                    "created_at": notification.created_at,
                    "metadata": notification.meta_data,
                }
            )

        return result_list

    async def getUnreadNotificationCount(self, user_id: int) -> int:
        """
        獲取用戶未讀通知數量

        Args:
            user_id: 用戶ID

        Returns:
            int: 未讀通知數量
        """
        from sqlalchemy import and_

        # 個人通知未讀數量
        personal_query = select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.now(),
                ),
            )
        )

        # 系統公告未讀數量（未在NotificationRead中的）
        read_subquery = select(NotificationRead.notification_id).where(NotificationRead.user_id == user_id)

        system_query = select(func.count(Notification.id)).where(
            and_(
                Notification.user_id.is_(None),
                ~Notification.id.in_(read_subquery),
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.now(),
                ),
            )
        )

        personal_result = await self.db.execute(personal_query)
        system_result = await self.db.execute(system_query)

        personal_count = personal_result.scalar() or 0
        system_count = system_result.scalar() or 0

        return personal_count + system_count

    async def markNotificationAsRead(self, notification_id: int, user_id: int) -> bool:
        """
        標記通知為已讀

        Args:
            notification_id: 通知ID
            user_id: 用戶ID

        Returns:
            bool: 操作是否成功
        """
        # 獲取通知
        query = select(Notification).where(Notification.id == notification_id)
        result = await self.db.execute(query)
        notification = result.scalar_one_or_none()

        if not notification:
            return False

        if notification.user_id == user_id:
            # 個人通知直接更新
            notification.mark_as_read()
            await self.db.commit()
        elif notification.user_id is None:
            # 系統公告創建或更新NotificationRead記錄
            read_query = select(NotificationRead).where(
                and_(
                    NotificationRead.notification_id == notification_id,
                    NotificationRead.user_id == user_id,
                )
            )
            read_result = await self.db.execute(read_query)
            read_record = read_result.scalar_one_or_none()

            if not read_record:
                # 創建新的已讀記錄
                read_record = NotificationRead(notification_id=notification_id, user_id=user_id)
                self.db.add(read_record)
                await self.db.commit()

        return True

    async def markAllNotificationsAsRead(self, user_id: int) -> int:
        """
        標記用戶的所有通知為已讀

        Args:
            user_id: 用戶ID

        Returns:
            int: 標記為已讀的通知數量
        """
        from sqlalchemy import and_

        # 標記個人通知為已讀
        personal_update = (
            update(Notification)
            .where(and_(Notification.user_id == user_id, Notification.is_read.is_(False)))
            .values(is_read=True, read_at=datetime.now())
        )

        personal_result = await self.db.execute(personal_update)
        personal_updated = personal_result.rowcount

        # 獲取用戶未讀的系統公告
        read_subquery = select(NotificationRead.notification_id).where(NotificationRead.user_id == user_id)

        system_query = select(Notification.id).where(
            and_(
                Notification.user_id.is_(None),
                ~Notification.id.in_(read_subquery),
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.now(),
                ),
            )
        )

        system_result = await self.db.execute(system_query)
        system_notification_ids = [row[0] for row in system_result.fetchall()]

        # 為系統公告創建已讀記錄
        system_updated = 0
        if system_notification_ids:
            read_records = [NotificationRead(notification_id=nid, user_id=user_id) for nid in system_notification_ids]
            self.db.add_all(read_records)
            system_updated = len(read_records)

        await self.db.commit()
        return personal_updated + system_updated

    # === Facebook-style Scholarship-Specific Methods === #

    async def notify_new_scholarship_available(
        self,
        user_ids: List[int],
        scholarship_data: Dict[str, Any],
        use_batching: bool = True,
    ) -> Union[str, List[Notification]]:
        """
        Notify users about new scholarship opportunities (Facebook-style)

        Args:
            user_ids: List of eligible user IDs
            scholarship_data: Scholarship information
            use_batching: Whether to use batched delivery

        Returns:
            batch_id if batching enabled, otherwise list of notifications
        """
        notification_type = NotificationType.new_scholarship_available
        data = {
            "title": f"新獎學金機會：{scholarship_data['name']}",
            "title_en": f"New Scholarship Opportunity: {scholarship_data['name']}",
            "message": f"符合您條件的獎學金現已開放申請：{scholarship_data['name']}",
            "message_en": f"A scholarship matching your profile is now available: {scholarship_data['name']}",
            "scholarship_id": scholarship_data["id"],
            "scholarship_name": scholarship_data["name"],
            "deadline": scholarship_data.get("application_deadline"),
            "amount": scholarship_data.get("amount"),
        }

        if use_batching and len(user_ids) > 50:
            return await self.create_batched_notification(
                user_ids=user_ids,
                notification_type=notification_type,
                data=data,
                batch_size=100,
                delay_minutes=2,
            )
        else:
            notifications = []
            for user_id in user_ids:
                notification = await self.create_notification(
                    user_id=user_id,
                    notification_type=notification_type,
                    data=data,
                    href=f"/scholarships/{scholarship_data['id']}",
                    group_key="new_scholarships",
                    priority=NotificationPriority.high,
                )
                notifications.append(notification)
            return notifications

    async def notify_application_batch_updates(self, application_updates: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Send batched application status updates (Facebook-style aggregation)

        Args:
            application_updates: List of {user_id, application_id, status, ...}

        Returns:
            Statistics about notifications sent
        """
        # Group updates by user
        user_updates = defaultdict(list)
        for application_update in application_updates:
            user_updates[application_update["user_id"]].append(application_update)

        notifications_sent = 0
        aggregated_notifications = 0

        for user_id, updates in user_updates.items():
            if len(updates) == 1:
                # Single update - send individual notification
                first_update = updates[0]
                await self.notifyApplicationStatusChange(
                    user_id=user_id,
                    application_id=first_update["application_id"],
                    new_status=first_update["status"],
                    application_title=first_update.get("application_title", "獎學金申請"),
                )
                notifications_sent += 1
            else:
                # Multiple updates - send aggregated notification
                approved_count = sum(1 for u in updates if u["status"] == "approved")
                rejected_count = sum(1 for u in updates if u["status"] == "rejected")

                if approved_count > 0 and rejected_count == 0:
                    title = f"獎學金申請結果通知 - {approved_count} 項申請獲得核准"
                    message = f"恭喜！您有 {approved_count} 項獎學金申請已獲得核准"
                    notification_type = NotificationType.application_approved
                elif rejected_count > 0 and approved_count == 0:
                    title = f"獎學金申請結果通知 - {rejected_count} 項申請"
                    message = f"您有 {rejected_count} 項獎學金申請的審核結果已出爐"
                    notification_type = NotificationType.application_rejected
                else:
                    title = f"獎學金申請結果通知 - {len(updates)} 項申請"
                    message = f"您有 {len(updates)} 項獎學金申請的審核結果已出爐（核准：{approved_count}，其他：{rejected_count}）"
                    notification_type = NotificationType.info

                await self.create_notification(
                    user_id=user_id,
                    notification_type=notification_type,
                    data={
                        "title": title,
                        "message": message,
                        "updates": updates,
                        "approved_count": approved_count,
                        "rejected_count": rejected_count,
                        "total_count": len(updates),
                    },
                    href="/applications",
                    group_key="application_results",
                    priority=NotificationPriority.high,
                )
                aggregated_notifications += 1

        return {
            "individual_notifications": notifications_sent,
            "aggregated_notifications": aggregated_notifications,
            "total_users": len(user_updates),
        }

    async def notify_deadline_reminders_batch(self, deadline_data: List[Dict[str, Any]], days_before: int = 3) -> str:
        """
        Send batched deadline reminders (Facebook-style)

        Args:
            deadline_data: List of deadline information
            days_before: Days before deadline to send reminder

        Returns:
            batch_id for tracking
        """
        reminder_time = datetime.now(timezone.utc) + timedelta(hours=1)  # Send in 1 hour
        user_deadlines = defaultdict(list)

        # Group deadlines by user
        for item in deadline_data:
            user_deadlines[item["user_id"]].append(item)

        notifications_data = []
        for user_id, deadlines in user_deadlines.items():
            if len(deadlines) == 1:
                # Single deadline
                deadline = deadlines[0]
                data = {
                    "title": f"截止日期提醒：{deadline['title']}",
                    "message": f"{deadline['title']}將在 {days_before} 天後截止",
                    "deadline_id": deadline["id"],
                    "deadline_date": deadline["deadline"].isoformat(),
                    "days_left": days_before,
                }
            else:
                # Multiple deadlines - aggregate
                data = {
                    "title": f"截止日期提醒 - {len(deadlines)} 項事項",
                    "message": f"您有 {len(deadlines)} 項事項即將截止",
                    "deadlines": deadlines,
                    "count": len(deadlines),
                }

            notifications_data.append({"user_id": user_id, "data": data})

        # Create batched notifications
        batch_id = str(uuid.uuid4())
        for i, notif_data in enumerate(notifications_data):
            queue_entry = NotificationQueue(
                user_id=notif_data["user_id"],
                batch_id=batch_id,
                notification_type=NotificationType.deadline_approaching,
                notifications_data={
                    "user_ids": [notif_data["user_id"]],
                    "data": notif_data["data"],
                },
                scheduled_for=reminder_time + timedelta(seconds=30 * i),  # Stagger by 30 seconds
                priority=NotificationPriority.high,
            )
            self.db.add(queue_entry)

        await self.db.commit()
        return batch_id

    async def get_notification_analytics(self, user_id: Optional[int] = None, days: int = 30) -> Dict[str, Any]:
        """
        Get Facebook-style notification analytics

        Args:
            user_id: Specific user (None for system-wide)
            days: Number of days to analyze

        Returns:
            Analytics data
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        base_query = select(Notification).where(Notification.created_at >= start_date)
        if user_id:
            base_query = base_query.where(Notification.user_id == user_id)

        result = await self.db.execute(base_query)
        notifications = result.scalars().all()

        # Analyze data
        total_notifications = len(notifications)
        read_notifications = sum(1 for n in notifications if n.is_read)
        unread_notifications = total_notifications - read_notifications

        # Group by type
        type_counts = defaultdict(int)
        priority_counts = defaultdict(int)
        channel_counts = defaultdict(int)

        for notif in notifications:
            type_counts[notif.notification_type.value] += 1
            priority_counts[notif.priority.value] += 1
            channel_counts[notif.channel.value] += 1

        # Calculate engagement rate
        engagement_rate = (read_notifications / total_notifications * 100) if total_notifications > 0 else 0

        return {
            "period_days": days,
            "total_notifications": total_notifications,
            "read_notifications": read_notifications,
            "unread_notifications": unread_notifications,
            "engagement_rate": round(engagement_rate, 2),
            "type_breakdown": dict(type_counts),
            "priority_breakdown": dict(priority_counts),
            "channel_breakdown": dict(channel_counts),
            "user_id": user_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
