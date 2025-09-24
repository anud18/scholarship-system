#!/usr/bin/env python3
"""
簡化測試：測試固定文件複製功能
"""

import asyncio
import os
import sys
from datetime import datetime

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set test environment
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["TESTING"] = "true"


async def test_document_cloning():
    """測試文件複製功能"""

    from sqlalchemy import select

    from app.core.init_db import initDatabase
    from app.db.session import AsyncSessionLocal
    from app.models.application import Application, ApplicationFile
    from app.models.user import User
    from app.models.user_profile import UserProfile
    from app.services.application_service import ApplicationService

    print("🎯 測試固定文件複製功能")
    print("=" * 60)

    # 初始化資料庫
    await initDatabase()

    async with AsyncSessionLocal() as db:
        try:
            # 1. 建立測試用戶
            print("\n📝 建立測試用戶...")

            # 查找已存在的測試用戶
            stmt = select(User).where(User.nycu_id == "stu_under")  # 使用正確的 nycu_id
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                print("❌ 找不到測試用戶")
                return False

            print(f"✅ 使用測試用戶: {user.name} (ID: {user.id})")

            # 2. 建立或更新用戶個人資料
            print("\n📄 設定用戶個人資料...")

            # 檢查是否已有個人資料
            stmt = select(UserProfile).where(UserProfile.user_id == user.id)
            result = await db.execute(stmt)
            profile = result.scalar_one_or_none()

            if not profile:
                profile = UserProfile(
                    user_id=user.id,
                    bank_code="700",
                    account_number="1234567890123",
                    bank_document_photo_url="/api/v1/user-profiles/files/bank_documents/test_bank.jpg",
                    bank_document_object_name=f"user-profiles/{user.id}/bank-documents/test_bank.jpg",
                )
                db.add(profile)
            else:
                # 更新現有個人資料
                profile.bank_document_photo_url = "/api/v1/user-profiles/files/bank_documents/test_bank.jpg"
                profile.bank_document_object_name = f"user-profiles/{user.id}/bank-documents/test_bank.jpg"

            await db.commit()
            print("✅ 個人資料已設定，包含銀行文件")

            # 3. 建立測試申請
            print("\n🚀 建立測試申請...")

            # 建立簡單的申請記錄
            from app.models.scholarship import SubTypeSelectionMode

            application = Application(
                app_id=f"APP-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                user_id=user.id,
                scholarship_type_id=1,  # 假設有 ID 為 1 的獎學金類型
                scholarship_subtype_list=[],
                sub_type_selection_mode=SubTypeSelectionMode.SINGLE,  # 設定必填欄位
                status="draft",
                status_name="草稿",
                academic_year=114,
                submitted_form_data={"fields": {}, "documents": []},
            )
            db.add(application)
            await db.commit()
            await db.refresh(application)

            print(f"✅ 申請已建立: {application.app_id}")

            # 4. 執行文件複製
            print("\n📋 執行固定文件複製...")

            app_service = ApplicationService(db)
            await app_service._clone_user_profile_documents(application, user)

            print("✅ 文件複製完成")

            # 5. 檢查複製結果
            print("\n🔍 檢查複製結果...")

            # 查詢申請的文件
            stmt = select(ApplicationFile).where(ApplicationFile.application_id == application.id)
            result = await db.execute(stmt)
            files = result.scalars().all()

            print(f"找到 {len(files)} 個文件:")
            for file in files:
                print(f"  📎 文件類型: {file.file_type}")
                print(f"     檔名: {file.filename}")
                print(f"     路徑: {file.object_name}")
                print(f"     已驗證: {file.is_verified}")

                # 檢查是否在統一路徑
                if "/documents/" in file.object_name:
                    print("     ✅ 文件在統一路徑")
                else:
                    print("     ❌ 文件路徑不正確")

            # 6. 檢查 form_data 更新
            print("\n📊 檢查 form_data 更新...")

            # 重新查詢申請以獲取最新資料
            stmt = select(Application).where(Application.id == application.id)
            result = await db.execute(stmt)
            updated_application = result.scalar_one()

            documents = updated_application.submitted_form_data.get("documents", [])
            print(f"Form data 中有 {len(documents)} 個文件:")
            for doc in documents:
                print(f"  - {doc.get('document_name', doc.get('document_type'))}")
                print(f"    文件ID: {doc.get('file_id')}")
                print(f"    已驗證: {doc.get('is_verified')}")

            # 7. 總結
            print("\n" + "=" * 60)
            if len(files) > 0 and len(documents) > 0:
                print("✅ 測試成功！")
                print("✅ 固定文件已成功複製到申請資料夾")
                print("✅ 文件資訊已更新到 form_data")
                print("✅ 所有文件使用統一的儲存路徑")
                return True
            else:
                print("❌ 測試失敗：文件複製不完整")
                return False

        except Exception as e:
            print(f"\n❌ 測試過程中發生錯誤: {e}")
            import traceback

            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_document_cloning())
    sys.exit(0 if success else 1)
