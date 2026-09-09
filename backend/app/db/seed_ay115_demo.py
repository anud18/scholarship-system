"""AY115 demo cohort for the dev environment.

Timeline the seed represents: the 114 cycle is fully closed (rankings
finalized, distribution executed, rosters locked) and the 115 cycle is open
for both 新申請 and 續領. Three kinds of students exist:

1. **續領生 (currently on renewal)** — awarded in 113 (`phd_113`, 新申請,
   ranked + allocated) and renewed for 114 as 113 續領生: the renewal keeps
   `scholarship_configuration_id` / `allocation_config_id` on `phd_113` (the
   slot they hold) with `academic_year=114`, exactly as the self-renew path
   creates it. Both years are approved and sit in LOCKED **monthly** payment
   rosters under `phd_113` (113-09 … 114-08; 博士生是月度造冊), so 領獎紀錄 /
   領取月份數 show real history (12 + 12 months) and phd_113's 造冊列表 shows
   its second year segment.
2. **114 新申請得獎者** — first awarded in 114 through the college ranking +
   matrix distribution. They are what makes the 114 造冊 preview work: the
   matrix-mode roster/preview path reads *allocated ranking items*, and
   renewals never sit in a ranking.
3. **115 新申請** — plain student accounts for the application wizard.

Groups 1 and 2 are the 115 續領 pool: the student can self-renew via
`/renewals/eligible`, or the admin imports them through 匯入續領生 (workbook
from `backend/scripts/generate_ay115_import_samples.py`).

Students meant to arrive via 批次匯入 get an ACCOUNT ONLY (so they show up in
the Development Login picker); the import creates their applications.

Every student here is mirrored in `mock-student-api/main.py` (`_AY115_DEMO`)
with term rows through 115-2, so SIS lookups and the eligibility rules resolve.

Idempotent: users/profiles are created only when missing; applications,
rankings, rosters and schedules are skipped when they already exist.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ReviewStage
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.received_months import StudentReceivedMonthRecord
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.roster_schedule import RosterSchedule, RosterScheduleStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipRule, ScholarshipType, SubTypeSelectionMode
from app.models.user import EmployeeStatus, User, UserRole, UserType
from app.models.user_profile import UserProfile

logger = logging.getLogger(__name__)

PHD_SCHOLARSHIP_CODE = "phd"
FIRST_AWARD_YEAR = 113  # 新申請 year of the 續領 cohort
RENEWAL_YEAR = 114  # year they are currently renewing in; also the year of the 114 新申請 recipients
CLOSED_YEARS = (FIRST_AWARD_YEAR, RENEWAL_YEAR)
CONFIG_CODE_BY_YEAR = {FIRST_AWARD_YEAR: "phd_113", RENEWAL_YEAR: "phd_114"}
# The 造冊 dashboard (payment-rosters/cycle-status) lists a config's periods ONLY
# when the config has a RosterSchedule — without one, 114-整學年 shows nothing
# even though its locked rosters exist. 博士生是月度造冊: seed a monthly schedule for every PhD year.
SCHEDULE_CONFIG_CODES = ("phd_113", "phd_114", "phd_115")
APP_SEQUENCE_BASE = 200  # APP-<year>-0-002xx, clear of the sequence counter and other demo seeds
MONTHS_BEFORE_NOW_BY_YEAR = {FIRST_AWARD_YEAR: 24, RENEWAL_YEAR: 12}
DAYS_PER_MONTH = 30
RANKING_SUB_TYPE_CODE = "default"  # college rankings are per college, not per sub-type
# 已領月份數 baseline (StudentReceivedMonthRecord, the 領取月份數匯入 half of the
# additive rule in docs/adr/0001): the system half only counts rosters under the
# CURRENT config (phd_115), so months paid under phd_113/phd_114 must come from
# here or the 115 手動分發 grid shows 0 for every 續領 candidate. 鄭宇軒 sits at
# the 36-month ceiling (2 years before the system + 113/114), which is why the
# 115 續領 sheet marks them 領獎期滿.
MONTHS_PER_YEAR = 12
RECEIVED_MONTHS_CEILING_STUDENT = "311551205"
RECEIVED_MONTHS_CEILING = 36
COLLEGE_NAMES = {"C": "資訊學院", "E": "電機學院"}

# (stdcode, cname, ename, sex, academyno, academyname, depno, depname, enrollyear[, sub_type])
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

# --- 114 新申請得獎者：114 經學院排名 + 矩陣分發核准，115 亦為續領候選 ------------
NEW_RECIPIENTS_114 = [
    ("314551206", "114新申請-何冠廷", "HO,KUAN-TING", 1, "C", "資訊學院", "155", "資訊科學與工程研究所", 114, "nstc"),
    ("314551207", "114新申請-謝宜庭", "HSIEH,YI-TING", 2, "E", "電機學院", "3511", "電機工程學系", 114, "moe_1w"),
]

# --- 115 批次匯入：帳號先建好（Development Login 可見），申請由匯入建立 ----------
BATCH_IMPORT_STUDENTS_115 = [
    ("314551301", "匯入-陳柏宇", "CHEN,PO-YU", 1, "C", "資訊學院", "1550", "資訊工程學系", 114),
    ("314551302", "匯入-李欣怡", "LEE,HSIN-YI", 2, "C", "資訊學院", "155", "資訊科學與工程研究所", 114),
    ("314551303", "匯入-王志豪", "WANG,CHIH-HAO", 1, "E", "電機學院", "3511", "電機工程學系", 114),
    ("313551304", "匯入-劉育綺", "LIU,YU-CHI", 2, "E", "電機學院", "183", "電機學院博士班", 113),
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


async def _ensure_account(session: AsyncSession, entry: StudentEntry) -> bool:
    """User + profile for `entry`; True when the user was newly created."""
    before = await _find_user(session, entry[0])
    user = await _get_or_create_student_user(session, entry)
    await _ensure_profile(session, user, entry[0], ADVISOR_BY_COLLEGE[entry[4]])
    return before is None


def _submitted_at(year: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=MONTHS_BEFORE_NOW_BY_YEAR[year] * DAYS_PER_MONTH)


def _app_id(year: int, index: int) -> str:
    return f"APP-{year}-0-{APP_SEQUENCE_BASE + index:05d}"


async def _get_or_create_application(
    session: AsyncSession,
    *,
    entry: StudentEntry,
    index: int,
    year: int,
    is_renewal: bool,
    phd: ScholarshipType,
    config: ScholarshipConfiguration,
    previous_application: Optional[Application] = None,
) -> Application:
    """Approved yearly application for `year`, shaped like a finalized distribution
    left it, plus the professor's approving review so it does not linger in the
    professor's 待審核 list (approved is a reviewable status; 待審核 = no review row)."""
    stdcode, academyno, sub_type = entry[0], entry[4], entry[9]
    advisor = ADVISOR_BY_COLLEGE[academyno]
    user = await _get_or_create_student_user(session, entry)
    advisor_user = await _find_user(session, advisor["nycu_id"])
    app_id = _app_id(year, index)
    existing = (await session.execute(select(Application).where(Application.app_id == app_id))).scalar_one_or_none()
    if existing:
        return existing

    submitted_at = _submitted_at(year)
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
        # Self-renew convention (renewal.py): renewal_year = the prior award's year,
        # linked through previous_application_id.
        renewal_year=previous_application.academic_year if (is_renewal and previous_application) else None,
        previous_application_id=previous_application.id if (is_renewal and previous_application) else None,
        status=ApplicationStatus.approved.value,
        review_stage=ReviewStage.quota_distributed.value,
        quota_allocation_status="allocated",
        academic_year=year,
        semester=None,  # phd is yearly -> NULL
        student_data=_build_student_data(entry, year),
        submitted_form_data=_build_submitted_form_data(stdcode, advisor),
        agree_terms=True,
        submitted_at=submitted_at,
        approved_at=submitted_at + timedelta(days=40),
    )
    session.add(application)
    await session.flush()
    if advisor_user:
        review = ApplicationReview(
            application_id=application.id,
            reviewer_id=advisor_user.id,
            recommendation="approve",
            comments="推薦（開發環境示範資料）",
            reviewed_at=submitted_at + timedelta(days=10),
        )
        session.add(review)
        await session.flush()
        session.add(ApplicationReviewItem(review_id=review.id, sub_type_code=sub_type, recommendation="approve"))
    return application


