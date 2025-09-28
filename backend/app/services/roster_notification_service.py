"""
造冊相關通知服務
Roster-specific notification service
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.notification import NotificationPriority, NotificationType
from app.models.payment_roster import PaymentRoster, RosterStatus
from app.models.user import User, UserRole
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class RosterNotificationService:
    """
    造冊相關通知服務

    整合現有的 NotificationService，專門處理造冊相關的通知：
    - 造冊產生通知
    - 造冊完成通知
    - 造冊錯誤通知
    - 造冊狀態變更通知
    """

    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

    async def notify_roster_generated(self, roster: PaymentRoster, notify_roles: List[UserRole] = None) -> List[int]:
        """
        通知造冊已產生

        Args:
            roster: 造冊物件
            notify_roles: 要通知的角色清單

        Returns:
            List[int]: 已發送通知的使用者ID清單
        """
        if notify_roles is None:
            notify_roles = [UserRole.admin, UserRole.processor]

        try:
            # 取得要通知的使用者
            target_users = self._get_users_by_roles(notify_roles)

            if not target_users:
                logger.warning("No users found for roster generation notification")
                return []

            # 準備通知資料
            notification_data = {
                "title": f"造冊已產生：{roster.roster_code}",
                "title_en": f"Roster Generated: {roster.roster_code}",
                "message": f"系統已產生造冊 {roster.roster_code}，期間：{roster.period_label}，合格人數：{roster.qualified_count}",
                "message_en": f"Roster {roster.roster_code} has been generated for period {roster.period_label} with {roster.qualified_count} qualified recipients",
                "roster_id": roster.id,
                "roster_code": roster.roster_code,
                "period_label": roster.period_label,
                "qualified_count": roster.qualified_count,
                "total_amount": str(roster.total_amount),
                "generated_at": roster.created_at.isoformat(),
            }

            # 發送通知給每個使用者
            notified_users = []
            for user in target_users:
                try:
                    await self.notification_service.createUserNotification(
                        user_id=user.id,
                        title=notification_data["title"],
                        title_en=notification_data["title_en"],
                        message=notification_data["message"],
                        message_en=notification_data["message_en"],
                        notification_type=NotificationType.INFO,
                        priority=NotificationPriority.NORMAL,
                        related_resource_type="roster",
                        related_resource_id=roster.id,
                        action_url=f"/admin/rosters/{roster.id}",
                        metadata=notification_data,
                    )
                    notified_users.append(user.id)
                except Exception as e:
                    logger.error(f"Failed to send roster generation notification to user {user.id}: {e}")

            logger.info(
                f"Roster generation notification sent to {len(notified_users)} users for roster {roster.roster_code}"
            )
            return notified_users

        except Exception as e:
            logger.error(f"Failed to send roster generation notifications for roster {roster.id}: {e}")
            return []

    async def notify_roster_completed(
        self, roster: PaymentRoster, statistics: Dict[str, Any], notify_roles: List[UserRole] = None
    ) -> List[int]:
        """
        通知造冊處理完成

        Args:
            roster: 造冊物件
            statistics: 統計資料
            notify_roles: 要通知的角色清單

        Returns:
            List[int]: 已發送通知的使用者ID清單
        """
        if notify_roles is None:
            notify_roles = [UserRole.admin, UserRole.processor]

        try:
            target_users = self._get_users_by_roles(notify_roles)

            if not target_users:
                logger.warning("No users found for roster completion notification")
                return []

            notification_data = {
                "title": f"造冊處理完成：{roster.roster_code}",
                "title_en": f"Roster Processing Completed: {roster.roster_code}",
                "message": f"造冊 {roster.roster_code} 已完成處理。合格：{statistics.get('qualified_count', 0)} 人，總金額：NT$ {statistics.get('total_amount', 0)}",
                "message_en": f"Roster {roster.roster_code} processing completed. Qualified: {statistics.get('qualified_count', 0)}, Total amount: NT$ {statistics.get('total_amount', 0)}",
                "roster_id": roster.id,
                "roster_code": roster.roster_code,
                "statistics": statistics,
                "completed_at": datetime.now().isoformat(),
            }

            notified_users = []
            for user in target_users:
                try:
                    await self.notification_service.createUserNotification(
                        user_id=user.id,
                        title=notification_data["title"],
                        title_en=notification_data["title_en"],
                        message=notification_data["message"],
                        message_en=notification_data["message_en"],
                        notification_type=NotificationType.SUCCESS,
                        priority=NotificationPriority.NORMAL,
                        related_resource_type="roster",
                        related_resource_id=roster.id,
                        action_url=f"/admin/rosters/{roster.id}",
                        metadata=notification_data,
                    )
                    notified_users.append(user.id)
                except Exception as e:
                    logger.error(f"Failed to send roster completion notification to user {user.id}: {e}")

            logger.info(
                f"Roster completion notification sent to {len(notified_users)} users for roster {roster.roster_code}"
            )
            return notified_users

        except Exception as e:
            logger.error(f"Failed to send roster completion notifications for roster {roster.id}: {e}")
            return []

    async def notify_roster_error(self, error_data: Dict[str, Any], notify_roles: List[UserRole] = None) -> List[int]:
        """
        通知造冊處理錯誤

        Args:
            error_data: 錯誤資料
            notify_roles: 要通知的角色清單

        Returns:
            List[int]: 已發送通知的使用者ID清單
        """
        if notify_roles is None:
            notify_roles = [UserRole.admin]

        try:
            target_users = self._get_users_by_roles(notify_roles)

            if not target_users:
                logger.warning("No users found for roster error notification")
                return []

            notification_data = {
                "title": f"造冊處理錯誤：{error_data.get('config_name', 'Unknown')}",
                "title_en": f"Roster Processing Error: {error_data.get('config_name', 'Unknown')}",
                "message": f"造冊處理過程中發生錯誤，需要人工介入。配置：{error_data.get('config_name', 'N/A')}，錯誤：{error_data.get('error', 'Unknown error')}",
                "message_en": f"An error occurred during roster processing requiring manual intervention. Config: {error_data.get('config_name', 'N/A')}, Error: {error_data.get('error', 'Unknown error')}",
                "error_data": error_data,
                "error_time": datetime.now().isoformat(),
            }

            notified_users = []
            for user in target_users:
                try:
                    await self.notification_service.createUserNotification(
                        user_id=user.id,
                        title=notification_data["title"],
                        title_en=notification_data["title_en"],
                        message=notification_data["message"],
                        message_en=notification_data["message_en"],
                        notification_type=NotificationType.ERROR,
                        priority=NotificationPriority.CRITICAL,
                        related_resource_type="roster_error",
                        related_resource_id=error_data.get("config_id"),
                        action_url="/admin/rosters",
                        metadata=notification_data,
                    )
                    notified_users.append(user.id)
                except Exception as e:
                    logger.error(f"Failed to send roster error notification to user {user.id}: {e}")

            logger.info(f"Roster error notification sent to {len(notified_users)} users")
            return notified_users

        except Exception as e:
            logger.error(f"Failed to send roster error notifications: {e}")
            return []

    async def notify_roster_status_changed(
        self,
        roster: PaymentRoster,
        old_status: RosterStatus,
        new_status: RosterStatus,
        changed_by_user_id: int,
        notify_roles: List[UserRole] = None,
    ) -> List[int]:
        """
        通知造冊狀態變更

        Args:
            roster: 造冊物件
            old_status: 舊狀態
            new_status: 新狀態
            changed_by_user_id: 變更者使用者ID
            notify_roles: 要通知的角色清單

        Returns:
            List[int]: 已發送通知的使用者ID清單
        """
        if notify_roles is None:
            notify_roles = [UserRole.admin, UserRole.processor]

        try:
            target_users = self._get_users_by_roles(notify_roles)
            # 不通知變更者本人
            target_users = [user for user in target_users if user.id != changed_by_user_id]

            if not target_users:
                return []

            # 取得變更者資訊
            changed_by_user = self.db.query(User).filter(User.id == changed_by_user_id).first()
            changed_by_name = changed_by_user.name if changed_by_user else "Unknown"

            status_messages = {
                RosterStatus.PROCESSING: {"zh": "處理中", "en": "Processing"},
                RosterStatus.COMPLETED: {"zh": "已完成", "en": "Completed"},
                RosterStatus.LOCKED: {"zh": "已鎖定", "en": "Locked"},
                RosterStatus.FAILED: {"zh": "處理失敗", "en": "Failed"},
            }

            old_status_text = status_messages.get(old_status, {"zh": old_status.value, "en": old_status.value})
            new_status_text = status_messages.get(new_status, {"zh": new_status.value, "en": new_status.value})

            notification_data = {
                "title": f"造冊狀態變更：{roster.roster_code}",
                "title_en": f"Roster Status Changed: {roster.roster_code}",
                "message": f"造冊 {roster.roster_code} 的狀態已由「{old_status_text['zh']}」變更為「{new_status_text['zh']}」（變更者：{changed_by_name}）",
                "message_en": f"Roster {roster.roster_code} status changed from '{old_status_text['en']}' to '{new_status_text['en']}' (Changed by: {changed_by_name})",
                "roster_id": roster.id,
                "roster_code": roster.roster_code,
                "old_status": old_status.value,
                "new_status": new_status.value,
                "changed_by_user_id": changed_by_user_id,
                "changed_by_name": changed_by_name,
                "changed_at": datetime.now().isoformat(),
            }

            # 根據新狀態決定通知類型和優先級
            if new_status == RosterStatus.COMPLETED:
                notification_type = NotificationType.SUCCESS
                priority = NotificationPriority.NORMAL
            elif new_status == RosterStatus.LOCKED:
                notification_type = NotificationType.WARNING
                priority = NotificationPriority.HIGH
            elif new_status == RosterStatus.FAILED:
                notification_type = NotificationType.ERROR
                priority = NotificationPriority.HIGH
            else:
                notification_type = NotificationType.INFO
                priority = NotificationPriority.NORMAL

            notified_users = []
            for user in target_users:
                try:
                    await self.notification_service.createUserNotification(
                        user_id=user.id,
                        title=notification_data["title"],
                        title_en=notification_data["title_en"],
                        message=notification_data["message"],
                        message_en=notification_data["message_en"],
                        notification_type=notification_type,
                        priority=priority,
                        related_resource_type="roster",
                        related_resource_id=roster.id,
                        action_url=f"/admin/rosters/{roster.id}",
                        metadata=notification_data,
                    )
                    notified_users.append(user.id)
                except Exception as e:
                    logger.error(f"Failed to send roster status change notification to user {user.id}: {e}")

            logger.info(
                f"Roster status change notification sent to {len(notified_users)} users for roster {roster.roster_code}"
            )
            return notified_users

        except Exception as e:
            logger.error(f"Failed to send roster status change notifications for roster {roster.id}: {e}")
            return []

    async def notify_scheduled_roster_summary(
        self, summary_data: Dict[str, Any], notify_roles: List[UserRole] = None
    ) -> List[int]:
        """
        發送排程造冊摘要通知

        Args:
            summary_data: 摘要資料
            notify_roles: 要通知的角色清單

        Returns:
            List[int]: 已發送通知的使用者ID清單
        """
        if notify_roles is None:
            notify_roles = [UserRole.admin]

        try:
            target_users = self._get_users_by_roles(notify_roles)

            if not target_users:
                return []

            notification_data = {
                "title": f"每日造冊處理摘要 - {summary_data.get('date', datetime.now().date())}",
                "title_en": f"Daily Roster Processing Summary - {summary_data.get('date', datetime.now().date())}",
                "message": f"今日造冊處理摘要：產生 {summary_data.get('generated_rosters', 0)} 個造冊，成功 {summary_data.get('successful_rosters', 0)} 個，失敗 {summary_data.get('failed_rosters', 0)} 個",
                "message_en": f"Daily roster summary: {summary_data.get('generated_rosters', 0)} rosters generated, {summary_data.get('successful_rosters', 0)} successful, {summary_data.get('failed_rosters', 0)} failed",
                "summary_data": summary_data,
                "generated_at": datetime.now().isoformat(),
            }

            # 根據是否有失敗決定通知類型
            failed_count = summary_data.get("failed_rosters", 0)
            if failed_count > 0:
                notification_type = NotificationType.WARNING
                priority = NotificationPriority.HIGH
            else:
                notification_type = NotificationType.INFO
                priority = NotificationPriority.NORMAL

            notified_users = []
            for user in target_users:
                try:
                    await self.notification_service.createUserNotification(
                        user_id=user.id,
                        title=notification_data["title"],
                        title_en=notification_data["title_en"],
                        message=notification_data["message"],
                        message_en=notification_data["message_en"],
                        notification_type=notification_type,
                        priority=priority,
                        related_resource_type="roster_summary",
                        action_url="/admin/rosters",
                        metadata=notification_data,
                    )
                    notified_users.append(user.id)
                except Exception as e:
                    logger.error(f"Failed to send roster summary notification to user {user.id}: {e}")

            logger.info(f"Daily roster summary notification sent to {len(notified_users)} users")
            return notified_users

        except Exception as e:
            logger.error(f"Failed to send roster summary notifications: {e}")
            return []

    def _get_users_by_roles(self, roles: List[UserRole]) -> List[User]:
        """
        根據角色取得使用者清單

        Args:
            roles: 角色清單

        Returns:
            List[User]: 使用者清單
        """
        try:
            return self.db.query(User).filter(User.role.in_(roles), User.status == "active").all()  # 只取得啟用的使用者
        except Exception as e:
            logger.error(f"Failed to get users by roles {roles}: {e}")
            return []

    async def send_test_notification(self, user_id: int) -> bool:
        """
        發送測試通知

        Args:
            user_id: 使用者ID

        Returns:
            bool: 是否發送成功
        """
        try:
            await self.notification_service.createUserNotification(
                user_id=user_id,
                title="造冊通知測試",
                title_en="Roster Notification Test",
                message="這是一個造冊通知系統的測試訊息",
                message_en="This is a test message from the roster notification system",
                notification_type=NotificationType.INFO,
                priority=NotificationPriority.NORMAL,
                related_resource_type="test",
                metadata={"test": True, "sent_at": datetime.now().isoformat()},
            )
            logger.info(f"Test notification sent to user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send test notification to user {user_id}: {e}")
            return False
