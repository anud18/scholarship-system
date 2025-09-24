"""
Database initialization script for scholarship system
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base_class import Base
from app.db.session import AsyncSessionLocal, async_engine
from app.models.application import ApplicationStatus, ScholarshipMainType, ScholarshipSubType
from app.models.application_field import ApplicationDocument, ApplicationField
from app.models.email_management import EmailCategory, EmailHistory, EmailStatus, ScheduledEmail, ScheduleStatus
from app.models.enums import ApplicationCycle, QuotaManagementMode, Semester, SubTypeSelectionMode
from app.models.notification import Notification, NotificationPriority, NotificationType
from app.models.scholarship import (
    ScholarshipCategory,
    ScholarshipConfiguration,
    ScholarshipRule,
    ScholarshipStatus,
    ScholarshipSubTypeConfig,
    ScholarshipType,
)
from app.models.student import Degree  # 查詢表 (Reference data only)
from app.models.system_setting import EmailTemplate, SendingType
from app.models.user import EmployeeStatus, User, UserRole, UserType

logger = logging.getLogger(__name__)


async def initLookupTables(session: AsyncSession) -> None:
    """Initialize lookup tables using the dedicated lookup tables module"""

    # Import here to avoid circular imports
    from app.core.init_lookup_tables import initLookupTables as initLookup

    # Check if lookup tables are already initialized
    result = await session.execute(select(Degree))
    degrees = result.scalars().all()

    if len(degrees) == 0:
        logger.info("Lookup tables not found, initializing...")
        await initLookup(session)
    else:
        logger.info("Lookup tables already initialized, skipping...")
        logger.info(f"Found {len(degrees)} degrees in database")


async def createTestUsers(session: AsyncSession) -> list[User]:
    """Create test users"""

    print("👥 Creating test users...")

    test_users_data = [
        {
            "nycu_id": "admin",
            "name": "系統管理員",
            "email": "admin@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "9000",
            "dept_name": "教務處",
            "role": UserRole.ADMIN,
        },
        {
            "nycu_id": "super_admin",
            "name": "超級管理員",
            "email": "super_admin@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "9000",
            "dept_name": "教務處",
            "role": UserRole.SUPER_ADMIN,
        },
        {
            "nycu_id": "professor",
            "name": "李教授",
            "email": "professor@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "7000",
            "dept_name": "資訊學院",
            "role": UserRole.PROFESSOR,
        },
        {
            "nycu_id": "college",
            "name": "學院審核員",
            "email": "college@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "7000",
            "dept_name": "資訊學院",
            "role": UserRole.COLLEGE,
        },
        {
            "nycu_id": "stu_under",
            "name": "陳小明",
            "email": "stu_under@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "stu_phd",
            "name": "王博士",
            "email": "stu_phd@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "stu_direct",
            "name": "李逕升",
            "email": "stu_direct@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "stu_master",
            "name": "張碩士",
            "email": "stu_master@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "phd_china",
            "name": "陸生",
            "email": "phd_china@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        # Computer Science College Users
        {
            "nycu_id": "cs_professor",
            "name": "李資訊教授",
            "email": "cs_professor@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.PROFESSOR,
        },
        {
            "nycu_id": "cs_college",
            "name": "資訊學院審核員",
            "email": "cs_college@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.COLLEGE,
        },
        {
            "nycu_id": "cs_phd001",
            "name": "王博士研究生",
            "email": "cs_phd001@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "cs_phd002",
            "name": "陳AI博士",
            "email": "cs_phd002@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "cs_phd003",
            "name": "林機器學習博士",
            "email": "cs_phd003@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "cs_phd_intl",
            "name": "國際博士生",
            "email": "cs_phd_intl@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT,
        },
        # Electrical Engineering College Users
        {
            "nycu_id": "ee_professor",
            "name": "黃電機教授",
            "email": "ee_professor@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "EE",
            "dept_name": "電機工程學系",
            "role": UserRole.PROFESSOR,
        },
        {
            "nycu_id": "ee_college",
            "name": "電機學院審核員",
            "email": "ee_college@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "EE",
            "dept_name": "電機工程學系",
            "role": UserRole.COLLEGE,
        },
        {
            "nycu_id": "ee_phd001",
            "name": "吳電力博士",
            "email": "ee_phd001@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "EE",
            "dept_name": "電機工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "ee_phd002",
            "name": "劉通訊博士",
            "email": "ee_phd002@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "EE",
            "dept_name": "電機工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "ee_phd003",
            "name": "蔡半導體博士",
            "email": "ee_phd003@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "EE",
            "dept_name": "電機工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "ee_phd_exchange",
            "name": "交換博士生",
            "email": "ee_phd_exchange@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "EE",
            "dept_name": "電機工程學系",
            "role": UserRole.STUDENT,
        },
        # Mechanical Engineering College Users
        {
            "nycu_id": "me_professor",
            "name": "趙機械教授",
            "email": "me_professor@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "ME",
            "dept_name": "機械工程學系",
            "role": UserRole.PROFESSOR,
        },
        {
            "nycu_id": "me_college",
            "name": "工學院審核員",
            "email": "me_college@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "ME",
            "dept_name": "機械工程學系",
            "role": UserRole.COLLEGE,
        },
        {
            "nycu_id": "me_phd001",
            "name": "許製造博士",
            "email": "me_phd001@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "ME",
            "dept_name": "機械工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "me_phd002",
            "name": "周熱流博士",
            "email": "me_phd002@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "ME",
            "dept_name": "機械工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "me_phd003",
            "name": "楊材料博士",
            "email": "me_phd003@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "ME",
            "dept_name": "機械工程學系",
            "role": UserRole.STUDENT,
        },
        {
            "nycu_id": "me_phd_robotics",
            "name": "機器人博士研究員",
            "email": "me_phd_robotics@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "ME",
            "dept_name": "機械工程學系",
            "role": UserRole.STUDENT,
        },
    ]

    created_users = []

    for user_data in test_users_data:
        # Check if user exists
        result = await session.execute(select(User).where(User.nycu_id == user_data["nycu_id"]))
        existing = result.scalar_one_or_none()

        if not existing:
            user = User(
                nycu_id=user_data["nycu_id"],
                name=user_data["name"],
                email=user_data["email"],
                user_type=UserType(user_data["user_type"]),
                status=EmployeeStatus(user_data["status"]),
                dept_code=user_data["dept_code"],
                dept_name=user_data["dept_name"],
                role=user_data["role"],
            )
            session.add(user)
            created_users.append(user)

    await session.commit()

    # Refresh to get IDs
    for user in created_users:
        await session.refresh(user)

    print(f"✅ Created {len(created_users)} test users")
    return created_users


async def createTestScholarships(session: AsyncSession) -> None:
    """Create test scholarship data with dev-friendly settings"""

    print("🎓 Creating test scholarship data...")

    # ==== 基本獎學金 ====
    scholarships_data = [
        {
            "code": "undergraduate_freshman",
            "name": "學士班新生獎學金",
            "name_en": "Undergraduate Freshman Scholarship",
            "description": "適用於學士班新生 白名單 與 地區劃分",
            "description_en": "For undergraduate freshmen, white list and regional",
            "category": ScholarshipCategory.UNDERGRADUATE_FRESHMAN.value,
            "application_cycle": ApplicationCycle.SEMESTER,
            "whitelist_enabled": not settings.debug,
            "sub_type_selection_mode": SubTypeSelectionMode.SINGLE,
            "status": ScholarshipStatus.ACTIVE.value,
            "created_by": 1,
            "updated_by": 1,
        },
        {
            "code": "phd",
            "name": "博士生獎學金",
            "name_en": "PhD Scholarship",
            "description": "適用於一般博士生，需完整研究計畫和教授推薦 國科會/教育部博士生獎學金",
            "description_en": "For regular PhD students, requires complete research plan and professor recommendation",
            "category": ScholarshipCategory.PHD.value,
            "application_cycle": ApplicationCycle.YEARLY,
            "sub_type_list": ["nstc", "moe_1w", "moe_2w"],
            "whitelist_enabled": False,
            "sub_type_selection_mode": SubTypeSelectionMode.HIERARCHICAL,
            "status": ScholarshipStatus.ACTIVE.value,
            "created_by": 1,
            "updated_by": 1,
        },
        {
            "code": "direct_phd",
            "name": "逕讀博士獎學金",
            "name_en": "Direct PhD Scholarship",
            "description": "適用於逕讀博士班學生，需完整研究計畫",
            "description_en": "For direct PhD students, requires complete research plan",
            "category": ScholarshipCategory.DIRECT_PHD.value,
            "application_cycle": ApplicationCycle.YEARLY,
            "whitelist_enabled": not settings.debug,
            "sub_type_selection_mode": SubTypeSelectionMode.SINGLE,
            "status": ScholarshipStatus.ACTIVE.value,
            "created_by": 1,
            "updated_by": 1,
        },
    ]

    for scholarship_data in scholarships_data:
        # Check if scholarship already exists
        result = await session.execute(select(ScholarshipType).where(ScholarshipType.code == scholarship_data["code"]))
        existing = result.scalar_one_or_none()

        if not existing:
            scholarship = ScholarshipType(**scholarship_data)
            session.add(scholarship)
        else:
            # 更新現有的獎學金資料
            for key, value in scholarship_data.items():
                setattr(existing, key, value)

    # ==== 獎學金規則 ====
    # Get admin user for created_by field
    admin_user = await session.execute(select(User).where(User.role == UserRole.ADMIN))
    admin = admin_user.scalar_one_or_none()
    admin_id = admin.id if admin else 1

    scholarship_rules_data = [
        # 博士生獎學金 共同規則 - 114學年度
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "academic_year": 114,
            "semester": None,  # 學年制獎學金不需要學期
            "is_template": False,
            "rule_name": "博士生獎學金 博士生身分",
            "rule_type": "student",
            "tag": "博士生",
            "description": "博士生獎學金需要博士生身分",
            "condition_field": "std_degree",
            "operator": "==",
            "expected_value": "1",
            "message": "博士生獎學金需要博士生身分",
            "message_en": "PhD scholarship requires PhD student status",
            "is_hard_rule": True,
            "is_warning": False,
            "priority": 1,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "academic_year": 114,
            "semester": None,  # 學年制獎學金不需要學期
            "is_template": False,
            "rule_name": "博士生獎學金 在學生身分 1: 在學 2: 應畢 3: 延畢",
            "rule_type": "student_term",
            "tag": "在學生",
            "description": "博士生獎學金需要在學生身分 1: 在學 2: 應畢 3: 延畢",
            "condition_field": "trm_studystatus",
            "operator": "in",
            "expected_value": "1,2,3",
            "message": "博士生獎學金需要在學生身分 1: 在學 2: 應畢 3: 延畢",
            "message_en": "PhD scholarship requires active student status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 2,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "academic_year": 114,
            "semester": None,  # 學年制獎學金不需要學期
            "is_template": False,
            "rule_name": "博士生獎學金 非在職生身分 需要為一般生",
            "rule_type": "student",
            "tag": "非在職生",
            "description": "博士生獎學金需要非在職生身分 需要為一般生",
            "condition_field": "std_schoolid",
            "operator": "==",
            "expected_value": "1",
            "message": "博士生獎學金需要非在職生身分 需要為一般生",
            "message_en": "PhD scholarship ",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 3,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "academic_year": 114,
            "semester": None,  # 學年制獎學金不需要學期
            "is_template": False,
            "rule_name": "博士生獎學金 非陸港澳生身分",
            "rule_type": "student",
            "tag": "非陸生",
            "description": "博士生獎學金需要非陸港澳生身分",
            "condition_field": "std_identity",
            "operator": "!=",
            "expected_value": "17",
            "message": "博士生獎學金需要非陸港澳生身分",
            "message_en": "PhD scholarship requires non-Mainland China, Hong Kong, or Macao student status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 4,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        # 博士生獎學金 教育部獎學金 (一萬元) 5. 中華民國國籍 6. 一至三年級
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_1w",
            "academic_year": 114,
            "semester": None,  # 學年制獎學金不需要學期
            "is_template": False,
            "rule_name": "博士生獎學金 教育部獎學金 中華民國國籍",
            "tag": "中華民國國籍",
            "description": "博士生獎學金需要中華民國國籍",
            "rule_type": "student",
            "condition_field": "std_nation",
            "operator": "==",
            "expected_value": "中華民國",
            "message": "博士生獎學金需要中華民國國籍",
            "message_en": "PhD scholarship requires Chinese nationality",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 5,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_1w",
            "academic_year": 114,
            "semester": None,  # 學年制獎學金不需要學期
            "is_template": False,
            "rule_name": "博士生獎學金 教育部獎學金 一至三年級(1-6學期)",
            "tag": "三年級以下",
            "description": "博士生獎學金需要一至三年級",
            "rule_type": "student",
            "condition_field": "std_termcount",
            "operator": "in",
            "expected_value": "1,2,3,4,5,6",
            "message": "博士生獎學金需要一至三年級",
            "message_en": "PhD scholarship requires 1-3rd year",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 6,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        # 博士生獎學金 教育部獎學金 (兩萬元) 7. 中華民國國籍 8. 一至三年級
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_2w",
            "academic_year": 114,
            "semester": None,  # 學年制獎學金不需要學期
            "is_template": False,
            "rule_name": "博士生獎學金 教育部獎學金 中華民國國籍",
            "tag": "中華民國國籍",
            "description": "博士生獎學金需要中華民國國籍",
            "rule_type": "student",
            "condition_field": "std_nation",
            "operator": "==",
            "expected_value": "中華民國",
            "message": "博士生獎學金需要中華民國國籍",
            "message_en": "PhD scholarship requires Chinese nationality",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 7,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_2w",
            "academic_year": 114,
            "semester": None,  # 學年制獎學金不需要學期
            "is_template": False,
            "rule_name": "博士生獎學金 教育部獎學金 一至三年級(1-6學期)",
            "tag": "三年級以下",
            "description": "博士生獎學金需要一至三年級",
            "rule_type": "student",
            "condition_field": "std_termcount",
            "operator": "in",
            "expected_value": "1,2,3,4,5,6",
            "message": "博士生獎學金需要一至三年級",
            "message_en": "PhD scholarship requires 1-3rd year",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 8,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        # 逕博獎學金 共同規則 1. 博士生身分 2. 在學生身分 3. 非在職生身分 4. 非陸港澳生身分 5. 逕博生身分 6. 第一學年
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 114,
            "semester": None,
            "is_template": False,
            "rule_name": "逕讀博士獎學金 博士生身分",
            "tag": "博士生",
            "description": "逕讀博士獎學金需要博士生身分",
            "rule_type": "student",
            "condition_field": "std_degree",
            "operator": "==",
            "expected_value": "1",
            "message": "逕讀博士獎學金需要博士生身分",
            "message_en": "Direct PhD scholarship requires PhD student status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 1,
            "is_active": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 114,
            "semester": None,
            "is_template": False,
            "rule_name": "逕讀博士獎學金 在學生身分 1: 在學 2: 應畢 3: 延畢",
            "rule_type": "student_term",
            "tag": "在學生",
            "condition_field": "trm_studystatus",
            "operator": "in",
            "expected_value": "1,2,3",
            "message": "逕讀博士獎學金需要在學生身分 1: 在學 2: 應畢 3: 延畢",
            "message_en": "Direct PhD scholarship requires active student status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 2,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 114,
            "semester": None,
            "is_template": False,
            "rule_name": "逕讀博士獎學金 非在職生身分 需要為一般生",
            "rule_type": "student",
            "tag": "非在職生",
            "condition_field": "std_schoolid",
            "operator": "==",
            "expected_value": "1",
            "message": "逕讀博士獎學金需要非在職生身分 需要為一般生",
            "message_en": "Direct PhD scholarship requires regular student status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 3,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 114,
            "semester": None,
            "is_template": False,
            "rule_name": "逕讀博士獎學金 非陸港澳生身分",
            "rule_type": "student",
            "tag": "非陸生",
            "description": "逕讀博士獎學金需要非陸港澳生身分",
            "condition_field": "std_identity",
            "operator": "!=",
            "expected_value": "17",
            "message": "逕讀博士獎學金需要非陸港澳生身分",
            "message_en": "Direct PhD scholarship requires non-Mainland China, Hong Kong, or Macao student status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 4,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 114,
            "semester": None,
            "is_template": False,
            "rule_name": "逕讀博士獎學金 逕博生身分 8: 大學逕博 9: 碩士逕博 10: 跨校學士逕博 11: 跨校碩士逕博",
            "rule_type": "student",
            "tag": "逕博生",
            "description": "逕讀博士獎學金需要逕博生身分",
            "condition_field": "std_enrollterm",
            "operator": "in",
            "expected_value": "8,9,10,11",
            "message": "逕讀博士獎學金需要逕博生身分",
            "message_en": "Direct PhD scholarship requires direct PhD student status",
            "is_hard_rule": True,
            "is_warning": False,
            "priority": 5,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 114,
            "semester": None,
            "is_template": False,
            "rule_name": "逕讀博士獎學金 第一學年",
            "rule_type": "student",
            "tag": "第一學年",
            "description": "逕讀博士獎學金需要第一學年",
            "condition_field": "std_termcount",
            "operator": "in",
            "expected_value": "1,2",
            "message": "逕讀博士獎學金需要第一學年",
            "message_en": "Direct PhD scholarship requires first year",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 6,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        # 學士新生獎學金 共同規則 1.學士生身分
        {
            "scholarship_type_id": 1,
            "sub_type": None,
            "academic_year": 114,
            "semester": Semester.FIRST,
            "is_template": False,
            "rule_name": "學士新生獎學金 學士生身分",
            "tag": "學士生",
            "description": "學士新生獎學金需要學士生身分",
            "rule_type": "student",
            "condition_field": "std_degree",
            "operator": "==",
            "expected_value": "3",
            "message": "學士新生獎學金需要學士生身分",
            "message_en": "Undergraduate scholarship requires undergraduate student status",
            "is_hard_rule": True,
            "is_warning": False,
            "priority": 1,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        # 一般生入學管道提醒規則
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_1w",
            "academic_year": 114,
            "semester": None,
            "is_template": False,
            "rule_name": "博士生獎學金 一般生入學管道提醒",
            "tag": "一般生",
            "description": "一般生身份學生，其入學管道可能為2/5/6/7，請承辦人確認。若為2/5/6/7請特別留意（標紅字）。",
            "rule_type": "student",
            "condition_field": "std_enrollterm",
            "operator": "in",
            "expected_value": "2,5,6,7",
            "message": "此學生為一般生，但入學管道為2/5/6/7，請承辦人確認（標紅字）。",
            "message_en": "This student is a regular student but has an enrollment type of 2/5/6/7. Please double-check (highlighted in red).",
            "is_hard_rule": False,
            "is_warning": True,
            "priority": 99,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_2w",
            "academic_year": 114,
            "semester": None,
            "is_template": False,
            "rule_name": "博士生獎學金 一般生入學管道提醒",
            "tag": "一般生",
            "description": "一般生身份學生，其入學管道可能為2/5/6/7，請承辦人確認。若為2/5/6/7請特別留意（標紅字）。",
            "rule_type": "student",
            "condition_field": "std_enrollterm",
            "operator": "in",
            "expected_value": "2,5,6,7",
            "message": "此學生為一般生，但入學管道為2/5/6/7，請承辦人確認（標紅字）。",
            "message_en": "This student is a regular student but has an enrollment type of 2/5/6/7. Please double-check (highlighted in red).",
            "is_hard_rule": False,
            "is_warning": True,
            "priority": 99,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        # 中華民國國籍生身份提醒規則
        {
            "scholarship_type_id": 2,
            "sub_type": "nstc",
            "academic_year": 114,
            "semester": None,
            "is_template": False,
            "rule_name": "中華民國國籍生身份提醒",
            "tag": "中華民國國籍",
            "description": "中華民國國籍生的身份可能為僑生、外籍生，請承辦人自行確認（3/4標紅字）。",
            "rule_type": "student",
            "condition_field": "std_identity",
            "operator": "in",
            "expected_value": "3,4",
            "message": "此中華民國國籍生身份為僑生或外籍生，請承辦人確認（標紅字）。",
            "message_en": "This ROC national student is classified as Overseas Chinese or International Student. Please double-check (highlighted in red).",
            "is_hard_rule": False,
            "is_warning": True,
            "priority": 100,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        # === 規則模板 ===
        # 博士生獎學金基本資格模板
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "academic_year": None,
            "semester": None,
            "is_template": True,
            "template_name": "博士生基本資格模板",
            "template_description": "博士生獎學金的基本資格檢查規則模板",
            "rule_name": "博士生身分檢查",
            "rule_type": "student",
            "tag": "博士生",
            "description": "檢查申請者是否具有博士生身分",
            "condition_field": "std_degree",
            "operator": "==",
            "expected_value": "1",
            "message": "申請者必須具有博士生身分",
            "message_en": "Applicant must have PhD student status",
            "is_hard_rule": True,
            "is_warning": False,
            "priority": 1,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "academic_year": None,
            "semester": None,
            "is_template": True,
            "template_name": "博士生基本資格模板",
            "template_description": "博士生獎學金的基本資格檢查規則模板",
            "rule_name": "在學狀態檢查",
            "rule_type": "student_term",
            "tag": "在學生",
            "description": "檢查申請者的在學狀態",
            "condition_field": "trm_studystatus",
            "operator": "in",
            "expected_value": "1,2,3",
            "message": "申請者必須為在學、應畢或延畢狀態",
            "message_en": "Applicant must be in active, graduating, or extended study status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 2,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        # 學士班新生獎學金模板
        {
            "scholarship_type_id": 1,
            "sub_type": None,
            "academic_year": None,
            "semester": None,
            "is_template": True,
            "template_name": "學士班新生資格模板",
            "template_description": "學士班新生獎學金的基本資格檢查規則模板",
            "rule_name": "學士班新生身分檢查",
            "rule_type": "student",
            "tag": "學士班新生",
            "description": "檢查申請者是否為學士班新生",
            "condition_field": "std_degree",
            "operator": "==",
            "expected_value": "3",
            "message": "申請者必須為學士班學生",
            "message_en": "Applicant must be undergraduate student",
            "is_hard_rule": True,
            "is_warning": False,
            "priority": 1,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        # 逕讀博士獎學金模板
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": None,
            "semester": None,
            "is_template": True,
            "template_name": "逕讀博士資格模板",
            "template_description": "逕讀博士獎學金的基本資格檢查規則模板",
            "rule_name": "逕讀博士身分檢查",
            "rule_type": "student",
            "tag": "逕讀博士",
            "description": "檢查申請者是否為逕讀博士生",
            "condition_field": "std_degree",
            "operator": "==",
            "expected_value": "1",
            "message": "申請者必須為逕讀博士生",
            "message_en": "Applicant must be direct PhD student",
            "is_hard_rule": True,
            "is_warning": False,
            "priority": 1,
            "is_active": True,
            "is_initial_enabled": True,
            "is_renewal_enabled": True,
            "created_by": admin_id,
            "updated_by": admin_id,
        },
    ]

    for scholarship_rule in scholarship_rules_data:
        scholarship_rule = ScholarshipRule(**scholarship_rule)
        session.add(scholarship_rule)

    await session.commit()

    # === 創建子類型配置 ===
    print("🔧 Creating sub-type configurations...")

    # 獲取已創建的獎學金類型
    result = await session.execute(select(ScholarshipType))
    scholarships = result.scalars().all()

    # 創建子類型配置
    sub_type_configs_data = []

    for scholarship in scholarships:
        if scholarship.code == "undergraduate_freshman":
            # 學士班新生獎學金已移除地區子類型配置
            pass
        elif scholarship.code == "phd":
            # 博士生獎學金的子類型配置
            sub_type_configs_data.extend(
                [
                    {
                        "scholarship_type_id": scholarship.id,
                        "sub_type_code": "nstc",
                        "name": "國科會博士生獎學金",
                        "name_en": "NSTC PHD Scholarship",
                        "description": "國科會博士生獎學金，適用於符合條件的博士生",
                        "description_en": "NSTC PHD Scholarship for eligible PhD students",
                        "amount": None,  # 使用主獎學金金額
                        "display_order": 1,
                        "is_active": True,
                        "created_by": 1,
                        "updated_by": 1,
                    },
                    {
                        "scholarship_type_id": scholarship.id,
                        "sub_type_code": "moe_1w",
                        "name": "教育部博士生獎學金 (指導教授配合款一萬)",
                        "name_en": "MOE PHD Scholarship (Professor Match 10K)",
                        "description": "教育部博士生獎學金，指導教授配合款一萬元",
                        "description_en": "MOE PHD Scholarship with professor match of 10K",
                        "amount": None,  # 使用主獎學金金額
                        "display_order": 2,
                        "is_active": True,
                        "created_by": 1,
                        "updated_by": 1,
                    },
                    {
                        "scholarship_type_id": scholarship.id,
                        "sub_type_code": "moe_2w",
                        "name": "教育部博士生獎學金 (指導教授配合款兩萬)",
                        "name_en": "MOE PHD Scholarship (Professor Match 20K)",
                        "description": "教育部博士生獎學金，指導教授配合款兩萬元",
                        "description_en": "MOE PHD Scholarship with professor match of 20K",
                        "amount": None,  # 使用主獎學金金額
                        "display_order": 3,
                        "is_active": True,
                        "created_by": 1,
                        "updated_by": 1,
                    },
                ]
            )
        # 注意：general 子類型不需要特別配置，因為它代表預設情況

    # 創建子類型配置
    for config_data in sub_type_configs_data:
        # 檢查是否已存在
        result = await session.execute(
            select(ScholarshipSubTypeConfig).where(
                ScholarshipSubTypeConfig.scholarship_type_id == config_data["scholarship_type_id"],
                ScholarshipSubTypeConfig.sub_type_code == config_data["sub_type_code"],
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            config = ScholarshipSubTypeConfig(**config_data)
            session.add(config)

    await session.commit()
    print("✅ Sub-type configurations created successfully!")

    # === 創建名額管理配置 ===
    await createQuotaManagementConfigurations(session)
    await createTestApplicationsAndQuotaUsage(session)

    print("✅ Test scholarship data created successfully!")

    if settings.debug:
        print("🔧 DEV MODE: All scholarships are open for application")
        print("🔧 DEV MODE: Whitelist checks are bypassed")


async def createQuotaManagementConfigurations(session: AsyncSession) -> None:
    """Create quota management configurations for scholarships"""

    print("📊 Creating quota management configurations...")

    # 獲取管理員用戶ID
    result = await session.execute(select(User).where(User.nycu_id == "admin"))
    admin_user = result.scalar_one_or_none()
    admin_id = admin_user.id if admin_user else 1

    # 獲取已創建的獎學金類型
    result = await session.execute(select(ScholarshipType))
    scholarships = result.scalars().all()

    # 設定基本時間參數 - 使用台灣時間 (UTC+8)
    taiwan_tz = timezone(timedelta(hours=8))
    now = datetime.now(taiwan_tz)
    current_year = now.year

    # 申請時間設定 - 使用台灣時間，更實際的時間安排
    base_start = datetime(current_year, 9, 1, 0, 0, 0, tzinfo=taiwan_tz)  # 9月1日 00:00 台灣時間
    base_end = datetime(current_year, 10, 31, 23, 59, 59, tzinfo=taiwan_tz)  # 10月31日 23:59:59 台灣時間
    renewal_start = datetime(current_year, 8, 1, 0, 0, 0, tzinfo=taiwan_tz)  # 續領8月1日 00:00 台灣時間
    renewal_end = datetime(current_year, 9, 15, 23, 59, 59, tzinfo=taiwan_tz)  # 續領9月15日 23:59:59 台灣時間

    # 博士生獎學金子類型配額配置 - 統一且清晰的配額分配
    PHD_QUOTA_CONFIG = {
        "nstc": {
            "E": 6,
            "C": 5,
            "I": 5,
            "S": 4,
            "B": 3,
            "O": 4,
            "D": 4,
            "1": 5,
            "6": 3,
            "7": 3,
            "M": 3,
            "A": 3,
            "K": 2,
        },
        "moe_1w": {
            "E": 7,
            "C": 6,
            "I": 6,
            "S": 5,
            "B": 4,
            "O": 5,
            "D": 5,
            "1": 6,
            "6": 4,
            "7": 4,
            "M": 3,
            "A": 3,
            "K": 2,
        },
        "moe_2w": {
            "E": 8,
            "C": 7,
            "I": 7,
            "S": 6,
            "B": 5,
            "O": 6,
            "D": 6,
            "1": 7,
            "6": 5,
            "7": 5,
            "M": 4,
            "A": 4,
            "K": 3,
        },
    }

    def create_base_config(scholarship, academic_year, **overrides):
        """創建基礎配置模板"""
        # 設定有效期間 - 學年度的完整期間，使用台灣時間
        academic_start = datetime(current_year, 8, 1, 0, 0, 0, tzinfo=taiwan_tz)  # 8月1日 00:00 台灣時間
        academic_end = datetime(current_year + 1, 7, 31, 23, 59, 59, tzinfo=taiwan_tz)  # 隔年7月31日 23:59:59 台灣時間

        base_config = {
            "scholarship_type_id": scholarship.id,
            "academic_year": academic_year,
            "version": "1.0",
            "created_by": admin_id,
            "updated_by": admin_id,
            "is_active": True,
            "currency": "TWD",
            "whitelist_student_ids": {},
            "effective_start_date": academic_start,  # 配置生效開始時間
            "effective_end_date": academic_end,  # 配置生效結束時間
        }
        base_config.update(overrides)
        return base_config

    def create_review_schedule(
        start_date,
        end_date,
        renewal_start,
        renewal_end,
        professor_required=False,
        college_required=False,
    ):
        """創建審查時程配置"""
        schedule = {
            "requires_professor_recommendation": professor_required,
            "requires_college_review": college_required,
            "review_deadline": end_date + timedelta(days=30),
        }

        # 一般申請審查時程
        if professor_required:
            schedule.update(
                {
                    "professor_review_start": end_date + timedelta(days=1),
                    "professor_review_end": end_date + timedelta(days=14),
                }
            )

        if college_required:
            start_offset = 15 if professor_required else 1
            schedule.update(
                {
                    "college_review_start": end_date + timedelta(days=start_offset),
                    "college_review_end": end_date + timedelta(days=start_offset + 14),
                }
            )

        # 續領申請審查時程
        if professor_required:
            schedule.update(
                {
                    "renewal_professor_review_start": renewal_end + timedelta(days=1),
                    "renewal_professor_review_end": renewal_end + timedelta(days=10),
                }
            )

        if college_required:
            renewal_start_offset = 11 if professor_required else 1
            schedule.update(
                {
                    "renewal_college_review_start": renewal_end + timedelta(days=renewal_start_offset),
                    "renewal_college_review_end": renewal_end + timedelta(days=renewal_start_offset + 10),
                }
            )

        return schedule

    # 配置數據生成 - 包含113和114學年度
    quota_configs_data = []

    # 113學年度 - 舊配置用於驗證系統
    def create_113_configs():
        """創建113學年度配置 - 用於測試舊配置兼容性"""
        configs_113 = []

        for scholarship in scholarships:
            if scholarship.code == "undergraduate_freshman":
                # 113學年度學士班新生獎學金 - 每學期制
                for semester in [Semester.FIRST, Semester.SECOND]:
                    sem_name = "第一學期" if semester == Semester.FIRST else "第二學期"
                    sem_code = "first" if semester == Semester.FIRST else "second"

                    config = create_base_config(
                        scholarship,
                        113,
                        semester=semester,
                        config_name=f"113學年度學士班新生獎學金 - {sem_name}",
                        config_code=f"config_{scholarship.code}_113_{sem_code}",
                        description=f"113學年度{sem_name}學士班新生獎學金配置，已結束申請期間",
                        description_en=f"AY113-{sem_code} undergraduate freshman scholarship (application period ended)",
                        amount=45000,  # 113年較低的金額
                        has_quota_limit=False,
                        has_college_quota=False,
                        quota_management_mode=QuotaManagementMode.NONE,
                        total_quota=None,
                        quotas=None,
                        # 113年的申請時間 (已過期)
                        application_start_date=datetime(current_year - 1, 9, 1, 0, 0, 0, tzinfo=taiwan_tz),
                        application_end_date=datetime(current_year - 1, 10, 31, 23, 59, 59, tzinfo=taiwan_tz),
                        renewal_application_start_date=datetime(current_year - 1, 8, 1, 0, 0, 0, tzinfo=taiwan_tz),
                        renewal_application_end_date=datetime(current_year - 1, 9, 15, 23, 59, 59, tzinfo=taiwan_tz),
                        # 113年的有效期間 (已過期)
                        effective_start_date=datetime(current_year - 1, 8, 1, 0, 0, 0, tzinfo=taiwan_tz),
                        effective_end_date=datetime(current_year, 7, 31, 23, 59, 59, tzinfo=taiwan_tz),
                        is_active=True,
                    )
                    config.update(
                        create_review_schedule(
                            datetime(current_year - 1, 9, 1, tzinfo=taiwan_tz),
                            datetime(current_year - 1, 10, 31, tzinfo=taiwan_tz),
                            datetime(current_year - 1, 8, 1, tzinfo=taiwan_tz),
                            datetime(current_year - 1, 9, 15, tzinfo=taiwan_tz),
                            professor_required=False,
                            college_required=False,
                        )
                    )
                    configs_113.append(config)

            elif scholarship.code == "phd":
                # 113學年度博士生獎學金 - 舊的矩陣配額
                old_phd_config = {
                    "nstc": {
                        "E": 5,
                        "C": 4,
                        "I": 4,
                        "S": 3,
                        "B": 3,
                        "O": 3,
                        "D": 3,
                        "1": 4,
                        "6": 3,
                        "7": 3,
                        "M": 2,
                        "A": 2,
                        "K": 1,
                    },
                    "moe_1w": {
                        "E": 6,
                        "C": 5,
                        "I": 5,
                        "S": 4,
                        "B": 3,
                        "O": 4,
                        "D": 4,
                        "1": 5,
                        "6": 3,
                        "7": 3,
                        "M": 3,
                        "A": 3,
                        "K": 1,
                    },
                    "moe_2w": {
                        "E": 8,
                        "C": 6,
                        "I": 6,
                        "S": 5,
                        "B": 4,
                        "O": 5,
                        "D": 5,
                        "1": 6,
                        "6": 4,
                        "7": 4,
                        "M": 3,
                        "A": 3,
                        "K": 2,
                    },
                }

                total_old_quota = sum(sum(quotas.values()) for quotas in old_phd_config.values())

                config = create_base_config(
                    scholarship,
                    113,
                    semester=None,  # 學年制
                    config_name="113學年度博士生獎學金配置 - 矩陣配額管理",
                    config_code=f"config_{scholarship.code}_113",
                    description="113學年度博士生獎學金配置，已結束申請期間",
                    description_en="AY113 PhD scholarship with matrix allocation (application period ended)",
                    amount=55000,  # 113年的金額
                    has_quota_limit=True,
                    has_college_quota=True,
                    quota_management_mode=QuotaManagementMode.MATRIX_BASED,
                    total_quota=total_old_quota,
                    quotas=old_phd_config,
                    # 113年的申請時間 (已過期)
                    application_start_date=datetime(current_year - 1, 8, 1, 0, 0, 0, tzinfo=taiwan_tz),
                    application_end_date=datetime(current_year - 1, 9, 30, 23, 59, 59, tzinfo=taiwan_tz),
                    renewal_application_start_date=datetime(current_year - 1, 7, 1, 0, 0, 0, tzinfo=taiwan_tz),
                    renewal_application_end_date=datetime(current_year - 1, 8, 15, 23, 59, 59, tzinfo=taiwan_tz),
                    # 113年的有效期間 (已過期)
                    effective_start_date=datetime(current_year - 1, 8, 1, 0, 0, 0, tzinfo=taiwan_tz),
                    effective_end_date=datetime(current_year, 7, 31, 23, 59, 59, tzinfo=taiwan_tz),
                    is_active=True,
                )
                config.update(
                    create_review_schedule(
                        datetime(current_year - 1, 8, 1, tzinfo=taiwan_tz),
                        datetime(current_year - 1, 9, 30, tzinfo=taiwan_tz),
                        datetime(current_year - 1, 7, 1, tzinfo=taiwan_tz),
                        datetime(current_year - 1, 8, 15, tzinfo=taiwan_tz),
                        professor_required=True,
                        college_required=True,
                    )
                )
                configs_113.append(config)

            elif scholarship.code == "direct_phd":
                # 113學年度逕讀博士獎學金 - 學年制（舊配置，已過期）
                config = create_base_config(
                    scholarship,
                    113,
                    semester=None,
                    config_name="113學年度逕讀博士獎學金配置 - 學年制",
                    config_code=f"config_{scholarship.code}_113",
                    description="113學年度逕讀博士獎學金配置（學年制），已結束申請期間",
                    description_en="AY113 direct PhD scholarship (academic year) - application period ended",
                    amount=75000,  # 113年的金額
                    has_quota_limit=False,
                    has_college_quota=False,
                    quota_management_mode=QuotaManagementMode.NONE,
                    total_quota=None,
                    quotas=None,
                    # 113年的申請時間 (已過期)
                    application_start_date=datetime(current_year - 1, 9, 1, 0, 0, 0, tzinfo=taiwan_tz),
                    application_end_date=datetime(current_year - 1, 10, 31, 23, 59, 59, tzinfo=taiwan_tz),
                    renewal_application_start_date=datetime(current_year - 1, 8, 1, 0, 0, 0, tzinfo=taiwan_tz),
                    renewal_application_end_date=datetime(current_year - 1, 9, 15, 23, 59, 59, tzinfo=taiwan_tz),
                    # 113年的有效期間 (已過期)
                    effective_start_date=datetime(current_year - 1, 8, 1, 0, 0, 0, tzinfo=taiwan_tz),
                    effective_end_date=datetime(current_year, 7, 31, 23, 59, 59, tzinfo=taiwan_tz),
                    is_active=True,
                )
                config.update(
                    create_review_schedule(
                        datetime(current_year - 1, 9, 1, tzinfo=taiwan_tz),
                        datetime(current_year - 1, 10, 31, tzinfo=taiwan_tz),
                        datetime(current_year - 1, 8, 1, tzinfo=taiwan_tz),
                        datetime(current_year - 1, 9, 15, tzinfo=taiwan_tz),
                        professor_required=True,
                        college_required=True,
                    )
                )
                configs_113.append(config)

        return configs_113

    # 114學年度 - 當前配置
    def create_114_configs():
        """創建114學年度配置 - 當前活躍配置"""
        configs_114 = []

        for scholarship in scholarships:
            scholarship_configs = []

            if scholarship.code == "undergraduate_freshman":
                # 學士班新生獎學金 - 每學期制，無配額限制
                for semester in [Semester.FIRST, Semester.SECOND]:
                    sem_name = "第一學期" if semester == Semester.FIRST else "第二學期"
                    sem_code = "first" if semester == Semester.FIRST else "second"

                    # 為第二學期設定合理時間（翌年 2/1 至 3/31；續領 1/1 至 1/31）
                    if semester == Semester.FIRST:
                        app_start = base_start
                        app_end = base_end
                        ren_start = renewal_start
                        ren_end = renewal_end
                    else:
                        app_start = datetime(current_year + 1, 2, 1, 0, 0, 0, tzinfo=taiwan_tz)
                        app_end = datetime(current_year + 1, 3, 31, 23, 59, 59, tzinfo=taiwan_tz)
                        ren_start = datetime(current_year + 1, 1, 1, 0, 0, 0, tzinfo=taiwan_tz)
                        ren_end = datetime(current_year + 1, 1, 31, 23, 59, 59, tzinfo=taiwan_tz)

                    config = create_base_config(
                        scholarship,
                        114,
                        semester=semester,
                        config_name=f"學士班新生獎學金配置 - {sem_name}",
                        config_code=f"config_{scholarship.code}_114_{sem_code}",
                        description=f"114學年度{sem_name}學士班新生獎學金配置，無配額限制",
                        description_en=f"Undergraduate freshman scholarship AY114-{sem_code} without quota limits",
                        amount=50000,
                        has_quota_limit=False,
                        has_college_quota=False,
                        quota_management_mode=QuotaManagementMode.NONE,
                        total_quota=None,
                        quotas=None,
                        application_start_date=app_start,
                        application_end_date=app_end,
                        renewal_application_start_date=ren_start,
                        renewal_application_end_date=ren_end,
                    )
                    config.update(
                        create_review_schedule(
                            app_start,
                            app_end,
                            ren_start,
                            ren_end,
                            professor_required=False,
                            college_required=False,
                        )
                    )
                    scholarship_configs.append(config)

            elif scholarship.code == "phd":
                # 博士生獎學金 - 學年制，矩陣配額管理
                total_quota = sum(sum(quotas.values()) for quotas in PHD_QUOTA_CONFIG.values())

                config = create_base_config(
                    scholarship,
                    114,
                    semester=None,  # 學年制
                    config_name="博士生獎學金配置 - 矩陣配額管理",
                    config_code=f"config_{scholarship.code}_114",
                    description="114學年度博士生獎學金配置，採用子類型×學院矩陣配額管理",
                    description_en="PhD scholarship AY114 with sub-type × college matrix allocation",
                    amount=50000,  # 統一金額
                    has_quota_limit=True,
                    has_college_quota=True,
                    quota_management_mode=QuotaManagementMode.MATRIX_BASED,
                    total_quota=total_quota,
                    quotas=PHD_QUOTA_CONFIG,
                    application_start_date=base_start - timedelta(days=30),  # 提前開始申請
                    application_end_date=base_end,
                )
                # AY114博士生獎學金不需要續領期間與設定，僅建立初次審查時程
                config.update(
                    {
                        "requires_professor_recommendation": True,
                        "requires_college_review": True,
                        "review_deadline": base_end + timedelta(days=30),
                        "professor_review_start": base_end + timedelta(days=1),
                        "professor_review_end": base_end + timedelta(days=14),
                        "college_review_start": base_end + timedelta(days=15),
                        "college_review_end": base_end + timedelta(days=29),
                    }
                )
                scholarship_configs.append(config)

            elif scholarship.code == "direct_phd":
                # 逕讀博士獎學金 - 學年制，無配額限制
                config = create_base_config(
                    scholarship,
                    114,
                    semester=None,
                    config_name="逕讀博士獎學金配置 - 學年制",
                    config_code=f"config_{scholarship.code}_114",
                    description="114學年度逕讀博士獎學金配置（學年制），無配額限制",
                    description_en="Direct PhD scholarship AY114 (academic year) without quota limits",
                    amount=80000,  # 較高金額
                    has_quota_limit=False,
                    has_college_quota=False,
                    quota_management_mode=QuotaManagementMode.NONE,
                    total_quota=None,
                    quotas=None,
                    application_start_date=base_start,
                    application_end_date=base_end,
                    renewal_application_start_date=renewal_start,
                    renewal_application_end_date=renewal_end,
                )
                config.update(
                    create_review_schedule(
                        base_start,
                        base_end,
                        renewal_start,
                        renewal_end,
                        professor_required=True,
                        college_required=True,
                    )
                )
                scholarship_configs.append(config)

            configs_114.extend(scholarship_configs)
        return configs_114

    # 生成所有配置
    quota_configs_data.extend(create_113_configs())  # 113學年度配置
    quota_configs_data.extend(create_114_configs())  # 114學年度配置

    # 創建配置記錄 - 避免重複創建
    created_count = 0
    for config_data in quota_configs_data:
        result = await session.execute(
            select(ScholarshipConfiguration).where(ScholarshipConfiguration.config_code == config_data["config_code"])
        )
        existing = result.scalar_one_or_none()

        if not existing:
            config = ScholarshipConfiguration(**config_data)
            session.add(config)
            created_count += 1
        else:
            # 更新現有配置
            for key, value in config_data.items():
                if key != "config_code":
                    setattr(existing, key, value)

    await session.commit()

    # 輸出配置摘要
    print("✅ Scholarship configurations created/updated successfully!")
    print(f"📋 Total configurations: {created_count} new, {len(quota_configs_data) - created_count} updated")
    print(f"📊 Total configurations generated: {len(quota_configs_data)} (covering 2 academic years)")

    # 分別統計113和114年配置
    configs_113 = [c for c in quota_configs_data if c["academic_year"] == 113]
    configs_114 = [c for c in quota_configs_data if c["academic_year"] == 114]
    print(f"   📚 AY113: {len(configs_113)} configurations - active")
    print(f"   📚 AY114: {len(configs_114)} configurations - active")

    # 有效期間資訊 - 台灣時間
    academic_start_113 = datetime(current_year - 1, 8, 1, 0, 0, 0, tzinfo=taiwan_tz)
    academic_end_113 = datetime(current_year, 7, 31, 23, 59, 59, tzinfo=taiwan_tz)
    academic_start_114 = datetime(current_year, 8, 1, 0, 0, 0, tzinfo=taiwan_tz)
    academic_end_114 = datetime(current_year + 1, 7, 31, 23, 59, 59, tzinfo=taiwan_tz)

    print("\n⏰ Academic year periods (Taiwan time):")
    print(
        f"   📆 AY113: {academic_start_113.strftime('%Y-%m-%d')} to {academic_end_113.strftime('%Y-%m-%d')} (Legacy - Expired)"
    )
    print(
        f"   📆 AY114: {academic_start_114.strftime('%Y-%m-%d')} to {academic_end_114.strftime('%Y-%m-%d')} (Current - Active)"
    )

    print("\n🎯 Configuration comparison:")
    print("📚 AY113:")
    print("   - 學士班新生獎學金: 每學期制，無配額限制，金額 45,000元 [ACTIVE]")
    print("   - 博士生獎學金: 學年制，舊矩陣配額管理，金額 55,000元 [ACTIVE]")

    # 計算113年博士生配額
    old_phd_config = {
        "nstc": {
            "E": 5,
            "C": 4,
            "I": 4,
            "S": 3,
            "B": 3,
            "O": 3,
            "D": 3,
            "1": 4,
            "6": 3,
            "7": 3,
            "M": 2,
            "A": 2,
            "K": 1,
        },
        "moe_1w": {
            "E": 6,
            "C": 5,
            "I": 5,
            "S": 4,
            "B": 3,
            "O": 4,
            "D": 4,
            "1": 5,
            "6": 3,
            "7": 3,
            "M": 3,
            "A": 3,
            "K": 1,
        },
        "moe_2w": {
            "E": 8,
            "C": 6,
            "I": 6,
            "S": 5,
            "B": 4,
            "O": 5,
            "D": 5,
            "1": 6,
            "6": 4,
            "7": 4,
            "M": 3,
            "A": 3,
            "K": 2,
        },
    }
    old_phd_totals = {subtype: sum(quotas.values()) for subtype, quotas in old_phd_config.items()}
    total_old_phd = sum(old_phd_totals.values())
    print(
        f"     總配額: {total_old_phd}名 (國科會:{old_phd_totals['nstc']}, 教育部一萬:{old_phd_totals['moe_1w']}, 教育部二萬:{old_phd_totals['moe_2w']}) [ACTIVE]"
    )
    print("   - 逕讀博士獎學金: 學年制，無配額限制，金額 75,000元 [ACTIVE]")

    print("\n📚 AY114 (Current active configurations):")
    print("   - 學士班新生獎學金: 每學期制，無配額限制，金額 50,000元 [ACTIVE]")
    print("   - 博士生獎學金: 學年制，新矩陣配額管理，金額 50,000元 [ACTIVE]")

    # 計算並顯示114年博士生獎學金配額摘要
    phd_totals = {subtype: sum(quotas.values()) for subtype, quotas in PHD_QUOTA_CONFIG.items()}
    total_phd = sum(phd_totals.values())
    print(f"     總配額: {total_phd}名")
    print(f"     • 國科會: {phd_totals['nstc']}名")
    print(f"     • 教育部一萬: {phd_totals['moe_1w']}名")
    print(f"     • 教育部二萬: {phd_totals['moe_2w']}名")
    print("   - 逕讀博士獎學金: 學年制，無配額限制，金額 80,000元 [ACTIVE]")

    # 配置狀態摘要 - 包含台灣時間資訊
    print(f"\n📅 Active period overview: AY114 ({current_year}-{current_year+1})")
    print(
        f"🇹🇼 Application period (Taiwan time): {base_start.strftime('%Y-%m-%d %H:%M')} to {base_end.strftime('%Y-%m-%d %H:%M')}"
    )


async def createTestApplicationsAndQuotaUsage(session: AsyncSession) -> None:
    """Create quota management data and verify configuration completeness"""

    print("📊 Setting up quota management data...")

    # Verify quota configurations exist
    result = await session.execute(select(ScholarshipConfiguration).where(ScholarshipConfiguration.is_active == True))
    configs = result.scalars().all()

    print(f"✅ Found {len(configs)} active scholarship configurations:")
    for config in configs:
        print(f"   - {config.config_name}")
        if config.has_quota_limit and config.total_quota:
            print(f"     配額管理: 總名額 {config.total_quota}")
        elif not config.has_quota_limit:
            print("     配額管理: 無配額限制")
        if config.has_college_quota and config.quotas:
            print(f"     矩陣配額: {len(config.quotas)} 個子類型")

    # Verify scholarship configurations match API expectations
    result = await session.execute(select(ScholarshipType))
    scholarships = result.scalars().all()

    scholarship_codes = [s.code for s in scholarships]
    expected_codes = ["undergraduate_freshman", "phd", "direct_phd"]

    for expected in expected_codes:
        if expected in scholarship_codes:
            print(f"✅ {expected} scholarship configured")
        else:
            print(f"❌ Missing {expected} scholarship configuration")

    print("📋 Scholarship Management Summary:")
    print("   學士班新生獎學金 (undergraduate_freshman):")
    print("     - 配額管理：無配額限制")
    print("     - 評核方式：依學業成績與經濟需求")
    print("     - 申請資格：新生限定")

    print("   博士生獎學金 (phd):")
    print("     - 配額管理：矩陣配額管理，3種子類型 × 18個學院")
    print("     - 國科會 (40名)、教育部一萬 (49名)、教育部兩萬 (61名)")
    print("     - 總配額：150名")
    print("     - 支援同子類型學院間調配")

    print("   逕讀博士獎學金 (direct_phd):")
    print("     - 配額管理：無配額限制")
    print("     - 評核方式：依學術卓越表現")
    print("     - 申請資格：逕博生限定")

    print("✅ Quota management system ready for frontend integration!")

    # Create sample historical applications
    await createSampleHistoricalApplications(session)


async def createSampleHistoricalApplications(session: AsyncSession) -> None:
    """Create sample historical applications for testing"""

    print("📝 Creating sample historical applications...")

    # Get scholarship types and configurations
    result = await session.execute(select(ScholarshipType))
    scholarship_types = {st.code: st for st in result.scalars().all()}

    # Get test users
    result = await session.execute(select(User))
    users = result.scalars().all()

    # Filter users by type
    students = [u for u in users if u.user_type == UserType.STUDENT]
    professors = [u for u in users if u.user_type == UserType.EMPLOYEE and u.role == UserRole.PROFESSOR]
    admins = [u for u in users if u.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]]

    if not students or not professors or not admins:
        print("⚠️ Not enough test users to create applications")
        print(f"   Students: {len(students)}, Professors: {len(professors)}, Admins: {len(admins)}")
        print("   Available users:")
        for u in users[:5]:  # Show first 5 users for debugging
            print(f"     - {u.nycu_id} ({u.user_type}, role: {u.role})")
        return

    applications_data = []

    # Create applications for undergraduate freshman scholarship (113 學年度)
    if "undergraduate_freshman" in scholarship_types:
        scholarship_type = scholarship_types["undergraduate_freshman"]
        for i in range(8):
            student = students[i % len(students)]
            professor = professors[i % len(professors)]
            admin = admins[i % len(admins)]

            status_choices = [
                ApplicationStatus.APPROVED.value,
                ApplicationStatus.REJECTED.value,
                ApplicationStatus.UNDER_REVIEW.value,
                ApplicationStatus.SUBMITTED.value,
            ]

            app_data = {
                "app_id": f"APP-2024-{1000 + i:06d}",
                "user_id": student.id,
                "scholarship_type_id": scholarship_type.id,
                "scholarship_name": "113學年度學士班新生獎學金",
                "amount": 45000,
                "scholarship_subtype_list": [],
                "sub_type_selection_mode": SubTypeSelectionMode.SINGLE,
                "main_scholarship_type": ScholarshipMainType.UNDERGRADUATE_FRESHMAN.value,
                "sub_scholarship_type": ScholarshipSubType.GENERAL.value,
                "status": status_choices[i % len(status_choices)],
                "status_name": "已審核" if i % 2 == 0 else "審核中",
                "academic_year": 113,
                "semester": Semester.FIRST,
                "student_data": {
                    "cname": f"測試學生{i+1}",
                    "stdNo": f"11311{1001 + i}",
                    "dept": "資訊工程學系",
                    "grade": 1,
                    "gpa": round(3.0 + (i * 0.2), 2),
                },
                "submitted_form_data": {
                    "personal_statement": f"這是測試學生{i+1}的個人陳述",
                    "financial_need": i % 2 == 0,
                    "academic_achievements": f"學業成績優異，GPA {3.0 + (i * 0.2):.2f}",
                },
                "agree_terms": True,
                "professor_id": professor.id,
                "reviewer_id": admin.id,
                "review_score": round(80 + (i * 2.5), 2),
                "submitted_at": datetime.now(timezone.utc) - timedelta(days=30 + i),
                "reviewed_at": datetime.now(timezone.utc) - timedelta(days=20 + i) if i % 2 == 0 else None,
                "approved_at": datetime.now(timezone.utc) - timedelta(days=10 + i) if i < 4 else None,
                "created_at": datetime.now(timezone.utc) - timedelta(days=35 + i),
                "updated_at": datetime.now(timezone.utc) - timedelta(days=5 + i),
            }
            applications_data.append(app_data)

    # Create applications for PhD scholarship (113 學年度)
    if "phd" in scholarship_types:
        scholarship_type = scholarship_types["phd"]
        sub_types = ["NSTC", "MOE_1W", "MOE_2W"]

        for i in range(12):
            student = students[(i + 8) % len(students)]
            professor = professors[i % len(professors)]
            admin = admins[i % len(admins)]
            sub_type = sub_types[i % len(sub_types)]

            status_choices = [
                ApplicationStatus.APPROVED.value,
                ApplicationStatus.REJECTED.value,
                ApplicationStatus.PROFESSOR_REVIEW.value,
                ApplicationStatus.UNDER_REVIEW.value,
            ]

            app_data = {
                "app_id": f"APP-2024-{2000 + i:06d}",
                "user_id": student.id,
                "scholarship_type_id": scholarship_type.id,
                "scholarship_name": "113學年度博士生獎學金",
                "amount": 55000,
                "scholarship_subtype_list": [sub_type],
                "sub_type_selection_mode": SubTypeSelectionMode.SINGLE,
                "main_scholarship_type": ScholarshipMainType.PHD.value,
                "sub_scholarship_type": sub_type,
                "status": status_choices[i % len(status_choices)],
                "status_name": "已審核" if i % 3 == 0 else "審核中",
                "academic_year": 113,
                "semester": None,  # PhD scholarships are yearly
                "student_data": {
                    "cname": f"博士生{i+1}",
                    "stdNo": f"11311{3001 + i}",
                    "dept": ["資訊工程學系", "電機工程學系", "機械工程學系"][i % 3],
                    "grade": 3 + (i % 3),
                    "gpa": round(3.5 + (i * 0.1), 2),
                },
                "submitted_form_data": {
                    "research_plan": f"博士生{i+1}的研究計畫",
                    "publications": i % 2,
                    "advisor_recommendation": True,
                },
                "agree_terms": True,
                "professor_id": professor.id,
                "reviewer_id": admin.id,
                "review_score": round(85 + (i * 1.5), 2),
                "submitted_at": datetime.now(timezone.utc) - timedelta(days=45 + i),
                "reviewed_at": datetime.now(timezone.utc) - timedelta(days=25 + i) if i % 3 == 0 else None,
                "approved_at": datetime.now(timezone.utc) - timedelta(days=15 + i) if i < 6 else None,
                "created_at": datetime.now(timezone.utc) - timedelta(days=50 + i),
                "updated_at": datetime.now(timezone.utc) - timedelta(days=10 + i),
            }
            applications_data.append(app_data)

    # Create applications for Direct PhD scholarship (113 學年度)
    if "direct_phd" in scholarship_types:
        scholarship_type = scholarship_types["direct_phd"]

        for i in range(6):
            student = students[(i + 20) % len(students)]
            professor = professors[i % len(professors)]
            admin = admins[i % len(admins)]

            status_choices = [
                ApplicationStatus.APPROVED.value,
                ApplicationStatus.REJECTED.value,
                ApplicationStatus.RECOMMENDED.value,
            ]

            app_data = {
                "app_id": f"APP-2024-{3000 + i:06d}",
                "user_id": student.id,
                "scholarship_type_id": scholarship_type.id,
                "scholarship_name": "113學年度逕讀博士獎學金",
                "amount": 75000,
                "scholarship_subtype_list": [],
                "sub_type_selection_mode": SubTypeSelectionMode.SINGLE,
                "main_scholarship_type": ScholarshipMainType.DIRECT_PHD.value,
                "sub_scholarship_type": ScholarshipSubType.GENERAL.value,
                "status": status_choices[i % len(status_choices)],
                "status_name": "已審核" if i % 2 == 0 else "推薦中",
                "academic_year": 113,
                "semester": None,  # Direct PhD scholarships are yearly
                "student_data": {
                    "cname": f"逕博生{i+1}",
                    "stdNo": f"11311{4001 + i}",
                    "dept": ["資訊工程學系", "電機工程學系"][i % 2],
                    "grade": 1,
                    "gpa": round(3.8 + (i * 0.05), 2),
                },
                "submitted_form_data": {
                    "academic_excellence": f"逕博生{i+1}的學術卓越表現",
                    "direct_phd_qualification": True,
                    "research_potential": "具備優秀的研究潛力",
                },
                "agree_terms": True,
                "professor_id": professor.id,
                "reviewer_id": admin.id,
                "review_score": round(90 + (i * 1.0), 2),
                "submitted_at": datetime.now(timezone.utc) - timedelta(days=25 + i),
                "reviewed_at": datetime.now(timezone.utc) - timedelta(days=15 + i) if i % 2 == 0 else None,
                "approved_at": datetime.now(timezone.utc) - timedelta(days=5 + i) if i < 3 else None,
                "created_at": datetime.now(timezone.utc) - timedelta(days=30 + i),
                "updated_at": datetime.now(timezone.utc) - timedelta(days=2 + i),
            }
            applications_data.append(app_data)

    # Add applications from the model
    from app.models.application import Application

    for app_data in applications_data:
        application = Application(**app_data)
        session.add(application)

    await session.commit()

    print(f"✅ Created {len(applications_data)} sample historical applications:")
    print("   - 學士班新生獎學金: 8 筆")
    print("   - 博士生獎學金: 12 筆")
    print("   - 逕讀博士獎學金: 6 筆")
    print(f"   總計: {len(applications_data)} 筆歷史申請")


async def createSystemAnnouncements(session: AsyncSession) -> None:
    """Create initial system announcements"""

    print("📢 Creating system announcements...")

    # 計算公告過期時間（30天後）
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    announcements_data = [
        {
            "user_id": None,  # 系統公告 user_id 為 null
            "title": "獎學金申請系統初始化完成",
            "title_en": "Scholarship Application System Initialization Complete",
            "message": "歡迎使用國立陽明交通大學獎學金申請與簽核作業管理系統！系統已完成初始化，包含測試用戶帳號、獎學金類型等基礎資料。請使用測試帳號登入體驗各項功能。",
            "message_en": "Welcome to NYCU Scholarship Application and Approval Management System! The system has been initialized with test user accounts and scholarship types. Please use the test accounts to explore the features.",
            "notification_type": NotificationType.INFO.value,
            "priority": NotificationPriority.HIGH.value,
            "related_resource_type": "system",
            "related_resource_id": None,
            "action_url": None,
            "is_read": False,
            "is_dismissed": False,
            "send_email": False,
            "email_sent": False,
            "expires_at": expires_at,
            "meta_data": {
                "init_system": True,
                "version": "1.0.0",
                "created_by": "system_init",
            },
        },
        {
            "user_id": None,
            "title": "系統測試帳號說明",
            "title_en": "System Test Accounts Information",
            "message": "系統已建立多個測試帳號供開發測試使用：admin/admin123（管理員）、professor/professor123（教授）、college/college123（學院審核）、stu_under/stuunder123（學士生）、stu_phd/stuphd123（博士生）等。請妥善保管帳號密碼。",
            "message_en": "Test accounts have been created for development: admin/admin123 (Administrator), professor/professor123 (Professor), college/college123 (College Reviewer), stu_under/stuunder123 (Undergraduate), stu_phd/stuphd123 (PhD) etc. Please keep credentials secure.",
            "notification_type": NotificationType.WARNING.value,
            "priority": NotificationPriority.NORMAL.value,
            "related_resource_type": "system",
            "related_resource_id": None,
            "action_url": "/auth/login",
            "is_read": False,
            "is_dismissed": False,
            "send_email": False,
            "email_sent": False,
            "expires_at": expires_at,
            "meta_data": {"test_accounts": True, "security_notice": True},
        },
        {
            "user_id": None,
            "title": "開發模式提醒",
            "title_en": "Development Mode Notice",
            "message": "目前系統運行在開發模式下，所有獎學金申請期間已開放，白名單檢查已停用。正式環境請確保修改相關設定以符合實際需求。",
            "message_en": "The system is currently running in development mode. All scholarship application periods are open and whitelist checks are disabled. Please ensure proper configuration for production environment.",
            "notification_type": NotificationType.WARNING.value,
            "priority": NotificationPriority.HIGH.value,
            "related_resource_type": "system",
            "related_resource_id": None,
            "action_url": None,
            "is_read": False,
            "is_dismissed": False,
            "send_email": False,
            "email_sent": False,
            "expires_at": expires_at,
            "meta_data": {
                "dev_mode": True,
                "config_reminder": True,
                "environment": "development",
            },
        },
    ]

    for announcement_data in announcements_data:
        # 檢查是否已存在相同的公告（根據 title 和 meta_data 判斷）
        result = await session.execute(
            select(Notification).where(
                Notification.title == announcement_data["title"],
                Notification.related_resource_type == "system",
                Notification.user_id.is_(None),
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            announcement = Notification(**announcement_data)
            session.add(announcement)

    await session.commit()
    print("✅ System announcements created successfully!")
    print("📋 System announcements include:")
    print("   - System initialization notice")
    print("   - Test accounts information")
    print("   - Development mode reminder")


async def createTestEmailHistory(session: AsyncSession) -> None:
    """Create test email history records"""

    print("📧 Creating test email history records...")

    # Get test users for sending emails
    result = await session.execute(select(User).where(User.nycu_id.in_(["admin", "super_admin", "professor"])))
    users = {user.nycu_id: user for user in result.scalars().all()}

    # Get scholarship types for categorization
    result = await session.execute(select(ScholarshipType))
    scholarship_types = list(result.scalars().all())

    # Email history test data
    email_history_data = [
        {
            "recipient_email": "cs_phd001@nycu.edu.tw",
            "subject": "博士生獎學金申請開放通知",
            "body": "親愛的同學您好，\n\n113學年度第一學期博士生獎學金申請已開放，請於期限內完成申請。\n\n獎學金管理系統",
            "email_category": EmailCategory.APPLICATION_STUDENT,
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,  # PhD scholarship
            "sent_by_user_id": users.get("admin").id if users.get("admin") else None,
            "sent_by_system": False,
            "status": EmailStatus.SENT,
            "sent_at": datetime.now(timezone.utc) - timedelta(days=30),
            "email_size_bytes": 485,
        },
        {
            "recipient_email": "cs_professor@nycu.edu.tw",
            "subject": "學生推薦信請求通知",
            "body": "親愛的教授您好，\n\n您的指導學生 王博士研究生 申請博士生獎學金，需要您的推薦信。請登入系統查看詳情。\n\n獎學金管理系統",
            "email_category": EmailCategory.RECOMMENDATION_PROFESSOR,
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "sent_by_user_id": None,
            "sent_by_system": True,
            "status": EmailStatus.SENT,
            "sent_at": datetime.now(timezone.utc) - timedelta(days=25),
            "email_size_bytes": 392,
        },
        {
            "recipient_email": "cs_college@nycu.edu.tw",
            "subject": "資訊學院獎學金審核通知",
            "body": "親愛的審核員您好，\n\n有新的獎學金申請案件需要您的審核。請登入系統進行審核作業。\n\n申請件數：5件\n待審核期限：2天\n\n獎學金管理系統",
            "email_category": EmailCategory.REVIEW_COLLEGE,
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "sent_by_user_id": None,
            "sent_by_system": True,
            "status": EmailStatus.SENT,
            "sent_at": datetime.now(timezone.utc) - timedelta(days=20),
            "email_size_bytes": 456,
        },
        {
            "recipient_email": "cs_phd002@nycu.edu.tw",
            "subject": "申請文件補件通知",
            "body": "親愛的同學您好，\n\n您的獎學金申請文件需要補件：\n- 成績單正本\n- 推薦信\n\n請於3天內完成補件，逾期將影響審核結果。\n\n獎學金管理系統",
            "email_category": EmailCategory.SUPPLEMENT_STUDENT,
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "sent_by_user_id": users.get("professor").id if users.get("professor") else None,
            "sent_by_system": False,
            "status": EmailStatus.SENT,
            "sent_at": datetime.now(timezone.utc) - timedelta(days=15),
            "email_size_bytes": 398,
        },
        {
            "recipient_email": "cs_phd003@nycu.edu.tw",
            "subject": "獎學金審核結果通知",
            "body": "親愛的同學您好，\n\n恭喜您！您的博士生獎學金申請已通過審核。\n\n獎學金金額：NT$ 40,000\n發放日期：113年10月31日\n\n請注意相關權利義務事項。\n\n獎學金管理系統",
            "email_category": EmailCategory.RESULT_STUDENT,
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "sent_by_user_id": None,
            "sent_by_system": True,
            "status": EmailStatus.SENT,
            "sent_at": datetime.now(timezone.utc) - timedelta(days=10),
            "email_size_bytes": 512,
        },
        {
            "recipient_email": "ee_professor@nycu.edu.tw",
            "subject": "學生獲獎通知（指導教授）",
            "body": "親愛的教授您好，\n\n您的指導學生 劉通訊博士 已獲得博士生獎學金。\n\n獲獎學生資訊：\n- 姓名：劉通訊博士\n- 學號：ee_phd002\n- 獎學金：博士生獎學金\n- 金額：NT$ 40,000\n\n感謝您的指導。\n\n獎學金管理系統",
            "email_category": EmailCategory.RESULT_PROFESSOR,
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "sent_by_user_id": None,
            "sent_by_system": True,
            "status": EmailStatus.SENT,
            "sent_at": datetime.now(timezone.utc) - timedelta(days=8),
            "email_size_bytes": 634,
        },
        {
            "recipient_email": "ee_college@nycu.edu.tw",
            "subject": "學院獎學金分配結果通知",
            "body": "親愛的學院審核員您好，\n\n電機學院本期獎學金分配已完成：\n\n獲獎名單：\n- 劉通訊博士（博士生獎學金）\n- 蔡半導體博士（博士生獎學金）\n\n總計金額：NT$ 80,000\n剩餘名額：0名\n\n獎學金管理系統",
            "email_category": EmailCategory.RESULT_COLLEGE,
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "sent_by_user_id": None,
            "sent_by_system": True,
            "status": EmailStatus.SENT,
            "sent_at": datetime.now(timezone.utc) - timedelta(days=5),
            "email_size_bytes": 578,
        },
        {
            "recipient_email": "cs_phd_intl@nycu.edu.tw",
            "subject": "獎學金造冊確認通知",
            "body": "Dear International Student,\n\n您的獎學金已列入本期造冊名單。請確認以下資訊：\n\n- 獎學金：International PhD Scholarship\n- 金額：NT$ 40,000\n- 銀行帳戶：請確認您的銀行帳戶資訊正確\n\n如有疑問請聯繫國際事務處。\n\nScholarship Management System",
            "email_category": EmailCategory.ROSTER_STUDENT,
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "sent_by_user_id": users.get("super_admin").id if users.get("super_admin") else None,
            "sent_by_system": False,
            "status": EmailStatus.SENT,
            "sent_at": datetime.now(timezone.utc) - timedelta(days=3),
            "email_size_bytes": 632,
        },
        {
            "recipient_email": "admin@nycu.edu.tw",
            "subject": "系統維護通知",
            "body": "系統管理員您好，\n\n獎學金管理系統將於本週六晚上10點至12點進行例行性維護，期間系統將暫停服務。\n\n維護內容：\n- 資料庫優化\n- 安全性更新\n- 效能調整\n\n如有疑問請聯繫技術支援。\n\n系統通知",
            "email_category": EmailCategory.SYSTEM,
            "scholarship_type_id": None,
            "sent_by_user_id": None,
            "sent_by_system": True,
            "status": EmailStatus.SENT,
            "sent_at": datetime.now(timezone.utc) - timedelta(days=1),
            "email_size_bytes": 445,
        },
        {
            "recipient_email": "student_fail@example.com",
            "subject": "測試失敗郵件",
            "body": "這是一封測試失敗的郵件，用於測試錯誤處理機制。",
            "email_category": EmailCategory.OTHER,
            "scholarship_type_id": None,
            "sent_by_user_id": users.get("admin").id if users.get("admin") else None,
            "sent_by_system": False,
            "status": EmailStatus.FAILED,
            "error_message": "SMTP Error: Invalid email address",
            "sent_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "retry_count": 3,
            "email_size_bytes": 185,
        },
    ]

    # Create email history records
    for email_data in email_history_data:
        email_history = EmailHistory(**email_data)
        session.add(email_history)

    await session.commit()

    print(f"📧 Created {len(email_history_data)} email history records")
    print("📧 Email history includes:")
    print("   - Application notifications")
    print("   - Recommendation requests")
    print("   - Review notifications")
    print("   - Supplement requests")
    print("   - Result notifications")
    print("   - System maintenance notices")
    print("   - Failed email examples")


async def createTestScheduledEmails(session: AsyncSession) -> None:
    """Create test scheduled email records"""

    print("📅 Creating test scheduled email records...")

    # Get test users for creating scheduled emails
    result = await session.execute(select(User).where(User.nycu_id.in_(["admin", "super_admin", "professor"])))
    users = {user.nycu_id: user for user in result.scalars().all()}

    # Get scholarship types for categorization
    result = await session.execute(select(ScholarshipType))
    scholarship_types = list(result.scalars().all())

    # Scheduled email test data
    scheduled_email_data = [
        {
            "recipient_email": "cs_phd004@nycu.edu.tw",
            "subject": "博士生獎學金申請提醒",
            "body": "親愛的同學您好，\n\n提醒您博士生獎學金申請即將截止，請把握最後機會。\n\n截止日期：2025年9月25日 23:59\n注意事項：\n- 請確認所有必填欄位已完成\n- 上傳文件需為PDF格式\n- 推薦信需由指導教授提供\n\n如有問題請聯繫獎學金辦公室。\n\n獎學金管理系統",
            "email_category": EmailCategory.APPLICATION_STUDENT,
            "scheduled_for": datetime.now(timezone.utc) + timedelta(hours=2),
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "requires_approval": False,
            "created_by_user_id": users.get("admin").id if users.get("admin") else 1,
            "status": ScheduleStatus.PENDING,
            "priority": 2,
        },
        {
            "recipient_email": "ee_professor@nycu.edu.tw",
            "subject": "推薦信截止提醒",
            "body": "親愛的教授您好，\n\n您有學生的推薦信即將截止，請盡快完成：\n\n學生姓名：張電機博士\n申請獎學金：博士生獎學金\n截止時間：2025年9月23日 18:00\n\n請登入系統完成推薦信撰寫。\n\n感謝您的配合。\n\n獎學金管理系統",
            "email_category": EmailCategory.RECOMMENDATION_PROFESSOR,
            "scheduled_for": datetime.now(timezone.utc) + timedelta(hours=6),
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "requires_approval": True,
            "created_by_user_id": users.get("super_admin").id if users.get("super_admin") else 2,
            "approved_by_user_id": users.get("super_admin").id if users.get("super_admin") else 2,
            "approved_at": datetime.now(timezone.utc),
            "approval_notes": "例行性推薦信提醒，可自動發送",
            "status": ScheduleStatus.PENDING,
            "priority": 3,
        },
        {
            "recipient_email": "cs_college@nycu.edu.tw",
            "subject": "學院審核期限提醒",
            "body": "親愛的審核員您好，\n\n您有獎學金申請案件即將到期，請盡快完成審核：\n\n待審核案件：3件\n申請人：\n- 王資訊博士（申請編號：CS2025001）\n- 李演算法碩士（申請編號：CS2025002）\n- 陳人工智慧博士（申請編號：CS2025003）\n\n審核截止：2025年9月24日 17:00\n\n請登入系統進行審核作業。\n\n獎學金管理系統",
            "email_category": EmailCategory.REVIEW_COLLEGE,
            "scheduled_for": datetime.now(timezone.utc) + timedelta(days=1),
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "requires_approval": False,
            "created_by_user_id": users.get("admin").id if users.get("admin") else 1,
            "status": ScheduleStatus.PENDING,
            "priority": 1,
        },
        {
            "recipient_email": "me_phd001@nycu.edu.tw",
            "subject": "補件提醒通知",
            "body": "親愛的同學您好，\n\n您的獎學金申請需要補件，請在期限內完成：\n\n缺件項目：\n- 在學證明書（須為最新版本）\n- 指導教授同意書\n\n補件期限：2025年9月26日 23:59\n逾期將視為放棄申請。\n\n請儘早完成補件程序。\n\n獎學金管理系統",
            "email_category": EmailCategory.SUPPLEMENT_STUDENT,
            "scheduled_for": datetime.now(timezone.utc) + timedelta(days=2),
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "requires_approval": True,
            "created_by_user_id": users.get("professor").id if users.get("professor") else 3,
            "status": ScheduleStatus.PENDING,
            "priority": 4,
        },
        {
            "recipient_email": "all_students@nycu.edu.tw",
            "cc_emails": '["backup@nycu.edu.tw"]',
            "subject": "獎學金系統維護通知",
            "body": "親愛的同學們您好，\n\n獎學金管理系統將進行定期維護：\n\n維護時間：2025年9月25日 凌晨2:00 - 4:00\n影響範圍：系統將暫停服務2小時\n維護內容：\n- 資料庫效能優化\n- 安全性更新\n- 介面改善\n\n維護期間請勿進行申請或上傳文件。\n造成不便敬請見諒。\n\n如有緊急問題請聯繫技術支援。\n\n獎學金管理系統",
            "email_category": EmailCategory.SYSTEM,
            "scheduled_for": datetime.now(timezone.utc) + timedelta(days=3),
            "scholarship_type_id": None,
            "requires_approval": True,
            "created_by_user_id": users.get("super_admin").id if users.get("super_admin") else 2,
            "status": ScheduleStatus.PENDING,
            "priority": 5,
        },
        {
            "recipient_email": "cs_phd005@nycu.edu.tw",
            "subject": "獎學金核發通知",
            "body": "親愛的同學您好，\n\n恭喜您獲得博士生獎學金！\n\n獎學金詳情：\n- 獎學金名稱：博士生獎學金\n- 金額：NT$ 40,000\n- 核發學期：113學年度第一學期\n- 預計發放日期：2025年10月31日\n\n權利義務：\n- 需維持良好學業成績\n- 協助系上教學或研究工作\n- 按時參與獎學金受獎生活動\n\n詳細條款請參閱獎學金規定。\n\n再次恭喜您的獲獎！\n\n獎學金管理系統",
            "email_category": EmailCategory.RESULT_STUDENT,
            "scheduled_for": datetime.now(timezone.utc) + timedelta(hours=12),
            "scholarship_type_id": scholarship_types[1].id if len(scholarship_types) > 1 else None,
            "requires_approval": False,
            "created_by_user_id": users.get("admin").id if users.get("admin") else 1,
            "status": ScheduleStatus.PENDING,
            "priority": 2,
        },
    ]

    # Create scheduled email records
    for email_data in scheduled_email_data:
        scheduled_email = ScheduledEmail(**email_data)
        session.add(scheduled_email)

    await session.commit()

    print(f"📅 Created {len(scheduled_email_data)} scheduled email records")
    print("📅 Scheduled emails include:")
    print("   - Application deadline reminders")
    print("   - Recommendation letter reminders")
    print("   - Review deadline notifications")
    print("   - Supplement request reminders")
    print("   - System maintenance notices")
    print("   - Award notification emails")


async def initializeSystemEmailTemplates(session: AsyncSession) -> None:
    """Initialize default system email templates"""

    print("📧 Initializing system email templates...")

    # Check if templates already exist
    stmt = select(EmailTemplate)
    result = await session.execute(stmt)
    existing_templates = list(result.scalars().all())

    if existing_templates:
        print(f"   📊 Found {len(existing_templates)} existing templates, skipping initialization")
        return

    # Define default email templates
    default_templates = [
        # Single sending type templates
        {
            "key": "application_submitted_student",
            "subject_template": "申請確認通知 - {scholarship_name}",
            "body_template": """親愛的 {student_name} 同學：

