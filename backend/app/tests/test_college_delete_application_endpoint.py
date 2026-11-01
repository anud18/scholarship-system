"""學院承辦人刪除申請 — DELETE /api/v1/admin/applications/{id} opened to 學院.

A college user may hard-delete an application of THEIR OWN college, under the
same 分發-stage policy and audit trail as an admin. Out-of-scope rows return
404 (not 403), matching ``college_user_may_access`` everywhere else, so the
endpoint cannot be used to enumerate other colleges' application ids.

Authentication is simulated by overriding ``get_current_user`` with real
DB-backed User rows so the real role gate and scope logic run unmodified.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.college_review_service import CollegeReviewService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

DELETE_URL = "/api/v1/admin/applications/{id}"
OWN_COLLEGE = "C"
OTHER_COLLEGE = "E"


@pytest_asyncio.fixture
async def login():
    from app.core.security import get_current_user
    from app.main import app

    def _login(user: User) -> None:
        async def _override():
            return user

        app.dependency_overrides[get_current_user] = _override

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


def _employee(nycu_id: str, role: UserRole, college_code=None) -> User:
    return User(
        nycu_id=nycu_id,
        name=nycu_id,
        email=f"{nycu_id}@test.edu",
        user_type=UserType.employee,
        role=role,
        college_code=college_code,
    )


@pytest_asyncio.fixture
async def actors(db):
    users = {
        "college_own": _employee("del_college_c", UserRole.college, OWN_COLLEGE),
        "college_other": _employee("del_college_e", UserRole.college, OTHER_COLLEGE),
        "college_unbound": _employee("del_college_none", UserRole.college, None),
        "professor": _employee("del_prof", UserRole.professor),
        "admin": _employee("del_admin", UserRole.admin),
    }
    student = User(
        nycu_id="del_stu001",
        name="刪除測試學生",
        email="del_stu001@test.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add_all([*users.values(), student])
    stype = ScholarshipType(code="del_test", name="Delete Test Scholarship")
    db.add(stype)
    await db.commit()
    return {**users, "student": student, "stype": stype}


async def _make_application(db, actors, suffix: str, **overrides) -> Application:
    fields = {
        "app_id": f"APP-DEL-{suffix}",
        "user_id": actors["student"].id,
        "scholarship_type_id": actors["stype"].id,
        "sub_type_selection_mode": SubTypeSelectionMode.single,
        "status": ApplicationStatus.submitted.value,
        "academic_year": 114,
        "student_data": {"std_academyno": OWN_COLLEGE, "std_cname": "刪除測試學生", "std_stdcode": "del_stu001"},
        **overrides,
    }
    app_row = Application(**fields)
    db.add(app_row)
    await db.commit()
    await db.refresh(app_row)
    return app_row


async def _exists(db, app_id: int) -> bool:
    db.expire_all()
    return (await db.execute(select(Application.id).where(Application.id == app_id))).scalar_one_or_none() is not None


async def _delete(client, app_id: int, reason: str = "學生放棄申請"):
    return await client.request("DELETE", DELETE_URL.format(id=app_id), json={"reason": reason})


async def test_college_user_deletes_own_college_application(client, db, actors, login):
    app_row = await _make_application(db, actors, "OWN")
    login(actors["college_own"])

    response = await _delete(client, app_row.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["app_id"] == "APP-DEL-OWN"
    assert not await _exists(db, app_row.id)


async def test_college_user_cannot_delete_other_college_application(client, db, actors, login):
    app_row = await _make_application(db, actors, "OTHER")
    login(actors["college_other"])

    response = await _delete(client, app_row.id)

    # 404, not 403: an out-of-scope id must look exactly like a nonexistent one.
    assert response.status_code == 404
    assert await _exists(db, app_row.id)


async def test_unbound_college_user_cannot_delete(client, db, actors, login):
    app_row = await _make_application(db, actors, "UNBOUND")
    login(actors["college_unbound"])

    response = await _delete(client, app_row.id)

    assert response.status_code == 404
    assert await _exists(db, app_row.id)


async def test_college_user_cannot_delete_snapshotless_application(client, db, actors, login):
    app_row = await _make_application(db, actors, "NOSNAP", student_data=None)
    login(actors["college_own"])

    response = await _delete(client, app_row.id)

    assert response.status_code == 404
    assert await _exists(db, app_row.id)


async def test_college_user_blocked_once_application_entered_distribution(client, db, actors, login):
    app_row = await _make_application(db, actors, "DIST", quota_allocation_status="allocated")
    login(actors["college_own"])

    response = await _delete(client, app_row.id)

    assert response.status_code == 400
    assert await _exists(db, app_row.id)


async def test_professor_still_cannot_use_delete_endpoint(client, db, actors, login):
    app_row = await _make_application(db, actors, "PROF")
    login(actors["professor"])

    response = await _delete(client, app_row.id)

    assert response.status_code == 403
    assert await _exists(db, app_row.id)


async def test_admin_still_deletes_any_college_application(client, db, actors, login):
    app_row = await _make_application(db, actors, "ADMIN", student_data={"std_academyno": OTHER_COLLEGE})
    login(actors["admin"])

    response = await _delete(client, app_row.id)

    assert response.status_code == 200, response.text
    assert not await _exists(db, app_row.id)


async def test_college_review_list_carries_is_deletable(db, actors):
    deletable = await _make_application(db, actors, "LIST-OK")
    distributed = await _make_application(db, actors, "LIST-DIST", quota_allocation_status="allocated")

    rows = await CollegeReviewService(db).get_applications_for_review(college_code=OWN_COLLEGE)

    flags = {row["id"]: row["is_deletable"] for row in rows}
    assert flags == {deletable.id: True, distributed.id: False}
