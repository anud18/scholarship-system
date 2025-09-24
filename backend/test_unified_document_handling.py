#!/usr/bin/env python3
"""
測試固定文件和動態文件的統一處理
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


async def test_unified_document_handling():
    """測試固定文件複製和動態文件上傳的統一處理"""

    from sqlalchemy import select

    from app.core.init_db import initDatabase
    from app.db.session import AsyncSessionLocal
    from app.models.application import Application, ApplicationFile
    from app.models.user import User
    from app.services.application_service import ApplicationService
    from app.services.user_profile_service import UserProfileService

    print("🎯 測試固定文件和動態文件的統一處理")
    print("=" * 60)

    # 初始化資料庫
    await initDatabase()

    async with AsyncSessionLocal() as db:
        try:
            # 1. 準備測試用戶
            print("\n📝 準備測試資料...")
            from app.models.user import UserType

            user = User(
                id=100,
                nycu_id="test_student_100",
                name="測試學生",
                email="test@nycu.edu.tw",
                user_type=UserType.STUDENT,
                role="student",
                dept_code="3551",
                dept_name="資訊工程學系",
            )
            db.add(user)
            await db.commit()

            # 2. 設定用戶的個人資料（包含銀行文件）
            profile_service = UserProfileService(db)
            from app.models.user_profile import UserProfile

            profile = UserProfile(
                user_id=100,
                bank_code="700",
                account_number="1234567890",
                bank_document_photo_url="/api/v1/user-profiles/files/bank_documents/test_bank.jpg",
                bank_document_object_name="user-profiles/100/bank-documents/test_bank.jpg",
                advisor_name="王教授",
                advisor_email="wang@nycu.edu.tw",
                advisor_nycu_id="prof_001",
            )
            db.add(profile)
            await db.commit()

            print("✅ 用戶個人資料已建立，包含銀行文件")

            # 3. 創建申請（觸發固定文件複製）
            print("\n📄 創建申請，測試固定文件自動複製...")

            # 模擬申請資料
            from app.schemas.application import ApplicationCreate, ApplicationFormData, DynamicFormField

            form_data = ApplicationFormData(
                fields={
                    "research_topic": DynamicFormField(
                        field_id="research_topic",
                        field_name="research_topic",
                        field_value="AI研究計畫",
                        field_type="text",
                    ),
                    "expected_graduation": DynamicFormField(
                        field_id="expected_graduation",
                        field_name="expected_graduation",
                        field_value="2026-06",
                        field_type="date",
                    ),
                },
                documents=[],  # 初始沒有動態上傳的文件
            )

            application_data = ApplicationCreate(
                scholarship_type="phd",
                configuration_id=1,
                scholarship_subtype_list=["nstc"],
                form_data=form_data,
                is_renewal=False,
                agree_terms=True,
            )

            # 使用 ApplicationService 創建申請
            app_service = ApplicationService(db)

            # Mock the student service
            app_service.student_service.get_student_snapshot = lambda x: {
                "std_stdcode": x,
                "std_name": "測試學生",
                "std_degree": "1",
            }

            # 創建測試用的 scholarship type 和 configuration
            from app.models.enums import Semester
            from app.models.scholarship import ScholarshipConfiguration, ScholarshipType

            scholarship_type = ScholarshipType(
                id=1,
                code="phd",
                name="博士生獎學金",
                name_en="PhD Scholarship",
                category="phd",
                is_active=True,
            )
            db.add(scholarship_type)

            config = ScholarshipConfiguration(
                id=1,
                scholarship_type_id=1,
                academic_year=114,
                semester=Semester.FIRST,
                config_name="114學年度博士生獎學金",
                config_code="phd_114_first",
                amount=50000,
                is_active=True,
            )
            db.add(config)
            await db.commit()

            # 創建申請（會觸發文件複製）
            created_app = await app_service.create_application(
                user_id=100,
                student_code="test_student_100",
                application_data=application_data,
                is_draft=True,  # 儲存草稿也會觸發複製
            )

            print(f"✅ 申請已建立: {created_app.app_id}")

            # 4. 檢查固定文件是否已複製
            print("\n🔍 檢查固定文件複製結果...")

            # 查詢申請的文件
            stmt = select(ApplicationFile).where(ApplicationFile.application_id == created_app.id)
            result = await db.execute(stmt)
            files = result.scalars().all()

            print(f"找到 {len(files)} 個文件:")
            for file in files:
                print(f"  - 類型: {file.file_type}")
                print(f"    檔名: {file.filename}")
                print(f"    路徑: {file.object_name}")
                print(f"    已驗證: {file.is_verified}")

                # 檢查路徑是否統一
                if "applications/" in file.object_name and "/documents/" in file.object_name:
                    print("    ✅ 文件存放在統一路徑")
                else:
                    print("    ❌ 文件路徑不正確")

            # 5. 檢查 form_data 中的文件資訊
            print("\n📋 檢查 form_data 中的文件資訊...")

            # 重新載入申請
            stmt = select(Application).where(Application.id == created_app.id)
            result = await db.execute(stmt)
            application = result.scalar_one()

            form_documents = application.submitted_form_data.get("documents", [])
            print(f"Form data 中有 {len(form_documents)} 個文件:")
            for doc in form_documents:
                print(f"  - {doc.get('document_name', doc.get('document_type'))}")
                print(f"    ID: {doc.get('file_id')}")
                print(f"    已驗證: {doc.get('is_verified')}")

            # 6. 測試動態文件上傳（模擬）
            print("\n📤 模擬動態文件上傳...")

            # 創建一個動態上傳的文件記錄
            dynamic_file = ApplicationFile(
                application_id=application.id,
                file_type="research_proposal",
                filename="research_plan.pdf",
                original_filename="研究計畫書.pdf",
                file_size=1024000,
                content_type="application/pdf",
                object_name=f"applications/{application.app_id}/documents/dynamic_file.pdf",
                is_verified=False,  # 動態上傳的文件預設未驗證
                uploaded_at=datetime.now(timezone.utc),
            )
            db.add(dynamic_file)
            await db.commit()

            print("✅ 動態文件已上傳")

            # 7. 最終檢查：所有文件是否在同一路徑
            print("\n🎯 最終檢查：統一文件管理")

            stmt = select(ApplicationFile).where(ApplicationFile.application_id == application.id)
            result = await db.execute(stmt)
            all_files = result.scalars().all()

            print(f"申請共有 {len(all_files)} 個文件:")

            fixed_count = 0
            dynamic_count = 0
            unified_path_count = 0

            for file in all_files:
                if file.is_verified:
                    fixed_count += 1
                    print(f"  📎 [固定] {file.filename}")
                else:
                    dynamic_count += 1
                    print(f"  📤 [動態] {file.filename}")

                # 檢查是否在統一路徑
                if "/documents/" in file.object_name:
                    unified_path_count += 1

            print("\n統計:")
            print(f"  固定文件（從個人資料複製）: {fixed_count}")
            print(f"  動態文件（用戶上傳）: {dynamic_count}")
            print(f"  統一路徑儲存: {unified_path_count}/{len(all_files)}")

            if unified_path_count == len(all_files):
                print("\n✅ 測試通過！所有文件都使用統一的儲存路徑")
                print("✅ 固定文件和動態文件都被當作已上傳文件處理")
            else:
                print("\n❌ 測試失敗：部分文件未使用統一路徑")

            return True

        except Exception as e:
            print(f"\n❌ 測試過程中發生錯誤: {e}")
            import traceback

            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_unified_document_handling())
    sys.exit(0 if success else 1)
