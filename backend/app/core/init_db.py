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
    # 查詢表
    Degree, Identity, StudyingStatus, SchoolIdentity, Academy, Department, EnrollType,
    # 學生資料
    Student,
)

from app.db.base_class import Base
from app.models.scholarship import ScholarshipRule, ScholarshipType, ScholarshipStatus, ScholarshipCategory, ScholarshipSubTypeConfig
from app.models.enums import Semester, CycleType, SubTypeSelectionMode
from app.models.notification import Notification, NotificationType, NotificationPriority
from app.models.application_field import ApplicationField, ApplicationDocument
from app.core.config import settings


async def initLookupTables(session: AsyncSession) -> None:
    """Initialize lookup tables with base data"""
    
    print("📚 Initializing lookup tables...")
    
    # === 學位 ===
    # 1 博士, 2 碩士, 3 大學
    degrees_data = [
        {"id": 1, "name": "博士"},
        {"id": 2, "name": "碩士"},
        {"id": 3, "name": "學士"}
    ]
    
    for degree_data in degrees_data:
        result = await session.execute(select(Degree).where(Degree.id == degree_data["id"]))
        existing = result.scalar_one_or_none()
        
        if not existing:
            degree = Degree(**degree_data)
            session.add(degree)
    
    # === 學生身份 ===
    identities_data = [
        {"id": 1, "name": "一般生"},
        {"id": 2, "name": "原住民"},
        {"id": 3, "name": "僑生(目前有中華民國國籍生)"},
        {"id": 4, "name": "外籍生(目前有中華民國國籍生)"},
        {"id": 5, "name": "外交子女"},
        {"id": 6, "name": "身心障礙生"},
        {"id": 7, "name": "運動成績優良甄試學生"},
        {"id": 8, "name": "離島"},
        {"id": 9, "name": "退伍軍人"},
        {"id": 10, "name": "一般公費生"},
        {"id": 11, "name": "原住民公費生"},
        {"id": 12, "name": "離島公費生"},
        {"id": 13, "name": "退伍軍人公費生"},
        {"id": 14, "name": "願景計畫生"},
        {"id": 17, "name": "陸生"},
        {"id": 30, "name": "其他"}
    ]
    
    for identity_data in identities_data:
        result = await session.execute(select(Identity).where(Identity.id == identity_data["id"]))
        existing = result.scalar_one_or_none()
        
        if not existing:
            identity = Identity(**identity_data)
            session.add(identity)
    
    # === 學籍狀態 ===
    studying_statuses_data = [
        {"id": 1, "name": "在學"},
        {"id": 2, "name": "應畢"},
        {"id": 3, "name": "延畢"},
        {"id": 4, "name": "休學"},
        {"id": 5, "name": "期中退學"},
        {"id": 6, "name": "期末退學"},
        {"id": 7, "name": "開除學籍"},
        {"id": 8, "name": "死亡"},
        {"id": 9, "name": "保留學籍"},
        {"id": 10, "name": "放棄入學"},
        {"id": 11, "name": "畢業"}
    ]
    
    for status_data in studying_statuses_data:
        result = await session.execute(select(StudyingStatus).where(StudyingStatus.id == status_data["id"]))
        existing = result.scalar_one_or_none()
        
        if not existing:
            status = StudyingStatus(**status_data)
            session.add(status)
    
    # === 學校身份 ===
    school_identities_data = [
        {"id": 1, "name": "一般生"},
        {"id": 2, "name": "在職生"},
        {"id": 3, "name": "選讀學分"},
        {"id": 4, "name": "交換學生"},
        {"id": 5, "name": "外校生"},
        {"id": 6, "name": "提早選讀生"},
        {"id": 7, "name": "跨校生"},
        {"id": 8, "name": "專案選讀生"}
    ]
    
    for school_identity_data in school_identities_data:
        result = await session.execute(select(SchoolIdentity).where(SchoolIdentity.id == school_identity_data["id"]))
        existing = result.scalar_one_or_none()
        
        if not existing:
            school_identity = SchoolIdentity(**school_identity_data)
            session.add(school_identity)
    
    # === 學院 ===
    academies_data = [
        {"id": 1, "code": "EE", "name": "電機資訊學院"},
        {"id": 2, "code": "EN", "name": "工程學院"},
        {"id": 3, "code": "SC", "name": "理學院"},
        {"id": 4, "code": "LS", "name": "生科學院"},
        {"id": 5, "code": "HS", "name": "人社學院"},
        {"id": 6, "code": "MG", "name": "管理學院"},
        {"id": 7, "code": "HK", "name": "客家文化學院"},
        {"id": 8, "code": "IP", "name": "國際半導體產業學院"}
    ]
    
    for academy_data in academies_data:
        result = await session.execute(select(Academy).where(Academy.id == academy_data["id"]))
        existing = result.scalar_one_or_none()
        
        if not existing:
            academy = Academy(**academy_data)
            session.add(academy)
    
    # === 系所 ===
    departments_data = [
        {"id": 1, "code": "CS", "name": "資訊工程學系"},
        {"id": 2, "code": "ECE", "name": "電機工程學系"},
        {"id": 3, "code": "EE", "name": "電子工程學系"},
        {"id": 4, "code": "COMM", "name": "傳播與科技學系"},
        {"id": 5, "code": "CE", "name": "土木工程學系"},
        {"id": 6, "code": "CHE", "name": "化學工程學系"},
        {"id": 7, "code": "ME", "name": "機械工程學系"},
        {"id": 8, "code": "MSE", "name": "材料科學與工程學系"},
        {"id": 9, "code": "PHYS", "name": "物理學系"},
        {"id": 10, "code": "MATH", "name": "應用數學系"},
        {"id": 11, "code": "CHEM", "name": "應用化學系"},
        {"id": 12, "code": "LS", "name": "生命科學系"},
        {"id": 13, "code": "BIO", "name": "生物科技學系"},
        {"id": 14, "code": "FL", "name": "外國語文學系"},
        {"id": 15, "code": "ECON", "name": "經濟學系"},
        {"id": 16, "code": "MGMT", "name": "管理科學系"}
    ]
    
    for dept_data in departments_data:
        result = await session.execute(select(Department).where(Department.id == dept_data["id"]))
        existing = result.scalar_one_or_none()
        
        if not existing:
            department = Department(**dept_data)
            session.add(department)
    
    # === 入學管道 ===
    # 修正 degreeId: 1=博士, 2=碩士, 3=學士
    enroll_types_data = [
        # 博士班入學管道
        {"degreeId": 1, "code": 1, "name": "招生考試一般生", "name_en": "Regular Student - Entrance Exam"},
        {"degreeId": 1, "code": 2, "name": "招生考試在職生(目前有一般生)", "name_en": "Working Professional - Entrance Exam (Currently Regular)"},
        {"degreeId": 1, "code": 3, "name": "選讀生", "name_en": "Non-Degree Student"},
        {"degreeId": 1, "code": 4, "name": "推甄一般生", "name_en": "Regular Student - Recommendation"},
        {"degreeId": 1, "code": 5, "name": "推甄在職生(目前有一般生)", "name_en": "Working Professional - Recommendation (Currently Regular)"},
        {"degreeId": 1, "code": 6, "name": "僑生", "name_en": "Overseas Chinese Student"},
        {"degreeId": 1, "code": 7, "name": "外籍生", "name_en": "International Student"},
        {"degreeId": 1, "code": 8, "name": "大學逕博", "name_en": "Direct PhD from Bachelor"},
        {"degreeId": 1, "code": 9, "name": "碩士逕博", "name_en": "Direct PhD from Master"},
        {"degreeId": 1, "code": 10, "name": "跨校學士逕博", "name_en": "Direct PhD from Bachelor (Inter-University)"},
        {"degreeId": 1, "code": 11, "name": "跨校碩士逕博", "name_en": "Direct PhD from Master (Inter-University)"},
        {"degreeId": 1, "code": 12, "name": "雙聯學位", "name_en": "Dual Degree"},
        {"degreeId": 1, "code": 17, "name": "陸生", "name_en": "Mainland Chinese Student"},
        {"degreeId": 1, "code": 18, "name": "轉校", "name_en": "Transfer Student"},
        {"degreeId": 1, "code": 26, "name": "專案入學", "name_en": "Special Admission"},
        {"degreeId": 1, "code": 29, "name": "TIGP", "name_en": "Taiwan International Graduate Program"},
        {"degreeId": 1, "code": 30, "name": "其他", "name_en": "Others"},
        
        # 碩士班入學管道
        {"degreeId": 2, "code": 1, "name": "一般考試", "name_en": "Regular Entrance Exam"},
        {"degreeId": 2, "code": 2, "name": "推薦甄選", "name_en": "Recommendation Selection"},
        {"degreeId": 2, "code": 3, "name": "在職專班", "name_en": "Working Professional Program"},
        {"degreeId": 2, "code": 4, "name": "僑生", "name_en": "Overseas Chinese Student"},
        {"degreeId": 2, "code": 5, "name": "外籍生", "name_en": "International Student"},
        
        # 學士班入學管道
        {"degreeId": 3, "code": 1, "name": "大學個人申請", "name_en": "Individual Application"},
        {"degreeId": 3, "code": 2, "name": "大學考試分發", "name_en": "Examination Distribution"},
        {"degreeId": 3, "code": 3, "name": "四技二專甄選", "name_en": "Technical College Selection"},
        {"degreeId": 3, "code": 4, "name": "運動績優", "name_en": "Outstanding Athletic Achievement"},
        {"degreeId": 3, "code": 5, "name": "僑生", "name_en": "Overseas Chinese Student"},
        {"degreeId": 3, "code": 6, "name": "外籍生", "name_en": "International Student"}
    ]
    
    for enroll_type_data in enroll_types_data:
        enroll_type = EnrollType(**enroll_type_data)
        session.add(enroll_type)
    
    await session.commit()
    print("✅ Lookup tables initialized successfully!")


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


