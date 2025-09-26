"""
Environment-specific seed data with idempotency and advisory lock
使用冪等方式進行數據庫初始化

Usage:
    python -m app.seed              # Development: Full test data
    python -m app.seed --prod       # Production: Admin user only
"""

import asyncio
import json
import logging
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.user import EmployeeStatus, UserRole, UserType

logger = logging.getLogger(__name__)

# Advisory lock ID for this seed process
SEED_LOCK_ID = 1234567890


async def acquire_advisory_lock(session: AsyncSession) -> bool:
    """
    Try to acquire PostgreSQL advisory lock (non-blocking)
    防止多個 seed 程序同時執行
    """
    result = await session.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": SEED_LOCK_ID})
    return bool(result.scalar())


async def release_advisory_lock(session: AsyncSession):
    """Release PostgreSQL advisory lock"""
    await session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": SEED_LOCK_ID})


async def seed_lookup_tables(session: AsyncSession):
    """
    Initialize lookup/reference tables
    """
    print("📚 Checking lookup tables...")

    # Check if already initialized
    result = await session.execute(text("SELECT COUNT(*) FROM degrees"))
    count = result.scalar()

    if count == 0:
        print("  📖 Initializing lookup tables...")
        # Initialize lookup tables inline
        print("  📖 Initializing degrees...")
        await session.execute(
            text(
                """
            INSERT INTO degrees (id, name) VALUES
            (1, '學士'),
            (2, '碩士'),
            (3, '博士')
            ON CONFLICT (id) DO NOTHING
        """
            )
        )

        print("  🎓 Initializing student identities...")
        # Add other lookup table initialization as needed
        await session.commit()
    else:
        print(f"  ✓ Lookup tables already initialized ({count} degrees found)")


