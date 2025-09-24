#!/usr/bin/env python3
"""
調試固定文件複製問題
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set test environment
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["TESTING"] = "true"


async def debug_clone_issue():
    """調試複製問題"""

    from sqlalchemy import select

    from app.core.init_db import initDatabase
    from app.db.session import AsyncSessionLocal
    from app.models.application import Application, ApplicationFile
    from app.models.user import User
    from app.models.user_profile import UserProfile

    print("🔍 調試固定文件複製問題")
    print("=" * 60)

    # 初始化資料庫
    await initDatabase()

    async with AsyncSessionLocal() as db:
        try:
            # 使用現有測試用戶
            stmt = select(User).where(User.nycu_id == "stu_under")
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                print("❌ 找不到測試用戶")
                return False

            print(f"✅ 使用測試用戶: {user.name} (ID: {user.id})")

            # 建立個人資料
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
                await db.commit()

            print("✅ 個人資料設定完成")

            # 建立申請
            from app.models.scholarship import SubTypeSelectionMode

            application = Application(
                app_id=f"DEBUG-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                user_id=user.id,
                scholarship_type_id=1,
                scholarship_subtype_list=[],
                sub_type_selection_mode=SubTypeSelectionMode.SINGLE,
                status="draft",
                status_name="草稿",
                academic_year=114,
                submitted_form_data={"fields": {}, "documents": []},
            )
            db.add(application)
            await db.commit()
            await db.refresh(application)

            print(f"✅ 申請已建立: {application.app_id}")
            print(f"📊 初始 form_data.documents: {len(application.submitted_form_data.get('documents', []))} 個文件")

            # 執行文件複製，詳細追蹤
            print("\n🔍 開始詳細追蹤複製過程...")

            from app.services.minio_service import minio_service
            from app.services.user_profile_service import UserProfileService

            user_profile_service = UserProfileService(db)
            user_profile = await user_profile_service.get_user_profile(user.id)

            if not user_profile:
                print("❌ 無法找到個人資料")
                return False

            print(f"✅ 找到個人資料，bank_document_photo_url: {user_profile.bank_document_photo_url}")

            # 檢查是否已有 ApplicationFile
            stmt = select(ApplicationFile).where(
                ApplicationFile.application_id == application.id,
                ApplicationFile.file_type == "bank_account_proof",
            )
            result = await db.execute(stmt)
            existing_file = result.scalar_one_or_none()

            if existing_file:
                print(f"❌ 文件已存在，ID: {existing_file.id}")
                return False

            print("✅ 確認沒有重複文件")

            # 手動執行複製邏輯
            source_object_name = f"user-profiles/{user.id}/bank-documents/test_bank.jpg"
            filename = "test_bank.jpg"

            # 複製文件到 MinIO
            new_object_name = minio_service.clone_file_to_application(
                source_object_name=source_object_name,
                application_id=application.app_id,
                file_type="bank_account_proof",
            )
            print(f"✅ MinIO 複製成功: {new_object_name}")

            # 創建 ApplicationFile 記錄
            application_file = ApplicationFile(
                application_id=application.id,
                file_type="bank_account_proof",
                filename=filename,
                original_filename=filename,
                file_size=0,
                content_type="application/octet-stream",
                object_name=new_object_name,
                is_verified=True,
                uploaded_at=datetime.now(timezone.utc),
            )

            db.add(application_file)
            await db.flush()  # 確保獲得 ID

            print(f"✅ ApplicationFile 記錄創建，ID: {application_file.id}")

            # 更新 submitted_form_data
            form_data = application.submitted_form_data or {}

            if "documents" not in form_data:
                form_data["documents"] = []
                print("✅ 初始化 documents 陣列")

            # 生成 access token
            from app.core.config import settings
            from app.core.security import create_access_token

            token_data = {"sub": str(user.id)}
            access_token = create_access_token(token_data)
            base_url = f"{settings.base_url}{settings.api_v1_str}"

            doc_info = {
                "document_id": "bank_account_proof",
                "document_type": "bank_account_proof",
                "document_name": "存摺封面",
                "file_id": application_file.id,
                "filename": filename,
                "original_filename": filename,
                "file_path": f"{base_url}/files/applications/{application.id}/files/{application_file.id}?token={access_token}",
                "download_url": f"{base_url}/files/applications/{application.id}/files/{application_file.id}/download?token={access_token}",
                "object_name": new_object_name,
                "is_verified": True,
                "upload_time": datetime.now(timezone.utc).isoformat(),
            }

            form_data["documents"].append(doc_info)
            print("✅ 文件資訊已加入 form_data")

            # 更新申請記錄
            application.submitted_form_data = form_data
            print(f"✅ 申請記錄已更新，form_data.documents 有 {len(form_data['documents'])} 個文件")

            # 提交到資料庫
            await db.commit()
            print("✅ 資料庫提交完成")

            # 重新載入申請檢查
            stmt = select(Application).where(Application.id == application.id)
            result = await db.execute(stmt)
            reloaded_application = result.scalar_one()

            documents_after_reload = reloaded_application.submitted_form_data.get("documents", [])
            print(f"🔍 重新載入後，form_data.documents 有 {len(documents_after_reload)} 個文件")

            if documents_after_reload:
                for i, doc in enumerate(documents_after_reload):
                    print(f"  📄 文件 {i+1}:")
                    print(f"    - document_type: {doc.get('document_type')}")
                    print(f"    - file_id: {doc.get('file_id')}")
                    print(f"    - filename: {doc.get('filename')}")
                    print(f"    - is_verified: {doc.get('is_verified')}")

                print("✅ 測試成功！固定文件已正確複製並更新到 form_data")
                return True
            else:
                print("❌ 測試失敗：重新載入後 form_data.documents 為空")
                return False

        except Exception as e:
            print(f"\n❌ 調試過程中發生錯誤: {e}")
            import traceback

            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(debug_clone_issue())
    sys.exit(0 if success else 1)
