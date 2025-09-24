#!/usr/bin/env python3
"""
測試腳本：創建系統公告數據
用於測試前端公告管理功能
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

# 添加項目根目錄到Python路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import AsyncSessionLocal
from app.models.notification import NotificationPriority, NotificationType
from app.services.notification_service import NotificationService


async def create_test_announcements():
    """創建測試系統公告"""
    print("🚀 開始創建測試系統公告...")

    async with AsyncSessionLocal() as session:
        service = NotificationService(session)

        # 測試公告列表
        test_announcements = [
            {
                "title": "【重要】系統維護通知",
                "title_en": "Important: System Maintenance Notice",
                "message": "親愛的使用者，系統將於2025年6月15日晚上11:00-次日01:00進行例行維護，期間可能無法正常使用。造成不便敬請見諒。",
                "message_en": "Dear users, the system will undergo routine maintenance from 11:00 PM on June 15, 2025 to 1:00 AM the next day. Service may be unavailable during this time. We apologize for any inconvenience.",
                "notification_type": NotificationType.WARNING.value,
                "priority": NotificationPriority.HIGH.value,
                "expires_at": datetime.utcnow() + timedelta(days=30),
            },
            {
                "title": "🎉 新功能上線通知",
                "title_en": "🎉 New Feature Release",
                "message": "獎學金管理系統新增了通知功能！您現在可以及時收到申請狀態更新、審核結果以及重要系統公告。",
                "message_en": "The scholarship management system now includes a notification feature! You can now receive timely updates on application status, review results, and important system announcements.",
                "notification_type": NotificationType.SUCCESS.value,
                "priority": NotificationPriority.NORMAL.value,
                "action_url": "/notifications",
            },
            {
                "title": "⚠️ 申請截止日期提醒",
                "title_en": "⚠️ Application Deadline Reminder",
                "message": "2025年春季獎學金申請即將截止！請尚未提交申請的同學於6月30日前完成申請程序。逾期將無法受理。",
                "message_en": "The 2025 Spring Scholarship application deadline is approaching! Students who have not yet submitted their applications must complete the process by June 30. Late applications will not be accepted.",
                "notification_type": NotificationType.REMINDER.value,
                "priority": NotificationPriority.URGENT.value,
                "action_url": "/scholarships",
                "expires_at": datetime.utcnow() + timedelta(days=15),
            },
            {
                "title": "📢 系統操作指南發布",
                "title_en": "📢 System Operation Guide Released",
                "message": "為了幫助大家更好地使用獎學金管理系統，我們發布了詳細的操作指南。請查看幫助文件或聯繫技術支援。",
                "message_en": "To help everyone better use the scholarship management system, we have released a detailed operation guide. Please check the help documentation or contact technical support.",
                "notification_type": NotificationType.INFO.value,
                "priority": NotificationPriority.NORMAL.value,
                "action_url": "/help",
            },
            {
                "title": "🔒 安全政策更新",
                "title_en": "🔒 Security Policy Update",
                "message": "為了保護您的帳戶安全，系統已更新密碼安全政策。請確保您的密碼至少包含8個字符，包括大小寫字母、數字和特殊符號。",
                "message_en": "To protect your account security, the system has updated the password security policy. Please ensure your password contains at least 8 characters, including uppercase and lowercase letters, numbers, and special symbols.",
                "notification_type": NotificationType.WARNING.value,
                "priority": NotificationPriority.NORMAL.value,
            },
        ]

        created_count = 0

        try:
            for announcement_data in test_announcements:
                print(f"📢 創建公告: {announcement_data['title']}")

                announcement = await service.createSystemAnnouncement(
                    title=announcement_data["title"],
                    title_en=announcement_data["title_en"],
                    message=announcement_data["message"],
                    message_en=announcement_data["message_en"],
                    notification_type=announcement_data["notification_type"],
                    priority=announcement_data["priority"],
                    action_url=announcement_data.get("action_url"),
                    expires_at=announcement_data.get("expires_at"),
                    metadata={"source": "test_script", "created_by": "system"},
                )

                created_count += 1
                print(f"   ✅ 成功創建，ID: {announcement.id}")

            print("\n🎉 測試公告創建完成！")
            print(f"   📊 總共創建了 {created_count} 條系統公告")
            print("   🔗 您現在可以在管理介面的「系統公告」頁面查看這些公告")

        except Exception as e:
            print(f"❌ 創建公告時發生錯誤: {str(e)}")
            await session.rollback()
            raise


async def verify_announcements():
    """驗證公告是否成功創建"""
    print("\n🔍 驗證系統公告...")

    async with AsyncSessionLocal() as session:
        service = NotificationService(session)

        try:
            # 查詢所有系統公告
            from sqlalchemy import func, select

            from app.models.notification import Notification

            # 統計系統公告數量
            count_stmt = select(func.count(Notification.id)).where(
                Notification.user_id.is_(None)
            )
            count_result = await session.execute(count_stmt)
            total_announcements = count_result.scalar()

            print(f"   📊 資料庫中共有 {total_announcements} 條系統公告")

            # 獲取最新的5條公告
            stmt = (
                select(Notification)
                .where(Notification.user_id.is_(None))
                .order_by(Notification.created_at.desc())
                .limit(5)
            )

            result = await session.execute(stmt)
            recent_announcements = result.scalars().all()

            print("   📋 最近創建的公告:")
            for i, announcement in enumerate(recent_announcements, 1):
                print(f"      {i}. {announcement.title} (ID: {announcement.id})")
                print(
                    f"         類型: {announcement.notification_type}, 優先級: {announcement.priority}"
                )
                print(f"         創建時間: {announcement.created_at}")
                print()

        except Exception as e:
            print(f"❌ 驗證公告時發生錯誤: {str(e)}")


async def main():
    """主函數"""
    print("=" * 60)
    print("    獎學金系統 - 測試公告創建腳本")
    print("=" * 60)

    try:
        await create_test_announcements()
        await verify_announcements()

        print("\n" + "=" * 60)
        print("✅ 測試完成！現在您可以:")
        print("   1. 啟動後端服務 (uvicorn app.main:app --reload --port 8000)")
        print("   2. 啟動前端服務 (npm run dev)")
        print("   3. 以管理員身份登入系統")
        print("   4. 前往「系統公告管理」頁面查看公告列表")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 執行過程中發生錯誤: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
