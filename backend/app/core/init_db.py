"""
Database initialization script for scholarship system
"""

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, date, timezone, timedelta
from typing import List

from app.db.session import async_engine, AsyncSessionLocal
from app.models.user import User, UserRole, UserType, EmployeeStatus
from app.models.student import (
    # 查詢表 (Reference data only)
    Degree, Identity, StudyingStatus, SchoolIdentity, Academy, Department, EnrollType,
)

from app.db.base_class import Base
from app.models.scholarship import ScholarshipRule, ScholarshipType, ScholarshipStatus, ScholarshipCategory, ScholarshipSubTypeConfig, ScholarshipConfiguration
from app.models.enums import Semester, ApplicationCycle, SubTypeSelectionMode, QuotaManagementMode
from app.models.notification import Notification, NotificationType, NotificationPriority
from app.models.application_field import ApplicationField, ApplicationDocument
from app.core.config import settings


async def initLookupTables(session: AsyncSession) -> None:
    """Initialize lookup tables using the dedicated lookup tables module"""
    
    # Import here to avoid circular imports
    from app.core.init_lookup_tables import initLookupTables as initLookup
    
    # Check if lookup tables are already initialized
    result = await session.execute(select(Degree))
    degrees = result.scalars().all()
    
    if len(degrees) == 0:
        print("📚 Lookup tables not found, initializing...")
        await initLookup(session)
    else:
        print("📚 Lookup tables already initialized, skipping...")
        print(f"✅ Found {len(degrees)} degrees in database")


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
            "role": UserRole.ADMIN
        },
        {
            "nycu_id": "super_admin",
            "name": "超級管理員",
            "email": "super_admin@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "9000",
            "dept_name": "教務處",
            "role": UserRole.SUPER_ADMIN
        },
        {
            "nycu_id": "professor",
            "name": "李教授",
            "email": "professor@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "7000",
            "dept_name": "資訊學院",
            "role": UserRole.PROFESSOR
        },
        {
            "nycu_id": "college",
            "name": "學院審核員",
            "email": "college@nycu.edu.tw",
            "user_type": "employee",
            "status": "在職",
            "dept_code": "7000",
            "dept_name": "資訊學院",
            "role": UserRole.COLLEGE
        },
        {
            "nycu_id": "stu_under",
            "name": "陳小明",
            "email": "stu_under@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT
        },
        {
            "nycu_id": "stu_phd",
            "name": "王博士",
            "email": "stu_phd@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT
        },
        {
            "nycu_id": "stu_direct",
            "name": "李逕升",
            "email": "stu_direct@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT
        },
        {
            "nycu_id": "stu_master",
            "name": "張碩士",
            "email": "stu_master@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT
        },
        {
            "nycu_id": "phd_china",
            "name": "陸生",
            "email": "phd_china@nycu.edu.tw",
            "user_type": "student",
            "status": "在學",
            "dept_code": "CS",
            "dept_name": "資訊工程學系",
            "role": UserRole.STUDENT
        }
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
                role=user_data["role"]
            )
            session.add(user)
            created_users.append(user)
    
    await session.commit()
    
    # Refresh to get IDs
    for user in created_users:
        await session.refresh(user)
    
    print(f"✅ Created {len(created_users)} test users")
    return created_users


