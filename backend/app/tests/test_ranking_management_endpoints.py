"""
HTTP-layer tests for the college ranking endpoints
(app/api/v1/endpoints/college_review/ranking_management.py).

Focus (issue #1081 follow-up): cross-college authorization scoping,
finalized-state guards, input validation, and the {success, message, data}
response envelope.

Authentication is simulated by overriding `get_current_user` with real
DB-backed User rows so the actual require_college / require_scholarship_manager
role gates and assert_can_manage_ranking scoping run unmodified.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType

RANKINGS_URL = "/api/v1/college-review/rankings"

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest_asyncio.fixture
async def login():
    """Authenticate the test client as a given User via dependency override."""
    from app.core.security import get_current_user
    from app.main import app

    def _login(user: User) -> None:
        async def _override():
            return user

        app.dependency_overrides[get_current_user] = _override

    yield _login
    from app.core.security import get_current_user as _gcu
    from app.main import app as _app

    _app.dependency_overrides.pop(_gcu, None)


@pytest_asyncio.fixture
async def rank_users(db):
    users = {
        "college_eng": User(
            nycu_id="rank_eng1",
            name="ENG Reviewer",
            email="rank_eng1@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="ENG",
        ),
        "college_eng2": User(
            nycu_id="rank_eng2",
            name="ENG Reviewer Two",
            email="rank_eng2@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="ENG",
        ),
        "college_sci": User(
            nycu_id="rank_sci1",
            name="SCI Reviewer",
            email="rank_sci1@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="SCI",
        ),
        "admin": User(
            nycu_id="rank_admin",
            name="Rank Admin",
            email="rank_admin@test.edu",
            user_type=UserType.employee,
            role=UserRole.admin,
        ),
        "student": User(
            nycu_id="rank_student",
            name="Rank Student",
            email="rank_student@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
        "professor": User(
            nycu_id="rank_prof",
            name="Rank Professor",
            email="rank_prof@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
    }
    for user in users.values():
        db.add(user)
    await db.commit()
    for user in users.values():
        await db.refresh(user)
    return users


@pytest_asyncio.fixture
async def rank_scholarship(db) -> ScholarshipType:
    scholarship = ScholarshipType(
        code="rank_test_scholarship",
        name="Ranking Test Scholarship",
        description="Scholarship used by ranking endpoint tests",
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


@pytest_asyncio.fixture
async def ranking_eng(db, rank_users, rank_scholarship) -> CollegeRanking:
    ranking = CollegeRanking(
        scholarship_type_id=rank_scholarship.id,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        college_code="ENG",
        ranking_name="ENG nstc ranking",
        total_applications=0,
        created_by=rank_users["college_eng"].id,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)
    return ranking


@pytest_asyncio.fixture
async def ranking_sci(db, rank_users, rank_scholarship) -> CollegeRanking:
    ranking = CollegeRanking(
        scholarship_type_id=rank_scholarship.id,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        college_code="SCI",
        ranking_name="SCI nstc ranking",
        total_applications=0,
        created_by=rank_users["college_sci"].id,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)
    return ranking


@pytest_asyncio.fixture
async def ranking_eng_items(db, rank_users, rank_scholarship, ranking_eng):
    """Two ranked applications (student IDs S001/S002) inside the ENG ranking."""
    students = []
    for idx in (1, 2):
        student = User(
            nycu_id=f"rank_stu{idx}",
            name=f"Ranked Student {idx}",
            email=f"rank_stu{idx}@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(student)
        students.append(student)
    await db.commit()

    items = []
    for idx, student in enumerate(students, start=1):
        await db.refresh(student)
        application = Application(
            app_id=f"APP-114-1-0100{idx}",
            user_id=student.id,
            scholarship_type_id=rank_scholarship.id,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status=ApplicationStatus.approved.value,
            academic_year=114,
            semester="first",
            scholarship_subtype_list=["nstc"],
            student_data={"std_stdcode": f"S00{idx}", "std_cname": f"Ranked Student {idx}", "std_academyno": "ENG"},
            submitted_form_data={},
            agree_terms=True,
        )
        db.add(application)
        await db.commit()
        await db.refresh(application)

        item = CollegeRankingItem(
            ranking_id=ranking_eng.id,
            application_id=application.id,
            rank_position=idx,
            status="ranked",
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        items.append(item)

    ranking_eng.total_applications = len(items)
    await db.commit()
    return items


@pytest.mark.api
class TestRankingAuthorization:
    """Role gates and cross-college scoping."""

    async def test_list_rankings_unauthenticated_401(self, client):
        response = await client.get(RANKINGS_URL)
        assert response.status_code == 401
        assert response.json()["success"] is False

    async def test_create_ranking_unauthenticated_401(self, client):
        response = await client.post(RANKINGS_URL, json={})
        assert response.status_code == 401

    async def test_student_list_rankings_403(self, client, login, rank_users):
        login(rank_users["student"])
        response = await client.get(RANKINGS_URL)
        assert response.status_code == 403

    async def test_professor_list_rankings_403(self, client, login, rank_users):
        login(rank_users["professor"])
        response = await client.get(RANKINGS_URL)
        assert response.status_code == 403

    async def test_admin_list_rankings_403(self, client, login, rank_users):
        # Pins a behavior quirk: require_college accepts ONLY role=college, so
        # admins are rejected here even though the handler contains an
        # admin-sees-all branch (that branch is unreachable via HTTP).
        login(rank_users["admin"])
        response = await client.get(RANKINGS_URL)
        assert response.status_code == 403

    async def test_student_create_ranking_403(self, client, login, rank_users, rank_scholarship):
        login(rank_users["student"])
        payload = {
            "scholarship_type_id": rank_scholarship.id,
            "sub_type_code": "nstc",
            "academic_year": 114,
            "semester": "first",
        }
        response = await client.post(RANKINGS_URL, json=payload)
        assert response.status_code == 403

    async def test_college_list_scoped_to_own_college(self, client, login, rank_users, ranking_eng, ranking_sci):
        login(rank_users["college_eng"])
        response = await client.get(RANKINGS_URL)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        ids = [r["id"] for r in body["data"]]
        assert ranking_eng.id in ids
        assert ranking_sci.id not in ids

    async def test_same_college_second_reviewer_sees_ranking(self, client, login, rank_users, ranking_eng):
        # Rankings are college-owned (issue #1034): every reviewer of the
        # owning college shares the ranking, not only the creator.
        login(rank_users["college_eng2"])
        response = await client.get(RANKINGS_URL)
        assert response.status_code == 200
        assert ranking_eng.id in [r["id"] for r in response.json()["data"]]

    async def test_cross_college_get_detail_403(self, client, login, rank_users, ranking_sci):
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_sci.id}")
        assert response.status_code == 403

    async def test_cross_college_update_403(self, client, login, rank_users, ranking_sci):
        login(rank_users["college_eng"])
        response = await client.put(f"{RANKINGS_URL}/{ranking_sci.id}", json={"ranking_name": "hijacked"})
        assert response.status_code == 403

    async def test_cross_college_order_update_403(self, client, login, rank_users, ranking_sci):
        login(rank_users["college_eng"])
        response = await client.put(f"{RANKINGS_URL}/{ranking_sci.id}/order", json=[{"item_id": 1, "position": 1}])
        assert response.status_code == 403

    async def test_cross_college_finalize_403(self, client, login, rank_users, ranking_sci):
        login(rank_users["college_eng"])
        response = await client.post(f"{RANKINGS_URL}/{ranking_sci.id}/finalize")
        assert response.status_code == 403

    async def test_cross_college_unfinalize_403(self, client, login, db, rank_users, ranking_sci):
        ranking_sci.is_finalized = True
        ranking_sci.ranking_status = "finalized"
        await db.commit()

        login(rank_users["college_eng"])
        response = await client.post(f"{RANKINGS_URL}/{ranking_sci.id}/unfinalize")
        assert response.status_code == 403

    async def test_cross_college_delete_403(self, client, login, db, rank_users, ranking_sci):
        login(rank_users["college_eng"])
        response = await client.delete(f"{RANKINGS_URL}/{ranking_sci.id}")
        assert response.status_code == 403

        # Row must still exist
        row = (await db.execute(select(CollegeRanking).where(CollegeRanking.id == ranking_sci.id))).scalar_one()
        assert row is not None

    async def test_cross_college_import_excel_403(self, client, login, rank_users, ranking_sci):
        login(rank_users["college_eng"])
        payload = [{"student_id": "S001", "student_name": "X", "rank_position": 1}]
        response = await client.post(f"{RANKINGS_URL}/{ranking_sci.id}/import-excel", json=payload)
        assert response.status_code == 403

    async def test_cross_college_supplementary_import_403(self, client, login, rank_users, ranking_sci):
        login(rank_users["college_eng"])
        response = await client.post(
            f"{RANKINGS_URL}/{ranking_sci.id}/supplementary-import",
            files={"file": ("dummy.xlsx", b"PK\x03\x04dummy", XLSX_MIME)},
        )
        assert response.status_code == 403

    async def test_supplementary_import_flag_closed_403(self, client, login, rank_users, ranking_eng):
        # Own college, but no ScholarshipConfiguration opened the feature.
        login(rank_users["college_eng"])
        response = await client.post(
            f"{RANKINGS_URL}/{ranking_eng.id}/supplementary-import",
            files={"file": ("dummy.xlsx", b"PK\x03\x04dummy", XLSX_MIME)},
        )
        assert response.status_code == 403
        assert "補充匯入" in response.json()["message"]

    async def test_student_export_excel_403(self, client, login, rank_users, ranking_eng):
        login(rank_users["student"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_eng.id}/export-excel")
        assert response.status_code == 403

    async def test_cross_college_export_excel_403(self, client, login, rank_users, ranking_sci):
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_sci.id}/export-excel")
        assert response.status_code == 403

    async def test_export_excel_requires_scholarship_permission(self, client, login, rank_users, ranking_eng):
        # Own-college reviewer WITHOUT an AdminScholarship grant for this
        # scholarship type is rejected by the explicit permission check.
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_eng.id}/export-excel")
        assert response.status_code == 403

    async def test_create_ranking_blocked_after_deadline(self, client, login, db, rank_users, rank_scholarship):
        # College-review deadline in the past blocks ranking creation for
        # college users (#63); admins bypass (not exercised here).
        from datetime import datetime, timedelta, timezone

        config = ScholarshipConfiguration(
            scholarship_type_id=rank_scholarship.id,
            academic_year=114,
            semester=Semester.first,
            config_name="rank test config",
            config_code="rank_test_cfg_114_1",
            amount=10000,
            college_review_end=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add(config)
        await db.commit()

        login(rank_users["college_eng"])
        payload = {
            "scholarship_type_id": rank_scholarship.id,
            "sub_type_code": "nstc",
            "academic_year": 114,
            "semester": "first",
        }
        response = await client.post(RANKINGS_URL, json=payload)
        assert response.status_code == 403


@pytest.mark.api
class TestRankingValidationAndGuards:
    """404s, 409 finalized-state guards and payload validation."""

    async def test_get_detail_not_found_404(self, client, login, rank_users):
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/999999")
        assert response.status_code == 404

    async def test_update_not_found_404(self, client, login, rank_users):
        login(rank_users["college_eng"])
        response = await client.put(f"{RANKINGS_URL}/999999", json={"ranking_name": "x"})
        assert response.status_code == 404

    async def test_delete_not_found_404(self, client, login, rank_users):
        login(rank_users["college_eng"])
        response = await client.delete(f"{RANKINGS_URL}/999999")
        assert response.status_code == 404

    async def test_order_update_not_found_404(self, client, login, rank_users):
        login(rank_users["college_eng"])
        response = await client.put(f"{RANKINGS_URL}/999999/order", json=[{"item_id": 1, "position": 1}])
        assert response.status_code == 404

    async def test_update_empty_name_422(self, client, login, rank_users, ranking_eng):
        login(rank_users["college_eng"])
        response = await client.put(f"{RANKINGS_URL}/{ranking_eng.id}", json={"ranking_name": ""})
        assert response.status_code == 422

    async def test_create_ranking_missing_fields_422(self, client, login, rank_users):
        login(rank_users["college_eng"])
        response = await client.post(RANKINGS_URL, json={"sub_type_code": "nstc"})
        assert response.status_code == 422

    async def test_update_finalized_ranking_409(self, client, login, db, rank_users, ranking_eng):
        ranking_eng.is_finalized = True
        ranking_eng.ranking_status = "finalized"
        await db.commit()

        login(rank_users["college_eng"])
        response = await client.put(f"{RANKINGS_URL}/{ranking_eng.id}", json={"ranking_name": "new name"})
        assert response.status_code == 409

    async def test_delete_finalized_ranking_409(self, client, login, db, rank_users, ranking_eng):
        ranking_eng.is_finalized = True
        ranking_eng.ranking_status = "finalized"
        await db.commit()

        login(rank_users["college_eng"])
        response = await client.delete(f"{RANKINGS_URL}/{ranking_eng.id}")
        assert response.status_code == 409

    async def test_order_update_finalized_409(self, client, login, db, rank_users, ranking_eng, ranking_eng_items):
        ranking_eng.is_finalized = True
        ranking_eng.ranking_status = "finalized"
        await db.commit()

        login(rank_users["college_eng"])
        payload = [{"item_id": ranking_eng_items[0].id, "position": 1}]
        response = await client.put(f"{RANKINGS_URL}/{ranking_eng.id}/order", json=payload)
        assert response.status_code == 409

    async def test_order_update_duplicate_positions_400(
        self, client, login, rank_users, ranking_eng, ranking_eng_items
    ):
        login(rank_users["college_eng"])
        payload = [
            {"item_id": ranking_eng_items[0].id, "position": 1},
            {"item_id": ranking_eng_items[1].id, "position": 1},
        ]
        response = await client.put(f"{RANKINGS_URL}/{ranking_eng.id}/order", json=payload)
        assert response.status_code == 400

    async def test_finalize_already_finalized_409(self, client, login, db, rank_users, ranking_eng):
        ranking_eng.is_finalized = True
        ranking_eng.ranking_status = "finalized"
        await db.commit()

        login(rank_users["college_eng"])
        response = await client.post(f"{RANKINGS_URL}/{ranking_eng.id}/finalize")
        assert response.status_code == 409

    async def test_unfinalize_not_finalized_409(self, client, login, rank_users, ranking_eng):
        login(rank_users["college_eng"])
        response = await client.post(f"{RANKINGS_URL}/{ranking_eng.id}/unfinalize")
        assert response.status_code == 409

    async def test_import_excel_invalid_rank_422(self, client, login, rank_users, ranking_eng):
        login(rank_users["college_eng"])
        payload = [{"student_id": "S001", "student_name": "X", "rank_position": "X"}]
        response = await client.post(f"{RANKINGS_URL}/{ranking_eng.id}/import-excel", json=payload)
        assert response.status_code == 422

    async def test_import_excel_duplicate_student_ids_422(
        self, client, login, rank_users, ranking_eng, ranking_eng_items
    ):
        login(rank_users["college_eng"])
        payload = [
            {"student_id": "S001", "student_name": "A", "rank_position": 1},
            {"student_id": "S001", "student_name": "A", "rank_position": 2},
        ]
        response = await client.post(f"{RANKINGS_URL}/{ranking_eng.id}/import-excel", json=payload)
        assert response.status_code == 422

    async def test_import_excel_unknown_student_422(self, client, login, rank_users, ranking_eng, ranking_eng_items):
        login(rank_users["college_eng"])
        payload = [
            {"student_id": "S001", "student_name": "A", "rank_position": 1},
            {"student_id": "S002", "student_name": "B", "rank_position": 2},
            {"student_id": "S999", "student_name": "Ghost", "rank_position": 3},
        ]
        response = await client.post(f"{RANKINGS_URL}/{ranking_eng.id}/import-excel", json=payload)
        assert response.status_code == 422


@pytest.mark.api
class TestRankingFlowAndEnvelope:
    """Happy paths and the {success, message, data} envelope."""

    async def test_get_detail_owner_200_envelope(self, client, login, rank_users, ranking_eng):
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_eng.id}")
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) >= {"success", "message", "data"}
        assert body["success"] is True
        assert body["data"]["id"] == ranking_eng.id
        assert body["data"]["ranking_name"] == "ENG nstc ranking"
        assert body["data"]["items"] == []

    async def test_update_ranking_name_200(self, client, login, rank_users, ranking_eng):
        login(rank_users["college_eng"])
        response = await client.put(f"{RANKINGS_URL}/{ranking_eng.id}", json={"ranking_name": "Renamed"})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["ranking_name"] == "Renamed"

    async def test_finalize_then_unfinalize_flow(self, client, login, rank_users, ranking_eng):
        login(rank_users["college_eng"])

        finalized = await client.post(f"{RANKINGS_URL}/{ranking_eng.id}/finalize")
        assert finalized.status_code == 200
        body = finalized.json()
        assert body["success"] is True
        assert body["data"]["is_finalized"] is True
        assert body["data"]["ranking_status"] == "finalized"

        unfinalized = await client.post(f"{RANKINGS_URL}/{ranking_eng.id}/unfinalize")
        assert unfinalized.status_code == 200
        body = unfinalized.json()
        assert body["data"]["is_finalized"] is False
        assert body["data"]["ranking_status"] == "draft"

    async def test_same_college_second_reviewer_can_finalize(self, client, login, rank_users, ranking_eng):
        # College-owned rankings: any reviewer of the owning college may act.
        login(rank_users["college_eng2"])
        response = await client.post(f"{RANKINGS_URL}/{ranking_eng.id}/finalize")
        assert response.status_code == 200

    async def test_delete_ranking_200_and_gone(self, client, login, db, rank_users, ranking_eng):
        login(rank_users["college_eng"])
        response = await client.delete(f"{RANKINGS_URL}/{ranking_eng.id}")
        assert response.status_code == 200
        assert response.json()["data"]["ranking_id"] == ranking_eng.id

        row = (await db.execute(select(CollegeRanking).where(CollegeRanking.id == ranking_eng.id))).scalar_one_or_none()
        assert row is None

    async def test_import_excel_happy_path(self, client, login, db, rank_users, ranking_eng, ranking_eng_items):
        login(rank_users["college_eng"])
        payload = [
            {"student_id": "S002", "student_name": "Ranked Student 2", "rank_position": 1},
            {"student_id": "S001", "student_name": "Ranked Student 1", "rank_position": "N"},
        ]
        response = await client.post(f"{RANKINGS_URL}/{ranking_eng.id}/import-excel", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["updated_count"] == 2
        assert body["data"]["rejected_count"] == 1

        # S001 was marked "N": pushed after ranked students + college_rejected flag
        await db.refresh(ranking_eng_items[0])
        await db.refresh(ranking_eng_items[1])
        assert ranking_eng_items[1].rank_position == 1  # S002 ranked first
        assert ranking_eng_items[0].college_rejected is True
        assert ranking_eng_items[0].rank_position == 2

    async def test_order_update_happy_path(self, client, login, rank_users, ranking_eng, ranking_eng_items):
        login(rank_users["college_eng"])
        payload = [
            {"item_id": ranking_eng_items[0].id, "position": 2},
            {"item_id": ranking_eng_items[1].id, "position": 1},
        ]
        response = await client.put(f"{RANKINGS_URL}/{ranking_eng.id}/order", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_admin_export_excel_200(self, client, login, rank_users, ranking_sci):
        login(rank_users["admin"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_sci.id}/export-excel")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(XLSX_MIME)


@pytest.mark.api
class TestDistributionEndpointScoping:
    """Issue #1081 findings C/D: distribution-details and roster-status must be
    college-scoped exactly like GET /rankings/{id} (assert_can_manage_ranking)."""

    # ── Finding C: GET /rankings/{id}/distribution-details ──────────────────

    async def test_cross_college_distribution_details_403(self, client, login, rank_users, ranking_sci):
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_sci.id}/distribution-details")
        assert response.status_code == 403

    async def test_owning_college_distribution_details_200(self, client, login, rank_users, ranking_eng):
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_eng.id}/distribution-details")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["ranking_id"] == ranking_eng.id

    async def test_same_college_second_reviewer_distribution_details_200(self, client, login, rank_users, ranking_eng):
        login(rank_users["college_eng2"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_eng.id}/distribution-details")
        assert response.status_code == 200

    async def test_distribution_details_missing_ranking_404(self, client, login, rank_users):
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/999999/distribution-details")
        assert response.status_code == 404

    # ── Finding D: GET /rankings/{id}/roster-status ──────────────────────────

    async def test_cross_college_roster_status_403(self, client, login, rank_users, ranking_sci):
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_sci.id}/roster-status")
        assert response.status_code == 403

    async def test_owning_college_roster_status_200(self, client, login, rank_users, ranking_eng):
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/{ranking_eng.id}/roster-status")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["has_roster"] is False

    async def test_roster_status_missing_ranking_404(self, client, login, rank_users):
        # Previously a nonexistent ranking silently returned "no roster";
        # after the #1081 fix the ranking itself is loaded first.
        login(rank_users["college_eng"])
        response = await client.get(f"{RANKINGS_URL}/999999/roster-status")
        assert response.status_code == 404
