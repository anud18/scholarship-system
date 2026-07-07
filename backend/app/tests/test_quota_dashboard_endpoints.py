"""
HTTP-layer tests for the quota dashboard endpoints
(app/api/v1/endpoints/quota_dashboard.py).

Focus: authorization boundaries (require_staff vs require_admin), required-query
validation, the {success, message, data} response envelope, and the CSV export
branch. The export route is the sharpest boundary: it is admin-only while the
other three routes admit any staff member (admin / college / professor), so a
staff-but-not-admin user is accepted everywhere except export.

Authentication is simulated by overriding `get_current_user` with real
DB-backed User rows so the actual require_staff / require_admin gates run.
"""

import pytest
import pytest_asyncio

from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole, UserType

QUOTA_PREFIX = "/api/v1/quota-dashboard"


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
async def quota_users(db):
    """Real DB users covering the roles the quota routes distinguish."""
    users = {
        "student": User(
            nycu_id="quota_student",
            name="Quota Student",
            email="quota_student@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
        "professor": User(
            nycu_id="quota_prof",
            name="Quota Professor",
            email="quota_prof@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
        "college": User(
            nycu_id="quota_college",
            name="Quota College",
            email="quota_college@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="ENG",
        ),
        "admin": User(
            nycu_id="quota_admin",
            name="Quota Admin",
            email="quota_admin@test.edu",
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
async def quota_scholarship(db) -> ScholarshipType:
    scholarship = ScholarshipType(
        code="quota_scholarship",
        name="Quota Test Scholarship",
        description="Scholarship used by quota dashboard endpoint tests",
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


@pytest.mark.api
class TestQuotaOverview:
    """GET /overview - require_staff, academic_year required."""

    async def test_overview_unauthenticated_401(self, client):
        response = await client.get(f"{QUOTA_PREFIX}/overview", params={"academic_year": 114})
        assert response.status_code == 401
        assert response.json()["success"] is False

    async def test_overview_student_forbidden_403(self, client, login, quota_users):
        login(quota_users["student"])
        response = await client.get(f"{QUOTA_PREFIX}/overview", params={"academic_year": 114})
        assert response.status_code == 403

    async def test_overview_missing_academic_year_422(self, client, login, quota_users):
        login(quota_users["admin"])
        response = await client.get(f"{QUOTA_PREFIX}/overview")
        assert response.status_code == 422

    async def test_overview_admin_200_envelope(self, client, login, quota_users, quota_scholarship):
        login(quota_users["admin"])
        response = await client.get(f"{QUOTA_PREFIX}/overview", params={"academic_year": 114})
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) >= {"success", "message", "data"}
        assert body["success"] is True
        data = body["data"]
        assert data["academic_year"] == 114
        assert "overview" in data
        assert "global_stats" in data
        assert data["global_stats"]["total_applications"] == 0

    async def test_overview_professor_staff_allowed_200(self, client, login, quota_users):
        # require_staff admits professors.
        login(quota_users["professor"])
        response = await client.get(f"{QUOTA_PREFIX}/overview", params={"academic_year": 114})
        assert response.status_code == 200

    async def test_overview_college_staff_allowed_200(self, client, login, quota_users):
        login(quota_users["college"])
        response = await client.get(f"{QUOTA_PREFIX}/overview", params={"academic_year": 114})
        assert response.status_code == 200


@pytest.mark.api
class TestDetailedQuotaStatus:
    """GET /detailed/{scholarship_type_id}/{sub_type} - require_staff."""

    async def test_detailed_unauthenticated_401(self, client, quota_scholarship):
        response = await client.get(
            f"{QUOTA_PREFIX}/detailed/{quota_scholarship.id}/general", params={"academic_year": 114}
        )
        assert response.status_code == 401

    async def test_detailed_student_forbidden_403(self, client, login, quota_users, quota_scholarship):
        login(quota_users["student"])
        response = await client.get(
            f"{QUOTA_PREFIX}/detailed/{quota_scholarship.id}/general", params={"academic_year": 114}
        )
        assert response.status_code == 403

    async def test_detailed_missing_academic_year_422(self, client, login, quota_users, quota_scholarship):
        login(quota_users["admin"])
        response = await client.get(f"{QUOTA_PREFIX}/detailed/{quota_scholarship.id}/general")
        assert response.status_code == 422

    async def test_detailed_scholarship_not_found_404(self, client, login, quota_users):
        login(quota_users["admin"])
        response = await client.get(f"{QUOTA_PREFIX}/detailed/999999/general", params={"academic_year": 114})
        assert response.status_code == 404

    async def test_detailed_non_int_id_422(self, client, login, quota_users):
        login(quota_users["admin"])
        response = await client.get(f"{QUOTA_PREFIX}/detailed/not-an-int/general", params={"academic_year": 114})
        assert response.status_code == 422

    async def test_detailed_admin_200_envelope(self, client, login, quota_users, quota_scholarship):
        login(quota_users["admin"])
        response = await client.get(
            f"{QUOTA_PREFIX}/detailed/{quota_scholarship.id}/general", params={"academic_year": 114}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["scholarship_type"]["id"] == quota_scholarship.id
        assert data["scholarship_type"]["code"] == "quota_scholarship"
        assert "quota_status" in data
        assert data["recent_applications"] == []


@pytest.mark.api
class TestQuotaAlerts:
    """GET /alerts - require_staff."""

    async def test_alerts_unauthenticated_401(self, client):
        response = await client.get(f"{QUOTA_PREFIX}/alerts", params={"academic_year": 114})
        assert response.status_code == 401

    async def test_alerts_student_forbidden_403(self, client, login, quota_users):
        login(quota_users["student"])
        response = await client.get(f"{QUOTA_PREFIX}/alerts", params={"academic_year": 114})
        assert response.status_code == 403

    async def test_alerts_missing_academic_year_422(self, client, login, quota_users):
        login(quota_users["admin"])
        response = await client.get(f"{QUOTA_PREFIX}/alerts")
        assert response.status_code == 422

    async def test_alerts_college_200_envelope(self, client, login, quota_users, quota_scholarship):
        login(quota_users["college"])
        response = await client.get(f"{QUOTA_PREFIX}/alerts", params={"academic_year": 114})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        # No approved applications -> no alerts.
        assert body["data"]["alerts"] == []
        assert body["data"]["academic_year"] == 114


@pytest.mark.api
class TestQuotaExport:
    """GET /export - require_admin (stricter than the sibling routes)."""

    async def test_export_unauthenticated_401(self, client):
        response = await client.get(f"{QUOTA_PREFIX}/export", params={"academic_year": 114})
        assert response.status_code == 401

    async def test_export_student_forbidden_403(self, client, login, quota_users):
        login(quota_users["student"])
        response = await client.get(f"{QUOTA_PREFIX}/export", params={"academic_year": 114})
        assert response.status_code == 403

    async def test_export_professor_forbidden_403(self, client, login, quota_users):
        # Professor is staff (can hit /overview) but NOT admin -> export denied.
        login(quota_users["professor"])
        response = await client.get(f"{QUOTA_PREFIX}/export", params={"academic_year": 114})
        assert response.status_code == 403

    async def test_export_college_forbidden_403(self, client, login, quota_users):
        # College is staff but NOT admin -> export denied. Pins the require_admin
        # boundary that separates export from the other three quota routes.
        login(quota_users["college"])
        response = await client.get(f"{QUOTA_PREFIX}/export", params={"academic_year": 114})
        assert response.status_code == 403

    async def test_export_missing_academic_year_422(self, client, login, quota_users):
        login(quota_users["admin"])
        response = await client.get(f"{QUOTA_PREFIX}/export")
        assert response.status_code == 422

    async def test_export_invalid_format_422(self, client, login, quota_users):
        # format query is pattern-gated to ^(json|csv)$.
        login(quota_users["admin"])
        response = await client.get(f"{QUOTA_PREFIX}/export", params={"academic_year": 114, "format": "xml"})
        assert response.status_code == 422

    async def test_export_admin_json_200_envelope(self, client, login, quota_users, quota_scholarship):
        login(quota_users["admin"])
        response = await client.get(f"{QUOTA_PREFIX}/export", params={"academic_year": 114, "format": "json"})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "records" in body["data"]
        assert body["data"]["count"] == 0

    async def test_export_admin_csv_200_content_type(self, client, login, quota_users, quota_scholarship):
        login(quota_users["admin"])
        response = await client.get(f"{QUOTA_PREFIX}/export", params={"academic_year": 114, "format": "csv"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers.get("content-disposition", "")
