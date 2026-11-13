"""Endpoint tests for the admin 各學院排名繳交總覽."""

from datetime import datetime, timezone
from typing import Optional

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.main import app
from app.models.application import Application
from app.models.audit_log import AuditAction, AuditLog
from app.models.college_review import CollegeRanking
from app.models.scholarship import ScholarshipStatus, ScholarshipType, SubTypeSelectionMode
from app.models.student import Academy
from app.models.user import User, UserRole, UserType

URL = "/api/v1/admin/scholarships/{code}/college-ranking-overview"


@pytest_asyncio.fixture
async def phd(db: AsyncSession) -> ScholarshipType:
    st = ScholarshipType(
        code="cro_phd",
        name="博士生獎學金",
        status=ScholarshipStatus.active.value,
        sub_type_selection_mode=SubTypeSelectionMode.multiple,
    )
    db.add(st)
    await db.commit()
    await db.refresh(st)
    return st


@pytest_asyncio.fixture
async def as_user(client: AsyncClient):
    def _login(user: User) -> AsyncClient:
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


async def _user(db: AsyncSession, nycu_id: str, role: UserRole, name: Optional[str] = None) -> User:
    user = User(
        nycu_id=nycu_id,
        name=name or nycu_id,
        email=f"{nycu_id}@university.edu",
        user_type=UserType.student if role == UserRole.student else UserType.employee,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _application(
    db: AsyncSession,
    st: ScholarshipType,
    student: User,
    academy: str,
    *,
    status: str = "submitted",
    year: int = 115,
    semester: Optional[str] = None,
) -> None:
    db.add(
        Application(
            app_id=f"APP-CRO-{student.nycu_id}-{year}-{semester}",
            user_id=student.id,
            scholarship_type_id=st.id,
            academic_year=year,
            semester=semester,
            status=status,
            scholarship_subtype_list=["nstc"],
            sub_type_selection_mode=SubTypeSelectionMode.multiple,
            student_data={"std_stdcode": student.nycu_id, "std_academyno": academy},
        )
    )
    await db.commit()


async def _ranking(
    db: AsyncSession,
    st: ScholarshipType,
    college_code: Optional[str],
    creator: User,
    *,
    sub_type_code: str = "nstc",
    is_finalized: bool = False,
    year: int = 115,
    semester: Optional[str] = None,
    name: str = "排名",
) -> CollegeRanking:
    ranking = CollegeRanking(
        scholarship_type_id=st.id,
        sub_type_code=sub_type_code,
        academic_year=year,
        semester=semester,
        college_code=college_code,
        ranking_name=name,
        total_applications=3,
        is_finalized=is_finalized,
        finalized_at=datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc) if is_finalized else None,
        finalized_by=creator.id if is_finalized else None,
        created_by=creator.id,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)
    return ranking


async def _import_log(db: AsyncSession, ranking: CollegeRanking, actor: User, at: datetime) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            action=AuditAction.import_.value,
            resource_type="college_ranking",
            resource_id=str(ranking.id),
            description="ranking import-excel",
            created_at=at,
        )
    )
    await db.commit()


def _by_college(body: dict) -> dict:
    return {row["college_code"]: row for row in body["data"]["colleges"]}


@pytest.mark.asyncio
async def test_lists_every_expected_college_with_its_status(db, phd, as_user):
    admin = await _user(db, "cro_admin", UserRole.admin)
    reviewer_c = await _user(db, "cro_college_c", UserRole.college, name="資訊承辦")
    reviewer_e = await _user(db, "cro_college_e", UserRole.college, name="電機承辦")
    db.add(Academy(code="C", name="資訊學院（表）"))
    await db.commit()

    # A: applicants only ⇒ 尚未建立排名
    await _application(db, phd, await _user(db, "cro_a1", UserRole.student), "A")
    # B: an untouched draft ⇒ 草稿（未匯入）
    await _application(db, phd, await _user(db, "cro_b1", UserRole.student), "B")
    await _ranking(db, phd, "B", reviewer_c)
    # C: two drafts, one imported twice ⇒ 草稿已匯入, latest import wins
    await _application(db, phd, await _user(db, "cro_c1", UserRole.student), "C")
    await _application(db, phd, await _user(db, "cro_c2", UserRole.student), "C")
    draft_one = await _ranking(db, phd, "C", reviewer_c, name="草稿一")
    draft_two = await _ranking(db, phd, "C", reviewer_c, name="草稿二")
    await _import_log(db, draft_two, reviewer_e, datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc))
    await _import_log(db, draft_two, reviewer_c, datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc))
    # E: finalized ⇒ 已確認
    await _application(db, phd, await _user(db, "cro_e1", UserRole.student), "E")
    locked = await _ranking(db, phd, "E", reviewer_e, is_finalized=True)
    await _import_log(db, locked, reviewer_e, datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc))

    resp = await as_user(admin).get(URL.format(code=phd.code), params={"academic_year": 115})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["scholarship"]["code"] == "cro_phd"
    colleges = _by_college(body)
    assert list(colleges) == ["A", "B", "C", "E"]

    assert colleges["A"]["status"] == "not_created"
    assert colleges["A"]["applicant_count"] == 1
    assert colleges["A"]["rankings"] == []
    assert colleges["A"]["last_import_at"] is None

    assert colleges["B"]["status"] == "draft"
    assert colleges["B"]["last_import_at"] is None

    assert colleges["C"]["status"] == "draft_imported"
    assert colleges["C"]["college_name"] == "資訊學院（表）"
    assert colleges["C"]["applicant_count"] == 2
    assert colleges["C"]["last_import_by"] == "資訊承辦"
    assert colleges["C"]["last_import_at"].startswith("2026-11-03")
    rankings_c = {row["id"]: row for row in colleges["C"]["rankings"]}
    assert rankings_c[draft_one.id]["last_import_at"] is None
    assert rankings_c[draft_two.id]["last_import_by"] == "資訊承辦"
    assert rankings_c[draft_two.id]["created_by"] == "資訊承辦"

    assert colleges["E"]["status"] == "finalized"
    assert colleges["E"]["rankings"][0]["is_finalized"] is True
    assert colleges["E"]["rankings"][0]["finalized_by"] == "電機承辦"
    assert colleges["E"]["last_import_by"] == "電機承辦"

    assert body["data"]["summary"] == {
        "not_created": 1,
        "draft": 1,
        "draft_imported": 1,
        "finalized": 1,
        "total": 4,
    }