async def seed_test_users(session: AsyncSession):
    """
    建立測試用戶
    使用 ON CONFLICT 實現冪等性
    """
    print("👥 Creating/updating test users...")

    # 測試用戶數據
    test_users_data = [
        {
            "nycu_id": "admin",
            "name": "系統管理員",
            "email": "admin@nycu.edu.tw",
            "user_type": UserType.EMPLOYEE,
            "status": EmployeeStatus.ACTIVE,
            "dept_code": "9000",
            "dept_name": "教務處",
            "role": UserRole.ADMIN,
        },
        {
            "nycu_id": "super_admin",
            "name": "超級管理員",
            "email": "super_admin@nycu.edu.tw",
            "user_type": UserType.EMPLOYEE,
            "status": EmployeeStatus.ACTIVE,
            "dept_code": "9000",
            "dept_name": "教務處",
            "role": UserRole.SUPER_ADMIN,
        },
        {
            "nycu_id": "professor",
            "name": "李教授",
            "email": "professor@nycu.edu.tw",
            "user_type": UserType.EMPLOYEE,
            "status": EmployeeStatus.ACTIVE,
            "dept_code": "7000",
            "dept_name": "資訊學院",
            "role": UserRole.PROFESSOR,
        },
        {
            "nycu_id": "college",
            "name": "學院審核員",
            "email": "college@nycu.edu.tw",
            "user_type": UserType.EMPLOYEE,
            "status": EmployeeStatus.ACTIVE,
            "dept_code": "7000",
            "dept_name": "資訊學院",
            "role": UserRole.COLLEGE,
        },
        {
            "nycu_id": "stu_under",
            "name": "陳小明",
            "email": "stu_under@nycu.edu.tw",
            "user_type": UserType.STUDENT,
            "status": EmployeeStatus.STUDENT,
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "stu_phd",
            "name": "王博士",
            "email": "stu_phd@nycu.edu.tw",
            "user_type": UserType.STUDENT,
            "status": EmployeeStatus.STUDENT,
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "stu_direct",
            "name": "李逕升",
            "email": "stu_direct@nycu.edu.tw",
            "user_type": UserType.STUDENT,
            "status": EmployeeStatus.STUDENT,
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "stu_master",
            "name": "張碩士",
            "email": "stu_master@nycu.edu.tw",
            "user_type": UserType.STUDENT,
            "status": EmployeeStatus.STUDENT,
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "phd_china",
            "name": "陸生",
            "email": "phd_china@nycu.edu.tw",
            "user_type": UserType.STUDENT,
            "status": EmployeeStatus.STUDENT,
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        # Computer Science College Users
        {
            "nycu_id": "cs_professor",
            "name": "李資訊教授",
            "email": "cs_professor@nycu.edu.tw",
            "user_type": UserType.EMPLOYEE,
            "status": EmployeeStatus.ACTIVE,
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.PROFESSOR,
        },
        {
            "nycu_id": "cs_college",
            "name": "資訊學院審核員",
            "email": "cs_college@nycu.edu.tw",
            "user_type": UserType.EMPLOYEE,
            "status": EmployeeStatus.ACTIVE,
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.COLLEGE,
        },
        {
            "nycu_id": "cs_phd001",
            "name": "王博士研究生",
            "email": "cs_phd001@nycu.edu.tw",
            "user_type": UserType.STUDENT,
            "status": EmployeeStatus.STUDENT,
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "cs_phd002",
            "name": "陳AI博士",
            "email": "cs_phd002@nycu.edu.tw",
            "user_type": UserType.STUDENT,
            "status": EmployeeStatus.STUDENT,
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "cs_phd003",
            "name": "林機器學習博士",
            "email": "cs_phd003@nycu.edu.tw",
            "user_type": UserType.STUDENT,
            "status": EmployeeStatus.STUDENT,
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
    ]

    for user_data in test_users_data:
        # 使用原生 SQL 的 ON CONFLICT 實現冪等 upsert
        await session.execute(
            text(
                """
            INSERT INTO users (nycu_id, name, email, user_type, status, dept_code, dept_name, role)
            VALUES (:nycu_id, :name, :email, :user_type, :status, :dept_code, :dept_name, :role)
            ON CONFLICT (nycu_id) DO UPDATE
            SET name = EXCLUDED.name,
                email = EXCLUDED.email,
                user_type = EXCLUDED.user_type,
                status = EXCLUDED.status,
                dept_code = EXCLUDED.dept_code,
                dept_name = EXCLUDED.dept_name,
                role = EXCLUDED.role
        """
            ),
            {
                "nycu_id": user_data["nycu_id"],
                "name": user_data["name"],
                "email": user_data["email"],
                "user_type": user_data["user_type"].value,
                "status": user_data["status"].value if user_data.get("status") else None,
                "dept_code": user_data.get("dept_code"),
                "dept_name": user_data.get("dept_name"),
                "role": user_data["role"].value,
            },
        )

    await session.commit()
    print(f"  ✓ {len(test_users_data)} test users created/updated")


async def seed_admin_user(session: AsyncSession):
    """
    建立或更新第一個 admin 用戶（production 環境）
    使用環境變數 ADMIN_EMAIL
    """
    admin_email = os.getenv("ADMIN_EMAIL", "admin@nycu.edu.tw")

    print(f"👤 Setting up admin user: {admin_email}")

    # 使用 UPSERT
    await session.execute(
        text(
            """
        INSERT INTO users (nycu_id, name, email, user_type, status, role)
        VALUES (:nycu_id, :name, :email, 'employee', '在職', 'admin')
        ON CONFLICT (nycu_id) DO UPDATE
        SET role = 'admin',
            email = EXCLUDED.email,
            name = EXCLUDED.name
    """
        ),
        {"nycu_id": admin_email.split("@")[0], "name": "System Administrator", "email": admin_email},
    )

    await session.commit()
    print(f"  ✓ Admin user configured: {admin_email}")


async def seed_scholarships(session: AsyncSession):
    """
    建立獎學金資料
    """
    print("🎓 Creating scholarship data...")

    from app.models.enums import ApplicationCycle, SubTypeSelectionMode
    from app.models.scholarship import ScholarshipCategory, ScholarshipStatus

    # 基本獎學金類型
    scholarships_data = [
        {
            "code": "undergraduate_freshman",
            "name": "學士班新生獎學金",
            "name_en": "Undergraduate Freshman Scholarship",
            "description": "適用於學士班新生 白名單 與 地區劃分",
            "description_en": "For undergraduate freshmen, white list and regional",
            "category": ScholarshipCategory.UNDERGRADUATE_FRESHMAN.value,
            "application_cycle": ApplicationCycle.SEMESTER.value,
            "whitelist_enabled": False,
            "sub_type_selection_mode": SubTypeSelectionMode.SINGLE.value,
            "status": ScholarshipStatus.ACTIVE.value,
        },
        {
            "code": "phd",
            "name": "博士生獎學金",
            "name_en": "PhD Scholarship",
            "description": "適用於一般博士生，需完整研究計畫和教授推薦",
            "description_en": "For regular PhD students, requires complete research plan",
            "category": ScholarshipCategory.PHD.value,
            "application_cycle": ApplicationCycle.YEARLY.value,
            "sub_type_list": ["nstc", "moe_1w", "moe_2w"],
            "whitelist_enabled": False,
            "sub_type_selection_mode": SubTypeSelectionMode.HIERARCHICAL.value,
            "status": ScholarshipStatus.ACTIVE.value,
        },
        {
            "code": "direct_phd",
            "name": "逕讀博士獎學金",
            "name_en": "Direct PhD Scholarship",
            "description": "適用於逕讀博士班學生，需完整研究計畫",
            "description_en": "For direct PhD students, requires complete research plan",
            "category": ScholarshipCategory.DIRECT_PHD.value,
            "application_cycle": ApplicationCycle.YEARLY.value,
            "whitelist_enabled": False,
            "sub_type_selection_mode": SubTypeSelectionMode.SINGLE.value,
            "status": ScholarshipStatus.ACTIVE.value,
        },
    ]

    for scholarship_data in scholarships_data:
        # Convert list to JSON for sub_type_list
        if "sub_type_list" in scholarship_data and isinstance(scholarship_data["sub_type_list"], list):
            scholarship_data["sub_type_list"] = json.dumps(scholarship_data["sub_type_list"])

        await session.execute(
            text(
                """
                INSERT INTO scholarship_types (code, name, name_en, description, description_en,
                                              category, application_cycle, whitelist_enabled,
                                              sub_type_selection_mode, status, sub_type_list)
                VALUES (:code, :name, :name_en, :description, :description_en,
                        :category, :application_cycle, :whitelist_enabled,
                        :sub_type_selection_mode, :status, :sub_type_list)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    name_en = EXCLUDED.name_en,
                    description = EXCLUDED.description,
                    description_en = EXCLUDED.description_en,
                    category = EXCLUDED.category,
                    application_cycle = EXCLUDED.application_cycle,
                    whitelist_enabled = EXCLUDED.whitelist_enabled,
                    sub_type_selection_mode = EXCLUDED.sub_type_selection_mode,
                    status = EXCLUDED.status,
                    sub_type_list = EXCLUDED.sub_type_list
            """
            ),
            {
                **scholarship_data,
                "sub_type_list": scholarship_data.get("sub_type_list"),
            },
        )

    await session.commit()
    print(f"  ✓ {len(scholarships_data)} scholarship types created/updated")


async def seed_application_fields(session: AsyncSession):
    """
    建立申請欄位配置
    """
    print("📝 Creating application field configurations...")

    # 獲取 admin 用戶 ID
    result = await session.execute(text("SELECT id FROM users WHERE nycu_id = 'admin'"))
    admin_id = result.scalar()
    if not admin_id:
        admin_id = 1

    # 逕讀博士獎學金字段（範例）
    direct_phd_fields = [
        {
            "scholarship_type": "direct_phd",
            "field_name": "advisors",
            "field_label": "多位指導教授資訊",
            "field_label_en": "Multiple Advisors Information",
            "field_type": "text",
            "is_required": True,
            "placeholder": "請輸入所有指導教授的姓名（如有多位請以逗號分隔）",
            "max_length": 200,
            "display_order": 1,
            "is_active": True,
            "help_text": "請填寫所有指導教授的姓名",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "direct_phd",
            "field_name": "research_topic_zh",
            "field_label": "研究題目（中文）",
            "field_label_en": "Research Topic (Chinese)",
            "field_type": "text",
            "is_required": True,
            "placeholder": "請輸入研究題目（中文）",
            "max_length": 200,
            "display_order": 2,
            "is_active": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
    ]

    for field_data in direct_phd_fields:
        await session.execute(
            text(
                """
                INSERT INTO application_fields (scholarship_type, field_name, field_label, field_label_en,
                                                field_type, is_required, placeholder, max_length,
                                                display_order, is_active, help_text, created_by, updated_by)
                VALUES (:scholarship_type, :field_name, :field_label, :field_label_en,
                        :field_type, :is_required, :placeholder, :max_length,
                        :display_order, :is_active, :help_text, :created_by, :updated_by)
                ON CONFLICT (scholarship_type, field_name) DO UPDATE SET
                    field_label = EXCLUDED.field_label,
                    field_label_en = EXCLUDED.field_label_en,
                    field_type = EXCLUDED.field_type,
                    is_required = EXCLUDED.is_required,
                    placeholder = EXCLUDED.placeholder,
                    max_length = EXCLUDED.max_length,
                    display_order = EXCLUDED.display_order,
                    is_active = EXCLUDED.is_active,
                    help_text = EXCLUDED.help_text,
                    updated_by = EXCLUDED.updated_by
            """
            ),
            field_data,
        )

    await session.commit()
    print(f"  ✓ {len(direct_phd_fields)} application fields created/updated")


async def seed_development():
    """
    Development environment seed
    對應完整的 init_db.py 流程
    """
    print("🌱 Starting development seed process...")
    print(f"   Environment: {settings.environment}")

    async with AsyncSessionLocal() as session:
        # Try to acquire lock
        if not await acquire_advisory_lock(session):
            print("❌ Another seed process is running. Exiting.")
            return

        try:
            # 1. Lookup tables (參考資料)
            await seed_lookup_tables(session)

            # 2. Test users
            await seed_test_users(session)

            # 3. Scholarships
            await seed_scholarships(session)

            # 4. Application fields
            await seed_application_fields(session)

            print("\n📋 Test User Accounts:")
            print("- Admin: admin@nycu.edu.tw")
            print("- Super Admin: super_admin@nycu.edu.tw")
            print("- Professor: professor@nycu.edu.tw")
            print("- College: college@nycu.edu.tw")
            print("- Student (學士): stu_under@nycu.edu.tw")
            print("- Student (博士): stu_phd@nycu.edu.tw")
            print("- Student (逕讀博士): stu_direct@nycu.edu.tw")
            print("- Student (碩士): stu_master@nycu.edu.tw")

            print("\n✅ Development seed completed successfully!")

        except Exception as e:
            print(f"❌ Error during seed: {e}")
            import traceback

            traceback.print_exc()
            raise
        finally:
            # Always release lock
            await release_advisory_lock(session)
            print("🔓 Released advisory lock")


async def seed_production():
    """
    Production environment seed
    僅建立必要的 admin 用戶
    """
    print("🌱 Starting production seed process...")
    print(f"   Environment: {settings.environment}")

    async with AsyncSessionLocal() as session:
        # Try to acquire lock
        if not await acquire_advisory_lock(session):
            print("❌ Another seed process is running. Exiting.")
            return

        try:
            # Lookup tables still needed
            await seed_lookup_tables(session)

            # Production: Only admin user
            await seed_admin_user(session)

            print("\n⚠️ Production mode: Only admin user configured")
            print("  Please set initial password through admin panel")

            print("\n✅ Production seed completed successfully!")

        except Exception as e:
            print(f"❌ Error during seed: {e}")
            import traceback

            traceback.print_exc()
            raise
        finally:
            # Always release lock
            await release_advisory_lock(session)
            print("🔓 Released advisory lock")


async def main():
    """Main entry point"""
    # Determine mode from command line or environment
    is_prod = "--prod" in sys.argv or settings.environment == "production"

    if is_prod:
        await seed_production()
    else:
        await seed_development()


if __name__ == "__main__":
    asyncio.run(main())
