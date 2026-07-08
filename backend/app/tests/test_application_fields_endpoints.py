"""
HTTP-layer (endpoint) tests for dynamic application-form field management.

Target module: app/api/v1/endpoints/application_fields.py (mounted under
/api/v1/application-fields).

Auth map (verified against the module):
  * GET  /fields/{type}, /documents/{type}, /form-config/{type},
    /documents/{id}/example                      -> get_current_user (any role)
  * POST/PUT/DELETE fields & documents, form-config save, upload/delete example
                                                 -> require_admin

Priority order per route: unauth 401 -> non-admin 403 -> not-found 404 ->
invalid payload 422 -> happy-path {success, message, data} envelope.

Harness mirrors test_admin_endpoints.py: overrides ``get_current_user`` with a
REAL DB User so ``require_admin`` runs its genuine role check.
"""

import pytest
import pytest_asyncio

from app.models.application_field import ApplicationDocument, ApplicationField
from app.models.user import User, UserRole, UserType


async def _shared_db():
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
class TestApplicationFieldsEndpoints:
    """Endpoint tests for application_fields.py."""

    @pytest_asyncio.fixture(autouse=True)
    async def _clear_cache(self):
        """The @cached GETs key on scholarship_type; clear between tests so a
        prior payload never leaks (fail-open no-op when Redis is absent)."""
        from app.core.cache import invalidate

        for prefix in ("fields:", "documents:", "formconfig:"):
            try:
                await invalidate(prefix)
            except Exception:
                pass
        yield

    @pytest_asyncio.fixture
    async def login(self, client):
        from app.core.security import get_current_user
        from app.main import app

        def _login(user):
            app.dependency_overrides[get_current_user] = lambda: user
            return client

        yield _login
        app.dependency_overrides.pop(get_current_user, None)

    @pytest_asyncio.fixture
    async def admin(self):
        return await _make_user(UserRole.admin, "admin_af")

    @pytest_asyncio.fixture
    async def student(self):
        return await _make_user(UserRole.student, "student_af")

    async def _make_field(self, scholarship_type="undergraduate", field_type="text", **overrides):
        db = await _shared_db()
        defaults = dict(
            scholarship_type=scholarship_type,
            field_name="contact_phone",
            field_label="聯絡電話",
            field_type=field_type,
            is_required=False,
            is_active=True,
        )
        defaults.update(overrides)
        field = ApplicationField(**defaults)
        db.add(field)
        await db.commit()
        await db.refresh(field)
        return field

    async def _make_document(self, scholarship_type="undergraduate", **overrides):
        db = await _shared_db()
        defaults = dict(
            scholarship_type=scholarship_type,
            document_name="存摺封面",
            is_required=True,
            accepted_file_types=["PDF"],
            is_active=True,
        )
        defaults.update(overrides)
        doc = ApplicationDocument(**defaults)
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc

    # ------------------------------------------------------------------
    # GET /fields/{scholarship_type}  (get_current_user)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_fields_unauthenticated_401(self, client):
        resp = await client.get("/api/v1/application-fields/fields/undergraduate")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_fields_student_allowed(self, login, student):
        """Any authenticated user (incl. student) may read field config."""
        await self._make_field(scholarship_type="undergrad_get")
        c = login(student)
        resp = await c.get("/api/v1/application-fields/fields/undergrad_get")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert any(f["field_name"] == "contact_phone" for f in body["data"])

    # ------------------------------------------------------------------
    # POST /fields  (require_admin)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_field_non_admin_403(self, login, student):
        c = login(student)
        resp = await c.post(
            "/api/v1/application-fields/fields",
            json={"scholarship_type": "undergraduate", "field_name": "x", "field_label": "X"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_field_missing_required_422(self, login, admin):
        c = login(admin)
        resp = await c.post(
            "/api/v1/application-fields/fields",
            json={"scholarship_type": "undergraduate"},  # missing field_name/field_label
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_field_export_flag_on_nontext_422(self, login, admin):
        """include_in_college_export only valid for field_type='text'."""
        c = login(admin)
        resp = await c.post(
            "/api/v1/application-fields/fields",
            json={
                "scholarship_type": "undergraduate",
                "field_name": "amount",
                "field_label": "金額",
                "field_type": "number",
                "include_in_college_export": True,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_field_happy_envelope(self, login, admin):
        c = login(admin)
        resp = await c.post(
            "/api/v1/application-fields/fields",
            json={
                "scholarship_type": "undergrad_create",
                "field_name": "contact_phone",
                "field_label": "聯絡電話",
                "field_type": "text",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["field_name"] == "contact_phone"
        assert body["data"]["id"] > 0

    # ------------------------------------------------------------------
    # PUT /fields/{field_id}  (require_admin)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_field_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.put(
            "/api/v1/application-fields/fields/999999",
            json={"field_label": "new"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_field_non_admin_403(self, login, student):
        c = login(student)
        resp = await c.put(
            "/api/v1/application-fields/fields/1",
            json={"field_label": "new"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_field_happy(self, login, admin):
        field = await self._make_field(scholarship_type="undergrad_put")
        c = login(admin)
        resp = await c.put(
            f"/api/v1/application-fields/fields/{field.id}",
            json={"field_label": "更新後標籤"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["field_label"] == "更新後標籤"

    @pytest.mark.asyncio
    async def test_update_field_export_flag_against_existing_nontext_422(self, login, admin):
        """Endpoint re-checks the export flag against the MERGED field_type:
        toggling include_in_college_export on an existing number field (with
        field_type omitted from the payload) must 422."""
        field = await self._make_field(scholarship_type="undergrad_put2", field_type="number", field_name="amount")
        c = login(admin)
        resp = await c.put(
            f"/api/v1/application-fields/fields/{field.id}",
            json={"include_in_college_export": True},
        )
        assert resp.status_code == 422

    # ------------------------------------------------------------------
    # DELETE /fields/{field_id}  (require_admin)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_field_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.delete("/api/v1/application-fields/fields/999999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_field_non_admin_403(self, login, student):
        c = login(student)
        resp = await c.delete("/api/v1/application-fields/fields/1")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_field_happy(self, login, admin):
        field = await self._make_field(scholarship_type="undergrad_del")
        c = login(admin)
        resp = await c.delete(f"/api/v1/application-fields/fields/{field.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] is True

    # ------------------------------------------------------------------
    # GET /documents/{scholarship_type}  (get_current_user)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_documents_unauthenticated_401(self, client):
        resp = await client.get("/api/v1/application-fields/documents/undergraduate")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_documents_student_allowed(self, login, student):
        await self._make_document(scholarship_type="undergrad_docget")
        c = login(student)
        resp = await c.get("/api/v1/application-fields/documents/undergrad_docget")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert any(d["document_name"] == "存摺封面" for d in body["data"])

    # ------------------------------------------------------------------
    # POST /documents  (require_admin)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_document_non_admin_403(self, login, student):
        c = login(student)
        resp = await c.post(
            "/api/v1/application-fields/documents",
            json={"scholarship_type": "undergraduate", "document_name": "存摺"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_document_happy(self, login, admin):
        c = login(admin)
        resp = await c.post(
            "/api/v1/application-fields/documents",
            json={"scholarship_type": "undergrad_doccreate", "document_name": "存摺封面"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["document_name"] == "存摺封面"

    # ------------------------------------------------------------------
    # PUT /documents/{document_id}  (require_admin)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_document_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.put(
            "/api/v1/application-fields/documents/999999",
            json={"document_name": "new"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_document_happy(self, login, admin):
        doc = await self._make_document(scholarship_type="undergrad_docput")
        c = login(admin)
        resp = await c.put(
            f"/api/v1/application-fields/documents/{doc.id}",
            json={"document_name": "更新後文件"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["document_name"] == "更新後文件"

    # ------------------------------------------------------------------
    # DELETE /documents/{document_id}  (require_admin)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_document_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.delete("/api/v1/application-fields/documents/999999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_document_non_admin_403(self, login, student):
        c = login(student)
        resp = await c.delete("/api/v1/application-fields/documents/1")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_document_happy(self, login, admin):
        doc = await self._make_document(scholarship_type="undergrad_docdel")
        c = login(admin)
        resp = await c.delete(f"/api/v1/application-fields/documents/{doc.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] is True

    # ------------------------------------------------------------------
    # GET /form-config/{scholarship_type}  (get_current_user, path pattern)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_form_config_unauthenticated_401(self, client):
        resp = await client.get("/api/v1/application-fields/form-config/undergraduate")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_form_config_invalid_type_422(self, login, student):
        """Uppercase violates the ^[a-z_]{1,50}$ path pattern -> 422."""
        c = login(student)
        resp = await c.get("/api/v1/application-fields/form-config/BADTYPE")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_form_config_happy(self, login, student):
        c = login(student)
        resp = await c.get("/api/v1/application-fields/form-config/undergrad_formcfg")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["scholarship_type"] == "undergrad_formcfg"
        # Fixed bank fields are always injected
        assert isinstance(body["data"]["fields"], list)

    # ------------------------------------------------------------------
    # POST /form-config/{scholarship_type}  (require_admin)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_save_form_config_non_admin_403(self, login, student):
        c = login(student)
        resp = await c.post(
            "/api/v1/application-fields/form-config/undergraduate",
            json={"fields": [], "documents": []},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_save_form_config_missing_keys_422(self, login, admin):
        c = login(admin)
        resp = await c.post(
            "/api/v1/application-fields/form-config/undergraduate",
            json={"fields": []},  # missing documents
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_save_form_config_happy(self, login, admin):
        c = login(admin)
        resp = await c.post(
            "/api/v1/application-fields/form-config/undergrad_savecfg",
            json={"fields": [], "documents": []},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["scholarship_type"] == "undergrad_savecfg"

    # ------------------------------------------------------------------
    # POST /documents/{document_id}/upload-example  (require_admin)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_upload_example_non_admin_403(self, login, student):
        c = login(student)
        resp = await c.post(
            "/api/v1/application-fields/documents/1/upload-example",
            files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_upload_example_missing_file_422(self, login, admin):
        c = login(admin)
        resp = await c.post("/api/v1/application-fields/documents/1/upload-example")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_example_document_not_found_404(self, login, admin):
        """Valid file passes upload validation, then document lookup 404s."""
        c = login(admin)
        resp = await c.post(
            "/api/v1/application-fields/documents/999999/upload-example",
            files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        assert resp.status_code == 404

    # ------------------------------------------------------------------
    # GET /documents/{document_id}/example  (get_current_user)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_example_unauthenticated_401(self, client):
        resp = await client.get("/api/v1/application-fields/documents/1/example")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_example_not_found_404(self, login, student):
        """Document without an example_file_url -> 404."""
        doc = await self._make_document(scholarship_type="undergrad_exget")
        c = login(student)
        resp = await c.get(f"/api/v1/application-fields/documents/{doc.id}/example")
        assert resp.status_code == 404

    # ------------------------------------------------------------------
    # DELETE /documents/{document_id}/example  (require_admin)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_example_non_admin_403(self, login, student):
        c = login(student)
        resp = await c.delete("/api/v1/application-fields/documents/1/example")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_example_document_not_found_404(self, login, admin):
        c = login(admin)
        resp = await c.delete("/api/v1/application-fields/documents/999999/example")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_example_no_example_url_404(self, login, admin):
        doc = await self._make_document(scholarship_type="undergrad_exdel")
        c = login(admin)
        resp = await c.delete(f"/api/v1/application-fields/documents/{doc.id}/example")
        assert resp.status_code == 404

    # ------------------------------------------------------------------
    # display_in_list / requires_upload flags
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_document_flags_default_true(self, login, admin):
        """Documents created without the new flags default both to True."""
        client = login(admin)
        resp = await client.post(
            "/api/v1/application-fields/documents",
            json={"scholarship_type": "undergraduate", "document_name": "成績單"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["display_in_list"] is True
        assert data["requires_upload"] is True

    @pytest.mark.asyncio
    async def test_create_document_with_explicit_flags(self, login, admin):
        client = login(admin)
        resp = await client.post(
            "/api/v1/application-fields/documents",
            json={
                "scholarship_type": "undergraduate",
                "document_name": "紙本切結書",
                "display_in_list": True,
                "requires_upload": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["display_in_list"] is True
        assert data["requires_upload"] is False

    @pytest.mark.asyncio
    async def test_update_document_flags(self, login, admin):
        doc = await self._make_document()
        client = login(admin)
        resp = await client.put(
            f"/api/v1/application-fields/documents/{doc.id}",
            json={"display_in_list": False, "requires_upload": False},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["display_in_list"] is False
        assert data["requires_upload"] is False

    @pytest.mark.asyncio
    async def test_form_config_documents_include_flags(self, login, admin):
        await self._make_document(document_name="推薦信", requires_upload=False)
        client = login(admin)
        resp = await client.get("/api/v1/application-fields/form-config/undergraduate")
        assert resp.status_code == 200
        docs = resp.json()["data"]["documents"]
        by_name = {d["document_name"]: d for d in docs}
        assert by_name["推薦信"]["requires_upload"] is False
        assert by_name["推薦信"]["display_in_list"] is True
        # Injected fixed documents also carry the flags (schema defaults)
        assert all("requires_upload" in d and "display_in_list" in d for d in docs)

    # ------------------------------------------------------------------
    # 申請文件 note (application_document_note on scholarship_types)
    # ------------------------------------------------------------------

    async def _make_scholarship_type(self, code="undergraduate"):
        from app.models.scholarship import ScholarshipType

        db = await _shared_db()
        st = ScholarshipType(code=code, name="學士班獎學金", name_en="Undergraduate Scholarship")
        db.add(st)
        await db.commit()
        await db.refresh(st)
        return st

    @pytest.mark.asyncio
    async def test_save_form_config_persists_application_document_note(self, login, admin):
        await self._make_scholarship_type()
        client = login(admin)
        resp = await client.post(
            "/api/v1/application-fields/form-config/undergraduate",
            json={
                "fields": [],
                "documents": [],
                "application_document_note": "請以PDF合併上傳",
                "application_document_note_en": "Please merge into a single PDF",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["application_document_note"] == "請以PDF合併上傳"
        assert data["application_document_note_en"] == "Please merge into a single PDF"

        # Round-trips through the GET
        resp = await client.get("/api/v1/application-fields/form-config/undergraduate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["application_document_note"] == "請以PDF合併上傳"
        assert data["application_document_note_en"] == "Please merge into a single PDF"

    @pytest.mark.asyncio
    async def test_save_form_config_without_note_leaves_existing_note(self, login, admin):
        st = await self._make_scholarship_type(code="phd")
        db = await _shared_db()
        st.application_document_note = "既有說明"
        await db.commit()

        client = login(admin)
        resp = await client.post(
            "/api/v1/application-fields/form-config/phd",
            json={"fields": [], "documents": []},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["application_document_note"] == "既有說明"
