"""
HTTP-layer tests for the scholarship endpoints (app/api/v1/endpoints/scholarships.py).

Focus: authorization boundaries (public vs authenticated vs admin-only),
input validation (path-pattern + request body), the {success, message, data}
response envelope, and the dev-only debug gate.

These exercise the real FastAPI app over ASGI with the in-memory SQLite database
from conftest. Authentication is simulated by overriding the `get_current_user`
dependency with real DB-backed User rows so that every downstream role gate
(require_admin, etc.) runs unmodified.
"""

import pytest
import pytest_asyncio

from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType

SCHOLARSHIPS_PREFIX = "/api/v1/scholarships"


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
async def sch_users(db):
    """Real DB users covering every role the scholarship routes distinguish."""
    users = {
        "student": User(
            nycu_id="sch_student",
            name="Scholarship Student",
            email="sch_student@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
        "professor": User(
            nycu_id="sch_prof",
            name="Scholarship Professor",
            email="sch_prof@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
        "college": User(
            nycu_id="sch_college",
            name="Scholarship College",
            email="sch_college@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="ENG",
        ),
        "admin": User(
            nycu_id="sch_admin",
            name="Scholarship Admin",
            email="sch_admin@test.edu",
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
async def scholarship(db) -> ScholarshipType:
    scholarship = ScholarshipType(
        code="phd_scholarship",
        name="PhD Test Scholarship",
        description="Scholarship used by scholarships endpoint tests",
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


@pytest_asyncio.fixture
async def active_config(db, scholarship) -> ScholarshipConfiguration:
    """An active configuration (amount > 0) so ScholarshipTypeResponse validates.

    Without an active config the detail / whitelist responses build
    ScholarshipTypeResponse(amount=0), which fails the ``amount > 0`` schema
    validator and 500s (see TestScholarshipResponseBuildBug).
    """
    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=114,
        semester=Semester.first,
        config_name="phd test config",
        config_code="phd_test_cfg_114_1",
        amount=10000,
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@pytest.mark.api
class TestPublicListingAndDetail:
    """GET "" and GET /{id} are unauthenticated / public routes."""

    async def test_list_scholarships_public_200_envelope(self, client, scholarship):
        response = await client.get(SCHOLARSHIPS_PREFIX)
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) >= {"success", "message", "data"}
        assert body["success"] is True
        assert isinstance(body["data"], list)
        codes = [s["code"] for s in body["data"]]
        assert "phd_scholarship" in codes

    async def test_list_scholarships_empty_ok(self, client):
        response = await client.get(SCHOLARSHIPS_PREFIX)
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_list_scholarships_with_filters(self, client, scholarship):
        response = await client.get(SCHOLARSHIPS_PREFIX, params={"academic_year": 114, "semester": "first"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(s["academic_year"] == 114 for s in data)
        assert all(s["semester"] == "first" for s in data)

    async def test_list_invalid_academic_year_422(self, client):
        response = await client.get(SCHOLARSHIPS_PREFIX, params={"academic_year": "not-a-number"})
        assert response.status_code == 422

    async def test_get_detail_public_200_envelope(self, client, scholarship, active_config):
        response = await client.get(f"{SCHOLARSHIPS_PREFIX}/{scholarship.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == scholarship.id
        assert body["data"]["code"] == "phd_scholarship"

    async def test_get_detail_not_found_404(self, client):
        response = await client.get(f"{SCHOLARSHIPS_PREFIX}/999999")
        assert response.status_code == 404

    async def test_get_detail_non_int_id_422(self, client):
        response = await client.get(f"{SCHOLARSHIPS_PREFIX}/not-an-int")
        assert response.status_code == 422


@pytest.mark.api
class TestEligibleScholarships:
    """GET /eligible requires authentication (any role); resolves student data."""

    async def test_eligible_unauthenticated_401(self, client):
        response = await client.get(f"{SCHOLARSHIPS_PREFIX}/eligible")
        assert response.status_code == 401
        assert response.json()["success"] is False

    async def test_eligible_non_student_returns_404(self, client, login, sch_users):
        # get_student_data_from_user returns None for a non-student role, so the
        # endpoint raises STUDENT_DATA_NOT_FOUND (404) deterministically without
        # touching the external SIS API.
        login(sch_users["professor"])
        response = await client.get(f"{SCHOLARSHIPS_PREFIX}/eligible")
        assert response.status_code == 404


@pytest.mark.api
class TestWhitelistToggle:
    """PATCH /{id}/whitelist is admin-only (require_admin)."""

    async def test_whitelist_unauthenticated_401(self, client, scholarship):
        response = await client.patch(f"{SCHOLARSHIPS_PREFIX}/{scholarship.id}/whitelist", json={"enabled": True})
        assert response.status_code == 401

    async def test_whitelist_student_forbidden_403(self, client, login, sch_users, scholarship):
        login(sch_users["student"])
        response = await client.patch(f"{SCHOLARSHIPS_PREFIX}/{scholarship.id}/whitelist", json={"enabled": True})
        assert response.status_code == 403

    async def test_whitelist_professor_forbidden_403(self, client, login, sch_users, scholarship):
        login(sch_users["professor"])
        response = await client.patch(f"{SCHOLARSHIPS_PREFIX}/{scholarship.id}/whitelist", json={"enabled": True})
        assert response.status_code == 403

    async def test_whitelist_college_forbidden_403(self, client, login, sch_users, scholarship):
        # require_admin excludes college; only admin/super_admin may toggle.
        login(sch_users["college"])
        response = await client.patch(f"{SCHOLARSHIPS_PREFIX}/{scholarship.id}/whitelist", json={"enabled": True})
        assert response.status_code == 403

    async def test_whitelist_admin_not_found_404(self, client, login, sch_users):
        login(sch_users["admin"])
        response = await client.patch(f"{SCHOLARSHIPS_PREFIX}/999999/whitelist", json={"enabled": True})
        assert response.status_code == 404

    async def test_whitelist_missing_body_422(self, client, login, sch_users, scholarship):
        login(sch_users["admin"])
        response = await client.patch(f"{SCHOLARSHIPS_PREFIX}/{scholarship.id}/whitelist", json={})
        assert response.status_code == 422

    async def test_whitelist_admin_enable_200_envelope(self, client, login, db, sch_users, scholarship, active_config):
        login(sch_users["admin"])
        response = await client.patch(f"{SCHOLARSHIPS_PREFIX}/{scholarship.id}/whitelist", json={"enabled": True})
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) >= {"success", "message", "data"}
        assert body["success"] is True
        assert body["data"]["id"] == scholarship.id
        assert body["data"]["whitelist_enabled"] is True

        await db.refresh(scholarship)
        assert scholarship.whitelist_enabled is True

    async def test_whitelist_admin_disable_200(self, client, login, sch_users, scholarship, active_config):
        login(sch_users["admin"])
        response = await client.patch(f"{SCHOLARSHIPS_PREFIX}/{scholarship.id}/whitelist", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["data"]["whitelist_enabled"] is False


@pytest.mark.api
class TestTermsDocument:
    """GET /{scholarship_type}/terms requires authentication; path is pattern-gated."""

    async def test_get_terms_unauthenticated_401(self, client, scholarship):
        response = await client.get(f"{SCHOLARSHIPS_PREFIX}/phd_scholarship/terms")
        assert response.status_code == 401

    async def test_get_terms_missing_document_404(self, client, login, sch_users, scholarship):
        # Scholarship exists but has no terms_document_url uploaded.
        login(sch_users["student"])
        response = await client.get(f"{SCHOLARSHIPS_PREFIX}/phd_scholarship/terms")
        assert response.status_code == 404

    async def test_get_terms_unknown_type_404(self, client, login, sch_users):
        login(sch_users["student"])
        response = await client.get(f"{SCHOLARSHIPS_PREFIX}/no_such_type/terms")
        assert response.status_code == 404

    async def test_get_terms_invalid_path_pattern_422(self, client, login, sch_users):
        # Path pattern is ^[a-z_]{1,50}$ - uppercase/digits are rejected.
        login(sch_users["student"])
        response = await client.get(f"{SCHOLARSHIPS_PREFIX}/BadType123/terms")
        assert response.status_code == 422


@pytest.mark.api
class TestUploadTerms:
    """POST /{scholarship_type}/upload-terms is admin-only (require_admin)."""

    def _file(self):
        return {"file": ("terms.pdf", b"%PDF-1.4 dummy terms content", "application/pdf")}

    async def test_upload_terms_unauthenticated_401(self, client):
        response = await client.post(f"{SCHOLARSHIPS_PREFIX}/phd_scholarship/upload-terms", files=self._file())
        assert response.status_code == 401

    async def test_upload_terms_student_forbidden_403(self, client, login, sch_users):
        login(sch_users["student"])
        response = await client.post(f"{SCHOLARSHIPS_PREFIX}/phd_scholarship/upload-terms", files=self._file())
        assert response.status_code == 403

    async def test_upload_terms_admin_unknown_type_404(self, client, login, sch_users):
        # Admin passes the role gate + file validation, but the scholarship type
        # does not exist -> 404 (raised before any MinIO interaction).
        login(sch_users["admin"])
        response = await client.post(f"{SCHOLARSHIPS_PREFIX}/no_such_type/upload-terms", files=self._file())
        assert response.status_code == 404


@pytest.mark.api
class TestDevEndpointsDebugGate:
    """The /dev/* routes are admin-only AND gated behind settings.debug.

    In the test environment settings.debug is False, so an authenticated admin
    is still rejected with 403 ("Only available in development mode"). This pins
    the double gate: role first, then the debug flag.
    """

    async def test_reset_periods_unauthenticated_401(self, client):
        response = await client.post(f"{SCHOLARSHIPS_PREFIX}/dev/reset-application-periods")
        assert response.status_code == 401

    async def test_reset_periods_student_forbidden_403(self, client, login, sch_users):
        login(sch_users["student"])
        response = await client.post(f"{SCHOLARSHIPS_PREFIX}/dev/reset-application-periods")
        assert response.status_code == 403

    async def test_reset_periods_admin_blocked_by_debug_gate_403(self, client, login, sch_users):
        login(sch_users["admin"])
        response = await client.post(f"{SCHOLARSHIPS_PREFIX}/dev/reset-application-periods")
        assert response.status_code == 403

    async def test_toggle_whitelist_admin_blocked_by_debug_gate_403(self, client, login, sch_users, scholarship):
        login(sch_users["admin"])
        response = await client.post(f"{SCHOLARSHIPS_PREFIX}/dev/toggle-whitelist/{scholarship.id}")
        assert response.status_code == 403

    async def test_add_to_whitelist_student_forbidden_403(self, client, login, sch_users, scholarship):
        login(sch_users["student"])
        response = await client.post(
            f"{SCHOLARSHIPS_PREFIX}/dev/add-to-whitelist/{scholarship.id}", params={"student_id": 5}
        )
        assert response.status_code == 403

    async def test_add_to_whitelist_admin_blocked_by_debug_gate_403(self, client, login, sch_users, scholarship):
        login(sch_users["admin"])
        response = await client.post(
            f"{SCHOLARSHIPS_PREFIX}/dev/add-to-whitelist/{scholarship.id}", params={"student_id": 5}
        )
        assert response.status_code == 403


@pytest.mark.api
class TestScholarshipResponseBuildBug:
    """BUG (pinned current behavior): GET /{id} and PATCH /{id}/whitelist crash
    for any scholarship type that has NO active ScholarshipConfiguration.

    scholarships.py builds ScholarshipTypeResponse(amount=0) when active_config is
    None (lines ~299 and ~736), but ScholarshipTypeResponse's field validator
    rejects ``amount <= 0`` ("Amount must be greater than 0"), so the response
    construction raises a pydantic ValidationError. In production the error
    middleware turns this into an HTTP 500; under the ASGI test transport the
    exception propagates to the caller (pinned with pytest.raises below). A
    brand-new scholarship type (created before its configuration) is therefore
    un-viewable via these routes.
    """

    async def test_get_detail_without_config_raises(self, client, scholarship):
        # BUG: should be 200 with amount=0; instead the amount>0 validator raises.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            await client.get(f"{SCHOLARSHIPS_PREFIX}/{scholarship.id}")

    async def test_whitelist_toggle_without_config_raises(self, client, login, sch_users, scholarship):
        # BUG: the whitelist flag IS persisted (commit precedes response building),
        # but the response construction raises because there is no active config.
        from pydantic import ValidationError

        login(sch_users["admin"])
        with pytest.raises(ValidationError):
            await client.patch(f"{SCHOLARSHIPS_PREFIX}/{scholarship.id}/whitelist", json={"enabled": True})
