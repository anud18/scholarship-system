"""
HTTP-layer tests for the roster-schedule endpoints
(app/api/v1/endpoints/roster_schedules.py).

Focus: authorization boundaries (admin/super_admin only), input validation
(cron / status / required fields), not-found handling, and the
{success, message, data} response envelope.

NOTE: several roster routes call into the APScheduler-backed
`roster_scheduler` singleton (and, in production, Redis). Every handler runs
`check_user_roles(...)` and its DB lookups *before* any scheduler call, so
these tests exercise the auth / validation / 404 layer that precedes the
scheduler and deliberately avoid asserting scheduler side-effects. The
happy-path create test uses status=ACTIVE with no cron_expression, which the
handler explicitly skips adding to the scheduler.

Authentication is simulated by overriding the `get_current_user` dependency
with real DB-backed User rows so all downstream role-scoping runs unmodified.
The roster router resolves auth via `app.core.deps.get_current_user`, so the
login fixture overrides that (and the security-module variant too, for reuse).
"""

import pytest
import pytest_asyncio

from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType

PREFIX = "/api/v1/roster-schedules"


@pytest_asyncio.fixture
async def login():
    """Authenticate the test client as a given User by overriding get_current_user."""
    from app.core.deps import get_current_user as deps_gcu
    from app.core.security import get_current_user as sec_gcu
    from app.main import app

    def _login(user: User) -> None:
        async def _override():
            return user

        app.dependency_overrides[deps_gcu] = _override
        app.dependency_overrides[sec_gcu] = _override

    yield _login

    from app.core.deps import get_current_user as _deps_gcu
    from app.core.security import get_current_user as _sec_gcu
    from app.main import app as _app

    _app.dependency_overrides.pop(_deps_gcu, None)
    _app.dependency_overrides.pop(_sec_gcu, None)