@pytest.mark.asyncio
async def test_only_the_selected_period_and_rankable_applications_count(db, phd, as_user):
    admin = await _user(db, "cro_admin", UserRole.admin)
    reviewer = await _user(db, "cro_college", UserRole.college)
    await _application(db, phd, await _user(db, "cro_s1", UserRole.student), "C")
    await _application(db, phd, await _user(db, "cro_s2", UserRole.student), "E", status="draft")
    await _application(db, phd, await _user(db, "cro_s3", UserRole.student), "I", year=114)
    await _application(db, phd, await _user(db, "cro_s4", UserRole.student), "S", semester="first")
    await _ranking(db, phd, "I", reviewer, year=114, is_finalized=True)
    await _ranking(db, phd, "S", reviewer, semester="first", is_finalized=True)

    yearly = await as_user(admin).get(URL.format(code=phd.code), params={"academic_year": 115})
    first = await as_user(admin).get(URL.format(code=phd.code), params={"academic_year": 115, "semester": "first"})

    assert list(_by_college(yearly.json())) == ["C"]
    assert _by_college(yearly.json())["C"]["status"] == "not_created"
    first_colleges = _by_college(first.json())
    assert first_colleges["S"]["status"] == "finalized"
    assert first_colleges["S"]["applicant_count"] == 1


@pytest.mark.asyncio
async def test_college_is_only_as_complete_as_its_least_complete_sub_type(db, phd, as_user):
    admin = await _user(db, "cro_admin", UserRole.admin)
    reviewer = await _user(db, "cro_college", UserRole.college)
    await _ranking(db, phd, "C", reviewer, sub_type_code="nstc", is_finalized=True)
    await _ranking(db, phd, "C", reviewer, sub_type_code="moe_1w")
    await _ranking(db, phd, None, admin, sub_type_code="nstc")

    resp = await as_user(admin).get(URL.format(code=str(phd.id)), params={"academic_year": 115})

    colleges = _by_college(resp.json())
    # A ranking with no eligible applicants still gets its row.
    assert colleges["C"]["status"] == "draft"
    assert colleges["C"]["applicant_count"] == 0
    assert len(colleges["C"]["rankings"]) == 2
    assert colleges[""]["college_name"] == "全校（管理員建立）"
    # The admin global ranking is listed but is not a college that owes a ranking.
    assert resp.json()["data"]["summary"]["total"] == 1


@pytest.mark.asyncio
async def test_applications_without_a_college_are_reported_separately(db, phd, as_user):
    admin = await _user(db, "cro_admin", UserRole.admin)
    await _application(db, phd, await _user(db, "cro_s1", UserRole.student), "C")
    await _application(db, phd, await _user(db, "cro_s2", UserRole.student), "")

    resp = await as_user(admin).get(URL.format(code=phd.code), params={"academic_year": 115})

    assert list(_by_college(resp.json())) == ["C"]
    assert resp.json()["data"]["unassigned_applicant_count"] == 1


@pytest.mark.asyncio
async def test_requires_admin_and_a_known_scholarship(db, phd, as_user):
    college = await _user(db, "cro_college", UserRole.college)
    admin = await _user(db, "cro_admin", UserRole.admin)

    forbidden = await as_user(college).get(URL.format(code=phd.code), params={"academic_year": 115})
    missing = await as_user(admin).get(URL.format(code="no_such_type"), params={"academic_year": 115})
    bad_semester = await as_user(admin).get(
        URL.format(code=phd.code), params={"academic_year": 115, "semester": "summer"}
    )

    assert forbidden.status_code == 403
    assert missing.status_code == 404
    assert bad_semester.status_code == 422
