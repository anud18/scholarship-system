"""AY115 demo cohort for the dev environment.

The current academic year is 115. A realistic 博士生獎學金 cycle mixes three
kinds of students, and this module seeds the two that must already exist in
the database before anyone touches the UI:

1. **114 recipients (續領 pool)** — approved `phd_114` applications. In 115
   they show up as 續領 candidates: the student can self-renew via
   `/renewals/eligible` (prior-year approved + open 115 renewal window), and
   the admin can bulk-import them through 匯入續領生 (see the sample workbook
   built by `backend/scripts/generate_ay115_import_samples.py`).
2. **115 new applicants** — plain student accounts so they can log in through
   mock SSO and walk the application wizard themselves.

Students that are meant to arrive via 批次匯入 are deliberately NOT seeded:
the import creates their user rows, exactly like production.

Every student here is mirrored in `mock-student-api/main.py` (`_AY115_DEMO`)
with term rows up to 115-1, so SIS lookups and the eligibility rules resolve.

Idempotent: users are upserted by nycu_id, applications skipped when the
app_id already exists.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.enums import ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import EmployeeStatus, User, UserRole, UserType
from app.models.user_profile import UserProfile

logger = logging.getLogger(__name__)

PRIOR_ACADEMIC_YEAR = 114
PRIOR_CONFIG_CODE = "phd_114"
PHD_SCHOLARSHIP_CODE = "phd"

# (stdcode, cname, ename, sex, academyno, academyname, depno, depname, enrollyear)
# depno values are REAL departments.code rows so the 申請總表 join works:
#   1550 資訊工程學系(C) · 155 資訊科學與工程研究所(C) · 3511 電機工程學系(E) · 183 電機學院博士班(E)
StudentEntry = tuple

# --- 114 得獎者：115 學年的續領候選 ------------------------------------------
# sub_type = the category awarded in 114; renews = whether the 115 續領 sheet
# marks them 是+通過 (the last one hit the award ceiling and does not renew).
RECIPIENTS_114 = [
    ("313551201", "林承翰", "LIN,CHENG-HAN", 1, "C", "資訊學院", "1550", "資訊工程學系", 113, "nstc"),
    ("313551202", "張雅婷", "CHANG,YA-TING", 2, "C", "資訊學院", "155", "資訊科學與工程研究所", 113, "moe_1w"),
    ("312551203", "黃冠宇", "HUANG,KUAN-YU", 1, "E", "電機學院", "3511", "電機工程學系", 112, "nstc"),
    ("313551204", "吳佩珊", "WU,PEI-SHAN", 2, "E", "電機學院", "183", "電機學院博士班", 113, "moe_1w"),
    ("311551205", "鄭宇軒", "CHENG,YU-HSUAN", 1, "C", "資訊學院", "1550", "資訊工程學系", 111, "nstc"),
]

# --- 115 新申請：由學生自行登入申請 --------------------------------------------
NEW_APPLICANTS_115 = [
    ("315551401", "蔡承恩", "TSAI,CHENG-EN", 1, "C", "資訊學院", "1550", "資訊工程學系", 115),
    ("314551402", "郭芷瑄", "KUO,CHIH-HSUAN", 2, "C", "資訊學院", "155", "資訊科學與工程研究所", 114),
    ("315551403", "楊子萱", "YANG,TZU-HSUAN", 2, "E", "電機學院", "3511", "電機工程學系", 115),
    ("314551404", "許文傑", "HSU,WEN-CHIEH", 1, "E", "電機學院", "183", "電機學院博士班", 114),
]

# Advisor per college — both are seeded professor accounts (seed_test_users).
ADVISOR_BY_COLLEGE = {
    "C": {"nycu_id": "cs_professor", "name": "李資訊教授", "email": "cs_professor@nycu.edu.tw"},
    "E": {"nycu_id": "professor", "name": "李教授", "email": "professor@nycu.edu.tw"},
}


def _term_count(enroll_year: int, year: int, term: int) -> int:
    return (year - enroll_year) * 2 + term


def _build_student_data(entry: StudentEntry) -> Dict[str, Any]:
    """SIS snapshot as it looked when the 114 application was submitted (114-2)."""
    stdcode, cname, ename, sex, academyno, academyname, depno, depname, enrollyear = entry[:9]
    return {
        "std_stdcode": stdcode,
        "std_enrollyear": enrollyear,
        "std_enrollterm": 1,
        "std_highestschname": "國立陽明交通大學",
        "std_cname": cname,
        "std_ename": ename,
        "std_pid": f"A{stdcode}",
        "std_bdate": "900101",
        "std_academyno": academyno,
        "std_depno": depno,
        "std_sex": sex,
        "std_nation": "中華民國",
        "std_degree": 1,
        "std_enrolltype": 4,
        "std_identity": 1,
        "std_schoolid": 1,
        "std_overseaplace": "",
        "std_termcount": _term_count(enrollyear, PRIOR_ACADEMIC_YEAR, 2),
        "std_studingstatus": 2,
        "mgd_title": "在學",
        "ToDoctor": 0,
        "com_commadd": "新竹市東區大學路1001號",
        "com_email": f"{stdcode}@nycu.edu.tw",
        "com_cellphone": f"0912{stdcode[-6:]}",
        "trm_year": PRIOR_ACADEMIC_YEAR,
        "trm_term": 2,
        "trm_termcount": _term_count(enrollyear, PRIOR_ACADEMIC_YEAR, 2),
        "trm_studystatus": 1,
        "trm_degree": 1,
        "trm_academyno": academyno,
        "trm_academyname": academyname,
        "trm_depno": depno,
        "trm_depname": depname,
        "trm_placings": 0,
        "trm_placingsrate": 0.0,
        "trm_depplacing": 0,
        "trm_depplacingrate": 0.0,
        "trm_ascore_gpa": 3.85,
        "_api_fetched_at": "2025-10-01T00:00:00Z",
        "_term_data_status": "success",
    }


def _text_field(field_id: str, value: str) -> Dict[str, Any]:
    return {"field_id": field_id, "field_type": "text", "value": value, "required": True}


def _build_submitted_form_data(stdcode: str, advisor: Dict[str, str]) -> Dict[str, Any]:
    postal_account = f"0021{stdcode}"
    return {
        "fields": {
            "postal_account": _text_field("postal_account", postal_account),
            "advisor_name": _text_field("advisor_name", advisor["name"]),
            "advisor_email": _text_field("advisor_email", advisor["email"]),
            "advisor_nycu_id": _text_field("advisor_nycu_id", advisor["nycu_id"]),
            "master_school_info": _text_field("master_school_info", "國立陽明交通大學資訊學院資訊科學與工程研究所"),
        },
        "documents": [],
    }


async def _upsert_student_user(session: AsyncSession, entry: StudentEntry) -> User:
    stdcode, cname, _ename, _sex, _academyno, _academyname, depno, depname = entry[:8]
    user = (await session.execute(select(User).where(User.nycu_id == stdcode))).scalar_one_or_none()
    if user:
        return user
    user = User(
        nycu_id=stdcode,
        name=cname,
        email=f"{stdcode}@nycu.edu.tw",
        user_type=UserType.student,
        status=EmployeeStatus.student,
        dept_code=depno,
        dept_name=depname,
        role=UserRole.student,
    )
    session.add(user)
    await session.flush()
    return user


async def _upsert_profile(session: AsyncSession, user: User, stdcode: str, advisor: Dict[str, str]) -> None:
    """Profile carries the advisor trio so professor auto-assignment and
    notifications work the same way they do for wizard-submitted students."""
    existing = (await session.execute(select(UserProfile).where(UserProfile.user_id == user.id))).scalar_one_or_none()
    if existing:
        return
    session.add(
        UserProfile(
            user_id=user.id,
            account_number=f"0021{stdcode}",
            advisor_name=advisor["name"],
            advisor_email=advisor["email"],
            advisor_nycu_id=advisor["nycu_id"],
        )
    )


async def _find_user(session: AsyncSession, nycu_id: str) -> Optional[User]:
    return (await session.execute(select(User).where(User.nycu_id == nycu_id))).scalar_one_or_none()


async def _seed_114_recipients(session: AsyncSession, phd: ScholarshipType, config: ScholarshipConfiguration) -> int:
    submitted_at = datetime.now(timezone.utc) - timedelta(days=380)
    created = 0
    for idx, entry in enumerate(RECIPIENTS_114, start=1):
        stdcode, academyno, sub_type = entry[0], entry[4], entry[9]
        advisor = ADVISOR_BY_COLLEGE[academyno]
        user = await _upsert_student_user(session, entry)
        await _upsert_profile(session, user, stdcode, advisor)
        advisor_user = await _find_user(session, advisor["nycu_id"])

        app_id = f"APP-{PRIOR_ACADEMIC_YEAR}-0-{200 + idx:05d}"
        exists = (await session.execute(select(Application).where(Application.app_id == app_id))).scalar_one_or_none()
        if exists:
            continue

        session.add(
            Application(
                app_id=app_id,
                user_id=user.id,
                professor_id=advisor_user.id if advisor_user else None,
                scholarship_type_id=phd.id,
                scholarship_configuration_id=config.id,
                allocation_config_id=config.id,
                amount=config.amount,
                scholarship_subtype_list=[sub_type],
                sub_type_selection_mode=SubTypeSelectionMode.multiple,
                sub_scholarship_type=sub_type,
                is_renewal=False,
                renewal_year=None,
                status=ApplicationStatus.approved.value,
                review_stage=ReviewStage.completed.value,
                academic_year=PRIOR_ACADEMIC_YEAR,
                semester=None,  # phd is yearly -> NULL
                student_data=_build_student_data(entry),
                submitted_form_data=_build_submitted_form_data(stdcode, advisor),
                agree_terms=True,
                submitted_at=submitted_at,
            )
        )
        created += 1
    return created


async def _seed_115_new_applicants(session: AsyncSession) -> int:
    created = 0
    for entry in NEW_APPLICANTS_115:
        before = await _find_user(session, entry[0])
        user = await _upsert_student_user(session, entry)
        await _upsert_profile(session, user, entry[0], ADVISOR_BY_COLLEGE[entry[4]])
        if before is None:
            created += 1
    return created


async def seed_ay115_demo(session: AsyncSession) -> None:
    """Seed the 114 recipients (續領 pool) and the 115 new-applicant accounts."""
    phd = (
        await session.execute(select(ScholarshipType).where(ScholarshipType.code == PHD_SCHOLARSHIP_CODE))
    ).scalar_one_or_none()
    config = (
        await session.execute(
            select(ScholarshipConfiguration).where(ScholarshipConfiguration.config_code == PRIOR_CONFIG_CODE)
        )
    ).scalar_one_or_none()
    if not phd or not config:
        print(f"  ⚠️  {PHD_SCHOLARSHIP_CODE} scholarship or {PRIOR_CONFIG_CODE} config missing — skipping AY115 demo")
        return

    recipients = await _seed_114_recipients(session, phd, config)
    applicants = await _seed_115_new_applicants(session)
    await session.commit()

    logger.info("AY115 demo cohort seeded: %s recipients, %s applicants", recipients, applicants)
    print(f"  ✓ 114 得獎者 (approved {PRIOR_CONFIG_CODE}): +{recipients} applications")
    print(f"  ✓ 115 新申請學生帳號: +{applicants} users")