async def createTestStudents(session: AsyncSession, users: List[User]) -> None:
    """Create test student data with new normalized structure"""
    
    print("🎓 Creating test student data...")
    
    student_users = [user for user in users if user.role == UserRole.STUDENT]

    # 修正 degree: 1=博士, 2=碩士, 3=學士
    student_data = {
        "stu_under": {
            "std_pid": "A123456789",
            "std_sex": "1",  # 1:男, 2:女
            "std_degree": "3",  # 學士
            "std_identity": "1", # 一般生
            "std_studingstatus": "1", # 在學
            "std_schoolid": "1", # 一般生
            "std_termcount": 2,
            "std_depno": "CS",
            "std_depname": "資訊工程學系",
            "std_aca_no": "EE",
            "std_aca_cname": "電機資訊學院",
            "std_enrollterm": "1", # 大學個人申請
            "std_enrollyear": "112",
            "std_highestschname": "台北市立建國高級中學",
            "std_nation": "1", # 中華民國
            "com_cellphone": "0912345678",
            "com_email": "stu_under@nycu.edu.tw",
            "com_commzip": "30010",
            "com_commadd": "新竹市東區大學路1001號",
            "std_enrolled_date": date(2023, 9, 1),
            "std_bank_account": "1234567890",
            "notes": "學士班新生"
        },
        "stu_phd": {
            "std_pid": "B123456789",
            "std_sex": "1",  # 1:男, 2:女
            "std_degree": "1", # 博士
            "std_identity": "1", # 一般生
            "std_studingstatus": "1", # 在學
            "std_schoolid": "1", # 一般生
            "std_termcount": 1,
            "std_depno": "CS",
            "std_depname": "資訊工程學系",
            "std_aca_no": "EE",
            "std_aca_cname": "電機資訊學院",
            "std_enrollterm": "1", # 招生考試一般生
            "std_enrollyear": "112",
            "std_highestschname": "國立交通大學",
            "std_nation": "1", # 中華民國
            "com_cellphone": "0912345678",
            "com_email": "stu_phd@nycu.edu.tw",
            "com_commzip": "30010",
            "com_commadd": "新竹市東區大學路1001號",
            "std_enrolled_date": date(2023, 9, 1),
            "std_bank_account": "1234567890",
            "notes": "博士生"
        },
        "stu_direct": {
            "std_pid": "C123456789",
            "std_sex": "2",  # 1:男, 2:女
            "std_degree": "1", # 博士
            "std_identity": "1", # 一般生
            "std_studingstatus": "1", # 在學
            "std_schoolid": "1", # 一般生
            "std_termcount": 1,
            "std_depno": "CS",
            "std_depname": "資訊工程學系",
            "std_aca_no": "EE",
            "std_aca_cname": "電機資訊學院",
            "std_enrollterm": "1", # 第一學期
            "std_enrollyear": "112",
            "std_highestschname": "國立陽明交通大學",
            "std_nation": "1", # 中華民國
            "com_cellphone": "0912345678",
            "com_email": "stu_direct@nycu.edu.tw",
            "com_commzip": "30010",
            "com_commadd": "新竹市東區大學路1001號",
            "std_enrolled_date": date(2023, 9, 1),
            "std_bank_account": "1234567890",
            "notes": "逕讀博士生"
        },
        "stu_master": {
            "std_pid": "D123456789",
            "std_sex": "2",  # 1:男, 2:女
            "std_degree": "2", # 碩士
            "std_identity": "1", # 一般生
            "std_studingstatus": "1", # 在學
            "std_schoolid": "1", # 一般生
            "std_termcount": 1,
            "std_depno": "CS",
            "std_depname": "資訊工程學系",
            "std_aca_no": "EE",
            "std_aca_cname": "電機資訊學院",
            "std_enrollterm": "1", # 一般考試
            "std_enrollyear": "112",
            "std_highestschname": "國立台灣大學",
            "std_nation": "1", # 中華民國
            "com_cellphone": "0912345678",
            "com_email": "stu_master@nycu.edu.tw",
            "com_commzip": "30010",
            "com_commadd": "新竹市東區大學路1001號",
            "std_enrolled_date": date(2023, 9, 1),
            "std_bank_account": "1234567890",
            "notes": "碩士生"
        },
        "phd_china": {
            "std_pid": "E123456789",
            "std_sex": "1",  # 1:男, 2:女
            "std_degree": "1", # 博士
            "std_identity": "17", # 陸生
            "std_studingstatus": "1", # 在學
            "std_schoolid": "1", # 一般生
            "std_termcount": 1,
            "std_depno": "CS",
            "std_depname": "資訊工程學系",
            "std_aca_no": "EE",
            "std_aca_cname": "電機資訊學院",
            "std_enrollterm": "1", # 第一學期
            "std_enrollyear": "112",
            "std_highestschname": "國立清華大學",
            "std_nation": "2", # 非中華民國國籍
            "com_cellphone": "0912345678",
            "com_email": "phd_china@nycu.edu.tw",
            "com_commzip": "30010",
            "com_commadd": "新竹市東區大學路1001號",
            "std_enrolled_date": date(2023, 9, 1),
            "std_bank_account": "1234567890",
            "notes": "陸生博士生"
        }
    }

    for user in student_users:
        student_info = student_data[user.nycu_id]

        result = await session.execute(select(Student).where(Student.std_pid == student_info["std_pid"]))
        existing = result.scalar_one_or_none()
        
        if not existing:
            student = Student(
                std_stdcode=user.nycu_id,
                std_cname=user.name,
                std_ename=user.name,
                std_degree=student_info.get("std_degree", "3"),  # Default to undergraduate
                std_sex=student_info.get("std_sex", "1"),
                std_pid=student_info.get("std_pid"),
                std_studingstatus=student_info.get("std_studingstatus", "1"),
                std_enrollyear=student_info.get("std_enrollyear"),
                std_enrollterm=student_info.get("std_enrollterm"),
                std_termcount=student_info.get("std_termcount"),
                std_nation=student_info.get("std_nation", "1"),
                std_schoolid=student_info.get("std_schoolid", "1"),
                std_identity=student_info.get("std_identity"),
                std_depno=student_info.get("std_depno"),
                std_depname=student_info.get("std_depname"),
                std_aca_no=student_info.get("std_aca_no"),
                std_aca_cname=student_info.get("std_aca_cname"),
                std_highestschname=student_info.get("std_highestschname"),
                com_cellphone=student_info.get("com_cellphone"),
                com_email=student_info.get("com_email"),
                com_commzip=student_info.get("com_commzip"),
                com_commadd=student_info.get("com_commadd"),
                std_enrolled_date=student_info.get("std_enrolled_date"),
                std_bank_account=student_info.get("std_bank_account"),
                notes=student_info.get("notes")
            )
            session.add(student)
        
        await session.commit()
        print(f"✅ Student {user.nycu_id} created successfully!")

    print("✅ Test student data created successfully!")


