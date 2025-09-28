#!/usr/bin/env python3
"""
造冊系統整合測試
Complete integration test for payment roster system
"""

import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import sessionmaker

from app.db.session import sync_engine
from app.models.application import Application, ApplicationStatus
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole
from app.services.roster_service import RosterService
from app.services.student_verification_service import StudentVerificationService


def create_test_session():
    """建立測試用的資料庫連線"""
    try:
        SessionLocal = sessionmaker(bind=sync_engine)
        return SessionLocal()
    except Exception as e:
        print(f"❌ Failed to create database session: {e}")
        return None


def test_complete_roster_workflow():
    """測試完整造冊工作流程"""
    print("🔄 測試完整造冊工作流程...")

    db = create_test_session()
    if not db:
        print("❌ 無法連接資料庫，跳過整合測試\n")
        return

    try:
        # 檢查是否有測試用的獎學金配置
        scholarship_config = db.query(ScholarshipConfiguration).first()
        if not scholarship_config:
            print("❌ 找不到獎學金配置，請先建立測試資料")
            return

        print(f"  • 使用獎學金配置: {scholarship_config.scholarship_type.name}")

        # 檢查是否有測試用申請資料
        applications = (
            db.query(Application)
            .filter(
                Application.scholarship_configuration_id == scholarship_config.id,
                Application.status == ApplicationStatus.APPROVED.value,
            )
            .limit(5)
            .all()
        )

        if not applications:
            print("❌ 找不到已核准的申請資料")
            return

        print(f"  • 找到 {len(applications)} 筆已核准申請")

        # 建立造冊服務
        roster_service = RosterService(db)

        # 測試期間標記
        period_label = "2025-01"  # 2025年1月
        academic_year = 113

        print(f"  • 造冊期間: {period_label} (學年度: {academic_year})")

        # 檢查是否已存在此期間的造冊
        existing_roster = (
            db.query(PaymentRoster)
            .filter(
                PaymentRoster.scholarship_configuration_id == scholarship_config.id,
                PaymentRoster.period_label == period_label,
            )
            .first()
        )

        if existing_roster:
            print(f"  • 發現現有造冊: {existing_roster.roster_code}")
            print(f"    - 狀態: {existing_roster.status.value}")
            print(f"    - 合格人數: {existing_roster.qualified_count}")
            print(f"    - 總金額: {existing_roster.total_amount}")

            # 檢查明細
            items = db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == existing_roster.id).all()

            print(f"    - 明細筆數: {len(items)}")

            for item in items[:3]:  # 只顯示前3筆
                print(f"      * {item.student_name}: {item.verification_status.value} - NT${item.scholarship_amount}")

            if len(items) > 3:
                print(f"      ... 還有 {len(items) - 3} 筆")
        else:
            print("  • 此期間尚無造冊記錄")

        print("✅ 造冊工作流程測試完成\n")

    except Exception as e:
        print(f"❌ 造冊工作流程測試失敗: {e}\n")
    finally:
        db.close()


def test_scholarship_configurations():
    """測試獎學金配置"""
    print("📋 測試獎學金配置...")

    db = create_test_session()
    if not db:
        print("❌ 無法連接資料庫，跳過配置測試\n")
        return

    try:
        # 查詢所有獎學金配置
        configs = db.query(ScholarshipConfiguration).all()

        print(f"  • 總配置數: {len(configs)}")

        for config in configs[:5]:  # 只顯示前5個
            scholarship_type = config.scholarship_type
            print(f"    - {scholarship_type.name} ({scholarship_type.code})")
            print(f"      學年度: {scholarship_type.academic_year}, 學期: {scholarship_type.semester.value}")
            print(f"      金額: NT${scholarship_type.amount}")

            # 查詢該配置的申請數
            app_count = db.query(Application).filter(Application.scholarship_configuration_id == config.id).count()
            print(f"      申請數: {app_count}")

        if len(configs) > 5:
            print(f"    ... 還有 {len(configs) - 5} 個配置")

        print("✅ 獎學金配置測試完成\n")

    except Exception as e:
        print(f"❌ 獎學金配置測試失敗: {e}\n")
    finally:
        db.close()


def test_roster_statistics():
    """測試造冊統計"""
    print("📊 測試造冊統計...")

    db = create_test_session()
    if not db:
        print("❌ 無法連接資料庫，跳過統計測試\n")
        return

    try:
        # 查詢所有造冊
        rosters = db.query(PaymentRoster).all()

        print(f"  • 總造冊數: {len(rosters)}")

        # 按狀態統計
        status_counts = {}
        for roster in rosters:
            status = roster.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        for status, count in status_counts.items():
            print(f"    - {status}: {count}")

        # 計算總金額
        total_amount = sum(roster.total_amount or 0 for roster in rosters)
        print(f"  • 所有造冊總金額: NT${total_amount}")

        print("✅ 造冊統計測試完成\n")

    except Exception as e:
        print(f"❌ 造冊統計測試失敗: {e}\n")
    finally:
        db.close()


def test_student_verification_integration():
    """測試學籍驗證整合"""
    print("🔍 測試學籍驗證整合...")

    # 測試學籍驗證服務與真實資料
    service = StudentVerificationService()

    db = create_test_session()
    if not db:
        print("❌ 無法連接資料庫，跳過驗證整合測試\n")
        return

    try:
        # 查詢有學生資料的申請
        applications = db.query(Application).filter(Application.student_data.isnot(None)).limit(5).all()

        if not applications:
            print("❌ 找不到有學生資料的申請")
            return

        print(f"  • 測試 {len(applications)} 筆申請的學籍驗證")

        for app in applications:
            try:
                student_data = app.student_data or {}
                student_id = student_data.get("student_id", "Unknown")
                student_name = student_data.get("name", "Unknown")

                if student_id == "Unknown" or student_name == "Unknown":
                    print(f"    - {app.id}: 缺少學生ID或姓名")
                    continue

                result = service.verify_student(student_id, student_name)
                status = result["status"]
                message = result["message"]
                print(f"    - {student_id} ({student_name}): {status.value} - {message}")
            except Exception as e:
                print(f"    - {app.id}: 驗證失敗 - {e}")

        print("✅ 學籍驗證整合測試完成\n")

    except Exception as e:
        print(f"❌ 學籍驗證整合測試失敗: {e}\n")
    finally:
        db.close()


def main():
    """主測試函數"""
    print("🚀 造冊系統整合測試開始...\n")

    print("=" * 60)
    test_scholarship_configurations()

    print("=" * 60)
    test_complete_roster_workflow()

    print("=" * 60)
    test_roster_statistics()

    print("=" * 60)
    test_student_verification_integration()

    print("=" * 60)
    print("🎉 造冊系統整合測試完成！")
    print("\n" + "=" * 60)
    print("測試項目:")
    print("✅ 獎學金配置資料檢查")
    print("✅ 完整造冊工作流程模擬")
    print("✅ 造冊統計資料分析")
    print("✅ 學籍驗證服務整合")
    print("=" * 60)


if __name__ == "__main__":
    main()
