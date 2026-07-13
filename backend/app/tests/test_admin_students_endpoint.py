"""Integration tests for GET /api/v1/admin/students applied-scholarships data + filters.

Covers the admin student list additions:
  - each item carries applied_scholarships (distinct scholarship CONFIGURATIONS,
    獎學金配置, with per-configuration application counts, drafts / deleted excluded)
  - scholarship_type_id query filter (students who applied for that type)
  - has_application query filter (true = applied for anything, false = nothing)

Auth pattern follows test_admin_student_history_endpoint.py — overrides
require_admin, uses the conftest `client` whose get_db override shares the
in-memory SQLite session.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType


@pytest_asyncio.fixture
async def authed_admin_client(client, admin_user):
    """AsyncClient with require_admin overridden to return the mock admin_user."""
    from app.core.security import require_admin
    from app.main import app

    async def override_require_admin():
        return admin_user

    app.dependency_overrides[require_admin] = override_require_admin
    yield client
    app.dependency_overrides.pop(require_admin, None)


@pytest_asyncio.fixture
async def seeded_students(client):
    """Three students + two scholarship types + applications in every relevant state.

    - applicant_multi: 2 qualifying applications for PHD (submitted + approved)
      plus a draft for NSTC (must NOT count) and a soft-deleted PHD row
      (must NOT count).
    - applicant_single: 1 qualifying application for NSTC.
    - non_applicant: no applications at all.
    """
    from app.db.deps import get_db
    from app.main import app

    db_gen = app.dependency_overrides[get_db]()
    db = await db_gen.__anext__()

    students = {}
    for key, nycu_id, name in [
        ("applicant_multi", "stu001", "多申請學生"),
        ("applicant_single", "stu002", "單申請學生"),
        ("non_applicant", "stu003", "未申請學生"),
    ]:
        user = User(
            nycu_id=nycu_id,
            name=name,
            email=f"{nycu_id}@nycu.edu.tw",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(user)
        students[key] = user
    await db.commit()
    for user in students.values():
        await db.refresh(user)

    phd = ScholarshipType(code="phd_test", name="博士生獎學金", description="Test")
    nstc = ScholarshipType(code="nstc_test", name="國科會獎學金", description="Test")
    db.add_all([phd, nstc])
    await db.commit()
    await db.refresh(phd)
    await db.refresh(nstc)

    # One configuration (獎學金配置) per type — the badge column groups by config.
    phd_cfg = ScholarshipConfiguration(
        scholarship_type_id=phd.id,
        academic_year=113,
        config_name="博士生獎學金 113學年",
        config_code="phd_113_test",
        amount=30000,
    )
    nstc_cfg = ScholarshipConfiguration(
        scholarship_type_id=nstc.id,
        academic_year=113,
        semester="first",
        config_name="國科會獎學金 113學年第一學期",
        config_code="nstc_113_1_test",
        amount=20000,
    )
    db.add_all([phd_cfg, nstc_cfg])
    await db.commit()
    await db.refresh(phd_cfg)
    await db.refresh(nstc_cfg)

    now = datetime.now(timezone.utc)
    applications = [
        # applicant_multi: two qualifying applications for the SAME phd config
        # → one badge for that config with application_count 2
        Application(
            app_id="APP-113-1-00001",
            user_id=students["applicant_multi"].id,
            scholarship_type_id=phd.id,
            scholarship_configuration_id=phd_cfg.id,
            status=ApplicationStatus.submitted.value,
            academic_year=113,
            semester="first",
            sub_type_selection_mode="single",
        ),
        Application(
            app_id="APP-113-2-00001",
            user_id=students["applicant_multi"].id,
            scholarship_type_id=phd.id,
            scholarship_configuration_id=phd_cfg.id,
            status=ApplicationStatus.approved.value,
            academic_year=113,
            semester="second",
            sub_type_selection_mode="single",
        ),
        # draft: must NOT count as applied
        Application(
            app_id="APP-113-1-00002",
            user_id=students["applicant_multi"].id,
            scholarship_type_id=nstc.id,
            scholarship_configuration_id=nstc_cfg.id,
            status=ApplicationStatus.draft.value,
            academic_year=113,
            semester="first",
            sub_type_selection_mode="single",
        ),
        # soft-deleted: must NOT count as applied
        Application(
            app_id="APP-112-1-00001",
            user_id=students["applicant_multi"].id,
            scholarship_type_id=phd.id,
            scholarship_configuration_id=phd_cfg.id,
            status=ApplicationStatus.rejected.value,
            academic_year=112,
            semester="first",
            sub_type_selection_mode="single",
            deleted_at=now,
        ),
        # applicant_single: one qualifying NSTC application
        Application(
            app_id="APP-113-1-00003",
            user_id=students["applicant_single"].id,
            scholarship_type_id=nstc.id,
            scholarship_configuration_id=nstc_cfg.id,
            status=ApplicationStatus.under_review.value,
            academic_year=113,
            semester="first",
            sub_type_selection_mode="single",
        ),
    ]
    db.add_all(applications)
    await db.commit()

    return {"students": students, "phd": phd, "nstc": nstc, "phd_cfg": phd_cfg, "nstc_cfg": nstc_cfg}


def _items_by_nycu_id(body: dict) -> dict:
    return {item["nycu_id"]: item for item in body["data"]["items"]}


@pytest.mark.asyncio
async def test_list_includes_applied_scholarships_aggregation(authed_admin_client, seeded_students):
    """Every item has applied_scholarships; counts aggregate per configuration
    and exclude drafts and soft-deleted applications."""
    response = await authed_admin_client.get("/api/v1/admin/students")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    items = _items_by_nycu_id(body)
    assert set(items.keys()) == {"stu001", "stu002", "stu003"}

    phd_cfg = seeded_students["phd_cfg"]
    nstc_cfg = seeded_students["nstc_cfg"]

    # applicant_multi: only the PHD config counts (draft NSTC + soft-deleted PHD
    # excluded); both qualifying PHD applications aggregate into one config entry
    # carrying the config name (獎學金配置), with count 2
    multi = items["stu001"]["applied_scholarships"]
    assert multi == [
        {
            "scholarship_configuration_id": phd_cfg.id,
            "config_code": "phd_113_test",
            "name": "博士生獎學金 113學年",
            "application_count": 2,
        }
    ]

    single = items["stu002"]["applied_scholarships"]
    assert single == [
        {
            "scholarship_configuration_id": nstc_cfg.id,
            "config_code": "nstc_113_1_test",
            "name": "國科會獎學金 113學年第一學期",
            "application_count": 1,
        }
    ]

    assert items["stu003"]["applied_scholarships"] == []


@pytest.mark.asyncio
async def test_filter_by_scholarship_type_id(authed_admin_client, seeded_students):
    """scholarship_type_id returns only students with a qualifying application
    for that type — a draft does not qualify."""
    phd = seeded_students["phd"]
    nstc = seeded_students["nstc"]

    response = await authed_admin_client.get("/api/v1/admin/students", params={"scholarship_type_id": phd.id})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 1
    assert set(_items_by_nycu_id(body).keys()) == {"stu001"}

    # stu001's NSTC application is a draft → only stu002 matches NSTC
    response = await authed_admin_client.get("/api/v1/admin/students", params={"scholarship_type_id": nstc.id})
    body = response.json()
    assert body["data"]["total"] == 1
    assert set(_items_by_nycu_id(body).keys()) == {"stu002"}


@pytest.mark.asyncio
async def test_filter_has_application_true(authed_admin_client, seeded_students):
    response = await authed_admin_client.get("/api/v1/admin/students", params={"has_application": "true"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 2
    assert set(_items_by_nycu_id(body).keys()) == {"stu001", "stu002"}


@pytest.mark.asyncio
async def test_filter_has_application_false(authed_admin_client, seeded_students):
    """A student whose only applications are drafts/soft-deleted has not applied."""
    response = await authed_admin_client.get("/api/v1/admin/students", params={"has_application": "false"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 1
    assert set(_items_by_nycu_id(body).keys()) == {"stu003"}


@pytest.mark.asyncio
async def test_scholarship_filter_combines_with_status_filter(authed_admin_client, seeded_students):
    """Scholarship filters AND with the existing filters (nonexistent type → empty)."""
    response = await authed_admin_client.get("/api/v1/admin/students", params={"scholarship_type_id": 999999})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 0
    assert body["data"]["items"] == []


@pytest.mark.asyncio
async def test_student_detail_includes_applied_scholarships(authed_admin_client, seeded_students):
    """GET /{user_id} carries the same applied_scholarships shape."""
    user_id = seeded_students["students"]["applicant_multi"].id
    response = await authed_admin_client.get(f"/api/v1/admin/students/{user_id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["applied_scholarships"]) == 1
    assert data["applied_scholarships"][0]["config_code"] == "phd_113_test"
    assert data["applied_scholarships"][0]["name"] == "博士生獎學金 113學年"
    assert data["applied_scholarships"][0]["application_count"] == 2


@pytest.mark.asyncio
async def test_unauthenticated_returns_401_or_403(client):
    response = await client.get("/api/v1/admin/students")
    assert response.status_code in (401, 403)
