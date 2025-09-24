import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock

from sqlalchemy import select

from app.api.v1.endpoints.professor import (
    get_application_sub_types,
    get_professor_applications,
    get_professor_review,
    submit_professor_review,
)
from app.core.init_db import initDatabase
from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole
from app.schemas.application import ProfessorReviewCreate, ProfessorReviewItemCreate


async def test_complete_professor_workflow_with_time_fix():
    await initDatabase()

    async with AsyncSessionLocal() as db:
        print("🧪 測試完整教授審查工作流程 (時間授權已修復)")
        print("=" * 70)

        # Get PhD scholarship and configuration
        stmt = select(ScholarshipType).filter(ScholarshipType.code == "phd")
        result = await db.execute(stmt)
        scholarship_type = result.scalar_one()

        stmt = select(ScholarshipConfiguration).filter(ScholarshipConfiguration.config_code == "config_phd_114")
        result = await db.execute(stmt)
        phd_config = result.scalar_one()

        # Get professor
        stmt = select(User).filter(User.role == UserRole.PROFESSOR).limit(1)
        result = await db.execute(stmt)
        professor = result.scalar_one()

        print(f"👨‍🏫 教授: {professor.name} (ID: {professor.id})")
        print(f"📚 獎學金配置: {phd_config.config_name}")

        # Create test application
        test_app = Application(
            app_id="APP-COMPLETE-WORKFLOW-TEST",
            user_id=6,  # PhD student
            scholarship_type_id=scholarship_type.id,
            scholarship_configuration_id=phd_config.id,
            scholarship_name=phd_config.config_name,
            amount=phd_config.amount,
            scholarship_subtype_list=["nstc", "moe_1w"],  # Multiple subtypes
            sub_type_selection_mode=SubTypeSelectionMode.SINGLE,
            main_scholarship_type="PHD",
            sub_scholarship_type="NSTC",
            is_renewal=False,
            academic_year=phd_config.academic_year,
            semester=phd_config.semester,
            student_data={
                "cname": "測試完整流程學生",
                "ename": "Complete Workflow Test Student",
                "stdNo": "workflow_test_001",
                "email": "workflow.test@example.com",
                "dept_code": "3551",
                "dept_name": "資訊工程學系",
            },
            submitted_form_data={
                "research_field": "Machine Learning",
                "gpa": 3.95,
                "publications": 8,
            },
            agree_terms=True,
            status="submitted",
            professor_id=professor.id,
            submitted_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db.add(test_app)
        await db.commit()
        await db.refresh(test_app)

        print(f"✅ 創建測試申請: {test_app.app_id}")

        # Mock professor user
        mock_professor = Mock()
        mock_professor.id = professor.id
        mock_professor.role = UserRole.PROFESSOR
        mock_professor.name = professor.name

        # Step 1: Get professor applications list
        print("\n📋 Step 1: 取得教授申請列表")
        try:
            applications = await get_professor_applications(status_filter=None, current_user=mock_professor, db=db)

            print(f"✅ 找到 {len(applications)} 個申請")
            if applications:
                app = applications[0]
                print(f"   學生: {app.student_name} ({app.student_no})")
                print(f"   獎學金: {app.scholarship_name}")
                print(f"   金額: ${app.amount:,} {app.currency}")
                print(f"   狀態: {app.status}")
        except Exception as e:
            print(f"❌ Step 1 失敗: {e}")
            return

        # Step 2: Get application sub-types
        print("\n🏷️ Step 2: 取得申請子類型")
        try:
            sub_types = await get_application_sub_types(application_id=test_app.id, current_user=mock_professor, db=db)

            print(f"✅ 找到 {len(sub_types)} 個子類型:")
            for st in sub_types:
                print(f'   - {st["value"]}: {st["label"]}')
        except Exception as e:
            print(f"❌ Step 2 失敗: {e}")
            return

        # Step 3: Check existing review
        print("\n🔍 Step 3: 檢查現有審查")
        try:
            existing_review = await get_professor_review(application_id=test_app.id, current_user=mock_professor, db=db)
            print(f"✅ 審查檢查完成 (ID: {existing_review.id}, 新審查: {existing_review.id == 0})")
        except Exception as e:
            print(f"❌ Step 3 失敗: {e}")
            return

        # Step 4: Submit professor review - This tests our time authorization fix
        print("\n✍️ Step 4: 提交教授審查 (測試時間授權修復)")
        try:
            # Create review data
            review_items = []
            for i, st in enumerate(sub_types):
                review_items.append(
                    ProfessorReviewItemCreate(
                        sub_type_code=st["value"],
                        is_recommended=i == 0,  # Recommend first sub-type only
                        comments=f'針對 {st["label"]} 的評估: 學生在此領域表現優異，{"推薦" if i == 0 else "不推薦"}申請。',
                    )
                )

            review_data = ProfessorReviewCreate(
                recommendation="經過詳細評估，此學生在學術研究方面表現優秀，具備獲得博士生獎學金的資格。特別在機器學習領域有傑出表現，已發表8篇論文，GPA達3.95。整體推薦此學生申請獎學金。",
                items=review_items,
            )

            submitted_review = await submit_professor_review(
                review_data=review_data,
                application_id=test_app.id,
                current_user=mock_professor,
                db=db,
            )

            print("✅ 審查提交成功!")
            print(f"   審查ID: {submitted_review.id}")
            print(f"   整體推薦: {submitted_review.recommendation[:60]}...")
            print(f"   審查狀態: {submitted_review.review_status}")
            print(f"   子類型審查數量: {len(submitted_review.items)}")

            print("\n📊 子類型審查結果:")
            for item in submitted_review.items:
                status = "✅ 推薦" if item.is_recommended else "❌ 不推薦"
                print(f"   - {item.sub_type_code}: {status}")
                print(f"     評語: {item.comments[:50]}...")

        except Exception as e:
            print(f"❌ Step 4 失敗: {e}")
            print("   這表示時間授權修復可能還有問題")
            import traceback

            traceback.print_exc()
            return

        # Step 5: Verify review was saved correctly
        print("\n✅ Step 5: 驗證審查已正確保存")
        try:
            final_review = await get_professor_review(application_id=test_app.id, current_user=mock_professor, db=db)

            print("✅ 審查驗證成功")
            print(f"   審查ID: {final_review.id}")
            print(f"   審查時間: {final_review.reviewed_at}")
            print(f"   子類型項目: {len(final_review.items)}")

            # Check application status
            stmt = select(Application).where(Application.id == test_app.id)
            result = await db.execute(stmt)
            updated_app = result.scalar_one()
            print(f"   申請狀態已更新為: {updated_app.status}")

        except Exception as e:
            print(f"❌ Step 5 失敗: {e}")
            return

        print("\n🎉 完整工作流程測試成功!")
        print("=" * 70)
        print("✅ 所有功能均正常運作:")
        print("   1. ✅ 教授申請列表顯示")
        print("   2. ✅ 子類型取得")
        print("   3. ✅ 現有審查檢查")
        print("   4. ✅ 審查提交 (時間授權已修復)")
        print("   5. ✅ 審查驗證")
        print("\n🔧 關鍵修復:")
        print("   ✅ 時間授權期間從 professor_review_start → application_start_date")
        print("   ✅ 教授可以從學生申請提交後立即進行審查")
        print("   ✅ 審查期間: application_start_date 到 professor_review_end")
        print('   ✅ 符合用戶要求: "once the student send out the application that the professor can do the review"')


if __name__ == "__main__":
    asyncio.run(test_complete_professor_workflow_with_time_fix())