# Student data creation removed - students are now fetched from external API
# async def createTestStudents(session: AsyncSession, users: List[User]) -> None:
#     """Create test student data with new normalized structure"""
#     
#     print("🎓 Creating test student data...")
#     
#     student_users = [user for user in users if user.role == UserRole.STUDENT]
# 
#     # 修正 degree: 1=博士, 2=碩士, 3=學士
#     student_data = {
#        "stu_under": {
#            "std_pid": "A123456789",
#            "std_sex": "1",  # 1:男, 2:女
#            "std_degree": "3",  # 學士
#            "std_identity": "1", # 一般生
#            "std_studingstatus": "1", # 在學
#            "std_schoolid": "1", # 一般生
#            "std_termcount": 2,
#            "std_depno": "CS",
#            "std_depname": "資訊工程學系",
#            "std_aca_no": "EE",
#            "std_aca_cname": "電機資訊學院",
#            "std_enrollterm": "1", # 大學個人申請
#            "std_enrollyear": "112",
#            "std_highestschname": "台北市立建國高級中學",
#            "std_nation": "1", # 中華民國
#            "com_cellphone": "0912345678",
#            "com_email": "stu_under@nycu.edu.tw",
#            "com_commzip": "30010",
#            "com_commadd": "新竹市東區大學路1001號",
#            "std_enrolled_date": date(2023, 9, 1),
#            "std_bank_account": "1234567890",
#            "notes": "學士班新生"
#        },
#        "stu_phd": {
#            "std_pid": "B123456789",
#            "std_sex": "1",  # 1:男, 2:女
#            "std_degree": "1", # 博士
#            "std_identity": "1", # 一般生
#            "std_studingstatus": "1", # 在學
#            "std_schoolid": "1", # 一般生
#            "std_termcount": 1,
#            "std_depno": "CS",
#            "std_depname": "資訊工程學系",
#            "std_aca_no": "EE",
#            "std_aca_cname": "電機資訊學院",
#            "std_enrollterm": "1", # 招生考試一般生
#            "std_enrollyear": "112",
#            "std_highestschname": "國立交通大學",
#            "std_nation": "1", # 中華民國
#            "com_cellphone": "0912345678",
#            "com_email": "stu_phd@nycu.edu.tw",
#            "com_commzip": "30010",
#            "com_commadd": "新竹市東區大學路1001號",
#            "std_enrolled_date": date(2023, 9, 1),
#            "std_bank_account": "1234567890",
#            "notes": "博士生"
#        },
#        "stu_direct": {
#            "std_pid": "C123456789",
#            "std_sex": "2",  # 1:男, 2:女
#            "std_degree": "1", # 博士
#            "std_identity": "1", # 一般生
#            "std_studingstatus": "1", # 在學
#            "std_schoolid": "1", # 一般生
#            "std_termcount": 1,
#            "std_depno": "CS",
#            "std_depname": "資訊工程學系",
#            "std_aca_no": "EE",
#            "std_aca_cname": "電機資訊學院",
#            "std_enrollterm": "1", # 第一學期
#            "std_enrollyear": "112",
#            "std_highestschname": "國立陽明交通大學",
#            "std_nation": "1", # 中華民國
#            "com_cellphone": "0912345678",
#            "com_email": "stu_direct@nycu.edu.tw",
#            "com_commzip": "30010",
#            "com_commadd": "新竹市東區大學路1001號",
#            "std_enrolled_date": date(2023, 9, 1),
#            "std_bank_account": "1234567890",
#            "notes": "逕讀博士生"
#        },
#        "stu_master": {
#            "std_pid": "D123456789",
#            "std_sex": "2",  # 1:男, 2:女
#            "std_degree": "2", # 碩士
#            "std_identity": "1", # 一般生
#            "std_studingstatus": "1", # 在學
#            "std_schoolid": "1", # 一般生
#            "std_termcount": 1,
#            "std_depno": "CS",
#            "std_depname": "資訊工程學系",
#            "std_aca_no": "EE",
#            "std_aca_cname": "電機資訊學院",
#            "std_enrollterm": "1", # 一般考試
#            "std_enrollyear": "112",
#            "std_highestschname": "國立台灣大學",
#            "std_nation": "1", # 中華民國
#            "com_cellphone": "0912345678",
#            "com_email": "stu_master@nycu.edu.tw",
#            "com_commzip": "30010",
#            "com_commadd": "新竹市東區大學路1001號",
#            "std_enrolled_date": date(2023, 9, 1),
#            "std_bank_account": "1234567890",
#            "notes": "碩士生"
#        },
#        "phd_china": {
#            "std_pid": "E123456789",
#            "std_sex": "1",  # 1:男, 2:女
#            "std_degree": "1", # 博士
#            "std_identity": "17", # 陸生
#            "std_studingstatus": "1", # 在學
#            "std_schoolid": "1", # 一般生
#            "std_termcount": 1,
#            "std_depno": "CS",
#            "std_depname": "資訊工程學系",
#            "std_aca_no": "EE",
#            "std_aca_cname": "電機資訊學院",
#            "std_enrollterm": "1", # 第一學期
#            "std_enrollyear": "112",
#            "std_highestschname": "國立清華大學",
#            "std_nation": "2", # 非中華民國國籍
#            "com_cellphone": "0912345678",
#            "com_email": "phd_china@nycu.edu.tw",
#            "com_commzip": "30010",
#            "com_commadd": "新竹市東區大學路1001號",
#            "std_enrolled_date": date(2023, 9, 1),
#            "std_bank_account": "1234567890",
#            "notes": "陸生博士生"
#        }
#    }
#
#    for user in student_users:
#        student_info = student_data[user.nycu_id]
#
#        result = await session.execute(select(Student).where(Student.std_pid == student_info["std_pid"]))
#        existing = result.scalar_one_or_none()
#        
#        if not existing:
#            student = Student(
#                std_stdcode=user.nycu_id,
#                std_cname=user.name,
#                std_ename=user.name,
#                std_degree=student_info.get("std_degree", "3"),  # Default to undergraduate
#                std_sex=student_info.get("std_sex", "1"),
#                std_pid=student_info.get("std_pid"),
#                std_studingstatus=student_info.get("std_studingstatus", "1"),
#                std_enrollyear=student_info.get("std_enrollyear"),
#                std_enrollterm=student_info.get("std_enrollterm"),
#                std_termcount=student_info.get("std_termcount"),
#                std_nation=student_info.get("std_nation", "中華民國"),
#                std_schoolid=student_info.get("std_schoolid", "1"),
#                std_identity=student_info.get("std_identity"),
#                std_depno=student_info.get("std_depno"),
#                std_depname=student_info.get("std_depname"),
#                std_aca_no=student_info.get("std_aca_no"),
#                std_aca_cname=student_info.get("std_aca_cname"),
#                std_highestschname=student_info.get("std_highestschname"),
#                com_cellphone=student_info.get("com_cellphone"),
#                com_email=student_info.get("com_email"),
#                com_commzip=student_info.get("com_commzip"),
#                com_commadd=student_info.get("com_commadd"),
#                std_enrolled_date=student_info.get("std_enrolled_date"),
#                std_bank_account=student_info.get("std_bank_account"),
#                notes=student_info.get("notes")
#            )
#            session.add(student)
#        
#        await session.commit()
#        print(f"✅ Student {user.nycu_id} created successfully!")
#
#    print("✅ Test student data created successfully!")


