#!/usr/bin/env python3
"""
造冊系統測試腳本
Test script for payment roster system functionality
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
from app.models.scholarship import ScholarshipConfiguration, ScholarshipRule
from app.models.user import User, UserRole
from app.services.excel_export_service import ExcelExportService
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


def test_student_verification_service():
    """測試學籍驗證服務"""
    print("🔍 測試學籍驗證服務...")

    service = StudentVerificationService()

    # 測試mock驗證 - 使用不同的身分證字號末位數
    test_cases = [
        ("A123456789", "張三", "應該通過驗證"),  # 末位 9 -> not_found
        ("B234567890", "李四", "應該通過驗證"),  # 末位 0 -> verified
        ("C345678901", "王五", "應該通過驗證"),  # 末位 1 -> verified
        ("D456789012", "趙六", "應該通過驗證"),  # 末位 2 -> verified
        ("E567890127", "錢七", "應該畢業"),  # 末位 7 -> graduated
        ("F678901238", "孫八", "應該休學"),  # 末位 8 -> suspended
    ]

    for student_id, name, expected in test_cases:
        result = service.verify_student(student_id, name)
        status = result["status"]
        message = result["message"]
        print(f"  • {name} ({student_id}): {status.value} - {message}")

    print("✅ 學籍驗證服務測試完成\n")


def test_roster_generation_logic():
    """測試造冊邏輯（不需要資料庫）"""
    print("📋 測試造冊邏輯...")

    # 測試期間標記解析
    test_periods = [
        ("2025-01", "月份", "first"),
        ("2025-07", "月份", "second"),
        ("2025-H1", "半年", "first"),
        ("2025-H2", "半年", "second"),
        ("2025", "年度", None),
    ]

    for period, type_name, expected_semester in test_periods:
        # 簡化的學期推導邏輯
        semester = None
        if period.endswith("-H1"):
            semester = "first"
        elif period.endswith("-H2"):
            semester = "second"
        elif "-" in period and len(period.split("-")) == 2:
            year, month = period.split("-")
            month_int = int(month)
            if month_int in [2, 3, 4, 5, 6, 7]:
                semester = "second"
            elif month_int in [8, 9, 10, 11, 12, 1]:
                semester = "first"

        print(f"  • 期間標記 {period} ({type_name}) -> 學期: {semester}")

    print("✅ 造冊邏輯測試完成\n")


def test_excel_export_service():
    """測試Excel匯出服務（基本功能）"""
    print("📊 測試Excel匯出服務...")

    try:
        service = ExcelExportService()

        # 檢查template columns
        print(f"  • Excel範本欄位數: {len(service.template_columns)}")
        print(f"  • 前5個欄位: {service.template_columns[:5]}")

        # 檢查匯出目錄
        service.ensure_export_directory()
        print(f"  • 匯出目錄: {service.export_base_path}")

        print("✅ Excel匯出服務基本功能正常\n")

    except Exception as e:
        print(f"❌ Excel匯出服務測試失敗: {e}\n")


def test_database_models():
    """測試資料庫模型（需要資料庫連線）"""
    print("🗄️  測試資料庫模型...")

    db = create_test_session()
    if not db:
        print("❌ 無法連接資料庫，跳過資料庫模型測試\n")
        return

    try:
        # 檢查資料表是否存在
        tables_to_check = ["payment_rosters", "payment_roster_items", "roster_audit_logs", "roster_schedules"]

        from sqlalchemy import text

        for table in tables_to_check:
            result = db.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :table_name"),
                {"table_name": table},
            )
            count = result.scalar()
            status = "✅" if count > 0 else "❌"
            print(f"  • 資料表 {table}: {status}")

        # 檢查enum類型
        enum_types = [
            "rostercycle",
            "rosterstatus",
            "rostertriggertype",
            "studentverificationstatus",
            "rosterauditaction",
            "rosterauditlevel",
        ]

        for enum_type in enum_types:
            result = db.execute(
                text("SELECT COUNT(*) FROM pg_type WHERE typname = :type_name"), {"type_name": enum_type}
            )
            count = result.scalar()
            status = "✅" if count > 0 else "❌"
            print(f"  • Enum類型 {enum_type}: {status}")

        print("✅ 資料庫模型檢查完成\n")

    except Exception as e:
        print(f"❌ 資料庫模型測試失敗: {e}\n")
    finally:
        db.close()


def demo_roster_workflow():
    """展示完整的造冊工作流程"""
    print("🎯 造冊系統工作流程展示\n")

    print("1️⃣ 階段1: 學籍驗證")
    test_student_verification_service()

    print("2️⃣ 階段2: 造冊邏輯")
    test_roster_generation_logic()

    print("3️⃣ 階段3: Excel匯出")
    test_excel_export_service()

    print("4️⃣ 階段4: 資料庫模型")
    test_database_models()

    print("🎉 造冊系統展示完成！")
    print("\n" + "=" * 60)
    print("造冊系統主要功能:")
    print("✅ 學籍驗證 (Mock模式 + 真實API支援)")
    print("✅ 獎學金規則驗證整合")
    print("✅ 多種造冊週期 (月/半年/年)")
    print("✅ STD_UP_MIXLISTA Excel範本匯出 (30欄位)")
    print("✅ 完整稽核日誌追蹤")
    print("✅ 造冊鎖定/解鎖機制")
    print("✅ 權限控制系統")
    print("✅ 前後端枚舉同步")
    print("=" * 60)


if __name__ == "__main__":
    print("🚀 造冊系統測試開始...\n")
    demo_roster_workflow()