async def createTestScholarships(session: AsyncSession) -> None:
    """Create test scholarship data with dev-friendly settings"""
    
    print("🎓 Creating test scholarship data...")
    
    # 獲取學生ID用於白名單
    result = await session.execute(select(User).where(User.role == UserRole.STUDENT))
    student_users = result.scalars().all()
    
    # 獲取對應的學生資料
    student_ids = []
    for user in student_users:
        result = await session.execute(select(Student).where(Student.std_stdcode == user.nycu_id))
        student = result.scalar_one_or_none()
        if student:
            student_ids.append(student.id)
    
    # 開發模式下設定申請期間（當前時間前後各30天）
    now = datetime.now(timezone.utc)
    
    # 續領期間設定（優先處理，完整流程）
    renewal_start = now - timedelta(days=60)  # 續領申請開始
    renewal_end = now - timedelta(days=40)    # 續領申請結束
    renewal_professor_start = now - timedelta(days=39)  # 續領教授審查開始
    renewal_professor_end = now - timedelta(days=30)    # 續領教授審查結束
    renewal_college_start = now - timedelta(days=29)    # 續領學院審查開始
    renewal_college_end = now - timedelta(days=20)      # 續領學院審查結束
    
    # 一般申請期間設定（續領流程完全結束後）
    start_date = now - timedelta(days=15)     # 一般申請開始
    end_date = now + timedelta(days=15)       # 一般申請結束
    
    # ==== 基本獎學金 ====
    scholarships_data = [
        {
            "code": "undergraduate_freshman",
            "name": "學士班新生獎學金",
            "name_en": "Undergraduate Freshman Scholarship",
            "description": "適用於學士班新生，需符合 GPA ≥ 3.38 或前35%排名",
            "description_en": "For undergraduate freshmen, requires GPA ≥ 3.38 or top 35% ranking",
            "category": ScholarshipCategory.UNDERGRADUATE_FRESHMAN.value,
            "academic_year": 113,  # 民國113年
            "semester": Semester.FIRST,
            "application_cycle": CycleType.SEMESTER,
            "amount": 10000.00,
            "currency": "TWD",
            "whitelist_enabled": not settings.debug,
            "whitelist_student_ids": student_ids if not settings.debug else [],
            # 續領申請期間（優先處理，完整流程）
            "renewal_application_start_date": renewal_start,
            "renewal_application_end_date": renewal_end,
            # 續領審查期間
            "renewal_professor_review_start": renewal_professor_start,
            "renewal_professor_review_end": renewal_professor_end,
            "renewal_college_review_start": renewal_college_start,
            "renewal_college_review_end": renewal_college_end,
            # 一般申請期間（續領流程完全結束後）
            "application_start_date": start_date,
            "application_end_date": end_date,
            # 一般申請審查期間
            "professor_review_start": end_date + timedelta(days=1),
            "professor_review_end": end_date + timedelta(days=14),
            "college_review_start": end_date + timedelta(days=15),
            "college_review_end": end_date + timedelta(days=21),
            "sub_type_selection_mode": SubTypeSelectionMode.SINGLE,
            "status": ScholarshipStatus.ACTIVE.value,
            "requires_professor_recommendation": False,
            "requires_college_review": False,
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
            "academic_year": 113,  # 民國113年
            "semester": Semester.FIRST,
            "application_cycle": CycleType.SEMESTER,
            "sub_type_list": ["nstc", "moe_1w", "moe_2w"],
            "amount": 40000.00,
            "currency": "TWD",
            "whitelist_enabled": False,
            "whitelist_student_ids": [],
            # 續領申請期間（優先處理，完整流程）
            "renewal_application_start_date": renewal_start,
            "renewal_application_end_date": renewal_end,
            # 續領審查期間
            "renewal_professor_review_start": renewal_professor_start,
            "renewal_professor_review_end": renewal_professor_end,
            "renewal_college_review_start": renewal_college_start,
            "renewal_college_review_end": renewal_college_end,
            # 一般申請期間（續領流程完全結束後）
            "application_start_date": start_date,
            "application_end_date": end_date,
            # 一般申請審查期間
            "professor_review_start": end_date + timedelta(days=1),
            "professor_review_end": end_date + timedelta(days=14),
            "college_review_start": end_date + timedelta(days=15),
            "college_review_end": end_date + timedelta(days=21),
            "sub_type_selection_mode": SubTypeSelectionMode.MULTIPLE,
            "status": ScholarshipStatus.ACTIVE.value,
            "requires_professor_recommendation": True,
            "requires_college_review": True,
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
            "academic_year": 113,  # 民國113年
            "semester": Semester.FIRST,
            "application_cycle": CycleType.SEMESTER,
            "amount": 10000.00,
            "currency": "TWD",
            "whitelist_enabled": not settings.debug,
            "whitelist_student_ids": student_ids if not settings.debug else [],
            # 續領申請期間（優先處理，完整流程）
            "renewal_application_start_date": renewal_start,
            "renewal_application_end_date": renewal_end,
            # 續領審查期間
            "renewal_professor_review_start": renewal_professor_start,
            "renewal_professor_review_end": renewal_professor_end,
            "renewal_college_review_start": renewal_college_start,
            "renewal_college_review_end": renewal_college_end,
            # 一般申請期間（續領流程完全結束後）
            "application_start_date": start_date,
            "application_end_date": end_date,
            # 一般申請審查期間
            "professor_review_start": end_date + timedelta(days=1),
            "professor_review_end": end_date + timedelta(days=14),
            "college_review_start": end_date + timedelta(days=15),
            "college_review_end": end_date + timedelta(days=21),
            "sub_type_selection_mode": SubTypeSelectionMode.SINGLE,
            "status": ScholarshipStatus.ACTIVE.value,
            "requires_professor_recommendation": False,
            "requires_college_review": False,
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
    scholarship_rules_data = [
        # 博士生獎學金 共同規則 1. 博士生身分 2. 在學生身分 3. 非在職生身分 4. 非陸港澳生身分
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "rule_name": "博士生獎學金 博士生身分",
            "rule_type": "degree",
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
            "is_active": True
        },
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "rule_name": "博士生獎學金 在學生身分 1: 在學 2: 應畢 3: 延畢",
            "rule_type": "studyingStatus",
            "tag": "在學生",
            "description": "博士生獎學金需要在學生身分 1: 在學 2: 應畢 3: 延畢",
            "condition_field": "std_studingstatus",
            "operator": "in",
            "expected_value": "1,2,3",
            "message": "博士生獎學金需要在學生身分 1: 在學 2: 應畢 3: 延畢",
            "message_en": "PhD scholarship requires active student status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 2,
            "is_active": True
        },
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "rule_name": "博士生獎學金 非在職生身分 需要為一般生",
            "rule_type": "schoolIdentity",
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
            "is_active": True
        },
        {
            "scholarship_type_id": 2,
            "sub_type": None,
            "rule_name": "博士生獎學金 非陸港澳生身分",
            "rule_type": "Identity",
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
            "is_active": True
        },
        # 博士生獎學金 教育部獎學金 (一萬元) 5. 中華民國國籍 6. 一至三年級
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_1w",
            "rule_name": "博士生獎學金 教育部獎學金 中華民國國籍",
            "tag": "中華民國國籍",
            "description": "博士生獎學金需要中華民國國籍",
            "rule_type": "nationality",
            "condition_field": "std_nation",
            "operator": "==",
            "expected_value": "1",
            "message": "博士生獎學金需要中華民國國籍",
            "message_en": "PhD scholarship requires Chinese nationality",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 5,
            "is_active": True
        },
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_1w",
            "rule_name": "博士生獎學金 教育部獎學金 一至三年級(1-6學期)",
            "tag": "三年級以下",
            "description": "博士生獎學金需要一至三年級",
            "rule_type": "termCount",
            "condition_field": "std_termcount",
            "operator": "in",
            "expected_value": "1,2,3,4,5,6",
            "message": "博士生獎學金需要一至三年級",
            "message_en": "PhD scholarship requires 1-3rd year",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 6,
            "is_active": True
        },
        # 博士生獎學金 教育部獎學金 (兩萬元) 7. 中華民國國籍 8. 一至三年級
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_2w",
            "rule_name": "博士生獎學金 教育部獎學金 中華民國國籍",
            "tag": "中華民國國籍",
            "description": "博士生獎學金需要中華民國國籍",
            "rule_type": "nationality",
            "condition_field": "std_nation",
            "operator": "==",
            "expected_value": "1",
            "message": "博士生獎學金需要中華民國國籍",
            "message_en": "PhD scholarship requires Chinese nationality",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 7,
            "is_active": True
        },
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_2w",
            "rule_name": "博士生獎學金 教育部獎學金 一至三年級(1-6學期)",
            "tag": "三年級以下",
            "description": "博士生獎學金需要一至三年級",
            "rule_type": "termCount",
            "condition_field": "std_termcount",
            "operator": "in",
            "expected_value": "1,2,3,4,5,6",
            "message": "博士生獎學金需要一至三年級",
            "message_en": "PhD scholarship requires 1-3rd year",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 8,
            "is_active": True
        },
        # 逕博獎學金 共同規則 1. 博士生身分 2. 在學生身分 3. 非在職生身分 4. 非陸港澳生身分 5. 逕博生身分 6. 第一學年
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "rule_name": "逕讀博士獎學金 博士生身分",
            "tag": "博士生",
            "description": "逕讀博士獎學金需要博士生身分",
            "rule_type": "degree",
            "condition_field": "std_degree",
            "operator": "==",
            "expected_value": "1",
            "message": "逕讀博士獎學金需要博士生身分",
            "message_en": "Direct PhD scholarship requires PhD student status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 1,
            "is_active": True
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "rule_name": "逕讀博士獎學金 在學生身分 1: 在學 2: 應畢 3: 延畢",
            "rule_type": "studyingStatus",
            "tag": "在學生",
            "condition_field": "std_studingstatus",
            "operator": "in",
            "expected_value": "1,2,3",
            "message": "逕讀博士獎學金需要在學生身分 1: 在學 2: 應畢 3: 延畢",
            "message_en": "Direct PhD scholarship requires active student status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 2,
            "is_active": True
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "rule_name": "逕讀博士獎學金 非在職生身分 需要為一般生",
            "rule_type": "schoolIdentity",
            "tag": "非在職生",
            "condition_field": "std_schoolid",
            "operator": "==",
            "expected_value": "1",
            "message": "逕讀博士獎學金需要非在職生身分 需要為一般生",
            "message_en": "Direct PhD scholarship requires regular student status",
            "is_hard_rule": False,
            "is_warning": False,
            "priority": 3,
            "is_active": True
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "rule_name": "逕讀博士獎學金 非陸港澳生身分",
            "rule_type": "Identity",
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
            "is_active": True
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "rule_name": "逕讀博士獎學金 逕博生身分 8: 大學逕博 9: 碩士逕博 10: 跨校學士逕博 11: 跨校碩士逕博",
            "rule_type": "enrollType",
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
            "is_active": True
        },
        {
            "scholarship_type_id": 3,
            "sub_type": None,
            "rule_name": "逕讀博士獎學金 第一學年",
            "rule_type": "termCount",
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
            "is_active": True
        },
        # 學士新生獎學金 共同規則 1.學士生身分
        {
            "scholarship_type_id": 1,
            "sub_type": None,
            "rule_name": "學士新生獎學金 學士生身分",
            "tag": "學士生",
            "description": "學士新生獎學金需要學士生身分",
            "rule_type": "degree",
            "condition_field": "std_degree",
            "operator": "==",
            "expected_value": "3",
            "message": "學士新生獎學金需要學士生身分",
            "message_en": "Undergraduate scholarship requires undergraduate student status",
            "is_hard_rule": True,
            "is_warning": False,
            "priority": 1,
            "is_active": True
        },
        # 一般生入學管道提醒規則
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_1w",
            "rule_name": "博士生獎學金 一般生入學管道提醒",
            "tag": "一般生",
            "description": "一般生身份學生，其入學管道可能為2/5/6/7，請承辦人確認。若為2/5/6/7請特別留意（標紅字）。",
            "rule_type": "enrollTypeWarning",
            "condition_field": "std_enrollterm",
            "operator": "in",
            "expected_value": "2,5,6,7",
            "message": "此學生為一般生，但入學管道為2/5/6/7，請承辦人確認（標紅字）。",
            "message_en": "This student is a regular student but has an enrollment type of 2/5/6/7. Please double-check (highlighted in red).",
            "is_hard_rule": False,
            "is_warning": True,
            "priority": 99,
            "is_active": True
        },
        {
            "scholarship_type_id": 2,
            "sub_type": "moe_2w",
            "rule_name": "博士生獎學金 一般生入學管道提醒",
            "tag": "一般生",
            "description": "一般生身份學生，其入學管道可能為2/5/6/7，請承辦人確認。若為2/5/6/7請特別留意（標紅字）。",
            "rule_type": "enrollTypeWarning",
            "condition_field": "std_enrollterm",
            "operator": "in",
            "expected_value": "2,5,6,7",
            "message": "此學生為一般生，但入學管道為2/5/6/7，請承辦人確認（標紅字）。",
            "message_en": "This student is a regular student but has an enrollment type of 2/5/6/7. Please double-check (highlighted in red).",
            "is_hard_rule": False,
            "is_warning": True,
            "priority": 99,
            "is_active": True
        },
        # 中華民國國籍生身份提醒規則
        {
            "scholarship_type_id": 2,
            "sub_type": "nstc",
            "rule_name": "中華民國國籍生身份提醒",
            "tag": "中華民國國籍",
            "description": "中華民國國籍生的身份可能為僑生、外籍生，請承辦人自行確認（3/4標紅字）。",
            "rule_type": "identityWarning",
            "condition_field": "std_identity",
            "operator": "in",
            "expected_value": "3,4",
            "message": "此中華民國國籍生身份為僑生或外籍生，請承辦人確認（標紅字）。",
            "message_en": "This ROC national student is classified as Overseas Chinese or International Student. Please double-check (highlighted in red).",
            "is_hard_rule": False,
            "is_warning": True,
            "priority": 100,
            "is_active": True
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
        if scholarship.code == "phd":
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
    print("✅ Test scholarship data created successfully!")
    
    if settings.debug:
        print("🔧 DEV MODE: All scholarships are open for application")
        print("🔧 DEV MODE: Whitelist checks are bypassed")


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
        
        # Create test students
        await createTestStudents(session, users)
        
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