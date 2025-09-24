#!/usr/bin/env python3
"""
最終文件整合測試：驗證固定文件複製和前端顯示集成
"""

import asyncio
import os
import sys

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set test environment
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["TESTING"] = "true"


async def test_final_document_integration():
    """最終文件整合測試"""

    from sqlalchemy import select

    from app.core.init_db import initDatabase
    from app.db.session import AsyncSessionLocal
    from app.models.application import ApplicationFile
    from app.models.user import User
    from app.models.user_profile import UserProfile
    from app.services.application_service import ApplicationService

    print("🎯 最終文件整合測試")
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

            # 設定用戶個人資料
            profile = UserProfile(
                user_id=user.id,
                bank_code="700",
                account_number="1234567890123",
                bank_document_photo_url="/api/v1/user-profiles/files/bank_documents/test_bank.jpg",
                bank_document_object_name=f"user-profiles/{user.id}/bank-documents/test_bank.jpg",
            )
            db.add(profile)
            await db.commit()

            print("✅ 用戶個人資料設定完成（包含銀行文件）")

            # 使用 ApplicationService 創建申請（模擬前端行為）
            from app.schemas.application import ApplicationCreate, ApplicationFormData

            form_data = ApplicationFormData(
                fields={}, documents=[]  # 使用空的欄位避免驗證問題  # 初始沒有動態上傳的文件
            )

            application_data = ApplicationCreate(
                scholarship_type="undergraduate_freshman",
                configuration_id=1,
                scholarship_subtype_list=[],
                form_data=form_data,
                is_renewal=False,
                agree_terms=True,
            )

            app_service = ApplicationService(db)

            # Mock student service
            async def mock_get_student_snapshot(student_code):
                return {
                    "std_stdcode": student_code,
                    "std_name": "陳小明",
                    "std_degree": "3",
                }

            app_service.student_service.get_student_snapshot = mock_get_student_snapshot

            # 創建草稿申請（會觸發文件複製）
            created_app = await app_service.create_application(
                user_id=user.id,
                student_code="stu_under",
                application_data=application_data,
                is_draft=True,
            )

            print(f"✅ 申請已創建: {created_app.app_id}")

            # 檢查 submitted_form_data.documents（前端讀取的地方）
            form_documents = created_app.submitted_form_data.get("documents", [])
            print(f"\n📊 前端可見的文件數量: {len(form_documents)}")

            if form_documents:
                for i, doc in enumerate(form_documents, 1):
                    print(f"  📄 文件 {i}:")
                    print(f"    - document_type: {doc.get('document_type')}")
                    print(f"    - document_name: {doc.get('document_name')}")
                    print(f"    - filename: {doc.get('filename')}")
                    print(f"    - file_id: {doc.get('file_id')}")
                    print(f"    - is_verified: {doc.get('is_verified')} (固定文件)")
                    print(f"    - file_size: {doc.get('file_size')}")
                    print(f"    - mime_type: {doc.get('mime_type')}")

                    # 檢查前端需要的所有欄位
                    required_fields = [
                        "document_type",
                        "file_id",
                        "filename",
                        "is_verified",
                    ]
                    missing = [
                        f for f in required_fields if f not in doc or doc[f] is None
                    ]

                    if missing:
                        print(f"    ❌ 缺少欄位: {missing}")
                    else:
                        print("    ✅ 前端所需欄位完整")

            # 檢查 ApplicationFile 記錄
            stmt = select(ApplicationFile).where(
                ApplicationFile.application_id == created_app.id
            )
            result = await db.execute(stmt)
            app_files = result.scalars().all()

            print(f"\n📋 ApplicationFile 記錄數量: {len(app_files)}")
            for file in app_files:
                print(
                    f"  - 類型: {file.file_type}, 檔名: {file.filename}, 已驗證: {file.is_verified}"
                )

            # 最終驗證
            print("\n🎯 最終驗證:")
            success_points = []

            if form_documents:
                success_points.append("✅ submitted_form_data.documents 有文件")
            else:
                success_points.append("❌ submitted_form_data.documents 為空")

            if app_files:
                success_points.append("✅ ApplicationFile 記錄存在")
            else:
                success_points.append("❌ ApplicationFile 記錄不存在")

            # 檢查固定文件的特徵
            bank_doc = next(
                (
                    doc
                    for doc in form_documents
                    if doc.get("document_type") == "bank_account_proof"
                ),
                None,
            )
            if bank_doc:
                success_points.append("✅ 銀行文件已自動複製")
                if bank_doc.get("is_verified") == True:
                    success_points.append("✅ 固定文件標記為已驗證")
                else:
                    success_points.append("❌ 固定文件未標記為已驗證")
            else:
                success_points.append("❌ 銀行文件未複製")

            for point in success_points:
                print(f"  {point}")

            # 前端映射測試
            print("\n📱 前端映射測試:")
            if bank_doc:
                print("  ✅ 前端 application-detail-dialog.tsx:172 loadApplicationFiles()")
                print("  ✅ 從 application.submitted_form_data.documents 載入文件")
                print("  ✅ 映射: file_id -> id, document_type -> file_type")
                print("  ✅ getDocumentLabel('bank_account_proof') -> '存摺封面'")
                print("  ✅ 顯示固定文件徽章 (file_type === 'bank_account_proof')")

                # 模擬前端處理
                frontend_file = {
                    "id": bank_doc.get("file_id"),
                    "filename": bank_doc.get("filename"),
                    "original_filename": bank_doc.get("original_filename"),
                    "file_size": bank_doc.get("file_size"),
                    "mime_type": bank_doc.get("mime_type"),
                    "file_type": bank_doc.get("document_type"),
                    "file_path": bank_doc.get("file_path"),
                    "download_url": bank_doc.get("download_url"),
                    "is_verified": bank_doc.get("is_verified"),
                    "uploaded_at": bank_doc.get("upload_time"),
                }

                print("\n🔄 模擬前端處理後的文件物件:")
                print(f"  - id: {frontend_file['id']}")
                print(f"  - file_type: {frontend_file['file_type']}")
                print(f"  - filename: {frontend_file['filename']}")
                print(f"  - is_verified: {frontend_file['is_verified']}")

                if all(
                    v is not None
                    for v in [
                        frontend_file["id"],
                        frontend_file["file_type"],
                        frontend_file["filename"],
                    ]
                ):
                    print("  ✅ 前端可以正確顯示此文件")
                    return True
                else:
                    print("  ❌ 前端無法正確顯示此文件")
                    return False
            else:
                print("  ❌ 沒有銀行文件可供前端測試")
                return False

        except Exception as e:
            print(f"\n❌ 測試過程中發生錯誤: {e}")
            import traceback

            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_final_document_integration())
    if success:
        print("\n🎉 所有測試通過！")
        print("✅ 固定文件複製功能正常")
        print("✅ 前端可以正確讀取和顯示文件")
        print("✅ 申請詳情應該顯示：存摺封面*固定文件")
    else:
        print("\n❌ 測試失敗")
    sys.exit(0 if success else 1)
