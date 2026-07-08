# Document Display/Upload Flags + 申請文件 Note Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins control, per application document, whether it appears in the student scholarship-list card and whether students must upload it in wizard step 3; and let admins set a per-scholarship note shown under the 申請文件 section in step 3.

**Architecture:** Two new Boolean columns (`display_in_list`, `requires_upload`, both defaulting `true`) on `application_documents` flow from admin CRUD → form-config API → student UI filters. Two new Text columns (`application_document_note`, `application_document_note_en`) on `scholarship_types` flow through the form-config GET/save (admin edit) and the eligible-scholarships response (student display), mirroring the existing `terms_document_url` pattern.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic + Pydantic v2; Next.js + TypeScript + Jest.

**Spec:** `docs/superpowers/specs/2026-07-08-document-display-upload-config-design.md`

## Global Constraints

- Branch: `feat/document-display-upload-config` (already created from origin/main; spec committed).
- Alembic migrations MUST include existence checks (inspector) before DDL.
- All API responses use the `{success, message, data}` envelope (already handled by existing endpoints — do not change).
- Backend lint gate: `uvx --from "black==26.3.1" black --check --line-length=120 backend/app` AND `flake8 app --select=B904,B014 --max-line-length=120` must pass.
- Backend tests run on the HOST (dev container mounts a different worktree). Required env block for any backend `pytest`/`alembic`/app-import command, run from `backend/`:
  ```
  env ENVIRONMENT=development \
      DATABASE_URL=postgresql+asyncpg://scholarship_user:scholarship_pass@localhost:5432/scholarship_db \
      DATABASE_URL_SYNC=postgresql://scholarship_user:scholarship_pass@localhost:5432/scholarship_db \
      SECRET_KEY=dev-secret-key-for-development-only \
      REDIS_URL=redis://localhost:6379/0 \
      MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=minioadmin MINIO_SECRET_KEY=minioadmin123 \
      MINIO_BUCKET=scholarship-documents MINIO_SECURE=false \
      python -m pytest <target> -p no:cacheprovider --no-cov -v
  ```
  (referred to below as `<ENV> python -m pytest ...`)
- UI copy is Traditional Chinese (zh-TW) with English variants where the surrounding code has them.
- Git commit messages in English, conventional commits.
- Alembic head before this work: `update_moe_1w_label_001`.

---

### Task 1: Backend — `display_in_list` / `requires_upload` on application_documents

**Files:**
- Create: `backend/alembic/versions/add_doc_display_upload_flags_001.py`
- Modify: `backend/app/models/application_field.py:99` (ApplicationDocument, after `is_required`)
- Modify: `backend/app/schemas/application_field.py:117-151` (ApplicationDocumentBase + ApplicationDocumentUpdate)
- Test: `backend/app/tests/test_application_fields_endpoints.py` (append to `TestApplicationFieldsEndpoints`)

**Interfaces:**
- Consumes: existing `ApplicationDocument` model, `ApplicationDocumentCreate/Update/Response` schemas, existing endpoints in `backend/app/api/v1/endpoints/application_fields.py` (no endpoint changes needed — service uses `model_dump()` / `model_fields`, so schema additions flow through create/update/bulk-save automatically).
- Produces: `ApplicationDocumentResponse` now contains `display_in_list: bool` and `requires_upload: bool` (both default `True`). Task 3/4 rely on these exact JSON keys.

- [ ] **Step 1: Write failing endpoint tests**

