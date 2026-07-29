"""
HTTP-layer tests for the professor-student relationship endpoints
(app/api/v1/endpoints/professor_student.py).

Focus: authorization boundaries (GET = professor/admin/super_admin,
mutations = admin-only), professor self-scoping on GET (a professor may only
query their own relationships), input validation, not-found handling, and the
{success, message, data} response envelope.

Auth is resolved via `app.core.security` role dependencies (require_roles /
require_admin), which depend on `app.core.security.get_current_user`; the login
fixture overrides that.
"""

import pytest
import pytest_asyncio

from app.models.professor_student import ProfessorStudentRelationship
from app.models.user import User, UserRole, UserType

PREFIX = "/api/v1/professor-student"


@pytest_asyncio.fixture
async def login():
    """Authenticate the test client as a given User by overriding get_current_user."""
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
async def ps_users(db):
    users = {
        "professor": User(
            nycu_id="ps_prof",
            name="PS Professor",
            email="ps_prof@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
        "other_professor": User(
            nycu_id="ps_prof2",
            name="PS Other Professor",
            email="ps_prof2@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
        "student": User(
            nycu_id="ps_student",
            name="PS Student",
            email="ps_student@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
        "admin": User(
            nycu_id="ps_admin",
            name="PS Admin",
            email="ps_admin@test.edu",
            user_type=UserType.employee,
            role=UserRole.admin,
        ),
    }
    for user in users.values():
        db.add(user)
    await db.commit()
    for user in users.values():
        await db.refresh(user)
    return users


@pytest_asyncio.fixture
async def relationship(db, ps_users) -> ProfessorStudentRelationship:
    """An advisor relationship owned by `professor` for `student`."""
    rel = ProfessorStudentRelationship(
        professor_id=ps_users["professor"].id,
        student_id=ps_users["student"].id,
        relationship_type="advisor",
        is_active=True,
        created_by=ps_users["admin"].id,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return rel


@pytest.mark.api
class TestProfessorStudentAuthorization:
    """Role gating: GET open to professor/admin, mutations admin-only."""

    async def test_list_unauthenticated_401(self, client):
        response = await client.get(PREFIX)
        assert response.status_code == 401

    async def test_list_student_forbidden(self, client, login, ps_users):
        # require_roles(professor, admin, super_admin) excludes students.
        login(ps_users["student"])
        response = await client.get(PREFIX)
        assert response.status_code == 403

    async def test_create_unauthenticated_401(self, client, ps_users):
        response = await client.post(
            PREFIX,
            params={
                "professor_id": ps_users["professor"].id,
                "student_id": ps_users["student"].id,
                "relationship_type": "advisor",
            },
        )
        assert response.status_code == 401

    async def test_create_professor_forbidden(self, client, login, ps_users):
        # POST is require_admin; a professor may not create relationships.
        login(ps_users["professor"])
        response = await client.post(
            PREFIX,
            params={
                "professor_id": ps_users["professor"].id,
                "student_id": ps_users["student"].id,
                "relationship_type": "advisor",
            },
        )
        assert response.status_code == 403

    async def test_update_professor_forbidden(self, client, login, ps_users, relationship):
        login(ps_users["professor"])
        response = await client.put(f"{PREFIX}/{relationship.id}", params={"status": "inactive"})
        assert response.status_code == 403

    async def test_delete_student_forbidden(self, client, login, ps_users, relationship):
        login(ps_users["student"])
        response = await client.delete(f"{PREFIX}/{relationship.id}")
        assert response.status_code == 403


@pytest.mark.api
class TestProfessorStudentScoping:
    """A professor may only query their own relationships on GET."""

    async def test_professor_query_other_professor_forbidden(self, client, login, ps_users, relationship):
        # SECURITY: a professor passing professor_id != self is rejected before
        # the query is built (prevents reading other professors' rosters).
        login(ps_users["professor"])
        response = await client.get(PREFIX, params={"professor_id": ps_users["other_professor"].id})
        assert response.status_code == 403

    async def test_professor_query_own_id_allowed(self, client, login, ps_users, relationship):
        login(ps_users["professor"])
        response = await client.get(PREFIX, params={"professor_id": ps_users["professor"].id})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 1
        assert body["data"][0]["professor_id"] == ps_users["professor"].id

    async def test_professor_no_filter_sees_only_own(self, client, login, ps_users, relationship):
        # With no professor_id filter, a professor is implicitly scoped to self.
        login(ps_users["professor"])
        response = await client.get(PREFIX)
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(rel["professor_id"] == ps_users["professor"].id for rel in data)

    async def test_admin_query_any_professor_allowed(self, client, login, ps_users, relationship):
        # Admins are exempt from the self-scoping restriction.
        login(ps_users["admin"])
        response = await client.get(PREFIX, params={"professor_id": ps_users["professor"].id})
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1


@pytest.mark.api
class TestProfessorStudentValidationAndNotFound:
    """Input validation and not-found handling (admin-authenticated)."""

    async def test_create_missing_relationship_type_422(self, client, login, ps_users):
        login(ps_users["admin"])
        response = await client.post(
            PREFIX,
            params={"professor_id": ps_users["professor"].id, "student_id": ps_users["student"].id},
        )
        assert response.status_code == 422

    async def test_create_nonexistent_professor_400(self, client, login, ps_users):
        login(ps_users["admin"])
        response = await client.post(
            PREFIX,
            params={
                "professor_id": 999999,
                "student_id": ps_users["student"].id,
                "relationship_type": "advisor",
            },
        )
        assert response.status_code == 400

    async def test_update_nonexistent_404(self, client, login, ps_users):
        login(ps_users["admin"])
        response = await client.put(f"{PREFIX}/999999", params={"status": "inactive"})
        assert response.status_code == 404

    async def test_delete_nonexistent_404(self, client, login, ps_users):
        login(ps_users["admin"])
        response = await client.delete(f"{PREFIX}/999999")
        assert response.status_code == 404


@pytest.mark.api
class TestProfessorStudentEnvelopeAndFlow:
    """Happy-path envelope for the working paths (list / update / delete)."""

    async def test_admin_list_envelope(self, client, login, ps_users, relationship):
        login(ps_users["admin"])
        response = await client.get(PREFIX)
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) >= {"success", "message", "data"}
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert body["data"][0]["relationship_type"] == "advisor"
        assert body["data"][0]["status"] == "active"

    async def test_admin_update_envelope(self, client, login, ps_users, relationship):
        login(ps_users["admin"])
        response = await client.put(
            f"{PREFIX}/{relationship.id}",
            params={"status": "inactive", "notes": "ended"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "inactive"
        assert body["data"]["notes"] == "ended"

    async def test_admin_delete_envelope(self, client, login, ps_users, relationship):
        login(ps_users["admin"])
        response = await client.delete(f"{PREFIX}/{relationship.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] is None

    async def test_admin_create_valid_professor_succeeds(self, client, login, ps_users):
        # #1112 (fixed): the role check now compares UserRole enum members, so a
        # valid professor+student pair is accepted. Previously `professor.role
        # not in ["professor","admin"]` (enum vs bare string) rejected EVERY pair
        # with 400 — the create endpoint could never create a relationship.
        login(ps_users["admin"])
        response = await client.post(
            PREFIX,
            params={
                "professor_id": ps_users["professor"].id,
                "student_id": ps_users["student"].id,
                "relationship_type": "advisor",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True


@pytest.mark.api
class TestProfessorStudentNoPaginationCap:
    """size omitted → ALL relationships returned (no implicit 20-row cap);
    explicit page/size still paginates deterministically."""

    async def _seed_many(self, db, ps_users, count=25):
        # Distinct relationship_type per row to sidestep the
        # (professor, student, type) uniqueness rule.
        for i in range(count):
            db.add(
                ProfessorStudentRelationship(
                    professor_id=ps_users["professor"].id,
                    student_id=ps_users["student"].id,
                    relationship_type=f"nocap_t{i:02d}",
                    is_active=True,
                    created_by=ps_users["admin"].id,
                )
            )
        await db.commit()

    async def test_default_returns_all_rows_beyond_old_cap(self, client, login, db, ps_users):
        # 25 rows > the old default page size of 20.
        await self._seed_many(db, ps_users, count=25)
        login(ps_users["professor"])
        response = await client.get(PREFIX)
        assert response.status_code == 200
        assert len(response.json()["data"]) == 25

    async def test_explicit_size_still_paginates(self, client, login, db, ps_users):
        await self._seed_many(db, ps_users, count=25)
        login(ps_users["professor"])

        page1 = await client.get(PREFIX, params={"page": 1, "size": 10})
        assert page1.status_code == 200
        page1_ids = [rel["id"] for rel in page1.json()["data"]]
        assert len(page1_ids) == 10

        page3 = await client.get(PREFIX, params={"page": 3, "size": 10})
        assert page3.status_code == 200
        page3_ids = [rel["id"] for rel in page3.json()["data"]]
        assert len(page3_ids) == 5

        # Ordered by id → pages are disjoint and deterministic.
        assert not set(page1_ids) & set(page3_ids)
        assert max(page1_ids) < min(page3_ids)