async def createTestScholarships(session: AsyncSession) -> None:
    """Create test scholarship data with dev-friendly settings"""
    
    print("🎓 Creating test scholarship data...")
    
    # Since students are now fetched from external API, we'll use user IDs for scholarships
    result = await session.execute(select(User).where(User.role == UserRole.STUDENT))
    student_users = result.scalars().all()
    
    # Use user IDs instead of student IDs (students are now in external API)
    student_ids = [user.id for user in student_users]
        
    # ==== 基本獎學金 ====
    scholarships_data = [
        {
            "code": "undergraduate_freshman",
            "name": "學士班新生獎學金",
            "name_en": "Undergraduate Freshman Scholarship",
            "description": "適用於學士班新生，需符合 GPA ≥ 3.38 或前35%排名",
            "description_en": "For undergraduate freshmen, requires GPA ≥ 3.38 or top 35% ranking",
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
            "application_cycle": ApplicationCycle.SEMESTER,
            "whitelist_enabled": not settings.debug,
            "sub_type_selection_mode": SubTypeSelectionMode.SINGLE,
            "status": ScholarshipStatus.ACTIVE.value,
            "created_by": 1,
            "updated_by": 1,
        }
    ]
    
    for scholarship_data in scholarships_data:
        # Check if scholarship already exists
        result = await session.execute(
            select(ScholarshipType).where(ScholarshipType.code == scholarship_data["code"])
        )
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
            "semester": None, # 學年制獎學金不需要學期
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "academic_year": 114,
            "semester": None, # 學年制獎學金不需要學期
            "is_template": False,
            "rule_name": "博士生獎學金 在學生身分 1: 在學 2: 應畢 3: 延畢",
            "rule_type": "student_term",
            "tag": "在學生",
            "description": "博士生獎學金需要在學生身分 1: 在學 2: 應畢 3: 延畢",
            "condition_field": "trm_studingstatus",
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "academic_year": 114,
            "semester": None, # 學年制獎學金不需要學期
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "academic_year": 114,
            "semester": None, # 學年制獎學金不需要學期
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
            "updated_by": admin_id
        },
        # 博士生獎學金 教育部獎學金 (一萬元) 5. 中華民國國籍 6. 一至三年級
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_1w",
            "academic_year": 114,
            "semester": None, # 學年制獎學金不需要學期
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_1w",
            "academic_year": 114,
            "semester": None, # 學年制獎學金不需要學期
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
            "updated_by": admin_id
        },
        # 博士生獎學金 教育部獎學金 (兩萬元) 7. 中華民國國籍 8. 一至三年級
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_2w",
            "academic_year": 114,
            "semester": None, # 學年制獎學金不需要學期
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_2w",
            "academic_year": 114,
            "semester": None, # 學年制獎學金不需要學期
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
            "updated_by": admin_id
        },
        # 逕博獎學金 共同規則 1. 博士生身分 2. 在學生身分 3. 非在職生身分 4. 非陸港澳生身分 5. 逕博生身分 6. 第一學年
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 113,
            "semester": Semester.FIRST,
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 113,
            "semester": Semester.FIRST,
            "is_template": False,
            "rule_name": "逕讀博士獎學金 在學生身分 1: 在學 2: 應畢 3: 延畢",
            "rule_type": "student_term",
            "tag": "在學生",
            "condition_field": "trm_studingstatus",
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 113,
            "semester": Semester.FIRST,
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 113,
            "semester": Semester.FIRST,
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 113,
            "semester": Semester.FIRST,
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "academic_year": 113,
            "semester": Semester.FIRST,
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
            "updated_by": admin_id
        },
        # 學士新生獎學金 共同規則 1.學士生身分
        {
            "scholarship_type_id": 1,
            "sub_type": None,
            "academic_year": 113,
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
            "updated_by": admin_id
        },
        # 一般生入學管道提醒規則
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_1w",
            "academic_year": 113,
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
            "updated_by": admin_id
        },
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_2w",
            "academic_year": 113,
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
            "updated_by": admin_id
        },
        # 中華民國國籍生身份提醒規則
        {
            "scholarship_type_id": 2,
            "sub_type": "nstc",
            "academic_year": 113,
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "condition_field": "trm_studingstatus",
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
        }
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
            sub_type_configs_data.extend([
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
                    "updated_by": 1
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
                    "updated_by": 1
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
                    "updated_by": 1
                }
            ])
        # 注意：general 子類型不需要特別配置，因為它代表預設情況
    
    # 創建子類型配置
    for config_data in sub_type_configs_data:
        # 檢查是否已存在
        result = await session.execute(
            select(ScholarshipSubTypeConfig).where(
                ScholarshipSubTypeConfig.scholarship_type_id == config_data["scholarship_type_id"],
                ScholarshipSubTypeConfig.sub_type_code == config_data["sub_type_code"]
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
    
    # 設定基本時間參數
    now = datetime.now(timezone.utc)
    start_date = now + timedelta(days=7)  # 一般申請開始
    end_date = now + timedelta(days=21)   # 一般申請結束
    renewal_start = now - timedelta(days=60)  # 續領申請開始
    renewal_end = now - timedelta(days=40)    # 續領申請結束
    
    # 學院代碼對應表 (用於博士生獎學金) - 基於NYCU官方學院代碼
    college_quotas = {
        "E": {"name": "電機學院", "name_en": "College of Electrical and Computer Engineering", "quota": 15},
        "C": {"name": "資訊學院", "name_en": "College of Computer Science", "quota": 12},
        "I": {"name": "工學院", "name_en": "College of Engineering", "quota": 12},
        "S": {"name": "理學院", "name_en": "College of Science", "quota": 10},
        "B": {"name": "工程生物學院", "name_en": "College of Engineering Bioscience", "quota": 8},
        "M": {"name": "管理學院", "name_en": "College of Management", "quota": 6},
        "A": {"name": "人社院", "name_en": "College of Humanities Arts and Social Sciences", "quota": 6},
        "K": {"name": "客家學院", "name_en": "College of Hakka Studies", "quota": 3},
        "O": {"name": "光電學院", "name_en": "College of Photonics", "quota": 8},
        "L": {"name": "科技法律學院", "name_en": "School of Law", "quota": 4},
        "D": {"name": "半導體學院", "name_en": "International College of Semiconductor Technology", "quota": 7},
        "G": {"name": "綠能學院", "name_en": "College of Artificial Intelligence", "quota": 6},
        "1": {"name": "醫學院", "name_en": "College of Medicine", "quota": 10},
        "2": {"name": "牙醫學院", "name_en": "College of Dentistry", "quota": 3},
        "3": {"name": "護理學院", "name_en": "College of Nursing", "quota": 4},
        "5": {"name": "藥物科學院", "name_en": "College of Pharmaceutical Sciences", "quota": 5},
        "6": {"name": "生醫工學院", "name_en": "College of Biomedical Science and Engineering", "quota": 7},
        "7": {"name": "生命科學院", "name_en": "College of Life Sciences", "quota": 8}
    }
    
    # 創建名額管理配置
    quota_configs_data = []
    
    for scholarship in scholarships:
        if scholarship.code == "undergraduate_freshman":
            # 學士班新生獎學金配置 - 無配額限制
            quota_configs_data.append({
                "scholarship_type_id": scholarship.id,
                "academic_year": 113,  # 民國113年
                "semester": Semester.FIRST,  # 第一學期
                "config_name": "學士班新生獎學金配置",
                "config_code": f"config_{scholarship.code}_113_first",
                "description": "113學年度第一學期學士班新生獎學金配置，無配額限制",
                "description_en": "Undergraduate freshman scholarship configuration AY113-first without quota limits",
                "has_quota_limit": False,  # 移除配額限制
                "has_college_quota": False,
                "quota_management_mode": QuotaManagementMode.NONE,  # 無配額管理
                "total_quota": None,  # 無總配額限制
                "college_quota_config": None,  # 無配額配置
                
                # 金額設定 (從 ScholarshipType 移至此處)
                "amount": 50000,  # 學士班新生獎學金金額
                "currency": "TWD",
                
                # 白名單設定 (依子獎學金類型區分)
                "whitelist_student_ids": {},
                
                # 申請時間設定
                "application_start_date": start_date,
                "application_end_date": end_date,
                "renewal_application_start_date": renewal_start,
                "renewal_application_end_date": renewal_end,
                
                # 審查時間設定
                "requires_professor_recommendation": False,
                "professor_review_start": end_date + timedelta(days=1),
                "professor_review_end": end_date + timedelta(days=7),
                "requires_college_review": False,
                "college_review_start": end_date + timedelta(days=8),
                "college_review_end": end_date + timedelta(days=14),
                "review_deadline": end_date + timedelta(days=21),
                
                "quota_allocation_rules": {
                    "unlimited_allocation": True  # 無配額限制
                },
                "is_active": True,
                "version": "1.0",
                "created_by": admin_id,
                "updated_by": admin_id
            })
            
        elif scholarship.code == "phd":
            # 博士生獎學金 - 子類型×學院矩陣配額管理
            # 每個子類型在每個學院都有獨立的配額
            phd_college_subtype_quotas = {
                # 國科會博士生獎學金 - 各學院配額
                "nstc": {
                    "E": 5,  # 電機學院 國科會 5個
                    "C": 4,  # 資訊學院 國科會 4個
                    "I": 4,  # 工學院 國科會 4個
                    "S": 3,  # 理學院 國科會 3個
                    "B": 3,  # 工程生物學院 國科會 3個
                    "O": 3,  # 光電學院 國科會 3個
                    "D": 3,  # 半導體學院 國科會 3個
                    "1": 4,  # 醫學院 國科會 4個
                    "6": 3,  # 生醫工學院 國科會 3個
                    "7": 3,  # 生命科學院 國科會 3個
                    "M": 2,  # 管理學院 國科會 2個
                    "A": 2,  # 人社院 國科會 2個
                    "K": 1   # 客家學院 國科會 1個
                },
                # 教育部博士生獎學金(一萬配合款) - 各學院配額
                "moe_1w": {
                    "E": 6,  # 電機學院 教育部一萬 6個
                    "C": 5,  # 資訊學院 教育部一萬 5個
                    "I": 5,  # 工學院 教育部一萬 5個
                    "S": 4,  # 理學院 教育部一萬 4個
                    "B": 3,  # 工程生物學院 教育部一萬 3個
                    "O": 4,  # 光電學院 教育部一萬 4個
                    "D": 4,  # 半導體學院 教育部一萬 4個
                    "1": 5,  # 醫學院 教育部一萬 5個
                    "6": 3,  # 生醫工學院 教育部一萬 3個
                    "7": 3,  # 生命科學院 教育部一萬 3個
                    "M": 3,  # 管理學院 教育部一萬 3個
                    "A": 3,  # 人社院 教育部一萬 3個
                    "K": 1   # 客家學院 教育部一萬 1個
                },
                # 教育部博士生獎學金(兩萬配合款) - 各學院配額
                "moe_2w": {
                    "E": 8,  # 電機學院 教育部兩萬 8個
                    "C": 6,  # 資訊學院 教育部兩萬 6個
                    "I": 6,  # 工學院 教育部兩萬 6個
                    "S": 5,  # 理學院 教育部兩萬 5個
                    "B": 4,  # 工程生物學院 教育部兩萬 4個
                    "O": 5,  # 光電學院 教育部兩萬 5個
                    "D": 5,  # 半導體學院 教育部兩萬 5個
                    "1": 6,  # 醫學院 教育部兩萬 6個
                    "6": 4,  # 生醫工學院 教育部兩萬 4個
                    "7": 4,  # 生命科學院 教育部兩萬 4個
                    "M": 3,  # 管理學院 教育部兩萬 3個
                    "A": 3,  # 人社院 教育部兩萬 3個
                    "K": 2   # 客家學院 教育部兩萬 2個
                }
            }
            
            # 計算總配額
            total_phd_quota = sum(sum(college_quotas.values()) for college_quotas in phd_college_subtype_quotas.values())
            
            quota_configs_data.append({
                "scholarship_type_id": scholarship.id,
                "academic_year": 113,  # 民國113年
                "semester": None,  # 學年制獎學金不需要學期
                "config_name": "博士生獎學金名額管理配置",
                "config_code": f"quota_config_{scholarship.code}_113",
                "description": "113學年度博士生獎學金名額管理配置，採用子類型×學院矩陣配額管理",
                "description_en": "Quota management configuration for PhD scholarship AY113 with sub-type × college matrix allocation",
                "has_quota_limit": True,
                "has_college_quota": True,
                "quota_management_mode": QuotaManagementMode.MATRIX_BASED,  # 使用矩陣配額管理模式
                "total_quota": total_phd_quota,  # 總配額 (所有子類型×學院的總和)
                "college_quota_config": phd_college_subtype_quotas,  # 子類型×學院矩陣配額
                
                # 金額設定 (從 ScholarshipType 移至此處)
                "amount": 60000,  # 博士生獎學金金額
                "currency": "TWD",
                
                # 白名單設定 (依子獎學金類型區分)
                "whitelist_student_ids": {},
                
                # 申請時間設定
                "application_start_date": start_date - timedelta(days=365),
                "application_end_date": end_date - timedelta(days=365),
                "renewal_application_start_date": renewal_start - timedelta(days=365),
                "renewal_application_end_date": renewal_end - timedelta(days=365),

                "renewal_professor_review_start": end_date - timedelta(days=365) + timedelta(days=1),
                "renewal_professor_review_end": end_date - timedelta(days=365) + timedelta(days=10),
                "renewal_college_review_start": end_date - timedelta(days=365) + timedelta(days=11),
                "renewal_college_review_end": end_date - timedelta(days=365) + timedelta(days=21),
                
                # 審查時間設定
                "requires_professor_recommendation": True,
                "professor_review_start": end_date - timedelta(days=365) + timedelta(days=1),
                "professor_review_end": end_date - timedelta(days=365) + timedelta(days=10),
                "requires_college_review": True,
                "college_review_start": end_date - timedelta(days=365) + timedelta(days=11),
                "college_review_end": end_date - timedelta(days=365) + timedelta(days=21),
                "review_deadline": end_date - timedelta(days=365) + timedelta(days=30),
                "quota_allocation_rules": {
                    "sub_type_quotas": {
                        "nstc": sum(phd_college_subtype_quotas["nstc"].values()),      # 國科會總名額: 23個
                        "moe_1w": sum(phd_college_subtype_quotas["moe_1w"].values()),  # 教育部一萬總名額: 28個
                        "moe_2w": sum(phd_college_subtype_quotas["moe_2w"].values())   # 教育部兩萬總名額: 36個
                    },
                    "matrix_quotas": phd_college_subtype_quotas,  # 矩陣配額數據
                    "matrix_allocation": True,  # 啟用矩陣分配模式
                    "backup_allocation": True,  # 允許同子類型不同學院間調配
                    "cross_subtype_allocation": False,  # 不允許跨子類型調配
                    "college_subtype_strict": True,  # 嚴格按學院×子類型分配
                    "renewal_priority": True  # 續領優先
                },
                "is_active": True,
                "version": "1.0",
                "created_by": admin_id,
                "updated_by": admin_id
            })

            quota_configs_data.append({
                "scholarship_type_id": scholarship.id,
                "academic_year": 114,  # 民國114年
                "semester": None,  # 學年制獎學金不需要學期
                "config_name": "博士生獎學金名額管理配置",
                "config_code": f"quota_config_{scholarship.code}_114",
                "description": "114學年度博士生獎學金名額管理配置，採用子類型×學院矩陣配額管理",
                "description_en": "Quota management configuration for PhD scholarship AY114 with sub-type × college matrix allocation",
                "has_quota_limit": True,
                "has_college_quota": True,
                "quota_management_mode": QuotaManagementMode.MATRIX_BASED,  # 使用矩陣配額管理模式
                "total_quota": total_phd_quota,  # 總配額 (所有子類型×學院的總和)
                "college_quota_config": phd_college_subtype_quotas,  # 子類型×學院矩陣配額
                
                # 金額設定 (從 ScholarshipType 移至此處)
                "amount": 40000,  # 博士生獎學金金額
                "currency": "TWD",
                
                # 白名單設定 (依子獎學金類型區分)
                "whitelist_student_ids": {},
                
                # 申請時間設定
                "application_start_date": start_date,
                "application_end_date": end_date,
                "renewal_application_start_date": renewal_start,
                "renewal_application_end_date": renewal_end,

                "renewal_professor_review_start": end_date + timedelta(days=1),
                "renewal_professor_review_end": end_date + timedelta(days=10),
                "renewal_college_review_start": end_date + timedelta(days=11),
                "renewal_college_review_end": end_date + timedelta(days=21),
                
                # 審查時間設定
                "requires_professor_recommendation": True,
                "professor_review_start": end_date + timedelta(days=1),
                "professor_review_end": end_date + timedelta(days=10),
                "requires_college_review": True,
                "college_review_start": end_date + timedelta(days=11),
                "college_review_end": end_date + timedelta(days=21),
                "review_deadline": end_date + timedelta(days=30),
                "quota_allocation_rules": {
                    "sub_type_quotas": {
                        "nstc": sum(phd_college_subtype_quotas["nstc"].values()),      # 國科會總名額: 23個
                        "moe_1w": sum(phd_college_subtype_quotas["moe_1w"].values()),  # 教育部一萬總名額: 28個
                        "moe_2w": sum(phd_college_subtype_quotas["moe_2w"].values())   # 教育部兩萬總名額: 36個
                    },
                    "matrix_quotas": phd_college_subtype_quotas,  # 矩陣配額數據
                    "matrix_allocation": True,  # 啟用矩陣分配模式
                    "backup_allocation": True,  # 允許同子類型不同學院間調配
                    "cross_subtype_allocation": False,  # 不允許跨子類型調配
                    "college_subtype_strict": True,  # 嚴格按學院×子類型分配
                    "renewal_priority": True  # 續領優先
                },
                "is_active": True,
                "version": "1.0",
                "created_by": admin_id,
                "updated_by": admin_id
            })
            
        elif scholarship.code == "direct_phd":
            quota_configs_data.append({
                "scholarship_type_id": scholarship.id,
                "academic_year": 113,  # 民國113年
                "semester": Semester.FIRST,  # 第一學期
                "config_name": "逕讀博士獎學金配置",
                "config_code": f"config_{scholarship.code}_113_first",
                "description": "113學年度第一學期逕讀博士獎學金配置，無配額限制",
                "description_en": "Direct PhD scholarship configuration AY113-first without quota limits",
                "has_quota_limit": False,  # 移除配額限制
                "has_college_quota": False,
                "quota_management_mode": QuotaManagementMode.NONE,  # 無配額管理
                "total_quota": None,  # 無總配額限制
                "college_quota_config": None,  # 無配額配置
                
                # 金額設定 (從 ScholarshipType 移至此處)
                "amount": 80000,  # 逕讀博士獎學金金額較高
                "currency": "TWD",
                
                # 白名單設定 (依子獎學金類型區分)
                "whitelist_student_ids": {},
                
                # 申請時間設定
                "application_start_date": start_date,
                "application_end_date": end_date,
                "renewal_application_start_date": renewal_start,
                "renewal_application_end_date": renewal_end,
                
                # 審查時間設定
                "requires_professor_recommendation": False,
                "professor_review_start": end_date + timedelta(days=1),
                "professor_review_end": end_date + timedelta(days=14),
                "requires_college_review": True,
                "college_review_start": end_date + timedelta(days=15),
                "college_review_end": end_date + timedelta(days=28),
                "review_deadline": end_date + timedelta(days=35),
                "quota_allocation_rules": {
                    "strict_qualification": True,
                    "first_year_only": True,
                    "direct_phd_track_only": True,
                    "unlimited_allocation": True  # 無配額限制
                },
                "is_active": True,
                "version": "1.0",
                "created_by": admin_id,
                "updated_by": admin_id
            })
    
    # 創建配置記錄
    for config_data in quota_configs_data:
        # 檢查是否已存在
        result = await session.execute(
            select(ScholarshipConfiguration).where(
                ScholarshipConfiguration.config_code == config_data["config_code"]
            )
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            config = ScholarshipConfiguration(**config_data)
            session.add(config)
    
    await session.commit()
    print("✅ Scholarship configurations created successfully!")
    print("📋 Created configurations for:")
    print("   - 學士班新生獎學金: 無配額限制，依學業成績與經濟需求評核")
    print(f"   - 博士生獎學金: 總名額150個，採用子類型×學院矩陣分配")
    print(f"     • 國科會 (40名): 電機(E)5、資訊(C)4、工學(I)4、理學(S)3、生物(B)3、光電(O)3、半導體(D)3、醫學(1)4、生醫工(6)3、生科(7)3、管理(M)2、人社(A)2、客家(K)1")
    print(f"     • 教育部一萬 (49名): 電機(E)6、資訊(C)5、工學(I)5、理學(S)4、生物(B)3、光電(O)4、半導體(D)4、醫學(1)5、生醫工(6)3、生科(7)3、管理(M)3、人社(A)3、客家(K)1")
    print(f"     • 教育部兩萬 (61名): 電機(E)8、資訊(C)6、工學(I)6、理學(S)5、生物(B)4、光電(O)5、半導體(D)5、醫學(1)6、生醫工(6)4、生科(7)4、管理(M)3、人社(A)3、客家(K)2")
    print("   - 逕讀博士獎學金: 無配額限制，依學術卓越表現評核")
    print("   - 僅博士生獎學金採用矩陣配額管理，其他獎學金無配額限制")


async def createTestApplicationsAndQuotaUsage(session: AsyncSession) -> None:
    """Create quota management data and verify configuration completeness"""
    
    print("📊 Setting up quota management data...")
    
    # Verify quota configurations exist
    result = await session.execute(
        select(ScholarshipConfiguration).where(ScholarshipConfiguration.is_active == True)
    )
    configs = result.scalars().all()
    
    print(f"✅ Found {len(configs)} active scholarship configurations:")
    for config in configs:
        print(f"   - {config.config_name}")
        if config.has_quota_limit and config.total_quota:
            print(f"     配額管理: 總名額 {config.total_quota}")
        elif not config.has_quota_limit:
            print(f"     配額管理: 無配額限制")
        if config.has_college_quota and config.college_quota_config:
            print(f"     矩陣配額: {len(config.college_quota_config)} 個子類型")
    
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
                "created_by": "system_init"
            }
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
            "meta_data": {
                "test_accounts": True,
                "security_notice": True
            }
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
                "environment": "development"
            }
        }
    ]
    
    for announcement_data in announcements_data:
        # 檢查是否已存在相同的公告（根據 title 和 meta_data 判斷）
        result = await session.execute(
            select(Notification).where(
                Notification.title == announcement_data["title"],
                Notification.related_resource_type == "system",
                Notification.user_id.is_(None)
            )
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            announcement = Notification(**announcement_data)
            session.add(announcement)
    
    await session.commit()
    print(f"✅ System announcements created successfully!")
    print("📋 System announcements include:")
    print("   - System initialization notice")
    print("   - Test accounts information")
    print("   - Development mode reminder")


async def createApplicationFields(session: AsyncSession) -> None:
    """Create initial application field configurations"""
    
    print("📝 Creating application field configurations...")
    
    # 獲取管理員用戶ID
    result = await session.execute(select(User).where(User.nycu_id == "admin"))
    admin_user = result.scalar_one_or_none()
    admin_id = admin_user.id if admin_user else 1
    
    # === 學士班新生獎學金字段配置 ===
    undergraduate_fields = [
        {
            "scholarship_type": "undergraduate_freshman",
            "field_name": "bank_account",
            "field_label": "郵局局帳號/玉山帳號",
            "field_label_en": "Post Office/ESUN Bank Account Number",
            "field_type": "text",
            "is_required": True,
            "placeholder": "請輸入您的郵局局帳號或玉山銀行帳號",
            "placeholder_en": "Please enter your Post Office or ESUN Bank account number",
            "max_length": 30,
            "display_order": 1,
            "is_active": True,
            "help_text": "請填寫正確的郵局局帳號或玉山銀行帳號以便獎學金匯款",
            "help_text_en": "Please provide your correct Post Office or ESUN Bank account number for scholarship remittance",
            "created_by": admin_id,
            "updated_by": admin_id
        },
    ]
    
    # === 博士生獎學金字段配置 ===
    phd_fields = [
        {
            "scholarship_type": "phd",
            "field_name": "advisor_info",
            "field_label": "指導教授姓名",
            "field_label_en": "Advisor Name",
            "field_type": "text",
            "is_required": True,
            "placeholder": "請輸入指導教授的姓名",
            "placeholder_en": "Please enter the name of the advisor",
            "max_length": 100,
            "display_order": 1,
            "is_active": True,
            "help_text": "請填寫指導教授的姓名",
            "help_text_en": "Please provide the name of the advisor",
            "created_by": admin_id,
            "updated_by": admin_id
        },
        {
            "scholarship_type": "phd",
            "field_name": "advisor_email",
            "field_label": "指導教授Email",
            "field_label_en": "Advisor Email",
            "field_type": "email",
            "is_required": True,
            "placeholder": "請輸入指導教授的Email",
            "placeholder_en": "Please enter the email of the advisor",
            "max_length": 100,
            "display_order": 2,
            "is_active": True,
            "help_text": "請填寫指導教授的Email",
            "help_text_en": "Please provide the email of the advisor",
            "created_by": admin_id,
            "updated_by": admin_id
        },
        {
            "scholarship_type": "phd",
            "field_name": "bank_account",
            "field_label": "郵局局帳號/玉山帳號",
            "field_label_en": "Post Office/ESUN Bank Account Number",
            "field_type": "text",
            "is_required": True,
            "placeholder": "請輸入您的郵局局帳號或玉山銀行帳號",
            "placeholder_en": "Please enter your Post Office or ESUN Bank account number",
            "max_length": 30,
            "display_order": 2,
            "is_active": True,
            "help_text": "請填寫正確的郵局局帳號或玉山銀行帳號以便獎學金匯款",
            "help_text_en": "Please provide your correct Post Office or ESUN Bank account number for scholarship remittance",
            "created_by": admin_id,
            "updated_by": admin_id
        }
    ]
    
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
        },
        {
            "scholarship_type": "direct_phd",
            "field_name": "bank_account",
            "field_label": "郵局局帳號/玉山帳號/支票",
            "field_label_en": "Post Office/ESUN Bank Account Number/Cheque",
            "field_type": "text",
            "is_required": True,
            "placeholder": "請輸入您的郵局局帳號、玉山銀行帳號或支票資訊",
            "placeholder_en": "Please enter your Post Office, ESUN Bank account number, or cheque information",
            "max_length": 50,
            "display_order": 6,
            "is_active": True,
            "help_text": "請填寫正確的帳號或支票資訊以便獎學金匯款",
            "help_text_en": "Please provide your correct account or cheque information for scholarship remittance",
            "created_by": admin_id,
            "updated_by": admin_id
        }
    ]
    
    # 創建所有字段
    all_fields = undergraduate_fields + phd_fields + direct_phd_fields
    
    for field_data in all_fields:
        # 檢查是否已存在
        result = await session.execute(
            select(ApplicationField).where(
                ApplicationField.scholarship_type == field_data["scholarship_type"],
                ApplicationField.field_name == field_data["field_name"]
            )
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            field = ApplicationField(**field_data)
            session.add(field)
    
    # === 文件配置 ===
    document_configs = [
        # 學士班文件
        {
            "scholarship_type": "undergraduate_freshman",
            "document_name": "存摺封面",
            "document_name_en": "Bank Statement Cover",
            "description": "請上傳存摺封面",
            "description_en": "Please upload bank statement cover",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": 1,
            "is_active": True,
            "upload_instructions": "請確保存摺封面清晰可讀，包含戶名、帳號、銀行名稱等資訊",
            "upload_instructions_en": "Please ensure the bank statement cover is clear and readable, including account name, account number, bank name, etc.",
            "created_by": admin_id,
            "updated_by": admin_id
        },
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
        },
        {
            "scholarship_type": "phd",
            "document_name": "存摺封面",
            "document_name_en": "Bank Statement Cover",
            "description": "請上傳存摺封面",
            "description_en": "Please upload bank statement cover",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": 5,
            "is_active": True,
            "upload_instructions": "請確保存摺封面清晰可讀，包含戶名、帳號、銀行名稱等資訊",
            "upload_instructions_en": "Please ensure the bank statement cover is clear and readable, including account name, account number, bank name, etc.",
            "created_by": admin_id,
            "updated_by": admin_id
        },
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
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
            "updated_by": admin_id
        },
        {
            "scholarship_type": "direct_phd",
            "document_name": "存摺封面",
            "document_name_en": "Bank Statement Cover",
            "description": "請上傳存摺封面",
            "description_en": "Please upload bank statement cover",
            "is_required": True,
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": 8,
            "is_active": True,
            "upload_instructions": "請確保存摺封面清晰可讀，包含戶名、帳號、銀行名稱等資訊",
            "upload_instructions_en": "Please ensure the bank statement cover is clear and readable, including account name, account number, bank name, etc.",
            "created_by": admin_id,
            "updated_by": admin_id
        }
    ]
    
    for doc_data in document_configs:
        # 檢查是否已存在
        result = await session.execute(
            select(ApplicationDocument).where(
                ApplicationDocument.scholarship_type == doc_data["scholarship_type"],
                ApplicationDocument.document_name == doc_data["document_name"]
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
        users = await createTestUsers(session)
        
        # Student data creation removed - students are now fetched from external API
        # await createTestStudents(session, users)
        
        # Create test scholarships
        await createTestScholarships(session)
        
        # Create application field configurations
        await createApplicationFields(session)
        
        # Create system announcements
        await createSystemAnnouncements(session)
    
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