您好！

感謝您申請 {scholarship_name}。我們已收到您的申請資料，申請編號為：{application_id}

申請詳情：
- 申請時間：{submission_date}
- 獎學金名稱：{scholarship_name}
- 申請學期：{semester}
- 獎學金金額：{scholarship_amount}

我們會儘快處理您的申請，如有任何問題請隨時聯繫我們。

祝學業順利！

國立陽明交通大學
獎學金管理系統""",
            "sending_type": SendingType.SINGLE,
            "recipient_options": [{"label": "申請學生", "value": "student"}],
        },
        {
            "key": "application_submitted_admin",
            "subject_template": "新申請通知 - {student_name}",
            "body_template": """管理員您好：

有新的獎學金申請需要處理：

申請人資訊：
- 學生姓名：{student_name}
- 學生學號：{student_id}
- 申請時間：{submission_date}
- 申請編號：{application_id}
- 獎學金名稱：{scholarship_name}

請至管理系統查看詳細資料：{admin_portal_url}

獎學金管理系統""",
            "sending_type": SendingType.SINGLE,
            "recipient_options": [{"label": "管理員", "value": "admin"}],
        },
        {
            "key": "professor_review_notification",
            "subject_template": "審查通知 - {student_name} 的 {scholarship_name} 申請",
            "body_template": """{professor_name} 教授您好：

