"""Shared row builders for the college-ranking scope tests (not collected: no test_ prefix).

Plain async helpers (not fixtures) so the service- and endpoint-level tests of the
"several drafts, finalize keeps one" rules build identical rows. SQLite does not
enforce foreign keys, so the tests assert item / ranking row counts explicitly
(count_items / count_rankings) instead of relying on FK errors.
"""

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import func, select

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import Semester
from app.models.payment_roster import PaymentRoster, RosterCycle, RosterTriggerType
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType

# Default ranking scope of every helper: (nstc, 114, first).
SUB_TYPE = "nstc"
YEAR = 114
SEMESTER = "first"

# submitted_at of an application with order=0; order=n adds n minutes, which makes
# _ranking_sort_key (renewal first, then submission time) deterministic.
_BASE_SUBMITTED_AT = datetime(2025, 9, 1, 9, 0, tzinfo=timezone.utc)


async def make_user(db, nycu_id: str, *, role: UserRole = UserRole.college, college_code: Optional[str] = None) -> User:
    user = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@test.edu",
        user_type=UserType.student if role == UserRole.student else UserType.employee,
        role=role,
        college_code=college_code,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def make_scholarship(db, code: str = "scope_test_scholarship") -> ScholarshipType:
    scholarship = ScholarshipType(code=code, name=f"Scholarship {code}", description="ranking scope tests")
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


async def make_config(
    db,
    scholarship_id: int,
    *,
    code: str,
    academic_year: int = YEAR,
    semester: Optional[str] = SEMESTER,
    college_review_end: Optional[datetime] = None,
) -> ScholarshipConfiguration:
    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship_id,
        academic_year=academic_year,
        semester=Semester(semester) if semester else None,
        config_name=f"config {code}",
        config_code=code,
        amount=10000,
        college_review_end=college_review_end,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def make_expired_config(db, scholarship_id: int, *, code: str) -> ScholarshipConfiguration:
    """The default period's configuration with a college-review deadline in the past."""
    return await make_config(
        db, scholarship_id, code=code, college_review_end=datetime.now(timezone.utc) - timedelta(days=1)
    )


async def add_application(
    db,
    scholarship_id: int,
    key: str,
    *,
    college_code: str = "ENG",
    sub_type: str = SUB_TYPE,
    academic_year: int = YEAR,
    semester: Optional[str] = SEMESTER,
    is_renewal: bool = False,
    order: int = 0,
    status: ApplicationStatus = ApplicationStatus.approved,
    application_round: int = 1,
    configuration_id: Optional[int] = None,
) -> Application:
    """An application of one college — ranking-eligible with the defaults (approved).

    Each application gets its own student: on SQLite the per-user unique indexes of
    applications are full (their partial WHERE is PostgreSQL-only).
    """
    student = await make_user(db, f"stu_{key}", role=UserRole.student)
    application = Application(
        app_id=f"APP-{key}",
        user_id=student.id,
        scholarship_type_id=scholarship_id,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status=status.value,
        academic_year=academic_year,
        semester=semester,
        sub_scholarship_type=sub_type,
        scholarship_subtype_list=[sub_type],
        is_renewal=is_renewal,
        application_round=application_round,
        scholarship_configuration_id=configuration_id,
        submitted_at=_BASE_SUBMITTED_AT + timedelta(minutes=order),
        student_data={"std_stdcode": key, "std_cname": f"Student {key}", "std_academyno": college_code},
        submitted_form_data={},
        agree_terms=True,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


async def insert_ranking(
    db,
    scholarship_id: int,
    *,
    created_by: int,
    college_code: Optional[str] = "ENG",
    sub_type_code: str = SUB_TYPE,
    academic_year: int = YEAR,
    semester: Optional[str] = SEMESTER,
    application_ids: Iterable[int] = (),
    is_finalized: bool = False,
    name: Optional[str] = None,
) -> CollegeRanking:
    """A ranking row (plus one item per application, in the given order) built directly."""
    application_ids = list(application_ids)
    ranking = CollegeRanking(
        scholarship_type_id=scholarship_id,
        sub_type_code=sub_type_code,
        academic_year=academic_year,
        semester=semester,
        college_code=college_code,
        ranking_name=name or f"{college_code} {sub_type_code} {academic_year} {semester}",
        total_applications=len(application_ids),
        created_by=created_by,
        is_finalized=is_finalized,
        ranking_status="finalized" if is_finalized else "draft",
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)
    for position, application_id in enumerate(application_ids, 1):
        db.add(
            CollegeRankingItem(
                ranking_id=ranking.id, application_id=application_id, rank_position=position, status="ranked"
            )
        )
    await db.commit()
    return ranking


async def add_payment_roster(db, *, ranking_id: int, config_id: int, created_by: int) -> PaymentRoster:
    """A payment roster that references the ranking (payment_rosters.ranking_id)."""
    roster = PaymentRoster(
        roster_code=f"ROSTER-TEST-{ranking_id}",
        scholarship_configuration_id=config_id,
        ranking_id=ranking_id,
        period_label=str(YEAR),
        academic_year=YEAR,
        roster_cycle=RosterCycle.YEARLY,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=created_by,
    )
    db.add(roster)
    await db.commit()
    return roster


async def first_item(db, ranking_id: int) -> CollegeRankingItem:
    result = await db.execute(
        select(CollegeRankingItem)
        .where(CollegeRankingItem.ranking_id == ranking_id)
        .order_by(CollegeRankingItem.rank_position)
        .limit(1)
    )
    return result.scalar_one()


async def item_positions(db, ranking_id: int) -> List[Tuple[int, int]]:
    """(application_id, rank_position) pairs of a ranking, in rank order."""
    result = await db.execute(
        select(CollegeRankingItem.application_id, CollegeRankingItem.rank_position)
        .where(CollegeRankingItem.ranking_id == ranking_id)
        .order_by(CollegeRankingItem.rank_position, CollegeRankingItem.id)
    )
    return [(application_id, position) for application_id, position in result.all()]


async def count_items(db, ranking_id: int) -> int:
    return await db.scalar(
        select(func.count()).select_from(CollegeRankingItem).where(CollegeRankingItem.ranking_id == ranking_id)
    )


async def count_rankings(db, college_code: Optional[str] = None) -> int:
    stmt = select(func.count()).select_from(CollegeRanking)
    if college_code is not None:
        stmt = stmt.where(CollegeRanking.college_code == college_code)
    return await db.scalar(stmt)


async def ranking_exists(db, ranking_id: int) -> bool:
    return bool(
        await db.scalar(select(func.count()).select_from(CollegeRanking).where(CollegeRanking.id == ranking_id))
    )


async def final_positions(db, application_ids: Iterable[int]) -> dict:
    """application_id -> Application.final_ranking_position, read fresh from the DB."""
    result = await db.execute(
        select(Application.id, Application.final_ranking_position).where(Application.id.in_(list(application_ids)))
    )
    return {application_id: position for application_id, position in result.all()}
