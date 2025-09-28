#!/usr/bin/env python3
"""
測試造冊產生功能，包含學籍驗證和學生資料更新
Test roster generation with student verification and data update
"""

import os
import sys
from datetime import datetime, timezone

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import sessionmaker

from app.db.session import sync_engine
from app.models.application import Application, ApplicationStatus
from app.models.payment_roster import PaymentRoster, RosterCycle, RosterTriggerType
from app.models.scholarship import ScholarshipConfiguration
from app.services.roster_service import RosterService


def create_test_session():
    """建立測試用的資料庫連線"""
    try:
        SessionLocal = sessionmaker(bind=sync_engine)
        return SessionLocal()
    except Exception as e:
        print(f"❌ Failed to create database session: {e}")
        return None


def test_roster_generation_with_student_update():
    """測試造冊產生並驗證學生資料更新功能"""
    print("🔄 測試造冊產生與學生資料更新功能...\n")

    db = create_test_session()
    if not db:
        print("❌ 無法連接資料庫")
        return

    try:
        # 1. 找到測試用獎學金配置
        scholarship_config = db.query(ScholarshipConfiguration).first()
        if not scholarship_config:
            print("❌ 找不到測試用獎學金配置")
            print("   請先執行 python create_test_data.py")
            return

        print(f"📋 使用獎學金配置: {scholarship_config.config_name}")

        # 2. 檢查現有申請
        applications = (
            db.query(Application)
            .filter(
                Application.scholarship_configuration_id == scholarship_config.id,
                Application.status == ApplicationStatus.APPROVED.value,
            )
            .all()
        )

        print(f"📝 找到 {len(applications)} 筆已核准申請")

        # 顯示申請的現有學生資料
        print("  申請中的學生資料:")
        for app in applications:
            student_data = app.student_data or {}
            print(f"    • 申請 {app.id}: {student_data.get('name')} ({student_data.get('student_id')})")
            print(f"      Email: {student_data.get('email', 'N/A')}")
            print(f"      電話: {student_data.get('phone', 'N/A')}")
            print(f"      GPA: {student_data.get('gpa', 'N/A')}")

        # 3. 建立造冊服務並產生造冊
        print(f"\n🎯 開始產生造冊...")
        roster_service = RosterService(db)

        period_label = "2025-01"
        academic_year = 113

        try:
            # 檢查是否已存在
            existing_roster = (
                db.query(PaymentRoster)
                .filter(
                    PaymentRoster.scholarship_configuration_id == scholarship_config.id,
                    PaymentRoster.period_label == period_label,
                )
                .first()
            )

            if existing_roster:
                print(f"⚠️ 期間 {period_label} 已存在造冊，刪除後重新產生")
                db.delete(existing_roster)
                db.commit()

            # 產生新造冊 (使用月度週期)
            roster = roster_service.generate_roster(
                scholarship_configuration_id=scholarship_config.id,
                period_label=period_label,
                roster_cycle=RosterCycle.MONTHLY,
                academic_year=academic_year,
                created_by_user_id=1,  # 假設管理員ID為1
                trigger_type=RosterTriggerType.MANUAL,
                student_verification_enabled=True,
            )

            print(f"✅ 造冊產生成功!")
            print(f"   造冊代碼: {roster.roster_code}")
            print(f"   狀態: {roster.status.value}")
            print(f"   合格人數: {roster.qualified_count}")
            print(f"   不合格人數: {roster.disqualified_count}")
            print(f"   總金額: NT${roster.total_amount}")

            # 4. 檢查學生資料是否有更新
            print(f"\n🔍 檢查學生資料更新情況...")
            applications_after = (
                db.query(Application)
                .filter(
                    Application.scholarship_configuration_id == scholarship_config.id,
                    Application.status == ApplicationStatus.APPROVED.value,
                )
                .all()
            )

            print("  造冊後的學生資料:")
            for app in applications_after:
                student_data = app.student_data or {}
                print(f"    • 申請 {app.id}: {student_data.get('name')} ({student_data.get('student_id')})")
                print(f"      Email: {student_data.get('email', 'N/A')}")
                print(f"      電話: {student_data.get('phone', 'N/A')}")
                print(f"      GPA: {student_data.get('gpa', 'N/A')}")

            # 5. 檢查造冊明細
            if roster.items:
                print(f"\n📊 造冊明細:")
                for item in roster.items:
                    print(f"    • {item.student_name} ({item.student_id_number})")
                    print(f"      驗證狀態: {item.verification_status.value}")
                    print(f"      金額: NT${item.scholarship_amount}")
                    print(f"      合格: {'是' if item.is_qualified else '否'}")

            # 6. 檢查稽核日誌
            if roster.audit_logs:
                print(f"\n📝 稽核日誌:")
                for log in roster.audit_logs:
                    print(f"    • [{log.action.value}] {log.title}")
                    if log.description:
                        print(f"      {log.description}")

        except Exception as e:
            print(f"❌ 造冊產生失敗: {e}")

    except Exception as e:
        print(f"❌ 測試過程發生錯誤: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    print("🚀 造冊產生測試開始...\n")
    test_roster_generation_with_student_update()
    print("\n🎉 造冊產生測試完成！")
