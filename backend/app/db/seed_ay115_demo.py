"""AY115 demo cohort for the dev environment.

The current academic year is 115. A realistic 博士生獎學金 cycle mixes three
kinds of students, and this module seeds the two that must already exist in
the database before anyone touches the UI:

1. **續領生 (currently on renewal)** — awarded in 113 (`phd_113`, 新申請) and
   renewed in 114 (`phd_114`, is_renewal). Both years are approved and sit in
   a LOCKED yearly payment roster, so 領獎紀錄 / 領取月份數 show real history
   (12 + 12 months). In 115 they are the renewal pool: the student can
   self-renew via `/renewals/eligible` (prior-year approved + open 115 renewal
   window), or the admin imports them through 匯入續領生 (sample workbook from
   `backend/scripts/generate_ay115_import_samples.py`).
2. **115 new applicants** — plain student accounts so they can log in through
   mock SSO and walk the application wizard themselves.

Students that are meant to arrive via 批次匯入 are deliberately NOT seeded:
the import creates their user rows, exactly like production.

Every student here is mirrored in `mock-student-api/main.py` (`_AY115_DEMO`)
with term rows up to 115-1, so SIS lookups and the eligibility rules resolve.

Idempotent: users/profiles are created only when missing, applications and
rosters are skipped when their app_id / roster_code already exists.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.enums import ReviewStage
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.roster_schedule import RosterSchedule, RosterScheduleStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import EmployeeStatus, User, UserRole, UserType
from app.models.user_profile import UserProfile

logger = logging.getLogger(__name__)

PHD_SCHOLARSHIP_CODE = "phd"
FIRST_AWARD_YEAR = 113  # 新申請 year of the 續領 cohort
RENEWAL_YEAR = 114  # year they are currently renewing in
CONFIG_CODE_BY_YEAR = {FIRST_AWARD_YEAR: "phd_113", RENEWAL_YEAR: "phd_114"}
# The 造冊 dashboard (payment-rosters/cycle-status) lists a config's periods ONLY
# when the config has a RosterSchedule — without one, 114-整學年 shows nothing
# even though its locked rosters exist. Seed a yearly schedule for every PhD year.
SCHEDULE_CONFIG_CODES = ("phd_113", "phd_114", "phd_115")
APP_SEQUENCE_BASE = 200  # APP-<year>-0-0020x, clear of the sequence counter and other demo seeds
MONTHS_BEFORE_NOW_BY_YEAR = {FIRST_AWARD_YEAR: 24, RENEWAL_YEAR: 12}
DAYS_PER_MONTH = 30

# (stdcode, cname, ename, sex, academyno, academyname, depno, depname, enrollyear)
# depno values are REAL departments.code rows so the 申請總表 join works:
#   1550 資訊工程學系(C) · 155 資訊科學與工程研究所(C) · 3511 電機工程學系(E) · 183 電機學院博士班(E)
StudentEntry = tuple

# --- 續領生：113 新申請 → 114 續領（正在續領），115 為續領候選 ------------------
# sub_type = the category awarded; the last one hits the award ceiling in 114
# and does NOT renew in 115 (the 115 續領 sheet marks them 否).
RENEWAL_COHORT = [
    ("313551201", "續領-林承翰", "LIN,CHENG-HAN", 1, "C", "資訊學院", "1550", "資訊工程學系", 113, "nstc"),
    ("313551202", "續領-張雅婷", "CHANG,YA-TING", 2, "C", "資訊學院", "155", "資訊科學與工程研究所", 113, "moe_1w"),
    ("312551203", "續領-黃冠宇", "HUANG,KUAN-YU", 1, "E", "電機學院", "3511", "電機工程學系", 112, "nstc"),
    ("313551204", "續領-吳佩珊", "WU,PEI-SHAN", 2, "E", "電機學院", "183", "電機學院博士班", 113, "moe_1w"),
    ("311551205", "續領-鄭宇軒", "CHENG,YU-HSUAN", 1, "C", "資訊學院", "1550", "資訊工程學系", 111, "nstc"),
]

# --- 115 新申請：由學生自行登入申請 --------------------------------------------
NEW_APPLICANTS_115 = [
    ("315551401", "新申請-蔡承恩", "TSAI,CHENG-EN", 1, "C", "資訊學院", "1550", "資訊工程學系", 115),
    ("314551402", "新申請-郭芷瑄", "KUO,CHIH-HSUAN", 2, "C", "資訊學院", "155", "資訊科學與工程研究所", 114),
    ("315551403", "新申請-楊子萱", "YANG,TZU-HSUAN", 2, "E", "電機學院", "3511", "電機工程學系", 115),
    ("314551404", "新申請-許文傑", "HSU,WEN-CHIEH", 1, "E", "電機學院", "183", "電機學院博士班", 114),
]

# Advisor per college — both are seeded professor accounts (seed_test_users).
ADVISOR_BY_COLLEGE = {
    "C": {"nycu_id": "cs_professor", "name": "李資訊教授", "email": "cs_professor@nycu.edu.tw"},
    "E": {"nycu_id": "professor", "name": "李教授", "email": "professor@nycu.edu.tw"},
}


def _term_count(enroll_year: int, year: int, term: int) -> int:
    return (year - enroll_year) * 2 + term


def _postal_account(stdcode: str) -> str:
    return f"0021{stdcode}"


def _build_student_data(entry: StudentEntry, year: int) -> Dict[str, Any]:
    """SIS snapshot as it looked when the `year` application was submitted (term 2)."""
    stdcode, cname, ename, sex, academyno, academyname, depno, depname, enrollyear = entry[:9]
    term_count = _term_count(enrollyear, year, 2)
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
        "std_termcount": term_count,
        "std_studingstatus": 2,
        "mgd_title": "在學",
        "ToDoctor": 0,
        "com_commadd": "新竹市東區大學路1001號",
        "com_email": f"{stdcode}@nycu.edu.tw",
        "com_cellphone": f"0912{stdcode[-6:]}",
        "trm_year": year,
        "trm_term": 2,
        "trm_termcount": term_count,
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
        "_api_fetched_at": f"{year + 1911}-10-01T00:00:00Z",
        "_term_data_status": "success",
    }


def _text_field(field_id: str, value: str) -> Dict[str, Any]:
    return {"field_id": field_id, "field_type": "text", "value": value, "required": True}


def _build_submitted_form_data(stdcode: str, advisor: Dict[str, str]) -> Dict[str, Any]:
    return {
        "fields": {
            "postal_account": _text_field("postal_account", _postal_account(stdcode)),
            "advisor_name": _text_field("advisor_name", advisor["name"]),
            "advisor_email": _text_field("advisor_email", advisor["email"]),
            "advisor_nycu_id": _text_field("advisor_nycu_id", advisor["nycu_id"]),
            "master_school_info": _text_field("master_school_info", "國立陽明交通大學資訊學院資訊科學與工程研究所"),
        },
        "documents": [],
    }


async def _find_user(session: AsyncSession, nycu_id: str) -> Optional[User]:
    return (await session.execute(select(User).where(User.nycu_id == nycu_id))).scalar_one_or_none()


async def _get_or_create_student_user(session: AsyncSession, entry: StudentEntry) -> User:
    stdcode, cname, _ename, _sex, _academyno, _academyname, depno, depname = entry[:8]
    user = await _find_user(session, stdcode)
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


async def _ensure_profile(session: AsyncSession, user: User, stdcode: str, advisor: Dict[str, str]) -> None:
    """Profile carries the advisor trio so professor auto-assignment and
    notifications work the same way they do for wizard-submitted students."""
    existing = (await session.execute(select(UserProfile).where(UserProfile.user_id == user.id))).scalar_one_or_none()
    if existing:
        return
    session.add(
        UserProfile(
            user_id=user.id,
            account_number=_postal_account(stdcode),
            advisor_name=advisor["name"],
            advisor_email=advisor["email"],
            advisor_nycu_id=advisor["nycu_id"],
        )
    )


def _submitted_at(year: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=MONTHS_BEFORE_NOW_BY_YEAR[year] * DAYS_PER_MONTH)


async def _get_or_create_application(
    session: AsyncSession,
    *,
    entry: StudentEntry,
    index: int,
    year: int,
    phd: ScholarshipType,
    config: ScholarshipConfiguration,
    user: User,
    advisor_user: Optional[User],
) -> Application:
    """Approved yearly application for `year`; 114 is the renewal of 113."""
    stdcode, academyno, sub_type = entry[0], entry[4], entry[9]
    is_renewal = year == RENEWAL_YEAR
    app_id = f"APP-{year}-0-{APP_SEQUENCE_BASE + index:05d}"
    existing = (await session.execute(select(Application).where(Application.app_id == app_id))).scalar_one_or_none()
    if existing:
        return existing

    application = Application(
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
        is_renewal=is_renewal,
        # renewal_import_service convention: renewal_year = the year being renewed IN.
        renewal_year=year if is_renewal else None,
        status=ApplicationStatus.approved.value,
        review_stage=ReviewStage.completed.value,
        academic_year=year,
        semester=None,  # phd is yearly -> NULL
        student_data=_build_student_data(entry, year),
        submitted_form_data=_build_submitted_form_data(stdcode, ADVISOR_BY_COLLEGE[academyno]),
        agree_terms=True,
        submitted_at=_submitted_at(year),
    )
    session.add(application)
    await session.flush()
    return application


def _build_roster_item(roster: PaymentRoster, application: Application, phd: ScholarshipType) -> PaymentRosterItem:
    student_data = application.student_data
    identity = f"{application.academic_year}{'續領' if application.is_renewal else '新申請'}"
    return PaymentRosterItem(
        roster_id=roster.id,
        application_id=application.id,
        student_id_number=student_data["std_pid"],
        student_number=student_data["std_stdcode"],
        student_name=student_data["std_cname"],
        student_email=student_data["com_email"],
        bank_account=_postal_account(student_data["std_stdcode"]),
        mailing_address=student_data["com_commadd"],
        scholarship_name=phd.name,
        scholarship_amount=application.amount,
        scholarship_subtype=application.sub_scholarship_type,
        allocation_config_id=roster.allocation_config_id,
        allocation_year=roster.allocation_year,
        allocated_sub_type=application.sub_scholarship_type,
        application_identity=identity,
        verification_status=StudentVerificationStatus.VERIFIED,
        verification_message="學籍驗證通過",
        verification_at=roster.completed_at,
        is_included=True,
        nationality_code="1",
        residence_days_over_183="是",
        rule_validation_result={"is_eligible": True, "failed_rules": [], "warning_rules": []},
        failed_rules=[],
        warning_rules=[],
    )


async def _get_or_create_locked_roster(
    session: AsyncSession,
    *,
    config: ScholarshipConfiguration,
    sub_type: str,
    applications: List[Application],
    phd: ScholarshipType,
    admin_id: int,
) -> bool:
    """One LOCKED yearly roster per (config, sub_type), shaped like
    RosterService.generate_rosters_from_distribution output (matrix path)."""
    year = config.academic_year
    roster_code = f"ROSTER-{year}-{sub_type}-{config.config_code}-{config.config_code}"
    existing = (
        await session.execute(select(PaymentRoster).where(PaymentRoster.roster_code == roster_code))
    ).scalar_one_or_none()
    if existing:
        return False

    completed_at = _submitted_at(year) + timedelta(days=45)
    total_amount = sum(float(app.amount or 0) for app in applications)
    roster = PaymentRoster(
        roster_code=roster_code,
        scholarship_configuration_id=config.id,
        allocation_config_id=config.id,
        period_label=str(year),
        academic_year=year,
        roster_cycle=RosterCycle.YEARLY,
        sub_type=sub_type,
        allocation_year=year,
        project_number=(config.project_numbers or {}).get(sub_type),
        status=RosterStatus.LOCKED,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin_id,
        started_at=completed_at - timedelta(minutes=5),
        completed_at=completed_at,
        locked_at=completed_at + timedelta(days=1),
        locked_by=admin_id,
        total_applications=len(applications),
        qualified_count=len(applications),
        disqualified_count=0,
        total_amount=total_amount,
        student_verification_enabled=True,
        notes="開發環境示範資料（seed_ay115_demo）",
    )
    session.add(roster)
    await session.flush()
    for application in applications:
        session.add(_build_roster_item(roster, application, phd))
    return True


async def _ensure_yearly_schedule(session: AsyncSession, config: ScholarshipConfiguration, admin_id: int) -> bool:
    """Active yearly 造冊 schedule for `config`, as the admin would create it in 造冊管理."""
    existing = (
        await session.execute(select(RosterSchedule.id).where(RosterSchedule.scholarship_configuration_id == config.id))
    ).scalar_one_or_none()
    if existing:
        return False
    session.add(
        RosterSchedule(
            schedule_name=f"{config.config_name} 年度造冊",
            description="開發環境示範排程（seed_ay115_demo）",
            scholarship_configuration_id=config.id,
            roster_cycle=RosterCycle.YEARLY,
            auto_lock=False,
            student_verification_enabled=True,
            notification_enabled=False,
            status=RosterScheduleStatus.ACTIVE,
            created_by_user_id=admin_id,
        )
    )
    return True


async def _seed_renewal_cohort(
    session: AsyncSession, phd: ScholarshipType, configs: Dict[int, ScholarshipConfiguration], admin_id: int
) -> Dict[str, int]:
    apps_by_year_and_sub_type: Dict[tuple, List[Application]] = {}
    created_apps = 0
    for index, entry in enumerate(RENEWAL_COHORT, start=1):
        stdcode, academyno, sub_type = entry[0], entry[4], entry[9]
        advisor = ADVISOR_BY_COLLEGE[academyno]
        user = await _get_or_create_student_user(session, entry)
        await _ensure_profile(session, user, stdcode, advisor)
        advisor_user = await _find_user(session, advisor["nycu_id"])
        for year in (FIRST_AWARD_YEAR, RENEWAL_YEAR):
            before = await session.execute(
                select(Application.id).where(Application.app_id == f"APP-{year}-0-{APP_SEQUENCE_BASE + index:05d}")
            )
            application = await _get_or_create_application(
                session,
                entry=entry,
                index=index,
                year=year,
                phd=phd,
                config=configs[year],
                user=user,
                advisor_user=advisor_user,
            )
            created_apps += before.scalar_one_or_none() is None
            apps_by_year_and_sub_type.setdefault((year, sub_type), []).append(application)

    created_rosters = 0
    for (year, sub_type), applications in sorted(apps_by_year_and_sub_type.items()):
        created_rosters += await _get_or_create_locked_roster(
            session, config=configs[year], sub_type=sub_type, applications=applications, phd=phd, admin_id=admin_id
        )
    return {"applications": created_apps, "rosters": created_rosters}


async def _seed_115_new_applicants(session: AsyncSession) -> int:
    created = 0
    for entry in NEW_APPLICANTS_115:
        before = await _find_user(session, entry[0])
        user = await _get_or_create_student_user(session, entry)
        await _ensure_profile(session, user, entry[0], ADVISOR_BY_COLLEGE[entry[4]])
        created += before is None
    return created


async def seed_ay115_demo(session: AsyncSession) -> None:
    """Seed the 續領 cohort (113 award + 114 renewal + locked rosters) and the 115 new-applicant accounts."""
    phd = (
        await session.execute(select(ScholarshipType).where(ScholarshipType.code == PHD_SCHOLARSHIP_CODE))
    ).scalar_one_or_none()
    configs: Dict[int, ScholarshipConfiguration] = {}
    for year, code in CONFIG_CODE_BY_YEAR.items():
        config = (
            await session.execute(select(ScholarshipConfiguration).where(ScholarshipConfiguration.config_code == code))
        ).scalar_one_or_none()
        if config:
            configs[year] = config
    admin = await _find_user(session, "admin")
    if not phd or len(configs) != len(CONFIG_CODE_BY_YEAR) or not admin:
        print("  ⚠️  phd scholarship, phd_113/phd_114 configs or admin user missing — skipping AY115 demo")
        return

    cohort = await _seed_renewal_cohort(session, phd, configs, admin.id)
    applicants = await _seed_115_new_applicants(session)

    schedules = 0
    for code in SCHEDULE_CONFIG_CODES:
        config = (
            await session.execute(select(ScholarshipConfiguration).where(ScholarshipConfiguration.config_code == code))
        ).scalar_one_or_none()
        if config:
            schedules += await _ensure_yearly_schedule(session, config, admin.id)
    await session.commit()

    logger.info("AY115 demo cohort seeded: %s", {**cohort, "applicants": applicants})
    print(f"  ✓ 續領生 (113 新申請 + 114 續領, approved): +{cohort['applications']} applications")
    print(f"  ✓ 113/114 已鎖定造冊: +{cohort['rosters']} rosters")
    print(f"  ✓ 115 新申請學生帳號: +{applicants} users")
    print(f"  ✓ 年度造冊排程 (phd_113/114/115): +{schedules} schedules")
