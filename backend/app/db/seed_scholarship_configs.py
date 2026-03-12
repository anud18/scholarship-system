"""
Scholarship configuration seed data for testing

This module contains scholarship configurations, sub-type configs, rules, and email templates
for development and testing purposes.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base_class import Base
from app.db.session import AsyncSessionLocal, async_engine
from app.models.enums import QuotaManagementMode, Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipRule, ScholarshipSubTypeConfig, ScholarshipType
from app.models.system_setting import EmailTemplate, SendingType

logger = logging.getLogger(__name__)


async def seed_scholarship_configurations(session: AsyncSession) -> None:
    """Initialize scholarship configurations with quota and workflow settings"""

    logger.info("Initializing scholarship configurations...")
    print("  🎓 Initializing scholarship configurations...")

    # Get scholarship types
    undergrad_result = await session.execute(
        select(ScholarshipType).where(ScholarshipType.code == "undergraduate_freshman")
    )
    undergrad_scholarship = undergrad_result.scalar_one_or_none()

    phd_result = await session.execute(select(ScholarshipType).where(ScholarshipType.code == "phd"))
    phd_scholarship = phd_result.scalar_one_or_none()

    direct_phd_result = await session.execute(select(ScholarshipType).where(ScholarshipType.code == "direct_phd"))
    direct_phd_scholarship = direct_phd_result.scalar_one_or_none()

    if not all([undergrad_scholarship, phd_scholarship, direct_phd_scholarship]):
        print("  ⚠️  Scholarship types not found, skipping configuration seed")
        return

    # Current date for workflow testing
    now = datetime.now(timezone.utc)

    # === 獎學金配置 (114學年度) ===
    configurations_data = [
        # 學士班新生獎學金配置 (114-1)
        {
            "scholarship_type_id": undergrad_scholarship.id,
            "config_code": "undergraduate_freshman_114_1",
            "config_name": "學士班新生獎學金 114學年第一學期",
            "academic_year": 114,
            "semester": Semester.first,
            "description": "114學年度第一學期學士班新生獎學金配置",
            "description_en": "Undergraduate Freshman Scholarship Configuration for 114-1",
            "has_quota_limit": False,
            "has_college_quota": False,
            "quota_management_mode": QuotaManagementMode.simple,
            "total_quota": 50,
            "amount": 10000,
            "currency": "TWD",
            "application_start_date": now - timedelta(days=30),
            "application_end_date": now + timedelta(days=30),
            "is_active": True,
            "effective_start_date": now - timedelta(days=60),
            "effective_end_date": now + timedelta(days=90),
            "version": "1.0",
        },
        # 學士班新生獎學金配置 (114-2)
        {
            "scholarship_type_id": undergrad_scholarship.id,
            "config_code": "undergraduate_freshman_114_2",
            "config_name": "學士班新生獎學金 114學年第二學期",
            "academic_year": 114,
            "semester": Semester.second,
            "description": "114學年度第二學期學士班新生獎學金配置",
            "description_en": "Undergraduate Freshman Scholarship Configuration for 114-2",
            "has_quota_limit": False,
            "has_college_quota": False,
            "quota_management_mode": QuotaManagementMode.simple,
            "total_quota": 50,
            "amount": 10000,
            "currency": "TWD",
            "application_start_date": now - timedelta(days=30),
            "application_end_date": now + timedelta(days=30),
            "is_active": True,
            "effective_start_date": now - timedelta(days=60),
            "effective_end_date": now + timedelta(days=90),
            "version": "1.0",
        },
        # 博士生獎學金配置 (112學年) - 前年度剩餘配額
        {
            "scholarship_type_id": phd_scholarship.id,
            "config_code": "phd_112",
            "config_name": "博士生獎學金 112學年",
            "academic_year": 112,
            "semester": None,  # 學年制
            "description": "112學年度博士生獎學金配置（剩餘配額）",
            "description_en": "PhD Scholarship Configuration for Academic Year 112 (Remaining Quota)",
            "has_quota_limit": True,
            "has_college_quota": True,
            "quota_management_mode": QuotaManagementMode.matrix_based,
            "total_quota": 15,
            "quotas": {
                "nstc": {
                    "E": 2,
                    "C": 1,
                    "I": 1,
                    "S": 1,
                    "B": 1,
                    "O": 1,
                    "D": 1,
                    "1": 1,
                    "6": 1,
                    "7": 1,
                    "M": 1,
                    "A": 1,
                    "K": 1,
                },
            },
            "amount": 40000,
            "currency": "TWD",
            "is_active": False,
            "effective_start_date": now - timedelta(days=840),
            "effective_end_date": now - timedelta(days=480),
            "version": "1.0",
        },
        # 博士生獎學金配置 (113學年) - 前年度剩餘配額 (for prior-year quota testing)
        {
            "scholarship_type_id": phd_scholarship.id,
            "config_code": "phd_113",
            "config_name": "博士生獎學金 113學年",
            "academic_year": 113,
            "semester": None,  # 學年制
            "description": "113學年度博士生獎學金配置（剩餘配額）",
            "description_en": "PhD Scholarship Configuration for Academic Year 113 (Remaining Quota)",
            "has_quota_limit": True,
            "has_college_quota": True,
            "quota_management_mode": QuotaManagementMode.matrix_based,
            "total_quota": 30,
            "quotas": {
                "nstc": {
                    "E": 3,
                    "C": 2,
                    "I": 2,
                    "S": 1,
                    "B": 1,
                    "O": 1,
                    "D": 1,
                    "1": 1,
                    "6": 1,
                    "7": 1,
                    "M": 1,
                    "A": 1,
                    "K": 1,
                },
            },
            "amount": 40000,
            "currency": "TWD",
            "is_active": False,
            "effective_start_date": now - timedelta(days=480),
            "effective_end_date": now - timedelta(days=120),
            "version": "1.0",
        },
        # 博士生獎學金配置 (114學年) - Matrix Quota
        {
            "scholarship_type_id": phd_scholarship.id,
            "config_code": "phd_114",
            "config_name": "博士生獎學金 114學年",
            "academic_year": 114,
            "semester": None,  # 學年制
            "description": "114學年度博士生獎學金配置",
            "description_en": "PhD Scholarship Configuration for Academic Year 114 with Matrix Quota",
            "has_quota_limit": True,
            "has_college_quota": True,
            "quota_management_mode": QuotaManagementMode.matrix_based,
            "total_quota": 100,
            "quotas": {
                "nstc": {
                    "E": 15,
                    "C": 12,
                    "I": 10,
                    "S": 8,
                    "B": 6,
                    "O": 5,
                    "D": 4,
                    "1": 3,
                    "6": 3,
                    "7": 3,
                    "M": 5,
                    "A": 4,
                    "K": 2,
                },
                "moe_1w": {
                    "E": 10,
                    "C": 8,
                    "I": 7,
                    "S": 6,
                    "B": 4,
                    "O": 3,
                    "D": 3,
                    "1": 2,
                    "6": 2,
                    "7": 2,
                    "M": 4,
                    "A": 3,
                    "K": 1,
                },
            },
            "prior_quota_years": {"nstc": [113, 112], "moe_1w": []},
            "project_numbers": {
                "nstc": {
                    "114": "114R000001",
                    "113": "113R000001",
                    "112": "112R000001",
                },
                "moe_1w": {
                    "114": "114E000001",
                },
            },
            "amount": 40000,
            "currency": "TWD",
            "renewal_application_start_date": now - timedelta(days=90),
            "renewal_application_end_date": now - timedelta(days=60),
            "application_start_date": now - timedelta(days=45),
            "application_end_date": now + timedelta(days=15),
            "renewal_professor_review_start": now - timedelta(days=55),
            "renewal_professor_review_end": now - timedelta(days=40),
            "renewal_college_review_start": now - timedelta(days=35),
            "renewal_college_review_end": now - timedelta(days=20),
            "requires_professor_recommendation": True,
            "professor_review_start": now,
            "professor_review_end": now + timedelta(days=30),
            "requires_college_review": True,
            "college_review_start": now + timedelta(days=35),
            "college_review_end": now + timedelta(days=60),
            "review_deadline": now + timedelta(days=65),
            "is_active": True,
            "effective_start_date": now - timedelta(days=120),
            "effective_end_date": now + timedelta(days=365),
            "version": "1.0",
        },
        # 逕讀博士獎學金配置 (114學年)
        {
            "scholarship_type_id": direct_phd_scholarship.id,
            "config_code": "direct_phd_114",
            "config_name": "逕讀博士獎學金 114學年",
            "academic_year": 114,
            "semester": None,  # 學年制
            "description": "114學年度逕讀博士獎學金配置",
            "description_en": "Direct PhD Scholarship Configuration for Academic Year 114",
            "has_quota_limit": False,
            "has_college_quota": False,
            "quota_management_mode": QuotaManagementMode.simple,
            "total_quota": 30,
            "amount": 35000,
            "currency": "TWD",
            "application_start_date": now - timedelta(days=30),
            "application_end_date": now + timedelta(days=30),
            "requires_professor_recommendation": True,
            "professor_review_start": now + timedelta(days=5),
            "professor_review_end": now + timedelta(days=35),
            "is_active": True,
            "effective_start_date": now - timedelta(days=60),
            "effective_end_date": now + timedelta(days=365),
            "version": "1.0",
        },
    ]

    for config_data in configurations_data:
        # Check if config already exists
        result = await session.execute(
            select(ScholarshipConfiguration).where(ScholarshipConfiguration.config_code == config_data["config_code"])
        )
        existing = result.scalar_one_or_none()

        if not existing:
            config = ScholarshipConfiguration(**config_data)
            session.add(config)
            logger.info(f"Created configuration: {config_data['config_code']}")
        else:
            # Update prior_quota_years on existing configs if provided in seed data
            if "prior_quota_years" in config_data and existing.prior_quota_years != config_data["prior_quota_years"]:
                existing.prior_quota_years = config_data["prior_quota_years"]
                logger.info(f"Updated prior_quota_years for: {config_data['config_code']}")
            # Update project_numbers on existing configs if provided in seed data
            if "project_numbers" in config_data and existing.project_numbers != config_data["project_numbers"]:
                existing.project_numbers = config_data["project_numbers"]
                logger.info(f"Updated project_numbers for: {config_data['config_code']}")

    await session.commit()
    logger.info("Scholarship configurations initialized successfully!")
    print(f"  📊 Inserted: {len(configurations_data)} scholarship configurations")


async def seed_scholarship_rules(session: AsyncSession) -> None:
    """Initialize scholarship eligibility rules"""

    logger.info("Initializing scholarship rules...")
    print("  📋 Initializing scholarship rules...")

    # Check if scholarship rules already exist
    result = await session.execute(select(ScholarshipRule))
    existing_rules = result.scalars().all()

    if existing_rules:
        print(f"  ✓ Scholarship rules already initialized ({len(existing_rules)} found)")
        return

    # Get admin user ID
    result = await session.execute(text("SELECT id FROM users WHERE nycu_id = 'admin' LIMIT 1"))
    admin_id = result.scalar()
    if not admin_id:
        admin_id = 1

    # === 獎學金資格規則 (114學年度) ===
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
            "rule_type": "student_term",
            "condition_field": "trm_termcount",
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
            "rule_type": "student_term",
            "condition_field": "trm_termcount",
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
            "condition_field": "std_enrolltype",
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
            "semester": Semester.first,
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
            "condition_field": "std_enrolltype",
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
            "condition_field": "std_enrolltype",
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
    ]

    for rule_data in scholarship_rules_data:
        scholarship_rule = ScholarshipRule(**rule_data)
        session.add(scholarship_rule)

    await session.commit()
    logger.info("Scholarship rules initialized successfully!")
    print(f"  📊 Inserted: {len(scholarship_rules_data)} scholarship rules")


async def seed_scholarship_sub_type_configs(session: AsyncSession) -> None:
    """Initialize scholarship sub-type configurations"""

    logger.info("Initializing scholarship sub-type configurations...")
    print("  🔧 Initializing scholarship sub-type configurations...")

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
                ]
            )

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
    logger.info("Sub-type configurations initialized successfully!")
    print(f"  📊 Inserted: {len(sub_type_configs_data)} sub-type configurations")


async def seed_email_templates(session: AsyncSession) -> None:
    """Initialize default system email templates"""

    logger.info("Initializing email templates...")
    print("  📧 Initializing email templates...")

    # Check if templates already exist
    result = await session.execute(select(EmailTemplate))
    existing_templates = result.scalars().all()

    if existing_templates:
        print(f"  ✓ Email templates already initialized ({len(existing_templates)} found)")
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

我們會儘快處理您的申請，如有任何問題請隨時聯繫我們。

祝學業順利！

國立陽明交通大學
獎學金管理系統""",
            "sending_type": SendingType.single,
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
            "sending_type": SendingType.single,
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
            "sending_type": SendingType.single,
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
            "sending_type": SendingType.single,
            "recipient_options": [{"label": "管理員", "value": "admin"}],
        },
        {
            "key": "college_review_notification",
            "subject_template": "學院審核通知 - {student_name} 的 {scholarship_name} 申請",
            "body_template": """學院承辦人您好：

{professor_name} 教授已完成對 {student_name}（學號：{student_id}）的 {scholarship_name} 申請審查。

教授審查意見：{professor_recommendation}

請進行學院審核，審核截止日期：{review_deadline}

請至管理系統進行審核：{review_url}

如有任何問題，請隨時聯繫我們。

國立陽明交通大學
獎學金管理系統""",
            "sending_type": SendingType.single,
            "recipient_options": [{"label": "學院承辦人", "value": "college"}],
        },
        # Bulk sending type templates
        {
            "key": "scholarship_announcement",
            "subject_template": "獎學金公告 - {scholarship_name}",
            "body_template": """各位同學：

{scholarship_name} 現正開放申請！

申請期間：{application_period}
申請資格：{eligibility_criteria}

申請方式：
請至獎學金管理系統線上申請

如有任何問題，請聯繫承辦人員。

國立陽明交通大學
獎學金管理系統""",
            "sending_type": SendingType.bulk,
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
            "sending_type": SendingType.bulk,
            "recipient_options": [
                {"label": "尚未申請的學生", "value": "non_applicants"},
                {"label": "申請未完成的學生", "value": "incomplete_applicants"},
            ],
            "max_recipients": 1000,
        },
    ]

    for template_data in default_templates:
        template = EmailTemplate(**template_data)
        session.add(template)

    await session.commit()
    logger.info("Email templates initialized successfully!")
    print(f"  📊 Inserted: {len(default_templates)} email templates")


