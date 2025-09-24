"""
Lookup tables initialization script for scholarship system

This module contains all reference data that rarely changes,
separated from test data for better maintainability.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base_class import Base
from app.db.session import AsyncSessionLocal, async_engine
from app.models.student import Academy, Degree, Department, EnrollType, Identity, SchoolIdentity, StudyingStatus

logger = logging.getLogger(__name__)


async def initLookupTables(session: AsyncSession) -> None:
    """Initialize all lookup/reference tables with official NYCU data"""

    logger.info("Initializing lookup tables with official NYCU data...")

    # === 學位類型 ===
    print("  📖 Initializing degrees...")
    degrees_data = [
        {"id": 1, "name": "博士"},
        {"id": 2, "name": "碩士"},
        {"id": 3, "name": "學士"},
    ]

    for degree_data in degrees_data:
        result = await session.execute(select(Degree).where(Degree.id == degree_data["id"]))
        existing = result.scalar_one_or_none()

        if not existing:
            degree = Degree(**degree_data)
            session.add(degree)

    # === 學生身份類型 ===
    print("  🎓 Initializing student identities...")
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
        {"id": 30, "name": "其他"},
    ]

    for identity_data in identities_data:
        result = await session.execute(select(Identity).where(Identity.id == identity_data["id"]))
        existing = result.scalar_one_or_none()

        if not existing:
            identity = Identity(**identity_data)
            session.add(identity)

    # === 學籍狀態 ===
    print("  📋 Initializing studying statuses...")
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
        {"id": 11, "name": "畢業"},
    ]

    for status_data in studying_statuses_data:
        result = await session.execute(select(StudyingStatus).where(StudyingStatus.id == status_data["id"]))
        existing = result.scalar_one_or_none()

        if not existing:
            status = StudyingStatus(**status_data)
            session.add(status)

    # === 學校身份 ===
    print("  🏫 Initializing school identities...")
    school_identities_data = [
        {"id": 1, "name": "一般生"},
        {"id": 2, "name": "在職生"},
        {"id": 3, "name": "選讀學分"},
        {"id": 4, "name": "交換學生"},
        {"id": 5, "name": "外校生"},
        {"id": 6, "name": "提早選讀生"},
        {"id": 7, "name": "跨校生"},
        {"id": 8, "name": "專案選讀生"},
    ]

    for school_identity_data in school_identities_data:
        result = await session.execute(select(SchoolIdentity).where(SchoolIdentity.id == school_identity_data["id"]))
        existing = result.scalar_one_or_none()

        if not existing:
            school_identity = SchoolIdentity(**school_identity_data)
            session.add(school_identity)

    # === NYCU 官方學院資料 (28個學院) ===
    print("  🏛️ Initializing NYCU academies (28 colleges)...")
    # 基於 NYCU 官方學院代碼對應表
    academies_data = [
        {"id": 1, "code": "E", "name": "電機學院"},
        {"id": 2, "code": "Y", "name": "電資學院"},
        {"id": 3, "code": "C", "name": "資訊學院"},
        {"id": 4, "code": "B", "name": "工程生物學院"},
        {"id": 5, "code": "M", "name": "管理學院"},
        {"id": 6, "code": "I", "name": "工學院"},
        {"id": 7, "code": "S", "name": "理學院"},
        {"id": 8, "code": "A", "name": "人社院"},
        {"id": 9, "code": "K", "name": "客家學院"},
        {"id": 10, "code": "X", "name": "電機資訊學院"},
        {"id": 11, "code": "4", "name": "選讀生"},
        {"id": 12, "code": "*", "name": "外校生"},
        {"id": 13, "code": "^", "name": "校內其他單位"},
        {"id": 14, "code": "O", "name": "光電學院"},
        {"id": 15, "code": "L", "name": "科技法律學院"},
        {"id": 16, "code": "D", "name": "半導體學院"},
        {"id": 17, "code": "G", "name": "綠能學院"},
        {"id": 18, "code": "Z", "name": "國防中心"},
        {"id": 19, "code": "8", "name": "人社院"},
        {"id": 20, "code": "1", "name": "醫學院"},
        {"id": 21, "code": "2", "name": "牙醫學院"},
        {"id": 22, "code": "3", "name": "護理學院"},
        {"id": 23, "code": "5", "name": "藥物科學院"},
        {"id": 24, "code": "6", "name": "生醫工學院"},
        {"id": 25, "code": "7", "name": "生命科學院"},
        {"id": 26, "code": "0", "name": "校級"},
        {"id": 27, "code": "F", "name": "產創學院"},
        {"id": 28, "code": "P", "name": "跨院"},
        {"id": 29, "code": "J", "name": "博雅書苑"},
    ]

    for academy_data in academies_data:
        result = await session.execute(select(Academy).where(Academy.id == academy_data["id"]))
        existing = result.scalar_one_or_none()

        if not existing:
            academy = Academy(**academy_data)
            session.add(academy)

    # === 系所資料 ===
    print("  🏢 Initializing departments...")
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
        {"id": 16, "code": "MGMT", "name": "管理科學系"},
    ]

    for dept_data in departments_data:
        result = await session.execute(select(Department).where(Department.id == dept_data["id"]))
        existing = result.scalar_one_or_none()

        if not existing:
            department = Department(**dept_data)
            session.add(department)

    # === 入學管道 ===
    print("  🚪 Initializing enrollment types...")
    # 依學位分類：1=博士, 2=碩士, 3=學士
    enroll_types_data = [
        # 博士班入學管道
        {
            "degreeId": 1,
            "code": 1,
            "name": "招生考試一般生",
            "name_en": "Regular Student - Entrance Exam",
        },
        {
            "degreeId": 1,
            "code": 2,
            "name": "招生考試在職生(目前有一般生)",
            "name_en": "Working Professional - Entrance Exam (Currently Regular)",
        },
        {"degreeId": 1, "code": 3, "name": "選讀生", "name_en": "Non-Degree Student"},
        {
            "degreeId": 1,
            "code": 4,
            "name": "推甄一般生",
            "name_en": "Regular Student - Recommendation",
        },
        {
            "degreeId": 1,
            "code": 5,
            "name": "推甄在職生(目前有一般生)",
            "name_en": "Working Professional - Recommendation (Currently Regular)",
        },
        {"degreeId": 1, "code": 6, "name": "僑生", "name_en": "Overseas Chinese Student"},
        {"degreeId": 1, "code": 7, "name": "外籍生", "name_en": "International Student"},
        {
            "degreeId": 1,
            "code": 8,
            "name": "大學逕博",
            "name_en": "Direct PhD from Bachelor",
        },
        {"degreeId": 1, "code": 9, "name": "碩士逕博", "name_en": "Direct PhD from Master"},
        {
            "degreeId": 1,
            "code": 10,
            "name": "跨校學士逕博",
            "name_en": "Direct PhD from Bachelor (Inter-University)",
        },
        {
            "degreeId": 1,
            "code": 11,
            "name": "跨校碩士逕博",
            "name_en": "Direct PhD from Master (Inter-University)",
        },
        {"degreeId": 1, "code": 12, "name": "雙聯學位", "name_en": "Dual Degree"},
        {
            "degreeId": 1,
            "code": 17,
            "name": "陸生",
            "name_en": "Mainland Chinese Student",
        },
        {"degreeId": 1, "code": 18, "name": "轉校", "name_en": "Transfer Student"},
        {"degreeId": 1, "code": 26, "name": "專案入學", "name_en": "Special Admission"},
        {
            "degreeId": 1,
            "code": 29,
            "name": "TIGP",
            "name_en": "Taiwan International Graduate Program",
        },
        {"degreeId": 1, "code": 30, "name": "其他", "name_en": "Others"},
        # 碩士班入學管道
        {"degreeId": 2, "code": 1, "name": "一般考試", "name_en": "Regular Entrance Exam"},
        {
            "degreeId": 2,
            "code": 2,
            "name": "推薦甄選",
            "name_en": "Recommendation Selection",
        },
        {
            "degreeId": 2,
            "code": 3,
            "name": "在職專班",
            "name_en": "Working Professional Program",
        },
        {"degreeId": 2, "code": 4, "name": "僑生", "name_en": "Overseas Chinese Student"},
        {"degreeId": 2, "code": 5, "name": "外籍生", "name_en": "International Student"},
        # 學士班入學管道
        {
            "degreeId": 3,
            "code": 1,
            "name": "大學個人申請",
            "name_en": "Individual Application",
        },
        {
            "degreeId": 3,
            "code": 2,
            "name": "大學考試分發",
            "name_en": "Examination Distribution",
        },
        {
            "degreeId": 3,
            "code": 3,
            "name": "四技二專甄選",
            "name_en": "Technical College Selection",
        },
        {
            "degreeId": 3,
            "code": 4,
            "name": "運動績優",
            "name_en": "Outstanding Athletic Achievement",
        },
        {"degreeId": 3, "code": 5, "name": "僑生", "name_en": "Overseas Chinese Student"},
        {"degreeId": 3, "code": 6, "name": "外籍生", "name_en": "International Student"},
    ]

    for enroll_type_data in enroll_types_data:
        enroll_type = EnrollType(**enroll_type_data)
        session.add(enroll_type)

    await session.commit()
    logger.info("Lookup tables initialized successfully!")
    print(
        f"  📊 Inserted: {len(degrees_data)} degrees, {len(identities_data)} identities, {len(studying_statuses_data)} studying statuses"
    )
    print(
        f"  📊 Inserted: {len(school_identities_data)} school identities, {len(academies_data)} academies, {len(departments_data)} departments"
    )
    print(f"  📊 Inserted: {len(enroll_types_data)} enrollment types")


async def initAllLookupTables() -> None:
    """Initialize lookup tables - standalone execution function"""

    print("🚀 Initializing NYCU lookup tables database...")

    # Create all tables if they don't exist
    async with async_engine.begin() as conn:
        print("🗄️  Creating tables if they don't exist...")
        await conn.run_sync(Base.metadata.create_all)

    # Initialize lookup data
    async with AsyncSessionLocal() as session:
        await initLookupTables(session)

    print("✅ NYCU lookup tables initialization completed successfully!")
    print("\n📋 Reference Data Summary:")
    print("- 3 degree types (博士, 碩士, 學士)")
    print("- 16 student identity types")
    print("- 11 studying status types")
    print("- 8 school identity types")
    print("- 29 NYCU academies/colleges")
    print("- 16 departments")
    print("- 27 enrollment types")


if __name__ == "__main__":
    asyncio.run(initAllLookupTables())