async def _get_or_create_finalized_ranking(
    session: AsyncSession,
    *,
    phd: ScholarshipType,
    config: ScholarshipConfiguration,
    college_code: str,
    applications: List[Application],
    admin_id: int,
) -> Optional[CollegeRanking]:
    """Finalized + distribution-executed college ranking for `year`, holding the
    college's 新申請 as allocated items — exactly what the matrix 造冊/preview
    path joins on. Returns None when the ranking already existed."""
    year = config.academic_year
    existing = (
        await session.execute(
            select(CollegeRanking).where(
                CollegeRanking.scholarship_type_id == phd.id,
                CollegeRanking.academic_year == year,
                CollegeRanking.college_code == college_code,
                CollegeRanking.sub_type_code == RANKING_SUB_TYPE_CODE,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return None

    finalized_at = _submitted_at(year) + timedelta(days=30)
    ranking = CollegeRanking(
        scholarship_type_id=phd.id,
        sub_type_code=RANKING_SUB_TYPE_CODE,
        academic_year=year,
        semester=None,
        college_code=college_code,
        ranking_name=f"{COLLEGE_NAMES[college_code]} 博士生獎學金 {year} 全年",
        total_applications=len(applications),
        total_quota=config.total_quota,
        allocated_count=len(applications),
        is_finalized=True,
        ranking_status="finalized",
        distribution_executed=True,
        distribution_date=finalized_at + timedelta(days=7),
        finalized_at=finalized_at,
        created_by=admin_id,
        finalized_by=admin_id,
    )
    session.add(ranking)
    await session.flush()
    for position, application in enumerate(applications, start=1):
        session.add(
            CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=application.id,
                rank_position=position,
                is_allocated=True,
                status="allocated",
                allocation_reason="手動分發",
                allocated_sub_type=application.sub_scholarship_type,
                allocation_config_id=config.id,
            )
        )
    return ranking


def _rule_details(rules: List[ScholarshipRule]) -> Dict[str, Any]:
    """Frozen per-rule snapshot in the shape RosterService._validate_student_eligibility
    writes — the roster Excel builds its 資格 columns from these keys."""
    return {
        f"rule_{rule.id}": {
            "passed": True,
            "rule_name": rule.rule_name,
            "rule_type": rule.rule_type,
            "is_hard_rule": rule.is_hard_rule,
            "message": rule.message,
        }
        for rule in rules
    }


def _build_roster_item(
    roster: PaymentRoster,
    application: Application,
    config: ScholarshipConfiguration,
    phd: ScholarshipType,
    rules: List[ScholarshipRule],
) -> PaymentRosterItem:
    """`config` is the slot-owning configuration the item snapshots (per-period
    rosters carry no roster-level allocation snapshot, exactly like the service)."""
    student_data = application.student_data
    # 續領標得獎配置年度（113 續領生），新申請標送件年度 — 同 _create_roster_item。
    identity = f"{config.academic_year}續領" if application.is_renewal else f"{application.academic_year}新申請"
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
        allocation_config_id=config.id,
        allocation_year=config.academic_year,
        allocated_sub_type=application.sub_scholarship_type,
        application_identity=identity,
        verification_status=StudentVerificationStatus.VERIFIED,
        verification_message="學籍驗證通過",
        verification_at=roster.completed_at,
        verification_snapshot={"status": "verified", "message": "學籍驗證通過"},
        is_included=True,
        nationality_code="1",
        residence_days_over_183="是",
        rule_validation_result={
            "is_eligible": True,
            "failed_rules": [],
            "warning_rules": [],
            "details": _rule_details(rules),
        },
        failed_rules=[],
        warning_rules=[],
    )


ACADEMIC_YEAR_MONTHS = (9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8)  # 學年度 9 月起，同 cycle-status


def _month_completed_at(year: int, month: int) -> datetime:
    """A plausible 造冊 completion timestamp inside the paid month."""
    western_year = year + 1911
    calendar_year = western_year if month >= 9 else western_year + 1
    return datetime(calendar_year, month, 5, 9, 0, tzinfo=timezone.utc)


async def _get_or_create_locked_monthly_rosters(
    session: AsyncSession,
    *,
    config: ScholarshipConfiguration,
    year: int,
    applications: List[Application],
    phd: ScholarshipType,
    rules: List[ScholarshipRule],
    admin_id: int,
) -> int:
    """博士生是月度造冊：twelve LOCKED monthly rosters for one (slot-owning config,
    paying year), shaped like RosterService.generate_roster output — one roster
    per period holding every sub_type (the Excel splits them into sheets), no
    roster-level allocation snapshot (the items carry it). Returns rosters created."""
    created = 0
    total_amount = sum(float(app.amount or 0) for app in applications)
    for month in ACADEMIC_YEAR_MONTHS:
        period_label = f"{year}-{month:02d}"
        roster_code = f"ROSTER-{year}-{period_label}-{config.config_code}"
        existing = (
            await session.execute(select(PaymentRoster.id).where(PaymentRoster.roster_code == roster_code))
        ).scalar_one_or_none()
        if existing:
            continue

        completed_at = _month_completed_at(year, month)
        roster = PaymentRoster(
            roster_code=roster_code,
            scholarship_configuration_id=config.id,
            period_label=period_label,
            academic_year=year,
            roster_cycle=RosterCycle.MONTHLY,
            status=RosterStatus.LOCKED,
            trigger_type=RosterTriggerType.SCHEDULED,
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
            session.add(_build_roster_item(roster, application, config, phd, rules))
        created += 1
    return created


async def _ensure_monthly_schedule(session: AsyncSession, config: ScholarshipConfiguration, admin_id: int) -> bool:
    """Active monthly 造冊 schedule for `config`, as the admin would create it in 造冊管理."""
    # roster_schedules has no unique constraint on the config FK: an admin can add a
    # second schedule in 造冊管理, so never assume a single row.
    existing = (
        await session.execute(select(RosterSchedule.id).where(RosterSchedule.scholarship_configuration_id == config.id))
    ).first()
    if existing:
        return False
    session.add(
        RosterSchedule(
            schedule_name=f"{config.config_name} 月度造冊",
            description="開發環境示範排程（seed_ay115_demo）",
            scholarship_configuration_id=config.id,
            roster_cycle=RosterCycle.MONTHLY,
            auto_lock=False,
            student_verification_enabled=True,
            notification_enabled=False,
            status=RosterScheduleStatus.ACTIVE,
            created_by_user_id=admin_id,
        )
    )
    return True


def _closed_year_plan() -> List[tuple]:
    """(entry, index, year, is_renewal) for every approved application of the closed years."""
    plan = []
    for index, entry in enumerate(RENEWAL_COHORT, start=1):
        plan.append((entry, index, FIRST_AWARD_YEAR, False))
        plan.append((entry, index, RENEWAL_YEAR, True))
    offset = len(RENEWAL_COHORT)
    for index, entry in enumerate(NEW_RECIPIENTS_114, start=offset + 1):
        plan.append((entry, index, RENEWAL_YEAR, False))
    return plan


async def _seed_closed_years(
    session: AsyncSession, phd: ScholarshipType, configs: Dict[int, ScholarshipConfiguration], admin_id: int
) -> Dict[str, int]:
    """Approved applications, finalized rankings and locked rosters for 113 and 114."""
    counts = {"applications": 0, "rankings": 0, "rosters": 0}
    apps_by_year: Dict[int, List[Application]] = {year: [] for year in CLOSED_YEARS}

    for entry in RENEWAL_COHORT + NEW_RECIPIENTS_114:
        await _ensure_account(session, entry)
    first_award_by_index: Dict[int, Application] = {}
    for entry, index, year, is_renewal in _closed_year_plan():
        already = (
            await session.execute(select(Application.id).where(Application.app_id == _app_id(year, index)))
        ).scalar_one_or_none()
        # A renewal stays on the configuration that awarded the slot (113 續領生
        # renew phd_113 for 114); only 新申請 belong to their own year's config.
        application = await _get_or_create_application(
            session,
            entry=entry,
            index=index,
            year=year,
            is_renewal=is_renewal,
            phd=phd,
            config=configs[FIRST_AWARD_YEAR] if is_renewal else configs[year],
            previous_application=first_award_by_index.get(index) if is_renewal else None,
        )
        counts["applications"] += already is None
        apps_by_year[year].append(application)
        if year == FIRST_AWARD_YEAR:
            first_award_by_index[index] = application

    for year in CLOSED_YEARS:
        config = configs[year]
        rules = list(
            (
                await session.execute(
                    select(ScholarshipRule).where(
                        ScholarshipRule.scholarship_type_id == phd.id,
                        ScholarshipRule.academic_year == year,
                        ScholarshipRule.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        ranking_ids: List[int] = []
        for college_code in sorted(COLLEGE_NAMES):
            new_apps = [
                app
                for app in apps_by_year[year]
                if not app.is_renewal and app.student_data["std_academyno"] == college_code
            ]
            ranking = await _get_or_create_finalized_ranking(
                session, phd=phd, config=config, college_code=college_code, applications=new_apps, admin_id=admin_id
            )
            if ranking:
                counts["rankings"] += 1
                ranking_ids.append(ranking.id)
        # Twelve monthly rosters per (slot-owning config) paid in `year`: the 114
        # months under phd_113 hold the 113 續領生, the ones under phd_114 the 114 新申請.
        config_by_id = {c.id: c for c in configs.values()}
        for consumed_config_id in sorted({app.allocation_config_id for app in apps_by_year[year]}):
            consumed = config_by_id[consumed_config_id]
            group = [app for app in apps_by_year[year] if app.allocation_config_id == consumed_config_id]
            counts["rosters"] += await _get_or_create_locked_monthly_rosters(
                session,
                config=consumed,
                year=year,
                applications=group,
                phd=phd,
                rules=rules,
                admin_id=admin_id,
            )
    return counts


def _received_months_for(entry: StudentEntry, years_awarded: int) -> int:
    if entry[0] == RECEIVED_MONTHS_CEILING_STUDENT:
        return RECEIVED_MONTHS_CEILING
    return years_awarded * MONTHS_PER_YEAR


async def _ensure_received_months(session: AsyncSession, phd: ScholarshipType) -> int:
    """已領月份數 baseline rows for every closed-year recipient (see the constant note)."""
    created = 0
    cohort = [(entry, len(CLOSED_YEARS)) for entry in RENEWAL_COHORT] + [(entry, 1) for entry in NEW_RECIPIENTS_114]
    for entry, years_awarded in cohort:
        stdcode = entry[0]
        existing = (
            await session.execute(
                select(StudentReceivedMonthRecord.id).where(
                    StudentReceivedMonthRecord.student_number == stdcode,
                    StudentReceivedMonthRecord.scholarship_type_id == phd.id,
                )
            )
        ).first()
        if existing:
            continue
        session.add(
            StudentReceivedMonthRecord(
                student_number=stdcode,
                scholarship_type_id=phd.id,
                months=_received_months_for(entry, years_awarded),
                raw_row={"source": "seed_ay115_demo"},
            )
        )
        created += 1
    return created


async def _load_config(session: AsyncSession, code: str) -> Optional[ScholarshipConfiguration]:
    return (
        await session.execute(select(ScholarshipConfiguration).where(ScholarshipConfiguration.config_code == code))
    ).scalar_one_or_none()


async def seed_ay115_demo(session: AsyncSession) -> None:
    """Seed the closed 113/114 years (續領 + 114 新申請, rankings, locked rosters), the
    batch-import accounts, the 115 new-applicant accounts and the 造冊 schedules."""
    phd = (
        await session.execute(select(ScholarshipType).where(ScholarshipType.code == PHD_SCHOLARSHIP_CODE))
    ).scalar_one_or_none()
    configs: Dict[int, ScholarshipConfiguration] = {}
    for year, code in CONFIG_CODE_BY_YEAR.items():
        config = await _load_config(session, code)
        if config:
            configs[year] = config
    admin = await _find_user(session, "admin")
    if not phd or len(configs) != len(CONFIG_CODE_BY_YEAR) or not admin:
        print("  ⚠️  phd scholarship, phd_113/phd_114 configs or admin user missing — skipping AY115 demo")
        return

    closed = await _seed_closed_years(session, phd, configs, admin.id)
    received_months = await _ensure_received_months(session, phd)
    import_accounts = sum([await _ensure_account(session, entry) for entry in BATCH_IMPORT_STUDENTS_115])
    applicants = sum([await _ensure_account(session, entry) for entry in NEW_APPLICANTS_115])

    schedules = 0
    for code in SCHEDULE_CONFIG_CODES:
        config = await _load_config(session, code)
        if config:
            schedules += await _ensure_monthly_schedule(session, config, admin.id)
    await session.commit()

    logger.info(
        "AY115 demo cohort seeded: %s", {**closed, "import_accounts": import_accounts, "applicants": applicants}
    )
    print(f"  ✓ 113/114 已核准申請 (續領生 113 新申請 + 114 續領, 114 新申請得獎者): +{closed['applications']}")
    print(f"  ✓ 113/114 已定案並分發之學院排名: +{closed['rankings']}")
    print(f"  ✓ 113/114 已鎖定造冊: +{closed['rosters']}")
    print(f"  ✓ 已領月份數基準 (StudentReceivedMonthRecord): +{received_months}")
    print(f"  ✓ 115 批次匯入學生帳號 (僅帳號, 申請由匯入建立): +{import_accounts}")
    print(f"  ✓ 115 新申請學生帳號: +{applicants}")
    print(f"  ✓ 年度造冊排程 (phd_113/114/115): +{schedules}")