您的指導學生 {student_name}（學號：{student_id}）申請了 {scholarship_name}，需要您進行審查。

審查截止日期：{review_deadline}

請點擊以下連結進行審查：
{review_url}

如有任何問題，請隨時聯繫我們。

國立陽明交通大學
獎學金管理系統""",
            "sending_type": SendingType.SINGLE,
            "recipient_options": [{"label": "指導教授", "value": "professor"}],
        },
        {
            "key": "professor_review_submitted_admin",
            "subject_template": "教授審查結果通知 - {student_name}",
            "body_template": """管理員您好：

{professor_name} 教授已完成對 {student_name}（學號：{student_id}）的 {scholarship_name} 申請審查。

審查結果：{review_result}

請至管理系統查看詳細審查資料。

獎學金管理系統""",
            "sending_type": SendingType.SINGLE,
            "recipient_options": [{"label": "管理員", "value": "admin"}],
        },
        # Bulk sending type templates
        {
            "key": "scholarship_announcement",
            "subject_template": "獎學金公告 - {scholarship_name}",
            "body_template": """各位同學：

{scholarship_name} 現正開放申請！

申請期間：{application_period}
申請資格：{eligibility_criteria}
獎學金金額：{scholarship_amount}

申請方式：
請至獎學金管理系統線上申請