Append to the `TestApplicationFieldsEndpoints` class in `backend/app/tests/test_application_fields_endpoints.py` (uses the class's existing `login`/`admin` fixtures and `_make_document` helper):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && <ENV> python -m pytest app/tests/test_application_fields_endpoints.py -k "flags or flag" -p no:cacheprovider --no-cov -v`
Expected: FAIL — `'display_in_list' is an invalid keyword argument for ApplicationDocument` (from `_make_document(requires_upload=...)`) and `KeyError: 'display_in_list'` on the others.

- [ ] **Step 3: Add model columns**

In `backend/app/models/application_field.py`, inside `ApplicationDocument`, directly after `is_required = Column(Boolean, default=True)` (line 99):

```python
    # Admin-configurable visibility/upload behavior
    display_in_list = Column(Boolean, default=True, nullable=False, server_default="true")  # 顯示於獎學金列表框框
    requires_upload = Column(Boolean, default=True, nullable=False, server_default="true")  # 步驟3需要學生上傳
```

- [ ] **Step 4: Add schema fields**

In `backend/app/schemas/application_field.py`:

In `ApplicationDocumentBase`, after `is_required: bool = Field(...)` (line 117):

```python
    display_in_list: bool = Field(default=True, description="Show in scholarship-list document boxes")
    requires_upload: bool = Field(default=True, description="Student must upload this document in step 3")
```

In `ApplicationDocumentUpdate`, after `is_required: Optional[bool] = None` (line 142):

```python
    display_in_list: Optional[bool] = None
    requires_upload: Optional[bool] = None
```

No service/endpoint changes: `create_document`/`update_document`/`bulk_update_documents` copy schema fields generically, and the fixed-document dicts in `application_field_service.py` pick up the schema defaults when validated into `ApplicationDocumentResponse`.

- [ ] **Step 5: Write the Alembic migration**

Create `backend/alembic/versions/add_doc_display_upload_flags_001.py`:

```python
"""Add display_in_list / requires_upload flags to application_documents

Revision ID: add_doc_display_upload_flags_001
Revises: update_moe_1w_label_001
"""

import sqlalchemy as sa

from alembic import op

revision = "add_doc_display_upload_flags_001"
down_revision = "update_moe_1w_label_001"
branch_labels = None
depends_on = None

TABLE = "application_documents"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}

    if "display_in_list" not in existing_columns:
        op.add_column(TABLE, sa.Column("display_in_list", sa.Boolean(), nullable=False, server_default="true"))
    if "requires_upload" not in existing_columns:
        op.add_column(TABLE, sa.Column("requires_upload", sa.Boolean(), nullable=False, server_default="true"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}

    if "requires_upload" in existing_columns:
        op.drop_column(TABLE, "requires_upload")
    if "display_in_list" in existing_columns:
        op.drop_column(TABLE, "display_in_list")
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `cd backend && <ENV> python -m pytest app/tests/test_application_fields_endpoints.py -p no:cacheprovider --no-cov -v`
Expected: ALL PASS (whole file, not just the new tests — the bulk-save roundtrip tests must still pass).

- [ ] **Step 7: Run related model/service test files**

Run: `cd backend && <ENV> python -m pytest app/tests/test_application_field_models.py app/tests/test_application_field_service_unit.py app/tests/test_application_field_defaults.py app/tests/test_application_field_fixed_builders.py -p no:cacheprovider --no-cov -q`
Expected: PASS. If a fixed-builder test asserts an exact dict shape, add the two new keys with `True` to the expected dict.

- [ ] **Step 8: Lint and commit**

```bash
cd /home/howard/scholarship-system
uvx --from "black==26.3.1" black --check --line-length=120 backend/app || uvx --from "black==26.3.1" black --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014 --max-line-length=120 && cd ..
git add backend/app/models/application_field.py backend/app/schemas/application_field.py backend/alembic/versions/add_doc_display_upload_flags_001.py backend/app/tests/test_application_fields_endpoints.py
git commit -m "feat(api): add display_in_list/requires_upload flags to application documents"
```

---

### Task 2: Backend — per-scholarship 申請文件 note

**Files:**
- Create: `backend/alembic/versions/add_app_doc_note_001.py`
- Modify: `backend/app/models/scholarship.py:79` (after `terms_document_url`)
- Modify: `backend/app/schemas/scholarship.py:285` (EligibleScholarshipResponse, after `terms_document_url`)
- Modify: `backend/app/schemas/application_field.py:179` (ScholarshipFormConfigResponse)
- Modify: `backend/app/services/application_field_service.py:546-550,562-575` (form-config get + save)
- Modify: `backend/app/api/v1/endpoints/application_fields.py:261-289` (FormConfigSaveRequest + save endpoint)
- Modify: `backend/app/services/scholarship_service.py:203` (eligible dict)
- Modify: `backend/app/api/v1/endpoints/scholarships.py:248` (eligible response mapping)
- Test: `backend/app/tests/test_application_fields_endpoints.py`

**Interfaces:**
- Consumes: `ScholarshipType` model (`code`, `terms_document_url` pattern), `ApplicationFieldService.save_scholarship_form_config(scholarship_type, fields_data, documents_data, user_id)`.
- Produces:
  - `ScholarshipFormConfigResponse.application_document_note: Optional[str]` and `.application_document_note_en: Optional[str]` (form-config GET/save response).
  - `POST /application-fields/form-config/{type}` body accepts optional `application_document_note` / `application_document_note_en` strings; when present (not None) they are written to the `ScholarshipType` row.
  - `EligibleScholarshipResponse.application_document_note` / `.application_document_note_en` (student wizard reads these).
  - New service signature: `save_scholarship_form_config(scholarship_type, fields_data, documents_data, user_id, application_document_note=None, application_document_note_en=None)`.

- [ ] **Step 1: Write failing endpoint tests**

Append to `TestApplicationFieldsEndpoints` in `backend/app/tests/test_application_fields_endpoints.py`. The save endpoint bulk-replaces fields/documents, so send empty lists plus the notes; the class's `login`/`admin` fixtures apply. A `ScholarshipType` row must exist for the notes to land on:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && <ENV> python -m pytest app/tests/test_application_fields_endpoints.py -k "note" -p no:cacheprovider --no-cov -v`
Expected: FAIL — `'application_document_note' is an invalid keyword argument` / `KeyError: 'application_document_note'`.

- [ ] **Step 3: Add model columns**

In `backend/app/models/scholarship.py`, directly after `terms_document_url` (line 79):

```python
    # 申請文件區塊說明文字（學生申請步驟3「申請文件」下方，admin 可編輯）
    application_document_note = Column(Text, nullable=True)
    application_document_note_en = Column(Text, nullable=True)
```

(`Text` is already imported in this module.)

- [ ] **Step 4: Add schema fields**

In `backend/app/schemas/scholarship.py`, in `EligibleScholarshipResponse` after `terms_document_url: Optional[str] = None` (line 285):

```python
    application_document_note: Optional[str] = None
    application_document_note_en: Optional[str] = None
```

In `backend/app/schemas/application_field.py`, in `ScholarshipFormConfigResponse` after `terms_document_url: Optional[str] = None` (line 179):

```python
    application_document_note: Optional[str] = None
    application_document_note_en: Optional[str] = None
```

- [ ] **Step 5: Thread the note through form-config get/save**

In `backend/app/services/application_field_service.py`:

In `get_scholarship_form_config`, inside the `if scholarship_model:` block (after line 550 `config_data["terms_document_url"] = ...`):

```python
                config_data["application_document_note"] = scholarship_model.application_document_note
                config_data["application_document_note_en"] = scholarship_model.application_document_note_en
```

Replace `save_scholarship_form_config` (lines 562-575) with:

```python
    async def save_scholarship_form_config(
        self,
        scholarship_type: str,
        fields_data: List[Dict[str, Any]],
        documents_data: List[Dict[str, Any]],
        user_id: int,
        application_document_note: Optional[str] = None,
        application_document_note_en: Optional[str] = None,
    ) -> ScholarshipFormConfigResponse:
        """Save complete form configuration for a scholarship type"""

        # Update fields and documents
        fields = await self.bulk_update_fields(scholarship_type, fields_data, user_id)
        documents = await self.bulk_update_documents(scholarship_type, documents_data, user_id)

        # Persist the 申請文件 note on the scholarship type when provided.
        # None means "not part of this save"; empty string clears the note.
        from app.models.scholarship import ScholarshipType

        stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
        result = await self.db.execute(stmt)
        scholarship_model = result.scalar_one_or_none()

        if scholarship_model:
            if application_document_note is not None:
                scholarship_model.application_document_note = application_document_note
            if application_document_note_en is not None:
                scholarship_model.application_document_note_en = application_document_note_en
            await self.db.commit()

        return ScholarshipFormConfigResponse(
            scholarship_type=scholarship_type,
            fields=fields,
            documents=documents,
            application_document_note=scholarship_model.application_document_note if scholarship_model else None,
            application_document_note_en=(
                scholarship_model.application_document_note_en if scholarship_model else None
            ),
        )
```

In `backend/app/api/v1/endpoints/application_fields.py`, extend `FormConfigSaveRequest` (line 261) and the save endpoint call (line 278):

```python
class FormConfigSaveRequest(BaseModel):
    """Schema for saving form configuration"""

    fields: List[Dict[str, Any]]
    documents: List[Dict[str, Any]]
    application_document_note: Optional[str] = None
    application_document_note_en: Optional[str] = None
```

(add `Optional` to the existing `typing` import if missing) and:

```python
    config = await service.save_scholarship_form_config(
        scholarship_type=scholarship_type,
        fields_data=config_data.fields,
        documents_data=config_data.documents,
        user_id=current_user.id,
        application_document_note=config_data.application_document_note,
        application_document_note_en=config_data.application_document_note_en,
    )
```

- [ ] **Step 6: Expose the note on eligible scholarships**

In `backend/app/services/scholarship_service.py`, after `"terms_document_url": scholarship_type.terms_document_url,` (line 203):

```python
                    "application_document_note": scholarship_type.application_document_note,
                    "application_document_note_en": scholarship_type.application_document_note_en,
```

In `backend/app/api/v1/endpoints/scholarships.py`, in the `EligibleScholarshipResponse(...)` construction after `terms_document_url=scholarship.get("terms_document_url"),` (line 248):

```python
            application_document_note=scholarship.get("application_document_note"),
            application_document_note_en=scholarship.get("application_document_note_en"),
```

- [ ] **Step 7: Write the Alembic migration**

Create `backend/alembic/versions/add_app_doc_note_001.py`:

```python
"""Add application_document_note columns to scholarship_types

Revision ID: add_app_doc_note_001
Revises: add_doc_display_upload_flags_001
"""

import sqlalchemy as sa

from alembic import op

revision = "add_app_doc_note_001"
down_revision = "add_doc_display_upload_flags_001"
branch_labels = None
depends_on = None

TABLE = "scholarship_types"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}

    if "application_document_note" not in existing_columns:
        op.add_column(TABLE, sa.Column("application_document_note", sa.Text(), nullable=True))
    if "application_document_note_en" not in existing_columns:
        op.add_column(TABLE, sa.Column("application_document_note_en", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}

    if "application_document_note_en" in existing_columns:
        op.drop_column(TABLE, "application_document_note_en")
    if "application_document_note" in existing_columns:
        op.drop_column(TABLE, "application_document_note")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && <ENV> python -m pytest app/tests/test_application_fields_endpoints.py -p no:cacheprovider --no-cov -v`
Expected: ALL PASS.

Also run the scholarship-side suites that touch the changed serialization:
`cd backend && <ENV> python -m pytest app/tests/test_scholarship_service_pure_helpers.py app/tests/test_admin_scholarships_endpoints.py -p no:cacheprovider --no-cov -q`
Expected: PASS.

- [ ] **Step 9: Verify single alembic head and migration on throwaway DB**

```bash
cd backend && <ENV> alembic heads
```
Expected: exactly one head: `add_app_doc_note_001`.

```bash
docker exec scholarship_postgres_dev psql -U scholarship_user -d scholarship_db -c "DROP DATABASE IF EXISTS docflags_mig_test;" -c "CREATE DATABASE docflags_mig_test;"
cd backend && <ENV with DATABASE_URL and DATABASE_URL_SYNC pointing at .../docflags_mig_test> alembic upgrade head
docker exec scholarship_postgres_dev psql -U scholarship_user -d docflags_mig_test -c "\d application_documents" | grep -E "display_in_list|requires_upload"
docker exec scholarship_postgres_dev psql -U scholarship_user -d docflags_mig_test -c "\d scholarship_types" | grep application_document_note
docker exec scholarship_postgres_dev psql -U scholarship_user -d scholarship_db -c "DROP DATABASE docflags_mig_test;"
```
Expected: all four new columns present with correct types/defaults.

- [ ] **Step 10: Lint and commit**

```bash
cd /home/howard/scholarship-system
uvx --from "black==26.3.1" black --line-length=120 backend/app
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014 --max-line-length=120 && cd ..
git add backend/app/models/scholarship.py backend/app/schemas/scholarship.py backend/app/schemas/application_field.py backend/app/services/application_field_service.py backend/app/services/scholarship_service.py backend/app/api/v1/endpoints/application_fields.py backend/app/api/v1/endpoints/scholarships.py backend/alembic/versions/add_app_doc_note_001.py backend/app/tests/test_application_fields_endpoints.py
git commit -m "feat(api): admin-editable per-scholarship application document note"
```

---

### Task 3: Frontend — types, admin document switches, admin note editor

**Files:**
- Modify: `frontend/lib/api/types.ts:915-1060` (ApplicationDocument, ApplicationDocumentCreate, ApplicationDocumentUpdate, ScholarshipType, ScholarshipFormConfig, FormConfigSaveRequest)
- Modify: `frontend/components/application-document-form.tsx` (formData defaults ~87-141, switches after line 304)
- Modify: `frontend/components/admin-scholarship-management-interface.tsx` (state + loadFormConfig ~166-193, handleSaveSettings ~253-289, note editor Card after the 動態文件 Card ~line 1318ff)
- Test: `frontend/components/__tests__/admin-scholarship-management-interface.test.tsx` (only if it stubs the save payload — extend expected payload; otherwise no test change here, Task 4 has the behavior tests)

**Interfaces:**
- Consumes: backend JSON keys from Tasks 1–2: `display_in_list`, `requires_upload` on documents; `application_document_note`, `application_document_note_en` on form-config GET/save.
- Produces: TypeScript fields used by Task 4:
  - `ApplicationDocument.display_in_list: boolean`, `ApplicationDocument.requires_upload: boolean`
  - `ScholarshipType.application_document_note?: string`, `ScholarshipType.application_document_note_en?: string`

- [ ] **Step 1: Update `frontend/lib/api/types.ts`**

In `export interface ApplicationDocument` (line 915), after `is_required: boolean;`:

```typescript
  display_in_list: boolean;
  requires_upload: boolean;
```

In `export interface ApplicationDocumentCreate` (line 1010), after `is_required?: boolean;`:

```typescript
  display_in_list?: boolean;
  requires_upload?: boolean;
```

In `ApplicationDocumentUpdate` (directly after Create — same additions):

```typescript
  display_in_list?: boolean;
  requires_upload?: boolean;
```

In `export interface ScholarshipType` (line 210), after `terms_document_url?: string;`:

```typescript
  application_document_note?: string;
  application_document_note_en?: string;
```

In `export interface ScholarshipFormConfig` (line 1043), after `terms_document_url?: string;`:

```typescript
  application_document_note?: string;
  application_document_note_en?: string;
```

In `export interface FormConfigSaveRequest` (line 1055), add:

```typescript
  application_document_note?: string;
  application_document_note_en?: string;
```

- [ ] **Step 2: Add the two switches to `application-document-form.tsx`**

In the `useState` initial value (line 87) and the `mode === "create"` reset (line 126), add after `is_required: true,`:

```typescript
    display_in_list: true,
    requires_upload: true,
```

In the `mode === "edit"` init (line 110), add after `is_required: document.is_required,`:

```typescript
        display_in_list: document.display_in_list ?? true,
        requires_upload: document.requires_upload ?? true,
```

In the「檔案要求」card, directly after the existing `is_required` switch block (ends line 304), add:

```tsx
              <div className="flex items-center space-x-2">
                <Switch
                  id="display_in_list"
                  checked={formData.display_in_list ?? true}
                  onCheckedChange={checked =>
                    setFormData(prev => ({ ...prev, display_in_list: checked }))
                  }
                />
                <Label htmlFor="display_in_list">顯示於獎學金列表</Label>
              </div>

              <div className="flex items-center space-x-2">
                <Switch
                  id="requires_upload"
                  checked={formData.requires_upload ?? true}
                  onCheckedChange={checked =>
                    setFormData(prev => ({ ...prev, requires_upload: checked }))
                  }
                />
                <Label htmlFor="requires_upload">需要學生上傳</Label>
              </div>
```

`handleSubmit` spreads `formData`, so no payload change is needed.

- [ ] **Step 3: Persist the flags and the note in `admin-scholarship-management-interface.tsx`**

State — next to the other `useState` declarations (near `const [documentRequirements, ...]`, line 93):

```typescript
  const [appDocNote, setAppDocNote] = useState("");
  const [appDocNoteEn, setAppDocNoteEn] = useState("");
```

In `loadFormConfig` (line 172-177), after `setDocumentRequirements(documents);`:

```typescript
        setAppDocNote(config.application_document_note || "");
        setAppDocNoteEn(config.application_document_note_en || "");
```

In `handleSaveSettings`'s `configData.documents` mapping (line 274-288), add after `is_required: doc.is_required,`:

```typescript
          display_in_list: doc.display_in_list ?? true,
          requires_upload: doc.requires_upload ?? true,
```

and after the `documents:` array in `configData` (line 289), add:

```typescript
        application_document_note: appDocNote,
        application_document_note_en: appDocNoteEn,
```

(Sending `""` clears the note — the backend treats only `null`/absent as "unchanged".)

- [ ] **Step 4: Add the note editor Card**

Immediately after the closing `</Card>` of the「動態文件（可自訂）」card (which starts near line 1318 — find `動態文件（可自訂）` and its card's closing tag), insert:

```tsx
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2 text-lg">
                <FileText className="h-5 w-5 text-blue-600" />
                申請文件說明文字
              </CardTitle>
              <CardDescription className="text-gray-600">
                顯示在學生申請步驟3「申請文件」區塊下方的說明文字，留空則不顯示
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="app-doc-note">說明文字（中文）</Label>
                <Textarea
                  id="app-doc-note"
                  value={appDocNote}
                  onChange={e => setAppDocNote(e.target.value)}
                  placeholder="例如：請將所有文件合併為單一 PDF 檔案上傳"
                  rows={3}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="app-doc-note-en">說明文字（英文）</Label>
                <Textarea
                  id="app-doc-note-en"
                  value={appDocNoteEn}
                  onChange={e => setAppDocNoteEn(e.target.value)}
                  placeholder="e.g., Please merge all documents into a single PDF file"
                  rows={3}
                />
              </div>
            </CardContent>
          </Card>
```

If `Textarea` / `Label` are not yet imported in this file, add `import { Textarea } from "@/components/ui/textarea";` / `import { Label } from "@/components/ui/label";`.

- [ ] **Step 5: Type-check and run the admin interface tests**

Run: `cd frontend && npx tsc --noEmit`
Expected: no NEW errors in the touched files (the repo may have pre-existing errors elsewhere — compare against `git stash`-free baseline only if unsure).

Run: `cd frontend && npx jest components/__tests__/admin-scholarship-management-interface.test.tsx --watchAll=false`
Expected: PASS. If a test asserts the exact `saveFormConfig` payload, extend the expected object with the four new keys (`display_in_list: true`, `requires_upload: true` per document; `application_document_note: ""`, `application_document_note_en: ""`).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api/types.ts frontend/components/application-document-form.tsx frontend/components/admin-scholarship-management-interface.tsx frontend/components/__tests__/admin-scholarship-management-interface.test.tsx
git commit -m "feat(frontend): admin switches for document display/upload and application-document note editor"
```

---

### Task 4: Frontend — student-side filters and note display

**Files:**
- Modify: `frontend/lib/utils/application-helpers.ts` (new helpers at end of file)
- Test: `frontend/lib/utils/__tests__/application-helpers.test.ts` (append)
- Modify: `frontend/components/enhanced-student-portal.tsx:508-560` (progress copy) and `:1888-1940` (list boxes)
- Modify: `frontend/components/dynamic-application-form.tsx:805-807` (activeDocuments)
- Modify: `frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx:784-786` (progress filter) and `:1723-1730` (note display)

**Interfaces:**
- Consumes: `ApplicationDocument.display_in_list` / `.requires_upload`, `ScholarshipType.application_document_note(_en)` from Task 3.
- Produces (in `application-helpers.ts`):

```typescript
export const isDocumentListedInScholarshipCard = (doc: {
  is_active: boolean;
  display_in_list?: boolean;
}): boolean => doc.is_active && doc.display_in_list !== false;

export const isDocumentUploadRequired = (doc: {
  is_active: boolean;
  is_required: boolean;
  requires_upload?: boolean;
  is_fixed?: boolean;
}): boolean =>
  doc.is_active && doc.is_required && doc.requires_upload !== false && !doc.is_fixed;
```

- [ ] **Step 1: Write failing helper tests**

Append to `frontend/lib/utils/__tests__/application-helpers.test.ts`:

```typescript
import {
  isDocumentListedInScholarshipCard,
  isDocumentUploadRequired,
} from "../application-helpers";

describe("isDocumentListedInScholarshipCard", () => {
  it("shows active documents by default (flag missing)", () => {
    expect(isDocumentListedInScholarshipCard({ is_active: true })).toBe(true);
  });

  it("hides documents with display_in_list=false", () => {
    expect(
      isDocumentListedInScholarshipCard({ is_active: true, display_in_list: false })
    ).toBe(false);
  });

  it("hides inactive documents regardless of flag", () => {
    expect(
      isDocumentListedInScholarshipCard({ is_active: false, display_in_list: true })
    ).toBe(false);
  });
});

describe("isDocumentUploadRequired", () => {
  const base = { is_active: true, is_required: true };

  it("requires upload by default (flag missing)", () => {
    expect(isDocumentUploadRequired(base)).toBe(true);
  });

  it("does not require upload when requires_upload=false", () => {
    expect(isDocumentUploadRequired({ ...base, requires_upload: false })).toBe(false);
  });

  it("excludes fixed documents", () => {
    expect(isDocumentUploadRequired({ ...base, is_fixed: true })).toBe(false);
  });

  it("excludes optional documents", () => {
    expect(
      isDocumentUploadRequired({ is_active: true, is_required: false })
    ).toBe(false);
  });

  it("excludes inactive documents", () => {
    expect(isDocumentUploadRequired({ ...base, is_active: false })).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx jest lib/utils/__tests__/application-helpers.test.ts --watchAll=false`
Expected: FAIL — `isDocumentListedInScholarshipCard is not a function` (module has no such export).

- [ ] **Step 3: Implement the helpers**

Append to `frontend/lib/utils/application-helpers.ts` (exact code from the Interfaces block above, with a short doc comment):

```typescript
// Admin-configurable document visibility (see application_documents.display_in_list
// / requires_upload). `!== false` keeps pre-flag API payloads behaving as before.
export const isDocumentListedInScholarshipCard = (doc: {
  is_active: boolean;
  display_in_list?: boolean;
}): boolean => doc.is_active && doc.display_in_list !== false;

export const isDocumentUploadRequired = (doc: {
  is_active: boolean;
  is_required: boolean;
  requires_upload?: boolean;
  is_fixed?: boolean;
}): boolean =>
  doc.is_active && doc.is_required && doc.requires_upload !== false && !doc.is_fixed;
```

- [ ] **Step 4: Run helper tests to verify pass**

Run: `cd frontend && npx jest lib/utils/__tests__/application-helpers.test.ts --watchAll=false`
Expected: PASS.

- [ ] **Step 5: Apply the filters at all four call sites**

1. `frontend/components/enhanced-student-portal.tsx` — Required Documents box (line ~1890):

```typescript
                                {applicationInfo.documents
                                  .filter(
                                    doc =>
                                      doc.is_required &&
                                      isDocumentListedInScholarshipCard(doc)
                                  )
```

2. Same file — Optional Documents box: both the outer guard (line ~1915) and inner map filter (line ~1932) become:

```typescript
                                    doc =>
                                      !doc.is_required &&
                                      isDocumentListedInScholarshipCard(doc)
```

3. Same file — progress calculation (line ~510):

```typescript
        const requiredDocuments = documents.filter(isDocumentUploadRequired);
```

4. `frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx` — `calculateProgress` (line 784-786):

```typescript
      const requiredDocuments = documents.filter(isDocumentUploadRequired);
```

5. `frontend/components/dynamic-application-form.tsx` — `activeDocuments` (line 805-807):

```typescript
  const activeDocuments = formConfig.documents
    .filter(doc => doc.is_active && !doc.is_fixed && doc.requires_upload !== false)
    .sort((a, b) => a.display_order - b.display_order);
```

Add the corresponding imports from `@/lib/utils/application-helpers` in `enhanced-student-portal.tsx` and `ScholarshipApplicationStep.tsx` (the latter already imports from that module — extend the existing import).

- [ ] **Step 6: Render the note under the 申請文件 header**

In `frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx`, add near the other derived values before the return (e.g. right above the `return (` of the main render):

```typescript
  const applicationDocumentNote = selectedScholarship
    ? locale === "zh"
      ? selectedScholarship.application_document_note
      : selectedScholarship.application_document_note_en ||
        selectedScholarship.application_document_note
    : null;
```

Then in the Application Document Upload section, directly after the `<h4>…{text.applicationDocument}</h4>` closing tag (line ~1729), add:

```tsx
              {applicationDocumentNote && (
                <p className="text-sm text-gray-600 whitespace-pre-line mb-4">
                  {applicationDocumentNote}
                </p>
              )}
```

- [ ] **Step 7: Type-check and run affected component tests**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

Run: `cd frontend && npx jest components/__tests__/enhanced-student-portal.test.tsx lib/utils/__tests__/application-helpers.test.ts --watchAll=false`
Expected: PASS (if the portal test's fixture documents now get filtered out because they lack the new flags, the `!== false` semantics keep them visible — no fixture change should be needed; if one fails, add `display_in_list: true, requires_upload: true` to its document fixtures).

- [ ] **Step 8: Commit**

```bash
git add frontend/lib/utils/application-helpers.ts frontend/lib/utils/__tests__/application-helpers.test.ts frontend/components/enhanced-student-portal.tsx frontend/components/dynamic-application-form.tsx frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx
git commit -m "feat(frontend): honor document display/upload flags and show application-document note"
```

---

### Task 5: OpenAPI types, full verification, PR

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts` (regenerated)

**Interfaces:**
- Consumes: the backend app from Tasks 1–2 (its OpenAPI spec now includes the new fields).
- Produces: regenerated `schema.d.ts` (CI validates sync).

- [ ] **Step 1: Regenerate OpenAPI types from THIS checkout's app**

The running dev backend may serve a different worktree, so dump the spec from this checkout instead of `npm run api:generate`:

```bash
cd backend && <ENV> python -c "
import json
from app.main import app
print(json.dumps(app.openapi()))
" > /tmp/claude-1001/-home-howard-scholarship-system/37be4ee6-7cfb-4f80-81c0-a369fd2d24ce/scratchpad/openapi.json
cd ../frontend && npx openapi-typescript /tmp/claude-1001/-home-howard-scholarship-system/37be4ee6-7cfb-4f80-81c0-a369fd2d24ce/scratchpad/openapi.json -o ./lib/api/generated/schema.d.ts
```

Expected: `schema.d.ts` diff shows `display_in_list`, `requires_upload`, `application_document_note`, `application_document_note_en`.

- [ ] **Step 2: Full backend test files for touched modules**

```bash
cd backend && <ENV> python -m pytest app/tests/test_application_fields_endpoints.py app/tests/test_application_field_models.py app/tests/test_application_field_service_unit.py app/tests/test_application_field_defaults.py app/tests/test_application_field_fixed_builders.py app/tests/test_admin_scholarships_endpoints.py -p no:cacheprovider --no-cov -q
```
Expected: ALL PASS.

- [ ] **Step 3: Frontend test suite (touched areas) + lint**

```bash
cd frontend && npx jest components/__tests__/admin-scholarship-management-interface.test.tsx components/__tests__/enhanced-student-portal.test.tsx lib/utils/__tests__/application-helpers.test.ts --watchAll=false
cd frontend && npx tsc --noEmit
cd /home/howard/scholarship-system && uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014 --max-line-length=120
```
Expected: all pass.

- [ ] **Step 4: Commit regenerated types**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore(frontend): regenerate OpenAPI types for document flags and note"
```

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin feat/document-display-upload-config
gh pr create --title "feat: admin-configurable document display/upload flags and 申請文件 note" --body "$(cat <<'EOF'
## Summary
- Add `display_in_list` / `requires_upload` switches to each application document (admin 文件設定 dialog); the scholarship-list card only shows documents with 顯示於獎學金列表, and step 3 only renders/enforces uploads for documents with 需要學生上傳
- Add per-scholarship admin-editable 說明文字 shown under the 申請文件 section in wizard step 3 (`scholarship_types.application_document_note(_en)`), edited in the scholarship form-config page
- Both new document flags default to true — existing configurations behave exactly as before

## Test plan
- [ ] Backend: `test_application_fields_endpoints.py` (flags CRUD roundtrip, form-config note roundtrip)
- [ ] Frontend: helper unit tests for the two visibility predicates; admin interface + portal suites
- [ ] Migrations apply cleanly on a fresh DB (verified on throwaway Postgres DB)
- [ ] Manual: toggle both switches on a document, confirm list box + step 3 behavior; set/clear the note, confirm step 3 display

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_012pre6cVuVCM1kx59zp18xQ
EOF
)"
```

- [ ] **Step 6: End-to-end verification on localhost (after PR)**

Use the playwright-test-and-debug skill flow: log in as `admin`, open a scholarship's form config, toggle 需要學生上傳 off for one document and set a note; then log in as an eligible student (`stuphd001`), confirm the list box hides/shows accordingly, step 3 omits the upload widget, submit gating ignores that document, and the note appears under 申請文件.
