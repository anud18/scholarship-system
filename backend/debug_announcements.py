#!/usr/bin/env python3
"""
診斷腳本：檢查公告系統的所有組件
"""

import asyncio
import os
import sys
from datetime import datetime

# 添加項目根目錄到Python路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.notification import Notification, NotificationPriority, NotificationType
from app.models.user import User, UserRole
from app.services.notification_service import NotificationService


async def check_database_connection():
    """檢查數據庫連接"""
    print("=" * 60)
    print("🔗 檢查數據庫連接")
    print("=" * 60)

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(func.count(User.id)))
            user_count = result.scalar()
            print(f"✅ 數據庫連接成功，用戶總數: {user_count}")
            return True
    except Exception as e:
        print(f"❌ 數據庫連接失敗: {str(e)}")
        return False


async def check_admin_users():
    """檢查管理員用戶"""
    print("\n" + "=" * 60)
    print("👨‍💼 檢查管理員用戶")
    print("=" * 60)

    try:
        async with AsyncSessionLocal() as session:
            # 查詢所有管理員用戶
            stmt = select(User).where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
            result = await session.execute(stmt)
            admin_users = result.scalars().all()

            print(f"📊 找到 {len(admin_users)} 個管理員用戶:")
            for admin in admin_users:
                print(f"   - ID: {admin.id}, Email: {admin.email}, Role: {admin.role.value}")

            if not admin_users:
                print("⚠️  警告：沒有找到管理員用戶！")
                return False

            return True

    except Exception as e:
        print(f"❌ 檢查管理員用戶失敗: {str(e)}")
        return False


async def check_existing_announcements():
    """檢查現有公告"""
    print("\n" + "=" * 60)
    print("📢 檢查現有系統公告")
    print("=" * 60)

    try:
        async with AsyncSessionLocal() as session:
            # 統計系統公告
            count_stmt = select(func.count(Notification.id)).where(Notification.user_id.is_(None))
            count_result = await session.execute(count_stmt)
            total_announcements = count_result.scalar()

            print(f"📊 系統公告總數: {total_announcements}")

            if total_announcements > 0:
                # 獲取最新的10條公告
                stmt = (
                    select(Notification)
                    .where(Notification.user_id.is_(None))
                    .order_by(Notification.created_at.desc())
                    .limit(10)
                )
                result = await session.execute(stmt)
                announcements = result.scalars().all()

                print(f"📋 最新的 {len(announcements)} 條公告:")
                for i, announcement in enumerate(announcements, 1):
                    print(f"   {i}. ID: {announcement.id}")
                    print(f"      標題: {announcement.title}")
                    print(f"      類型: {announcement.notification_type}")
                    print(f"      優先級: {announcement.priority}")
                    print(f"      創建時間: {announcement.created_at}")
                    print()
            else:
                print("⚠️  沒有找到系統公告")

            return total_announcements > 0

    except Exception as e:
        print(f"❌ 檢查現有公告失敗: {str(e)}")
        return False


