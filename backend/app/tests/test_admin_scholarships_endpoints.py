"""
HTTP-layer (endpoint) tests for admin scholarship-type / sub-type-config CRUD.

Target module: app/api/v1/endpoints/admin/scholarships.py (mounted under
/api/v1/admin/scholarships).

Priority order, per route:
  (a) unauthenticated -> 401
  (b) non-admin role  -> 403
  (c) not-found       -> 404
  (d) invalid payload -> 422 / 400
  (e) happy-path CRUD + {success, message, data} envelope
  (f) uniqueness conflict -> 409

Harness: mirrors test_admin_endpoints.py -- overrides the auth dependency via
``app.dependency_overrides``. Here we override ``get_current_user`` with a REAL
DB User so the downstream ``require_admin`` / ``require_scholarship_manager``
guards run their genuine role logic (a truer authorization boundary test).
"""

from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.scholarship import ScholarshipSubTypeConfig, ScholarshipType
from app.models.user import User, UserRole, UserType


async def _shared_db():
    """Return the async session the test client is wired to."""
    from app.db.deps import get_db
    from app.main import app

    return await app.dependency_overrides[get_db]().__anext__()


async def _make_user(role: UserRole, nycu_id: str) -> User:
    db = await _shared_db()
    user = User(
        nycu_id=nycu_id,
        name=f"{role.value} user",
        email=f"{nycu_id}@university.edu",
        user_type=UserType.student if role == UserRole.student else UserType.employee,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.api
class TestAdminScholarshipsEndpoints:
    """Endpoint tests for admin/scholarships.py."""

    @pytest_asyncio.fixture
    async def login(self, client):
        """Return a helper that authenticates the client as the given user."""
        from app.core.security import get_current_user
        from app.main import app

        def _login(user):
            app.dependency_overrides[get_current_user] = lambda: user
            return client

        yield _login
        app.dependency_overrides.pop(get_current_user, None)

    @pytest_asyncio.fixture
    async def admin(self):
        return await _make_user(UserRole.admin, "admin_sch")

    @pytest_asyncio.fixture
    async def student(self):
        return await _make_user(UserRole.student, "student_sch")

    @pytest_asyncio.fixture
    async def professor(self):
        return await _make_user(UserRole.professor, "prof_sch")

    @pytest_asyncio.fixture
    async def college(self):
        return await _make_user(UserRole.college, "college_sch")

    @pytest_asyncio.fixture
    async def super_admin(self):
        return await _make_user(UserRole.super_admin, "superadmin_sch")

    @pytest_asyncio.fixture
    async def scholarship(self):
        db = await _shared_db()
        sch = ScholarshipType(
            code="sch_endpoint_test",
            name="Endpoint Test Scholarship",
            description="For admin scholarships endpoint tests",
            sub_type_list=["general", "nstc"],
        )
        db.add(sch)
        await db.commit()
        await db.refresh(sch)
        return sch

    @pytest_asyncio.fixture
    async def scholarship_no_general(self):
        """A scholarship whose sub_type_list has NO 'general' entry.

        The GET sub-type-configs endpoint crashes on the synthetic-general
        default path (see test_get_sub_type_configs_general_crashes_500), so
        the clean happy-path test must avoid triggering it.
        """
        db = await _shared_db()
        sch = ScholarshipType(
            code="sch_no_general",
            name="No General Scholarship",
            description="sub_type_list without general",
            sub_type_list=["nstc"],
        )
        db.add(sch)
        await db.commit()
        await db.refresh(sch)
        return sch

    @pytest_asyncio.fixture
    async def sub_type_config(self, scholarship):
        db = await _shared_db()
        cfg = ScholarshipSubTypeConfig(
            scholarship_type_id=scholarship.id,
            sub_type_code="nstc",
            name="國科會",
            name_en="NSTC",
            amount=Decimal("12000.00"),
            currency="TWD",
            display_order=1,
            is_active=True,
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
        return cfg

    # ------------------------------------------------------------------
    # GET /scholarships/{scholarship_identifier}/applications
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_applications_unauthenticated_401(self, client, scholarship):
        resp = await client.get(f"/api/v1/admin/scholarships/{scholarship.id}/applications")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_applications_non_admin_403(self, login, student, scholarship):
        c = login(student)
        resp = await c.get(f"/api/v1/admin/scholarships/{scholarship.id}/applications")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_applications_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.get("/api/v1/admin/scholarships/999999/applications")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_applications_invalid_identifier_422(self, login, admin):
        """Uppercase / mixed identifier violates the path pattern."""
        c = login(admin)
        resp = await c.get("/api/v1/admin/scholarships/BadCode/applications")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_applications_happy_envelope(self, login, admin, scholarship):
        c = login(admin)
        resp = await c.get(f"/api/v1/admin/scholarships/{scholarship.id}/applications")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "message" in body
        assert isinstance(body["data"], list)

    # ------------------------------------------------------------------
    # GET /scholarships/{scholarship_identifier}/audit-trail
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_audit_trail_non_admin_403(self, login, professor, scholarship):
        c = login(professor)
        resp = await c.get(f"/api/v1/admin/scholarships/{scholarship.id}/audit-trail")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_audit_trail_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.get("/api/v1/admin/scholarships/999999/audit-trail")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_audit_trail_happy_envelope(self, login, admin, scholarship):
        c = login(admin)
        resp = await c.get(f"/api/v1/admin/scholarships/{scholarship.id}/audit-trail")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)

    # ------------------------------------------------------------------
    # GET /scholarships/{scholarship_code}/sub-types
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_sub_types_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.get("/api/v1/admin/scholarships/nonexistent_code/sub-types")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_sub_types_invalid_code_422(self, login, admin):
        """Uppercase code violates the ^[a-z_]{1,50}$ path pattern."""
        c = login(admin)
        resp = await c.get("/api/v1/admin/scholarships/BADCODE/sub-types")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_sub_types_happy_envelope(self, login, admin, scholarship):
        c = login(admin)
        resp = await c.get(f"/api/v1/admin/scholarships/{scholarship.code}/sub-types")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        # sub_type_list = ["general", "nstc"] -> two stat entries
        codes = {row["sub_type"] for row in body["data"]}
        assert {"general", "nstc"} <= codes

    # ------------------------------------------------------------------
    # GET /scholarships/sub-type-translations
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_translations_unauthenticated_401(self, client):
        resp = await client.get("/api/v1/admin/scholarships/sub-type-translations")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_translations_non_admin_403(self, login, student):
        c = login(student)
        resp = await c.get("/api/v1/admin/scholarships/sub-type-translations")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_translations_happy_envelope(self, login, admin, scholarship):
        c = login(admin)
        resp = await c.get("/api/v1/admin/scholarships/sub-type-translations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "zh" in body["data"] and "en" in body["data"]

    # ------------------------------------------------------------------
    # GET /scholarships/{scholarship_id}/sub-type-configs
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_sub_type_configs_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.get("/api/v1/admin/scholarships/999999/sub-type-configs")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_sub_type_configs_happy(self, login, admin, scholarship_no_general):
        db = await _shared_db()
        cfg = ScholarshipSubTypeConfig(
            scholarship_type_id=scholarship_no_general.id,
            sub_type_code="nstc",
            name="國科會",
            is_active=True,
        )
        db.add(cfg)
        await db.commit()

        c = login(admin)
        resp = await c.get(f"/api/v1/admin/scholarships/{scholarship_no_general.id}/sub-type-configs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        codes = {row["sub_type_code"] for row in body["data"]}
        assert "nstc" in codes

    @pytest.mark.asyncio
    async def test_get_sub_type_configs_general_crashes_500(self, login, admin, scholarship):
        """BUG: GET sub-type-configs 500s when sub_type_list contains 'general'
        but no explicit general config exists.

        The synthetic-general default (admin/scholarships.py ~L449-453) reads
        ``scholarship.currency`` and ``scholarship.amount``, but ScholarshipType
        has NEITHER column (per CLAUDE.md these live on ScholarshipConfiguration).
        The unhandled AttributeError becomes an HTTP 500 in production; the test
        ASGI transport re-raises it. Pinning current (broken) behavior.
        """
        c = login(admin)
        with pytest.raises(AttributeError, match="currency"):
            await c.get(f"/api/v1/admin/scholarships/{scholarship.id}/sub-type-configs")

    # ------------------------------------------------------------------
    # POST /scholarships/{scholarship_id}/sub-type-configs
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_sub_type_config_non_admin_403(self, login, student, scholarship):
        c = login(student)
        resp = await c.post(
            f"/api/v1/admin/scholarships/{scholarship.id}/sub-type-configs",
            json={"sub_type_code": "nstc", "name": "國科會"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_sub_type_config_scholarship_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.post(
            "/api/v1/admin/scholarships/999999/sub-type-configs",
            json={"sub_type_code": "nstc", "name": "國科會"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_sub_type_config_invalid_code_400(self, login, admin, scholarship):
        """sub_type_code not present in scholarship.sub_type_list -> 400."""
        c = login(admin)
        resp = await c.post(
            f"/api/v1/admin/scholarships/{scholarship.id}/sub-type-configs",
            json={"sub_type_code": "not_in_list", "name": "X"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_sub_type_config_general_rejected_400(self, login, admin, scholarship):
        c = login(admin)
        resp = await c.post(
            f"/api/v1/admin/scholarships/{scholarship.id}/sub-type-configs",
            json={"sub_type_code": "general", "name": "一般"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_sub_type_config_missing_required_422(self, login, admin, scholarship):
        """Missing required 'name' -> pydantic 422."""
        c = login(admin)
        resp = await c.post(
            f"/api/v1/admin/scholarships/{scholarship.id}/sub-type-configs",
            json={"sub_type_code": "nstc"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_sub_type_config_happy_then_conflict(self, login, admin, scholarship):
        c = login(admin)
        payload = {"sub_type_code": "nstc", "name": "國科會", "amount": "12000.00"}
        resp = await c.post(
            f"/api/v1/admin/scholarships/{scholarship.id}/sub-type-configs",
            json=payload,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["sub_type_code"] == "nstc"

        # Duplicate -> 409
        resp2 = await c.post(
            f"/api/v1/admin/scholarships/{scholarship.id}/sub-type-configs",
            json=payload,
        )
        assert resp2.status_code == 409

    # ------------------------------------------------------------------
    # PUT /scholarships/sub-type-configs/{id}
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_sub_type_config_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.put(
            "/api/v1/admin/scholarships/sub-type-configs/999999",
            json={"name": "new"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_sub_type_config_happy(self, login, admin, sub_type_config):
        c = login(admin)
        resp = await c.put(
            f"/api/v1/admin/scholarships/sub-type-configs/{sub_type_config.id}",
            json={"name": "更新後名稱", "display_order": 5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["name"] == "更新後名稱"
        assert body["data"]["display_order"] == 5

    # ------------------------------------------------------------------
    # DELETE /scholarships/sub-type-configs/{id}
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_sub_type_config_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.delete("/api/v1/admin/scholarships/sub-type-configs/999999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_sub_type_config_happy_soft_delete(self, login, admin, sub_type_config):
        c = login(admin)
        resp = await c.delete(f"/api/v1/admin/scholarships/sub-type-configs/{sub_type_config.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] is None

        # Soft delete: row still exists but is_active False
        from sqlalchemy import select

        db = await _shared_db()
        row = (
            await db.execute(select(ScholarshipSubTypeConfig).where(ScholarshipSubTypeConfig.id == sub_type_config.id))
        ).scalar_one_or_none()
        assert row is not None
        assert row.is_active is False

    # ------------------------------------------------------------------
    # GET /scholarships/all-for-permissions
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_all_for_permissions_non_admin_403(self, login, professor):
        c = login(professor)
        resp = await c.get("/api/v1/admin/scholarships/all-for-permissions")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_all_for_permissions_happy(self, login, admin, scholarship):
        c = login(admin)
        resp = await c.get("/api/v1/admin/scholarships/all-for-permissions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert any(s["code"] == "sch_endpoint_test" for s in body["data"])

    # ------------------------------------------------------------------
    # GET /scholarships/my-scholarships (require_scholarship_manager)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_my_scholarships_unauthenticated_401(self, client):
        resp = await client.get("/api/v1/admin/scholarships/my-scholarships")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_my_scholarships_student_403(self, login, student):
        c = login(student)
        resp = await c.get("/api/v1/admin/scholarships/my-scholarships")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_my_scholarships_professor_403(self, login, professor):
        """Professor is NOT a scholarship manager -> 403."""
        c = login(professor)
        resp = await c.get("/api/v1/admin/scholarships/my-scholarships")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_my_scholarships_super_admin_sees_all(self, login, super_admin, scholarship):
        """Super admin sees ALL active scholarships (unassigned included)."""
        c = login(super_admin)
        resp = await c.get("/api/v1/admin/scholarships/my-scholarships")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert any(s["code"] == "sch_endpoint_test" for s in body["data"])

    @pytest.mark.asyncio
    async def test_my_scholarships_admin_sees_only_assigned(self, login, admin, scholarship):
        """A regular admin (not super) sees only AdminScholarship-assigned ones -> none here."""
        c = login(admin)
        resp = await c.get("/api/v1/admin/scholarships/my-scholarships")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert all(s["code"] != "sch_endpoint_test" for s in body["data"])

    @pytest.mark.asyncio
    async def test_my_scholarships_college_allowed(self, login, college, scholarship):
        """College role passes require_scholarship_manager; sees only assigned (none) scholarships."""
        c = login(college)
        resp = await c.get("/api/v1/admin/scholarships/my-scholarships")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
