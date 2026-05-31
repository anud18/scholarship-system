"""
Seed demo PhD (博士生獎學金) applications spread across several departments so an
admin can pick different 系所 in the 申請總表 (department summary) export and get
real data for each.

Creates one User + one approved phd/114 (yearly → semester NULL) Application per
roster entry, with a self-contained student_data snapshot whose std_depno is a
REAL departments.code (so the export's std_depno → departments.code → academy_code
join works). Idempotent: skips users / applications that already exist.

Mirror entries live in mock-student-api/main.py (SAMPLE_STUDENTS / SAMPLE_TERMS)
so the same students are loginable and re-submittable.

Usage:
    docker compose -f docker-compose.dev.yml exec backend python scripts/seed_summary_export_demo.py
"""

import asyncio
import sys

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.application import Application, ApplicationStatus
from app.models.enums import ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType

# (stdcode, cname, ename, sex, academyno, academyname, depno, depname, enrolltype, termcount)
# depno values are REAL departments.code rows (verified academy_code in parens):
#   155 資訊科學與工程研究所(C) · 256 網路工程研究所(C) · 257 多媒體工程研究所(C)
#   260 數據科學與工程研究所(C) · 183 電機學院博士班(E) · 3511 電機工程學系(E)
DEMO_ROSTER = [
    ("csdemo01", "林演算法", "LIN,ALGORITHM", 1, "C", "資訊學院", "155", "資訊科學與工程研究所", 4, 5),
    ("csdemo02", "黃資安", "HUANG,SECURITY", 2, "C", "資訊學院", "155", "資訊科學與工程研究所", 8, 3),
    ("csdemo03", "吳網路", "WU,NETWORK", 1, "C", "資訊學院", "256", "網路工程研究所", 4, 7),
    ("csdemo04", "趙多媒體", "CHAO,MULTIMEDIA", 2, "C", "資訊學院", "257", "多媒體工程研究所", 4, 4),
    ("csdemo05", "錢數據", "CHIEN,DATA", 1, "C", "資訊學院", "260", "數據科學與工程研究所", 8, 6),
    ("eedemo01", "周電機", "CHOU,EE", 1, "E", "電機學院", "183", "電機學院博士班", 4, 5),
    ("eedemo02", "鄭電子", "CHENG,ECE", 2, "E", "電機學院", "3511", "電機工程學系", 4, 8),
]

SUB_TYPE = "nstc"


def _build_student_data(idx: int, entry) -> dict:
    stdcode, cname, ename, sex, academyno, academyname, depno, depname, enrolltype, termcount = entry
    return {
        "std_stdcode": stdcode,
        "std_cname": cname,
        "std_ename": ename,
        "std_sex": sex,
        "std_nation": "中華民國",
        "std_degree": 1,
        "std_academyno": academyno,
        "std_depno": depno,
        "std_enrollyear": 112,
        "std_enrollterm": 1,
        "std_enrolltype": enrolltype,
        "std_pid": f"D1234{idx:05d}",
        "std_bdate": "900101",
        "std_studingstatus": 2,
        "mgd_title": "在學",
        "ToDoctor": 1,
        "com_email": f"{stdcode}@nycu.edu.tw",
        "com_commadd": "新竹市東區大學路1001號",
        "com_cellphone": f"091200{idx:04d}",
        "trm_year": 114,
        "trm_term": 1,
        "trm_termcount": termcount,
        "trm_academyno": academyno,
        "trm_academyname": academyname,
        "trm_depno": depno,
        "trm_depname": depname,
        "trm_degree": 1,
        "trm_studystatus": 1,
        "trm_ascore_gpa": 3.8,
        "_api_source": "seed_summary_export_demo",
        "_term_data_status": "success",
    }


async def main():
    async with AsyncSessionLocal() as db:
        phd = (await db.execute(select(ScholarshipType).where(ScholarshipType.code == "phd"))).scalar_one_or_none()
        if not phd:
            print("ERROR: PhD scholarship type not found. Run seed first.")
            sys.exit(1)

        phd_config = (
            await db.execute(select(ScholarshipConfiguration).where(ScholarshipConfiguration.config_code == "phd_114"))
        ).scalar_one_or_none()
        if not phd_config:
            print("ERROR: phd_114 config not found.")
            sys.exit(1)

        created_users = created_apps = 0

        for idx, entry in enumerate(DEMO_ROSTER, start=1):
            stdcode, cname = entry[0], entry[1]

            user = (await db.execute(select(User).where(User.nycu_id == stdcode))).scalar_one_or_none()
            if not user:
                user = User(
                    nycu_id=stdcode,
                    name=cname,
                    email=f"{stdcode}@nycu.edu.tw",
                    user_type=UserType.student,
                    role=UserRole.student,
                )
                db.add(user)
                await db.flush()
                created_users += 1

            app_id = f"APP-114-0-{100 + idx:05d}"
            existing = (await db.execute(select(Application).where(Application.app_id == app_id))).scalar_one_or_none()
            if existing:
                continue

            db.add(
                Application(
                    app_id=app_id,
                    user_id=user.id,
                    scholarship_type_id=phd.id,
                    scholarship_configuration_id=phd_config.id,
                    amount=phd_config.amount,
                    scholarship_subtype_list=[SUB_TYPE],
                    sub_type_selection_mode=SubTypeSelectionMode.multiple,
                    sub_scholarship_type=SUB_TYPE,
                    is_renewal=False,
                    renewal_year=None,
                    status=ApplicationStatus.approved.value,
                    review_stage=ReviewStage.completed.value,
                    academic_year=114,
                    semester=None,  # phd is yearly -> NULL
                    student_data=_build_student_data(idx, entry),
                    submitted_form_data={"fields": {}, "documents": []},
                    agree_terms=True,
                )
            )
            created_apps += 1

        await db.commit()

        print(f"OK Demo summary-export data seeded: +{created_users} users, +{created_apps} applications")
        print(f"   Scholarship: {phd.name} (id={phd.id}), 114 yearly")
        depts = sorted({e[6] for e in DEMO_ROSTER})
        print(f"   Departments now populated: {', '.join(depts)} (+ existing 1550, 1511)")


if __name__ == "__main__":
    asyncio.run(main())