async def create_test_announcement():
    """創建測試公告"""
    print("\n" + "=" * 60)
    print("🆕 創建測試公告")
    print("=" * 60)

    try:
        async with AsyncSessionLocal() as session:
            service = NotificationService(session)

            announcement = await service.createSystemAnnouncement(
                title="🧪 測試公告",
                title_en="🧪 Test Announcement",
                message="這是一個測試公告，用於驗證系統功能是否正常工作。",
                message_en="This is a test announcement to verify that the system functionality is working properly.",
                notification_type=NotificationType.INFO.value,
                priority=NotificationPriority.NORMAL.value,
                metadata={
                    "source": "debug_script",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            print("✅ 測試公告創建成功!")
            print(f"   ID: {announcement.id}")
            print(f"   標題: {announcement.title}")
            print(f"   創建時間: {announcement.created_at}")

            return announcement.id

    except Exception as e:
        print(f"❌ 創建測試公告失敗: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


async def test_api_simulation():
    """模擬API調用"""
    print("\n" + "=" * 60)
    print("🔧 模擬API調用測試")
    print("=" * 60)

    try:
        async with AsyncSessionLocal() as session:
            # 模擬 getAllAnnouncements API
            print("📡 模擬 getAllAnnouncements API...")

            # 構建查詢條件（與API中相同）
            conditions = [Notification.user_id.is_(None)]

            # 查詢總數
            count_stmt = select(func.count(Notification.id)).where(func.and_(*conditions))
            count_result = await session.execute(count_stmt)
            total = count_result.scalar()

            # 查詢數據（分頁）
            page = 1
            size = 10
            offset = (page - 1) * size
            stmt = (
                select(Notification)
                .where(func.and_(*conditions))
                .order_by(Notification.created_at.desc())
                .offset(offset)
                .limit(size)
            )

            result = await session.execute(stmt)
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
                    "notification_type": notification.notification_type,
                    "priority": notification.priority,
                    "action_url": notification.action_url,
                    "is_read": notification.is_read,
                    "is_dismissed": notification.is_dismissed,
                    "expires_at": notification.expires_at,
                    "created_at": notification.created_at,
                    "metadata": notification.meta_data,
                }
                items.append(notification_data)

            api_response = {
                "success": True,
                "message": "系統公告列表獲取成功",
                "data": {"items": items, "total": total, "page": page, "size": size},
            }

            print("✅ API模擬成功!")
            print(f"   total: {api_response['data']['total']}")
            print(f"   items count: {len(api_response['data']['items'])}")
            print(f"   response: {api_response['success']}")

            if api_response["data"]["items"]:
                print("📋 返回的公告列表:")
                for i, item in enumerate(api_response["data"]["items"][:3], 1):
                    print(f"   {i}. {item['title']} (ID: {item['id']})")

            return api_response

    except Exception as e:
        print(f"❌ API模擬失敗: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


async def check_notification_model():
    """檢查通知模型定義"""
    print("\n" + "=" * 60)
    print("🧩 檢查通知模型定義")
    print("=" * 60)

    try:
        # 檢查模型屬性
        notification_attrs = [attr for attr in dir(Notification) if not attr.startswith("_")]
        print("📋 Notification 模型屬性:")
        for attr in notification_attrs:
            print(f"   - {attr}")

        # 檢查枚舉值
        print("\n📋 NotificationType 枚舉值:")
        for enum_val in NotificationType:
            print(f"   - {enum_val.name}: {enum_val.value}")

        print("\n📋 NotificationPriority 枚舉值:")
        for enum_val in NotificationPriority:
            print(f"   - {enum_val.name}: {enum_val.value}")

        return True

    except Exception as e:
        print(f"❌ 檢查模型定義失敗: {str(e)}")
        return False


async def main():
    """主函數"""
    print("🔍 獎學金系統 - 公告功能診斷腳本")
    print("=" * 80)

    results = {}

    # 1. 檢查數據庫連接
    results["db_connection"] = await check_database_connection()

    # 2. 檢查管理員用戶
    results["admin_users"] = await check_admin_users()

    # 3. 檢查模型定義
    results["model_check"] = await check_notification_model()

    # 4. 檢查現有公告
    results["existing_announcements"] = await check_existing_announcements()

    # 5. 創建測試公告
    test_announcement_id = await create_test_announcement()
    results["test_announcement"] = test_announcement_id is not None

    # 6. 模擬API調用
    api_result = await test_api_simulation()
    results["api_simulation"] = api_result is not None

    # 總結
    print("\n" + "=" * 80)
    print("📊 診斷結果總結")
    print("=" * 80)

    all_passed = True
    for check, passed in results.items():
        status = "✅ 通過" if passed else "❌ 失敗"
        print(f"{check:25} : {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 所有檢查都通過！公告系統應該可以正常工作。")
        print("\n🔧 建議檢查項目:")
        print("   1. 確保前端已登入管理員帳戶")
        print("   2. 檢查瀏覽器開發者工具的網絡請求")
        print("   3. 檢查API請求的身份驗證token")
    else:
        print("⚠️  發現問題！請根據上述失敗的檢查項目進行修復。")

    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    result = asyncio.run(main())
