"""Tests for the admin toggle + college view of distribution results."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin, require_college
from app.main import app
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipStatus,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import AdminScholarship, User, UserRole, UserType

CONFIG_BASE = "/api/v1/scholarship-configurations/configurations"


@pytest_asyncio.fixture
async def sch_type(db: AsyncSession) -> ScholarshipType:
    st = ScholarshipType(
        code="cvd_phd",
        name="CVD PhD Scholarship",
        description="college-view-distribution test",
        status=ScholarshipStatus.active.value,
    )
    db.add(st)
    await db.commit()
    await db.refresh(st)
    return st


@pytest_asyncio.fixture
async def config(db: AsyncSession, sch_type) -> ScholarshipConfiguration:
    cfg = ScholarshipConfiguration(
        scholarship_type_id=sch_type.id,
        config_name="CVD 114-1",
        config_code="CVD-114-1",
        academic_year=114,
        semester="first",
        amount=40000,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@pytest_asyncio.fixture
async def admin_client(db: AsyncSession, client: AsyncClient, sch_type) -> AsyncClient:
    admin = User(
        nycu_id="cvd_admin",
        email="cvd_admin@university.edu",
        name="CVD Admin",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    db.add(AdminScholarship(admin_id=admin.id, scholarship_id=sch_type.id))
    await db.commit()

    async def override_admin():
        return admin

    app.dependency_overrides[require_admin] = override_admin
    try:
        yield client
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_admin_can_toggle_college_view_distribution(admin_client, config, db):
    resp = await admin_client.patch(f"{CONFIG_BASE}/{config.id}/college-view-distribution", json={"allow": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["allow_college_view_distribution"] is True

    await db.refresh(config)
    assert config.allow_college_view_distribution is True


DIST_URL = "/api/v1/college-review/distribution-results"


def _student_data(std_code: str, name: str, academy: str) -> dict:
    return {"std_stdcode": std_code, "std_cname": name, "std_academyno": academy}


@pytest_asyncio.fixture
async def college_client_factory(db: AsyncSession, client: AsyncClient):
    """Return a helper that overrides require_college with a college user bound to `academy`."""

    async def _make(academy: str) -> AsyncClient:
        user = User(
            nycu_id=f"cvd_college_{academy}",
            email=f"cvd_college_{academy}@university.edu",
            name=f"College {academy}",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code=academy,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        async def override_college():
            return user

        app.dependency_overrides[require_college] = override_college
        return client

    yield _make
    app.dependency_overrides.pop(require_college, None)


async def _seed_distribution(db, sch_type, *, executed: bool):
    """One finalized ranking for sub_type 'nstc' with 3 items in college 'A':
    admitted (rank1), backup (pos1), rejected; plus one admitted student in college 'B'."""
    ranking = CollegeRanking(
        scholarship_type_id=sch_type.id,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        ranking_name="nstc 114-1",
        total_applications=4,
        is_finalized=True,
        distribution_executed=executed,
        allocated_count=2,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)

    def app_row(sid, name, academy, status="approved"):
        # Application.user_id is NOT NULL and uq(user_id, scholarship_type_id, year,
        # semester) means each row needs its own student user.
        student = User(
            nycu_id=f"cvd_student_{sid}",
            email=f"cvd_student_{sid}@university.edu",
            name=name,
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(student)
        return Application(
            app_id=f"APP-CVD-{sid}",  # app_id is NOT NULL
            student=student,  # sets user_id (NOT NULL) via relationship
            scholarship_type_id=sch_type.id,
            academic_year=114,
            semester="first",
            status=status,
            sub_type_selection_mode=SubTypeSelectionMode.single,  # NOT NULL, no default
            student_data=_student_data(sid, name, academy),
        )

    a_admit = app_row("A001", "王小明", "A")
    a_backup = app_row("A002", "陳小美", "A", status="submitted")
    a_reject = app_row("A003", "張三", "A", status="submitted")
    b_admit = app_row("B001", "他校生", "B")
    for a in (a_admit, a_backup, a_reject, b_admit):
        db.add(a)
    await db.commit()
    for a in (a_admit, a_backup, a_reject, b_admit):
        await db.refresh(a)

    db.add_all(
        [
            CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=a_admit.id,
                rank_position=1,
                is_allocated=True,
                allocated_sub_type="nstc",
                status="allocated",
            ),
            CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=a_backup.id,
                rank_position=2,
                is_allocated=False,
                status="waitlisted",
                backup_allocations=[{"sub_type": "nstc", "backup_position": 1}],
            ),
            CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=a_reject.id,
                rank_position=3,
                is_allocated=False,
                status="rejected",
            ),
            CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=b_admit.id,
                rank_position=1,
                is_allocated=True,
                allocated_sub_type="nstc",
                status="allocated",
            ),
        ]
    )
    await db.commit()
    return ranking


@pytest.mark.asyncio
async def test_distribution_results_403_when_flag_off(college_client_factory, config, sch_type, db):
    # config.allow_college_view_distribution defaults to False
    cclient = await college_client_factory("A")
    resp = await cclient.get(
        DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    assert resp.status_code == 403
    # Backend may wrap HTTPException into {success,message,...} OR return FastAPI's {detail}.
    body = resp.json()
    assert "分發結果尚未開放查看" in (body.get("detail") or body.get("message") or "")


@pytest.mark.asyncio
async def test_distribution_results_allocation_wins_over_college_rejected(college_client_factory, config, sch_type, db):
    """FIX A precedence: a student who was actually allocated (is_allocated=True) must show
    as 正取 (admitted) even when college_rejected=True — i.e. the admin overrode the college's
    N. The allocation outcome wins over the college-rejection flag."""
    config.allow_college_view_distribution = True
    await db.commit()

    ranking = CollegeRanking(
        scholarship_type_id=sch_type.id,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        ranking_name="nstc 114-1 override",
        total_applications=1,
        is_finalized=True,
        distribution_executed=True,
        allocated_count=1,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)

    student = User(
        nycu_id="cvd_student_OVR1",
        email="cvd_student_OVR1@university.edu",
        name="覆核錄取生",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    appn = Application(
        app_id="APP-CVD-OVR1",
        student=student,  # distinct user_id satisfies uq(user_id, type, year, semester)
        scholarship_type_id=sch_type.id,
        academic_year=114,
        semester="first",
        status="approved",
        sub_type_selection_mode=SubTypeSelectionMode.single,
        student_data=_student_data("OVR1", "覆核錄取生", "A"),
    )
    db.add(appn)
    await db.commit()
    await db.refresh(appn)

    db.add(
        CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=appn.id,
            rank_position=1,
            is_allocated=True,
            allocated_sub_type="nstc",
            college_rejected=True,  # admin overrode the college's N
            status="allocated",
        )
    )
    await db.commit()

    cclient = await college_client_factory("A")
    resp = await cclient.get(
        DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    nstc = next(g for g in data["sub_types"] if g["code"] == "nstc")
    admitted_numbers = {s["student_number"] for s in nstc["admitted"]}
    rejected_numbers = {s["student_number"] for s in nstc["rejected"]}

    assert "OVR1" in admitted_numbers  # allocation outcome wins -> 正取
    assert "OVR1" not in rejected_numbers


@pytest.mark.asyncio
async def test_distribution_results_grouped_and_college_scoped(college_client_factory, config, sch_type, db):
    config.allow_college_view_distribution = True
    await db.commit()
    await _seed_distribution(db, sch_type, executed=True)

    cclient = await college_client_factory("A")
    resp = await cclient.get(
        DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["distribution_executed"] is True
    nstc = next(g for g in data["sub_types"] if g["code"] == "nstc")

    admitted_numbers = {s["student_number"] for s in nstc["admitted"]}
    backup_numbers = {s["student_number"] for s in nstc["backup"]}
    rejected_numbers = {s["student_number"] for s in nstc["rejected"]}

    assert admitted_numbers == {"A001"}  # B001 (other college) excluded
    assert backup_numbers == {"A002"}
    assert rejected_numbers == {"A003"}
    assert "B001" not in (admitted_numbers | backup_numbers | rejected_numbers)


@pytest.mark.asyncio
async def test_distribution_results_empty_when_not_executed(college_client_factory, config, sch_type, db):
    config.allow_college_view_distribution = True
    await db.commit()
    await _seed_distribution(db, sch_type, executed=False)

    cclient = await college_client_factory("A")
    resp = await cclient.get(
        DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["distribution_executed"] is False
    assert data["sub_types"] == []