如有任何問題，請聯繫承辦人員。

國立陽明交通大學
獎學金管理系統""",
            "sending_type": SendingType.BULK,
            "recipient_options": [
                {"label": "全體學生", "value": "all_students"},
                {"label": "特定科系學生", "value": "department_students"},
                {"label": "特定年級學生", "value": "grade_students"},
            ],
            "max_recipients": 500,
        },
        {
            "key": "application_deadline_reminder",
            "subject_template": "申請截止提醒 - {scholarship_name}",
            "body_template": """各位同學：

提醒您 {scholarship_name} 即將截止申請！

申請截止時間：{application_deadline}
剩餘時間：{remaining_time}

尚未申請的同學請把握時間完成申請手續。

獎學金管理系統""",
            "sending_type": SendingType.BULK,
            "recipient_options": [
                {"label": "尚未申請的學生", "value": "non_applicants"},
                {"label": "申請未完成的學生", "value": "incomplete_applicants"},
            ],
            "max_recipients": 1000,
        },
    ]

    print(f"   📧 Creating {len(default_templates)} default email templates...")

    # Create templates
    for template_data in default_templates:
        template = EmailTemplate(**template_data)
        session.add(template)
        print(f"      ✅ Created template: {template_data['key']} ({template_data['sending_type'].value})")

    await session.commit()

    print("   ✅ System email templates initialized successfully!")
    print("\n   📋 Created templates:")
    print("      Single sending templates:")
    print("      - application_submitted_student: 學生申請確認通知")
    print("      - application_submitted_admin: 管理員新申請通知")
    print("      - professor_review_notification: 教授審查通知")
    print("      - professor_review_submitted_admin: 教授審查結果通知")
    print("\n      Bulk sending templates:")
    print("      - scholarship_announcement: 獎學金公告")
    print("      - application_deadline_reminder: 申請截止提醒")


async def createApplicationFields(session: AsyncSession) -> None:
    """Create initial application field configurations"""

    print("📝 Creating application field configurations...")

    # 獲取管理員用戶ID
    result = await session.execute(select(User).where(User.nycu_id == "admin"))
    admin_user = result.scalar_one_or_none()
    admin_id = admin_user.id if admin_user else 1

    # === 學士班新生獎學金字段配置 ===
    # 銀行帳號將作為固定申請項目，不在此定義
    undergraduate_fields = []

    # === 博士生獎學金字段配置 ===
    # 指導教授資訊和銀行帳號將作為固定申請項目，不在此定義
    phd_fields = []

    # === 逕讀博士獎學金字段配置 ===
    direct_phd_fields = [
        {
            "scholarship_type": "direct_phd",
            "field_name": "advisors",
            "field_label": "多位指導教授資訊",
            "field_label_en": "Multiple Advisors Information",
            "field_type": "text",
            "is_required": True,
            "placeholder": "請輸入所有指導教授的姓名（如有多位請以逗號分隔）",
            "placeholder_en": "Please enter the names of all advisors (separate with commas if more than one)",
            "max_length": 200,
            "display_order": 1,
            "is_active": True,
            "help_text": "請填寫所有指導教授的姓名",
            "help_text_en": "Please provide the names of all advisors",
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
            "placeholder_en": "Please enter the research topic in Chinese",
            "max_length": 200,
            "display_order": 2,
            "is_active": True,
            "help_text": "請填寫研究題目（中文）",
            "help_text_en": "Please provide the research topic in Chinese",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "direct_phd",
            "field_name": "research_topic_en",
            "field_label": "研究題目（英文）",
            "field_label_en": "Research Topic (English)",
            "field_type": "text",
            "is_required": True,
            "placeholder": "Please enter the research topic in English",
            "placeholder_en": "Please enter the research topic in English",
            "max_length": 200,
            "display_order": 3,
            "is_active": True,
            "help_text": "請填寫研究題目（英文）",
            "help_text_en": "Please provide the research topic in English",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "direct_phd",
            "field_name": "recommender_name",
            "field_label": "推薦人姓名",
            "field_label_en": "Recommender Name",
            "field_type": "text",
            "is_required": True,
            "placeholder": "請輸入推薦人姓名",
            "placeholder_en": "Please enter the recommender's name",
            "max_length": 200,
            "display_order": 4,
            "is_active": True,
            "help_text": "請填寫推薦人姓名",
            "help_text_en": "Please provide the recommender's name",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "direct_phd",
            "field_name": "recommender_email",
            "field_label": "推薦人Email",
            "field_label_en": "Recommender Email",
            "field_type": "email",
            "is_required": True,
            "placeholder": "請輸入推薦人的Email",
            "placeholder_en": "Please enter the recommender's email",
            "max_length": 100,
            "display_order": 5,
            "is_active": True,
            "help_text": "請填寫推薦人的Email",
            "help_text_en": "Please provide the recommender's email",
            "created_by": admin_id,
            "updated_by": admin_id,
        }
        # 銀行帳號將作為固定申請項目，不在此定義
    ]

    # 創建所有字段
    all_fields = undergraduate_fields + phd_fields + direct_phd_fields

    for field_data in all_fields:
        # 檢查是否已存在
        result = await session.execute(
            select(ApplicationField).where(
                ApplicationField.scholarship_type == field_data["scholarship_type"],
                ApplicationField.field_name == field_data["field_name"],
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            field = ApplicationField(**field_data)
            session.add(field)

    # === 文件配置 ===
    document_configs = [
        # 存摺封面將作為固定申請項目，不在此定義
        # 博士生文件
        # 1.含前一學年度完整成績的歷年成績單(上傳)
        # 2.勞保投保紀錄(上傳)
        # 3.博士學位研習計畫
        # 4.可累加其他相關文件(上傳)
        # 5.存摺封面(沒資料者上傳)
        {
            "scholarship_type": "phd",
            "document_name": "歷年成績單",
            "document_name_en": "Yearly Transcript",
            "description": "請上傳含前一學年度完整成績的歷年成績單",
            "description_en": "Please upload yearly transcript including previous year's complete grades",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": 1,
            "is_active": True,
            "upload_instructions": "請確保成績單清晰可讀，包含所有學期成績",
            "upload_instructions_en": "Please ensure the transcript is clear and readable, including all semester grades",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "phd",
            "document_name": "勞保投保紀錄",
            "document_name_en": "Labor Insurance Record",
            "description": "請上傳勞保投保紀錄",
            "description_en": "Please upload labor insurance record",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": 2,
            "is_active": True,
            "upload_instructions": "請確保勞保投保紀錄清晰可讀，包含投保單位、投保金額、投保日期等資訊",
            "upload_instructions_en": "Please ensure the labor insurance record is clear and readable, including insurance company, insurance amount, insurance date, etc.",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "phd",
            "document_name": "博士學位研習計畫",
            "document_name_en": "PHD Study Plan",
            "description": "請上傳博士學位研習計畫",
            "description_en": "Please upload PHD study plan",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": 3,
            "is_active": True,
            "upload_instructions": "請確保博士學位研習計畫清晰可讀，包含研究背景、目標、方法、預期成果等資訊",
            "upload_instructions_en": "Please ensure the PHD study plan is clear and readable, including research background, objectives, methods, expected outcomes, etc.",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "phd",
            "document_name": "其他相關文件",
            "document_name_en": "Additional Related Documents",
            "description": "請上傳其他相關文件",
            "description_en": "Please upload other related documents",
            "is_required": False,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 5,
            "display_order": 4,
            "is_active": True,
            "upload_instructions": "請確保其他相關文件清晰可讀，包含文件名稱、文件內容等資訊",
            "upload_instructions_en": "Please ensure the other related documents are clear and readable, including file name, file content, etc.",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        # 存摺封面將作為固定申請項目，不在此定義
        # 逕讀博士文件
        # 1.個人基本資料(套印確認)
        # 2.博士班研修計畫書(範本下載)
        # 3.推薦信2封(註冊組上傳)
        # 4.含大學部歷年成績單(上傳)
        # 5.全時修讀切結書(套印下載再上傳)
        # 6.英文能力檢定成績單(上傳)
        # 7.可累加其他相關文件(上傳)
        # 8.勞保投保紀錄(上傳)
        # 9.存摺封面(沒資料者上傳)
        {
            "scholarship_type": "direct_phd",
            "document_name": "博士班研修計畫書",
            "document_name_en": "PHD Study Plan",
            "description": "請上傳博士班研修計畫書",
            "description_en": "Please upload PHD study plan",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": 1,
            "is_active": True,
            "upload_instructions": "請確保博士班研修計畫書清晰可讀，包含研究背景、目標、方法、預期成果等資訊",
            "upload_instructions_en": "Please ensure the PHD study plan is clear and readable, including research background, objectives, methods, expected outcomes, etc.",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "direct_phd",
            "document_name": "推薦信",
            "document_name_en": "Recommendation Letter",
            "description": "請上傳推薦信",
            "description_en": "Please upload recommendation letter",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 2,
            "display_order": 2,
            "is_active": True,
            "upload_instructions": "請確保推薦信清晰可讀，包含推薦人簽名、聯絡方式等資訊",
            "upload_instructions_en": "Please ensure the recommendation letter is clear and readable, including recommender's signature, contact information, etc.",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "direct_phd",
            "document_name": "大學部歷年成績單",
            "document_name_en": "Undergraduate Transcript",
            "description": "請上傳大學部歷年成績單",
            "description_en": "Please upload undergraduate transcript",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": 3,
            "is_active": True,
            "upload_instructions": "請確保大學部歷年成績單清晰可讀，包含所有學期成績",
            "upload_instructions_en": "Please ensure the undergraduate transcript is clear and readable, including all semester grades",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "direct_phd",
            "document_name": "全時修讀切結書",
            "document_name_en": "Full-time Study Commitment",
            "description": "請上傳全時修讀切結書",
            "description_en": "Please upload full-time study commitment",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": 4,
            "is_active": True,
            "upload_instructions": "請確保全時修讀切結書清晰可讀，包含學生簽名、日期等資訊",
            "upload_instructions_en": "Please ensure the full-time study commitment is clear and readable, including student signature, date, etc.",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "direct_phd",
            "document_name": "英文能力檢定成績單",
            "document_name_en": "English Proficiency Test",
            "description": "請上傳英文能力檢定成績單",
            "description_en": "Please upload English proficiency test",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 5,
            "display_order": 5,
            "is_active": True,
            "upload_instructions": "請確保英文能力檢定成績單清晰可讀，包含成績單名稱、成績等資訊",
            "upload_instructions_en": "Please ensure the English proficiency test is clear and readable, including test name, score, etc.",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "direct_phd",
            "document_name": "其他相關文件",
            "document_name_en": "Additional Related Documents",
            "description": "請上傳其他相關文件",
            "description_en": "Please upload other related documents",
            "is_required": False,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 5,
            "display_order": 6,
            "is_active": True,
            "upload_instructions": "請確保其他相關文件清晰可讀，包含文件名稱、文件內容等資訊",
            "upload_instructions_en": "Please ensure the other related documents are clear and readable, including file name, file content, etc.",
            "created_by": admin_id,
            "updated_by": admin_id,
        },
        {
            "scholarship_type": "direct_phd",
            "document_name": "勞保投保紀錄",
            "document_name_en": "Labor Insurance Record",
            "description": "請上傳勞保投保紀錄",
            "description_en": "Please upload labor insurance record",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": 7,
            "is_active": True,
            "upload_instructions": "請確保勞保投保紀錄清晰可讀，包含投保單位、投保金額、投保日期等資訊",
            "upload_instructions_en": "Please ensure the labor insurance record is clear and readable, including insurance company, insurance amount, insurance date, etc.",
            "created_by": admin_id,
            "updated_by": admin_id,
        }
        # 存摺封面將作為固定申請項目，不在此定義
    ]

    for doc_data in document_configs:
        # 檢查是否已存在
        result = await session.execute(
            select(ApplicationDocument).where(
                ApplicationDocument.scholarship_type == doc_data["scholarship_type"],
                ApplicationDocument.document_name == doc_data["document_name"],
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            document = ApplicationDocument(**doc_data)
            session.add(document)

    await session.commit()
    print("✅ Application field configurations created successfully!")
    print("📋 Created configurations for:")
    print("   - Undergraduate freshman scholarship fields and documents")
    print("   - PhD scholarship fields and documents")
    print("   - Direct PhD scholarship fields and documents")


async def initDatabase() -> None:
    """Initialize entire database"""

    print("🚀 Initializing scholarship system database...")

    # Create all tables
    async with async_engine.begin() as conn:
        print("🗄️  Dropping and recreating all tables...")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Initialize data
    async with AsyncSessionLocal() as session:
        # Initialize lookup tables
        await initLookupTables(session)

        # Create test users
        await createTestUsers(session)

        # Student data creation removed - students are now fetched from external API
        # await createTestStudents(session, users)

        # Create test scholarships
        await createTestScholarships(session)

        # Create application field configurations
        await createApplicationFields(session)

        # Create system announcements
        await createSystemAnnouncements(session)

        # Create test email history
        await createTestEmailHistory(session)

        # Create test scheduled emails
        await createTestScheduledEmails(session)

        # Initialize system email templates
        await initializeSystemEmailTemplates(session)

    print("✅ Database initialization completed successfully!")
    print("\n📋 Test User Accounts:")
    print("- Admin: admin / admin123")
    print("- Super Admin: super_admin / super123")
    print("- Professor: professor / professor123")
    print("- College: college / college123")
    print("- Student (學士): stu_under / stuunder123")
    print("- Student (博士): stu_phd / stuphd123")
    print("- Student (逕讀博士): stu_direct / studirect123")
    print("- Student (碩士): stu_master / stumaster123")
    print("- Student (陸生): stu_china / stuchina123")


if __name__ == "__main__":
    asyncio.run(initDatabase())