async def seed_email_automation_rules(session: AsyncSession) -> None:
    """Initialize default email automation rules"""
    from app.models.email_management import EmailAutomationRule, TriggerEvent

    logger.info("Initializing email automation rules...")
    print("  🤖 Initializing email automation rules...")

    # Check if automation rules already exist
    result = await session.execute(select(EmailAutomationRule))
    existing_rules = result.scalars().all()

    if existing_rules:
        print(f"  ✓ Email automation rules already initialized ({len(existing_rules)} found)")
        return

    # Define initial automation rules (disabled by default, admin must activate)
    initial_rules = [
        {
            "name": "申請提交確認郵件",
            "description": "當學生提交申請時，自動發送確認郵件給申請者",
            "trigger_event": TriggerEvent.application_submitted,
            "template_key": "application_submitted_student",
            "delay_hours": 0,
            "is_active": False,
            "condition_query": """
                SELECT email FROM (
                    SELECT applications.student_data->>'com_email' as email
                    FROM applications
                    WHERE applications.id = {application_id}
                    AND applications.student_data->>'com_email' IS NOT NULL
                    AND applications.student_data->>'com_email' != ''

                    UNION

                    SELECT users.email
                    FROM applications
                    JOIN users ON applications.user_id = users.id
                    WHERE applications.id = {application_id}
                    AND users.email IS NOT NULL
                    AND users.email != ''
                ) emails
                WHERE email IS NOT NULL
            """,
        },
        {
            "name": "教授審核通知",
            "description": "當申請提交後，通知指導教授有新申請待審核",
            "trigger_event": TriggerEvent.application_submitted,
            "template_key": "professor_review_notification",
            "delay_hours": 0,
            "is_active": False,
            "condition_query": """
                SELECT user_profiles.advisor_email as email
                FROM applications
                JOIN user_profiles ON applications.user_id = user_profiles.user_id
                WHERE applications.id = {application_id}
                AND user_profiles.advisor_email IS NOT NULL
                AND user_profiles.advisor_email != ''
            """,
        },
        {
            "name": "學院審核通知",
            "description": "當教授審核完成後，通知學院有新案件待審核",
            "trigger_event": TriggerEvent.professor_review_submitted,
            "template_key": "college_review_notification",
            "delay_hours": 0,
            "is_active": False,
        },
    ]

    for rule_data in initial_rules:
        rule = EmailAutomationRule(**rule_data)
        session.add(rule)

    await session.commit()
    logger.info("Email automation rules initialized successfully!")
    print(f"  📊 Inserted: {len(initial_rules)} email automation rules (disabled by default)")


async def init_all_scholarship_configs() -> None:
    """Initialize all scholarship configurations - standalone execution function"""

    print("🚀 Initializing scholarship configurations...")

    # Create all tables if they don't exist
    async with async_engine.begin() as conn:
        print("🗄️  Creating tables if they don't exist...")
        await conn.run_sync(Base.metadata.create_all)

    # Initialize configuration data
    async with AsyncSessionLocal() as session:
        await seed_scholarship_configurations(session)
        await seed_scholarship_rules(session)
        await seed_scholarship_sub_type_configs(session)
        await seed_email_templates(session)

    print("✅ Scholarship configuration initialization completed successfully!")
    print("\n📋 Configuration Data Summary:")
    print("- 3 scholarship configurations (114 academic year)")
    print("- 18 scholarship rules (114 academic year)")
    print("- 3 sub-type configurations (NSTC, MOE_1W, MOE_2W)")
    print("- 6 email templates (single + bulk sending)")


if __name__ == "__main__":
    asyncio.run(init_all_scholarship_configs())