@pytest_asyncio.fixture
async def roster_users(db):
    """Real DB users spanning every role that matters for authorization."""
    users = {
        "student": User(
            nycu_id="rs_student",
            name="Roster Student",
            email="rs_student@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
        "professor": User(
            nycu_id="rs_prof",
            name="Roster Professor",
            email="rs_prof@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
        "college": User(
            nycu_id="rs_college",
            name="Roster College",
            email="rs_college@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="ENG",
        ),
        "admin": User(
            nycu_id="rs_admin",
            name="Roster Admin",
            email="rs_admin@test.edu",
            user_type=UserType.employee,
            role=UserRole.admin,
        ),
        "super_admin": User(
            nycu_id="rs_super",
            name="Roster Super",
            email="rs_super@test.edu",
            user_type=UserType.employee,
            role=UserRole.super_admin,
        ),
    }
    for user in users.values():
        db.add(user)
    await db.commit()
    for user in users.values():
        await db.refresh(user)
    return users


@pytest_asyncio.fixture
async def scholarship_config(db) -> ScholarshipConfiguration:
    """A minimal scholarship configuration for happy-path create."""
    scholarship = ScholarshipType(
        code="rs_scholarship",
        name="Roster Schedule Scholarship",
        description="For roster schedule endpoint tests",
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)

    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=114,
        config_name="Roster Config",
        config_code="rs_config_114",
        amount=10000,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


def _create_payload(config_id: int, **overrides) -> dict:
    payload = {
        "scholarship_configuration_id": config_id,
        "roster_cycle": "monthly",
        "schedule_name": "Test Schedule",
    }
    payload.update(overrides)
    return payload


@pytest.mark.api
class TestRosterSchedulesAuthorization:
    """Only admin / super_admin may touch roster schedules."""

    async def test_list_unauthenticated_401(self, client):
        response = await client.get(PREFIX)
        assert response.status_code == 401

    async def test_list_student_forbidden(self, client, login, roster_users):
        login(roster_users["student"])
        response = await client.get(PREFIX)
        assert response.status_code == 403

    async def test_list_professor_forbidden(self, client, login, roster_users):
        login(roster_users["professor"])
        response = await client.get(PREFIX)
        assert response.status_code == 403

    async def test_list_college_forbidden(self, client, login, roster_users):
        login(roster_users["college"])
        response = await client.get(PREFIX)
        assert response.status_code == 403

    async def test_create_unauthenticated_401(self, client, scholarship_config):
        response = await client.post(PREFIX, json=_create_payload(scholarship_config.id))
        assert response.status_code == 401

    async def test_create_student_forbidden(self, client, login, roster_users, scholarship_config):
        login(roster_users["student"])
        response = await client.post(PREFIX, json=_create_payload(scholarship_config.id))
        assert response.status_code == 403

    async def test_get_schedule_student_forbidden(self, client, login, roster_users):
        login(roster_users["student"])
        response = await client.get(f"{PREFIX}/1")
        assert response.status_code == 403

    async def test_update_schedule_college_forbidden(self, client, login, roster_users):
        login(roster_users["college"])
        response = await client.put(f"{PREFIX}/1", json={"description": "x"})
        assert response.status_code == 403

    async def test_patch_status_professor_forbidden(self, client, login, roster_users):
        login(roster_users["professor"])
        response = await client.patch(f"{PREFIX}/1/status", json={"status": "paused"})
        assert response.status_code == 403

    async def test_delete_schedule_student_forbidden(self, client, login, roster_users):
        login(roster_users["student"])
        response = await client.delete(f"{PREFIX}/1")
        assert response.status_code == 403

    async def test_execute_schedule_student_forbidden(self, client, login, roster_users):
        login(roster_users["student"])
        response = await client.post(f"{PREFIX}/1/execute")
        assert response.status_code == 403

    async def test_by_config_student_forbidden(self, client, login, roster_users):
        login(roster_users["student"])
        response = await client.get(f"{PREFIX}/by-config/1")
        assert response.status_code == 403

    async def test_scheduler_status_student_forbidden(self, client, login, roster_users):
        login(roster_users["student"])
        response = await client.get(f"{PREFIX}/scheduler/status")
        assert response.status_code == 403

    async def test_scheduler_status_unauthenticated_401(self, client):
        response = await client.get(f"{PREFIX}/scheduler/status")
        assert response.status_code == 401


@pytest.mark.api
class TestRosterSchedulesValidationAndNotFound:
    """Input validation and not-found handling (admin-authenticated)."""

    async def test_create_nonexistent_config_404(self, client, login, roster_users):
        login(roster_users["admin"])
        response = await client.post(PREFIX, json=_create_payload(999999))
        assert response.status_code == 404

    async def test_create_missing_required_field_422(self, client, login, roster_users):
        login(roster_users["admin"])
        # Missing scholarship_configuration_id and roster_cycle.
        response = await client.post(PREFIX, json={"schedule_name": "no config"})
        assert response.status_code == 422

    async def test_create_invalid_cron_422(self, client, login, roster_users, scholarship_config):
        login(roster_users["admin"])
        payload = _create_payload(scholarship_config.id, cron_expression="not a cron")
        response = await client.post(PREFIX, json=payload)
        assert response.status_code == 422

    async def test_create_invalid_roster_cycle_422(self, client, login, roster_users, scholarship_config):
        login(roster_users["admin"])
        payload = _create_payload(scholarship_config.id, roster_cycle="fortnightly")
        response = await client.post(PREFIX, json=payload)
        assert response.status_code == 422

    async def test_get_schedule_not_found_404(self, client, login, roster_users):
        login(roster_users["admin"])
        response = await client.get(f"{PREFIX}/999999")
        assert response.status_code == 404

    async def test_update_schedule_not_found_404(self, client, login, roster_users):
        login(roster_users["admin"])
        response = await client.put(f"{PREFIX}/999999", json={"description": "x"})
        assert response.status_code == 404

    async def test_patch_status_not_found_404(self, client, login, roster_users):
        login(roster_users["admin"])
        response = await client.patch(f"{PREFIX}/999999/status", json={"status": "paused"})
        assert response.status_code == 404

    async def test_patch_status_invalid_value_422(self, client, login, roster_users):
        login(roster_users["admin"])
        response = await client.patch(f"{PREFIX}/1/status", json={"status": "not_a_status"})
        assert response.status_code == 422

    async def test_delete_schedule_not_found_404(self, client, login, roster_users):
        login(roster_users["admin"])
        response = await client.delete(f"{PREFIX}/999999")
        assert response.status_code == 404

    async def test_execute_schedule_not_found_returns_500_bug(self, client, login, roster_users):
        # BUG: execute_schedule_now() is the only handler in this module missing
        # the `except HTTPException: raise` guard. Its own 404 ("Roster schedule
        # not found") is caught by the bare `except Exception` and re-raised as
        # 500, masking a legitimate not-found as a server error. Every sibling
        # handler (get/update/patch/delete) correctly re-raises the 404.
        # Pinning current behavior; fix = add `except HTTPException: raise`
        # before the generic handler (see roster_schedules.py ~line 473).
        login(roster_users["admin"])
        response = await client.post(f"{PREFIX}/999999/execute")
        assert response.status_code == 500


@pytest.mark.api
class TestRosterSchedulesEnvelope:
    """Happy-path {success, message, data} envelope for scheduler-free paths."""

    async def test_list_admin_empty_envelope(self, client, login, roster_users):
        login(roster_users["admin"])
        response = await client.get(PREFIX)
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) >= {"success", "message", "data"}
        assert body["success"] is True
        assert body["data"]["items"] == []
        assert body["data"]["total"] == 0

    async def test_list_super_admin_ok(self, client, login, roster_users):
        login(roster_users["super_admin"])
        response = await client.get(PREFIX)
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_create_schedule_envelope(self, client, login, roster_users, scholarship_config):
        login(roster_users["admin"])
        response = await client.post(PREFIX, json=_create_payload(scholarship_config.id))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["schedule_name"] == "Test Schedule"
        assert data["scholarship_configuration_id"] == scholarship_config.id
        assert data["roster_cycle"] == "monthly"

    async def test_by_config_no_schedule_returns_null(self, client, login, roster_users):
        login(roster_users["admin"])
        response = await client.get(f"{PREFIX}/by-config/999999")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] is None
