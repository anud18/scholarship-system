# Supplementary System Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins upload an arbitrary number of supplementary reference documents (in addition to the existing fixed `regulations_url` and `sample_document_url` slots) and have students see them on the 申請須知 step inside a new 參考文件 list, with drag-and-drop ordering on the admin side.

**Architecture:** New `supplementary_docs` SQLAlchemy table (independent of `system_settings`). Six new endpoints under `/api/v1/system-settings/supplementary-docs`. Admin manages docs in a new sub-section of `SystemDocsPanel`. Students see them inside a new 參考文件 list inside `NoticeAgreementStep`. Two new Next.js proxy routes (`supp-file-proxy`, `supp-upload-proxy`) sit next to the existing ones.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic + Pydantic v2 (backend). Next.js 14 / React + `@dnd-kit/sortable` (already installed) + Jest + Testing Library + Playwright (frontend). PostgreSQL + MinIO.

**Spec:** `docs/superpowers/specs/2026-05-27-supplementary-system-docs-design.md`

---

## File Structure

### Backend

| Path | Action | Responsibility |
|------|--------|----------------|
| `backend/app/models/supplementary_doc.py` | create | SQLAlchemy `SupplementaryDoc` model |
| `backend/app/schemas/supplementary_doc.py` | create | Pydantic schemas (create, update, response, reorder item) |
| `backend/alembic/versions/add_supp_docs_001_add_supplementary_docs_table.py` | create | Migration |
| `backend/app/api/v1/endpoints/system_settings.py` | edit | Append 6 new endpoints (list, upload, update, delete, reorder, file) |
| `backend/app/tests/test_supplementary_docs.py` | create | All endpoint tests |

### Frontend

| Path | Action | Responsibility |
|------|--------|----------------|
| `frontend/lib/api/modules/system-settings.ts` | edit | Add `supplementaryDocs` namespace, `buildSuppDocFileProxyUrl`, `SupplementaryDoc` type |
| `frontend/lib/api/generated/schema.d.ts` | regenerate | OpenAPI typegen output |
| `frontend/app/api/v1/system-settings/supp-file-proxy/route.ts` | create | GET proxy for `/supplementary-docs/{id}/file` |
| `frontend/app/api/v1/system-settings/supp-upload-proxy/route.ts` | create | POST proxy for `/supplementary-docs` upload |
| `frontend/components/admin/system-docs/AddSupplementaryDocDialog.tsx` | create | Upload dialog (title + dropzone) |
| `frontend/components/admin/system-docs/SupplementaryDocsList.tsx` | create | Drag-sort list + row actions (preview / edit title / delete) |
| `frontend/components/admin/system-docs/SystemDocsPanel.tsx` | edit | Mount `<SupplementaryDocsList />` below existing 2 fixed slots |
| `frontend/components/admin/system-docs/__tests__/SupplementaryDocsList.test.tsx` | create | Component tests |
| `frontend/components/student-wizard/steps/NoticeAgreementStep.tsx` | edit | Replace sample-doc row with 參考文件 list, fetch supplementary docs, drop `sampleDocumentRow` copy |
| `frontend/components/__tests__/notice-agreement-step.test.tsx` | edit | Add cases for supplementary docs rendering / hidden when empty |

---

## Conventions Used in This Plan

- **Branch / worktree:** Implementation may happen in a feature branch; the user will choose. Run all `git` commands from repo root.
- **Backend tests:** `pytest` invoked from `backend/` directory. Existing fixtures (`admin_client`, `fake_minio`, `db`) come from `backend/app/tests/test_system_settings_upload_doc.py` and the project-wide `conftest.py`. Reuse those patterns.
- **Async SQLAlchemy:** the existing `system_settings.py` endpoints use `AsyncSession`. New endpoints follow the same pattern (`from sqlalchemy import select`, `await db.execute(...)`, `await db.commit()`).
- **API response envelope:** `{success, message, data}` per `CLAUDE.md` § 5. No `response_model=` decorator.
- **Frontend tests:** Jest + Testing Library. Mock `lib/api` via `jest.mock(...)` (see `frontend/components/__tests__/notice-agreement-step.test.tsx` for the existing pattern).
- **FastAPI route ordering:** literal paths (`/reorder`) MUST be registered BEFORE parameterized ones (`/{id}`) on the same method, otherwise the path param swallows the literal. See Task 9 for the explicit ordering.

---

## Task 1: SQLAlchemy Model

**Files:**
- Create: `backend/app/models/supplementary_doc.py`

- [ ] **Step 1: Create the model file**

```python
# backend/app/models/supplementary_doc.py
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class SupplementaryDoc(Base):
    """Admin-managed supplementary reference document shown to students
    in the application wizard's 參考文件 list."""

    __tablename__ = "supplementary_docs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    object_name = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    created_by_user = relationship("User", foreign_keys=[created_by])
```

- [ ] **Step 2: Register model with Base metadata**

Check `backend/app/models/__init__.py` (or wherever models are imported for Alembic autogeneration). If models are explicitly imported there, add:

```python
from app.models.supplementary_doc import SupplementaryDoc  # noqa: F401
```

If `__init__.py` does not exist or does not import siblings, no edit needed — Alembic env.py imports `app.db.base` which transitively imports all models via a registry.

To verify, run:

```bash
cd backend && python -c "from app.models.supplementary_doc import SupplementaryDoc; print(SupplementaryDoc.__tablename__)"
```

Expected output: `supplementary_docs`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/supplementary_doc.py
[ -f backend/app/models/__init__.py ] && git add backend/app/models/__init__.py
git commit -m "feat: add SupplementaryDoc SQLAlchemy model"
```

---

## Task 2: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/supplementary_doc.py`

- [ ] **Step 1: Write the schemas**

```python
# backend/app/schemas/supplementary_doc.py
from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SupplementaryDocResponse(BaseModel):
    id: int
    title: str
    object_name: str
    original_filename: str
    content_type: str
    file_size: int
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupplementaryDocUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title cannot be empty")
        return stripped


class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    items: List[ReorderItem] = Field(..., min_length=1)

    @field_validator("items")
    @classmethod
    def _unique_orders(cls, v: List[ReorderItem]) -> List[ReorderItem]:
        orders = [i.sort_order for i in v]
        if len(orders) != len(set(orders)):
            raise ValueError("sort_order values must be unique within payload")
        ids = [i.id for i in v]
        if len(ids) != len(set(ids)):
            raise ValueError("id values must be unique within payload")
        return v
```

- [ ] **Step 2: Verify it imports**

```bash
cd backend && python -c "from app.schemas.supplementary_doc import SupplementaryDocResponse, SupplementaryDocUpdate, ReorderRequest, ReorderItem; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/supplementary_doc.py
git commit -m "feat: add SupplementaryDoc Pydantic schemas"
```

---

## Task 3: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/add_supp_docs_001_add_supplementary_docs_table.py`

- [ ] **Step 1: Detect current head**

```bash
cd backend && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"
```

Expected: a list containing exactly one head (at spec time: `['merge_renewal_main_001']`). Use the printed value as `down_revision` below. If the head differs from `merge_renewal_main_001`, substitute the actual value.

- [ ] **Step 2: Write the migration file**

```python
# backend/alembic/versions/add_supp_docs_001_add_supplementary_docs_table.py
"""add supplementary_docs table

Revision ID: add_supp_docs_001
Revises: merge_renewal_main_001
Create Date: 2026-05-27

"""
from alembic import op
import sqlalchemy as sa


revision = "add_supp_docs_001"
down_revision = "merge_renewal_main_001"  # replace with current head if different
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "supplementary_docs" not in inspector.get_table_names():
        op.create_table(
            "supplementary_docs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("object_name", sa.String(length=500), nullable=False),
            sa.Column("original_filename", sa.String(length=500), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column(
                "sort_order",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "created_by",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "idx_supp_docs_sort",
            "supplementary_docs",
            ["sort_order"],
        )


def downgrade() -> None:
    op.drop_index("idx_supp_docs_sort", table_name="supplementary_docs")
    op.drop_table("supplementary_docs")
```

- [ ] **Step 3: Apply the migration**

```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

Expected: log line containing `Running upgrade ... -> add_supp_docs_001`.

- [ ] **Step 4: Verify the table exists**

```bash
docker compose -f docker-compose.dev.yml exec postgres psql -U scholarship_user -d scholarship_db -c "\d supplementary_docs"
```

Expected: table description showing all columns from Step 2.

- [ ] **Step 5: Verify downgrade also works**

```bash
docker compose -f docker-compose.dev.yml exec backend alembic downgrade -1
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

Both should succeed with no error output.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/add_supp_docs_001_add_supplementary_docs_table.py
git commit -m "feat: add migration for supplementary_docs table"
```

---

## Task 4: Test Fixture for SupplementaryDoc

**Files:**
- Create: `backend/app/tests/test_supplementary_docs.py`

- [ ] **Step 1: Create the file with imports + shared fixtures**

```python
# backend/app/tests/test_supplementary_docs.py
"""Tests for supplementary docs endpoints in system_settings.py.

Covers list / upload / update title / delete / reorder / file streaming.
Mirrors the patterns used in test_system_settings_upload_doc.py
(fake_minio + admin_client overrides).
"""

from io import BytesIO
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin
from app.db.deps import get_db
from app.main import app
from app.models.supplementary_doc import SupplementaryDoc
from app.models.user import User, UserRole, UserType


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    admin = User(
        nycu_id="suppdocs_admin",
        name="Supp Docs Admin",
        email="suppdocs_admin@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def student_user(db: AsyncSession) -> User:
    student = User(
        nycu_id="suppdocs_student",
        name="Supp Docs Student",
        email="suppdocs_student@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    await db.commit()
    await db.refresh(student)
    return student


@pytest_asyncio.fixture
async def admin_client(db: AsyncSession, admin_user: User) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db

    async def override_get_current_user():
        return admin_user

    async def override_require_admin():
        return admin_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_admin] = override_require_admin
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def student_client(db: AsyncSession, student_user: User) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db

    async def override_get_current_user():
        return student_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def fake_minio():
    with patch("app.services.minio_service.minio_service") as mock_service:
        mock_service.client = MagicMock()
        mock_service.default_bucket = "scholarship-system"
        yield mock_service
```

- [ ] **Step 2: Run the empty file to verify fixtures import**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py -v
```

Expected: collected 0 items (no tests yet, no errors).

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests/test_supplementary_docs.py
git commit -m "test: scaffold supplementary docs test fixtures"
```

---

## Task 5: List Endpoint (TDD)

**Files:**
- Modify: `backend/app/api/v1/endpoints/system_settings.py`
- Modify: `backend/app/tests/test_supplementary_docs.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/app/tests/test_supplementary_docs.py`:

```python
class TestListSupplementaryDocs:
    @pytest.mark.asyncio
    async def test_list_empty(self, admin_client: AsyncClient):
        response = await admin_client.get("/api/v1/system-settings/supplementary-docs")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_list_sorted_by_sort_order_then_id(
        self, admin_client: AsyncClient, db: AsyncSession
    ):
        db.add_all([
            SupplementaryDoc(
                title="C", object_name="system-docs/c.pdf", original_filename="c.pdf",
                content_type="application/pdf", file_size=10, sort_order=2,
            ),
            SupplementaryDoc(
                title="A", object_name="system-docs/a.pdf", original_filename="a.pdf",
                content_type="application/pdf", file_size=10, sort_order=0,
            ),
            SupplementaryDoc(
                title="B", object_name="system-docs/b.pdf", original_filename="b.pdf",
                content_type="application/pdf", file_size=10, sort_order=1,
            ),
        ])
        await db.commit()

        response = await admin_client.get("/api/v1/system-settings/supplementary-docs")
        body = response.json()
        titles = [item["title"] for item in body["data"]]
        assert titles == ["A", "B", "C"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestListSupplementaryDocs -v
```

Expected: 2 failures, both 404 (route not registered yet).

- [ ] **Step 3: Add the endpoint**

In `backend/app/api/v1/endpoints/system_settings.py`, append AFTER the existing `get_system_doc_file` function (around line 295) and BEFORE the `@router.get("/{id}")` route at line 297. This ordering ensures the literal `/supplementary-docs` prefix is matched before the catch-all `/{id}`:

```python
# ---------------------------------------------------------------------------
# Supplementary documents (admin-managed, arbitrary count)
# ---------------------------------------------------------------------------

from app.models.supplementary_doc import SupplementaryDoc  # noqa: E402
from app.schemas.supplementary_doc import (  # noqa: E402
    ReorderRequest,
    SupplementaryDocResponse,
    SupplementaryDocUpdate,
)


@router.get("/supplementary-docs")
async def list_supplementary_docs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    stmt = select(SupplementaryDoc).order_by(
        SupplementaryDoc.sort_order.asc(),
        SupplementaryDoc.id.asc(),
    )
    result = await db.execute(stmt)
    docs = result.scalars().all()
    return {
        "success": True,
        "message": "OK",
        "data": [SupplementaryDocResponse.model_validate(d).model_dump(mode="json") for d in docs],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestListSupplementaryDocs -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/system_settings.py backend/app/tests/test_supplementary_docs.py
git commit -m "feat: add list supplementary-docs endpoint"
```

---

## Task 6: Upload Endpoint (TDD)

**Files:**
- Modify: `backend/app/api/v1/endpoints/system_settings.py`
- Modify: `backend/app/tests/test_supplementary_docs.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/app/tests/test_supplementary_docs.py`:

```python
class TestUploadSupplementaryDoc:
    @pytest.mark.asyncio
    async def test_admin_uploads_pdf(self, admin_client: AsyncClient, fake_minio, db: AsyncSession):
        file_bytes = b"%PDF-1.4 test"
        response = await admin_client.post(
            "/api/v1/system-settings/supplementary-docs",
            data={"title": "FAQ"},
            files={"file": ("faq.pdf", BytesIO(file_bytes), "application/pdf")},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["data"]["title"] == "FAQ"
        assert body["data"]["original_filename"] == "faq.pdf"
        assert body["data"]["content_type"] == "application/pdf"
        assert body["data"]["file_size"] == len(file_bytes)
        assert body["data"]["object_name"].startswith("system-docs/supp_")
        fake_minio.client.put_object.assert_called_once()

        from sqlalchemy import select
        rows = (await db.execute(select(SupplementaryDoc))).scalars().all()
        assert len(rows) == 1
        assert rows[0].title == "FAQ"

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, student_client: AsyncClient, fake_minio):
        response = await student_client.post(
            "/api/v1/system-settings/supplementary-docs",
            data={"title": "FAQ"},
            files={"file": ("faq.pdf", BytesIO(b"%PDF"), "application/pdf")},
        )
        assert response.status_code == 403
        fake_minio.client.put_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_disallowed_extension(
        self, admin_client: AsyncClient, fake_minio
    ):
        response = await admin_client.post(
            "/api/v1/system-settings/supplementary-docs",
            data={"title": "EXE"},
            files={"file": ("evil.exe", BytesIO(b"MZ"), "application/octet-stream")},
        )
        assert response.status_code in (400, 415)
        fake_minio.client.put_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_oversize(self, admin_client: AsyncClient, fake_minio):
        big = b"%PDF" + b"\x00" * (11 * 1024 * 1024)
        response = await admin_client.post(
            "/api/v1/system-settings/supplementary-docs",
            data={"title": "Big"},
            files={"file": ("big.pdf", BytesIO(big), "application/pdf")},
        )
        assert response.status_code in (400, 413)
        fake_minio.client.put_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_empty_title(self, admin_client: AsyncClient, fake_minio):
        response = await admin_client.post(
            "/api/v1/system-settings/supplementary-docs",
            data={"title": "   "},
            files={"file": ("ok.pdf", BytesIO(b"%PDF"), "application/pdf")},
        )
        assert response.status_code == 400
        fake_minio.client.put_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_too_long_title(self, admin_client: AsyncClient, fake_minio):
        response = await admin_client.post(
            "/api/v1/system-settings/supplementary-docs",
            data={"title": "x" * 201},
            files={"file": ("ok.pdf", BytesIO(b"%PDF"), "application/pdf")},
        )
        assert response.status_code == 400
        fake_minio.client.put_object.assert_not_called()
```

- [ ] **Step 2: Run failing tests**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestUploadSupplementaryDoc -v
```

Expected: 6 failures (all routes return 404 / 405).

- [ ] **Step 3: Add the endpoint**

In `backend/app/api/v1/endpoints/system_settings.py`, append AFTER the list endpoint from Task 5:

```python
@router.post("/supplementary-docs")
async def create_supplementary_doc(
    file: UploadFile = File(...),
    title: str = Form(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    import io
    import uuid

    from app.core.path_security import validate_upload_file
    from app.services.minio_service import minio_service

    stripped_title = (title or "").strip()
    if not stripped_title:
        raise HTTPException(status_code=400, detail="title cannot be empty")
    if len(stripped_title) > 200:
        raise HTTPException(status_code=400, detail="title must be <= 200 chars")

    allowed_extensions = [".pdf", ".doc", ".docx"]
    file_content = await file.read()
    validate_upload_file(
        filename=file.filename,
        allowed_extensions=allowed_extensions,
        max_size_mb=10,
        file_size=len(file_content),
        allow_unicode=True,
    )

    ext = ""
    if file.filename:
        for e in allowed_extensions:
            if file.filename.lower().endswith(e):
                ext = e
                break

    object_name = f"system-docs/supp_{uuid.uuid4().hex}{ext}"

    minio_service.client.put_object(
        bucket_name=minio_service.default_bucket,
        object_name=object_name,
        data=io.BytesIO(file_content),
        length=len(file_content),
        content_type=file.content_type or "application/octet-stream",
    )

    doc = SupplementaryDoc(
        title=stripped_title,
        object_name=object_name,
        original_filename=file.filename or "",
        content_type=file.content_type or "application/octet-stream",
        file_size=len(file_content),
        sort_order=0,
        created_by=current_user.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return {
        "success": True,
        "message": "上傳成功",
        "data": SupplementaryDocResponse.model_validate(doc).model_dump(mode="json"),
    }
```

Also add `Form` to the existing FastAPI import at the top of `system_settings.py`:

```python
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestUploadSupplementaryDoc -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/system_settings.py backend/app/tests/test_supplementary_docs.py
git commit -m "feat: add upload supplementary-doc endpoint"
```

---

## Task 7: Update Title Endpoint (TDD)

**Files:**
- Modify: `backend/app/api/v1/endpoints/system_settings.py`
- Modify: `backend/app/tests/test_supplementary_docs.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/app/tests/test_supplementary_docs.py`:

```python
class TestUpdateSupplementaryDocTitle:
    @pytest.mark.asyncio
    async def test_admin_updates_title(self, admin_client: AsyncClient, db: AsyncSession):
        doc = SupplementaryDoc(
            title="Old", object_name="system-docs/x.pdf", original_filename="x.pdf",
            content_type="application/pdf", file_size=10, sort_order=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        response = await admin_client.patch(
            f"/api/v1/system-settings/supplementary-docs/{doc.id}",
            json={"title": "New Title"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["data"]["title"] == "New Title"

        await db.refresh(doc)
        assert doc.title == "New Title"
        assert doc.object_name == "system-docs/x.pdf"  # unchanged

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, admin_client: AsyncClient):
        response = await admin_client.patch(
            "/api/v1/system-settings/supplementary-docs/9999",
            json={"title": "x"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_empty_title_rejected(self, admin_client: AsyncClient, db: AsyncSession):
        doc = SupplementaryDoc(
            title="Old", object_name="system-docs/x.pdf", original_filename="x.pdf",
            content_type="application/pdf", file_size=10, sort_order=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        response = await admin_client.patch(
            f"/api/v1/system-settings/supplementary-docs/{doc.id}",
            json={"title": "   "},
        )
        assert response.status_code == 422
```

- [ ] **Step 2: Run failing tests**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestUpdateSupplementaryDocTitle -v
```

Expected: 3 failures.

- [ ] **Step 3: Add the endpoint** (insert AFTER the upload endpoint, still BEFORE `@router.get("/{id}")`)

```python
@router.patch("/supplementary-docs/reorder")
async def reorder_supplementary_docs(
    payload: ReorderRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Placeholder body — implementation lands in Task 9. We register the
    # literal "/reorder" route here so it is matched BEFORE the parametric
    # "/{doc_id}" routes added below. Returning 501 keeps the tests for the
    # other endpoints honest until Task 9.
    raise HTTPException(status_code=501, detail="not implemented")


@router.patch("/supplementary-docs/{doc_id}")
async def update_supplementary_doc(
    doc_id: int,
    payload: SupplementaryDocUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    stmt = select(SupplementaryDoc).where(SupplementaryDoc.id == doc_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="not found")

    doc.title = payload.title
    await db.commit()
    await db.refresh(doc)

    return {
        "success": True,
        "message": "已更新",
        "data": SupplementaryDocResponse.model_validate(doc).model_dump(mode="json"),
    }
```

The placeholder PATCH `/reorder` is required so FastAPI's path resolver matches `/reorder` before `/{doc_id}` (FastAPI walks routes in registration order). Task 9 replaces the body.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestUpdateSupplementaryDocTitle -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/system_settings.py backend/app/tests/test_supplementary_docs.py
git commit -m "feat: add update supplementary-doc title endpoint"
```

---

## Task 8: Delete Endpoint (TDD)

**Files:**
- Modify: `backend/app/api/v1/endpoints/system_settings.py`
- Modify: `backend/app/tests/test_supplementary_docs.py`

- [ ] **Step 1: Write failing tests**

```python
class TestDeleteSupplementaryDoc:
    @pytest.mark.asyncio
    async def test_admin_deletes(
        self, admin_client: AsyncClient, fake_minio, db: AsyncSession
    ):
        doc = SupplementaryDoc(
            title="X", object_name="system-docs/x.pdf", original_filename="x.pdf",
            content_type="application/pdf", file_size=10, sort_order=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        doc_id = doc.id

        response = await admin_client.delete(
            f"/api/v1/system-settings/supplementary-docs/{doc_id}"
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        fake_minio.client.remove_object.assert_called_once_with(
            "scholarship-system", "system-docs/x.pdf"
        )

        from sqlalchemy import select
        rows = (
            await db.execute(select(SupplementaryDoc).where(SupplementaryDoc.id == doc_id))
        ).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_delete_missing_returns_404(self, admin_client: AsyncClient, fake_minio):
        response = await admin_client.delete(
            "/api/v1/system-settings/supplementary-docs/99999"
        )
        assert response.status_code == 404
        fake_minio.client.remove_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_succeeds_even_when_minio_fails(
        self, admin_client: AsyncClient, fake_minio, db: AsyncSession
    ):
        doc = SupplementaryDoc(
            title="X", object_name="system-docs/x.pdf", original_filename="x.pdf",
            content_type="application/pdf", file_size=10, sort_order=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        fake_minio.client.remove_object.side_effect = RuntimeError("boom")

        response = await admin_client.delete(
            f"/api/v1/system-settings/supplementary-docs/{doc.id}"
        )
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True
```

- [ ] **Step 2: Run failing tests**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestDeleteSupplementaryDoc -v
```

Expected: 3 failures.

- [ ] **Step 3: Add the endpoint** (insert AFTER the update endpoint from Task 7)

```python
@router.delete("/supplementary-docs/{doc_id}")
async def delete_supplementary_doc(
    doc_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.services.minio_service import minio_service

    stmt = select(SupplementaryDoc).where(SupplementaryDoc.id == doc_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="not found")

    object_name = doc.object_name
    await db.delete(doc)
    await db.commit()

    try:
        minio_service.client.remove_object(minio_service.default_bucket, object_name)
    except Exception:
        logger.warning(
            "Failed to remove supplementary doc object %s from MinIO",
            object_name,
            exc_info=True,
        )

    return {
        "success": True,
        "message": "已刪除",
        "data": {"deleted": True},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestDeleteSupplementaryDoc -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/system_settings.py backend/app/tests/test_supplementary_docs.py
git commit -m "feat: add delete supplementary-doc endpoint"
```

---

## Task 9: Reorder Endpoint (TDD)

**Files:**
- Modify: `backend/app/api/v1/endpoints/system_settings.py`
- Modify: `backend/app/tests/test_supplementary_docs.py`

- [ ] **Step 1: Write failing tests**

```python
class TestReorderSupplementaryDocs:
    @pytest.mark.asyncio
    async def test_admin_reorders(self, admin_client: AsyncClient, db: AsyncSession):
        a = SupplementaryDoc(
            title="A", object_name="system-docs/a.pdf", original_filename="a.pdf",
            content_type="application/pdf", file_size=10, sort_order=0,
        )
        b = SupplementaryDoc(
            title="B", object_name="system-docs/b.pdf", original_filename="b.pdf",
            content_type="application/pdf", file_size=10, sort_order=1,
        )
        db.add_all([a, b])
        await db.commit()
        await db.refresh(a)
        await db.refresh(b)

        response = await admin_client.patch(
            "/api/v1/system-settings/supplementary-docs/reorder",
            json={"items": [
                {"id": a.id, "sort_order": 1},
                {"id": b.id, "sort_order": 0},
            ]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["updated"] == 2

        list_response = await admin_client.get(
            "/api/v1/system-settings/supplementary-docs"
        )
        titles = [item["title"] for item in list_response.json()["data"]]
        assert titles == ["B", "A"]

    @pytest.mark.asyncio
    async def test_reorder_with_missing_id_400_and_no_changes(
        self, admin_client: AsyncClient, db: AsyncSession
    ):
        a = SupplementaryDoc(
            title="A", object_name="system-docs/a.pdf", original_filename="a.pdf",
            content_type="application/pdf", file_size=10, sort_order=0,
        )
        db.add(a)
        await db.commit()
        await db.refresh(a)

        response = await admin_client.patch(
            "/api/v1/system-settings/supplementary-docs/reorder",
            json={"items": [
                {"id": a.id, "sort_order": 5},
                {"id": 99999, "sort_order": 6},
            ]},
        )
        assert response.status_code == 400

        await db.refresh(a)
        assert a.sort_order == 0  # unchanged

    @pytest.mark.asyncio
    async def test_reorder_duplicate_sort_orders_422(
        self, admin_client: AsyncClient, db: AsyncSession
    ):
        a = SupplementaryDoc(
            title="A", object_name="system-docs/a.pdf", original_filename="a.pdf",
            content_type="application/pdf", file_size=10, sort_order=0,
        )
        b = SupplementaryDoc(
            title="B", object_name="system-docs/b.pdf", original_filename="b.pdf",
            content_type="application/pdf", file_size=10, sort_order=1,
        )
        db.add_all([a, b])
        await db.commit()
        await db.refresh(a)
        await db.refresh(b)

        response = await admin_client.patch(
            "/api/v1/system-settings/supplementary-docs/reorder",
            json={"items": [
                {"id": a.id, "sort_order": 0},
                {"id": b.id, "sort_order": 0},
            ]},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reorder_empty_payload_422(self, admin_client: AsyncClient):
        response = await admin_client.patch(
            "/api/v1/system-settings/supplementary-docs/reorder",
            json={"items": []},
        )
        assert response.status_code == 422
```

- [ ] **Step 2: Run failing tests**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestReorderSupplementaryDocs -v
```

Expected: 4 failures (the placeholder returns 501 / duplicates pass through Pydantic).

- [ ] **Step 3: Replace the placeholder reorder body**

Replace the placeholder `reorder_supplementary_docs` body added in Task 7 with the real implementation. The decorator stays the same; only the function body changes:

```python
@router.patch("/supplementary-docs/reorder")
async def reorder_supplementary_docs(
    payload: ReorderRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    requested_ids = [item.id for item in payload.items]
    stmt = select(SupplementaryDoc).where(SupplementaryDoc.id.in_(requested_ids))
    result = await db.execute(stmt)
    docs = {doc.id: doc for doc in result.scalars().all()}

    missing = [doc_id for doc_id in requested_ids if doc_id not in docs]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"ids not found: {missing}"
        )

    for item in payload.items:
        docs[item.id].sort_order = item.sort_order

    await db.commit()

    return {
        "success": True,
        "message": "已重新排序",
        "data": {"updated": len(payload.items)},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestReorderSupplementaryDocs -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/system_settings.py backend/app/tests/test_supplementary_docs.py
git commit -m "feat: add reorder supplementary-docs endpoint"
```

---

## Task 10: File Streaming Endpoint (TDD)

**Files:**
- Modify: `backend/app/api/v1/endpoints/system_settings.py`
- Modify: `backend/app/tests/test_supplementary_docs.py`

- [ ] **Step 1: Write failing tests**

```python
class TestStreamSupplementaryDocFile:
    @pytest.mark.asyncio
    async def test_streams_file_for_authenticated_user(
        self, student_client: AsyncClient, fake_minio, db: AsyncSession
    ):
        doc = SupplementaryDoc(
            title="X", object_name="system-docs/x.pdf",
            original_filename="說明.pdf",
            content_type="application/pdf", file_size=10, sort_order=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        fake_response = MagicMock()
        fake_response.read.return_value = b"%PDF-1.4 data"
        fake_minio.client.get_object.return_value = fake_response

        response = await student_client.get(
            f"/api/v1/system-settings/supplementary-docs/{doc.id}/file"
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        # filename* must be encoded per RFC 5987
        assert "filename*=UTF-8''" in response.headers["content-disposition"]
        assert response.content == b"%PDF-1.4 data"

    @pytest.mark.asyncio
    async def test_file_404_for_missing_id(
        self, student_client: AsyncClient, fake_minio
    ):
        response = await student_client.get(
            "/api/v1/system-settings/supplementary-docs/9999/file"
        )
        assert response.status_code == 404
        fake_minio.client.get_object.assert_not_called()
```

- [ ] **Step 2: Run failing tests**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestStreamSupplementaryDocFile -v
```

Expected: 2 failures.

- [ ] **Step 3: Add the endpoint** (insert at the end of the supplementary docs block, AFTER the delete endpoint)

```python
@router.get("/supplementary-docs/{doc_id}/file")
async def stream_supplementary_doc_file(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import io
    from urllib.parse import quote

    from sqlalchemy import select

    from app.services.minio_service import minio_service

    stmt = select(SupplementaryDoc).where(SupplementaryDoc.id == doc_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="not found")

    try:
        response = minio_service.client.get_object(
            bucket_name=minio_service.default_bucket,
            object_name=doc.object_name,
        )
        file_content = response.read()
    except Exception as e:
        logger.exception("Failed to fetch supplementary doc")
        raise HTTPException(status_code=500, detail="無法取得文件") from e

    download_name = doc.original_filename or doc.object_name.split("/")[-1]
    encoded_name = quote(download_name, safe="")

    return StreamingResponse(
        io.BytesIO(file_content),
        media_type=doc.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
            "Content-Length": str(len(file_content)),
            "Accept-Ranges": "bytes",
            "X-Content-Type-Options": "nosniff",
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py::TestStreamSupplementaryDocFile -v
```

Expected: 2 passed.

- [ ] **Step 5: Run the full backend test suite for this module**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py -v
```

Expected: 20 passed (2 list + 6 upload + 3 update + 3 delete + 4 reorder + 2 stream).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/endpoints/system_settings.py backend/app/tests/test_supplementary_docs.py
git commit -m "feat: add supplementary-doc file streaming endpoint"
```

---

## Task 11: Frontend API Client Extension

**Files:**
- Modify: `frontend/lib/api/modules/system-settings.ts`

- [ ] **Step 1: Add the type, helper, and namespace**

In `frontend/lib/api/modules/system-settings.ts`, append AFTER the existing `buildFileProxyUrl` function (around line 42) and BEFORE the `// System configuration types` comment block:

```typescript
/** Supplementary doc payload returned by the backend. */
export type SupplementaryDoc = {
  id: number;
  title: string;
  object_name: string;
  original_filename: string;
  content_type: string;
  file_size: number;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

/**
 * Build the file-proxy URL for a supplementary doc. Mirrors buildFileProxyUrl
 * but routes via /api/v1/system-settings/supp-file-proxy?id=...
 */
export function buildSuppDocFileProxyUrl(
  id: number,
  objectName?: string | null
): string {
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('auth_token') || ''
      : '';
  const cacheBuster = encodeURIComponent(
    (objectName || '').split('/').pop() || String(id)
  );
  return `/api/v1/system-settings/supp-file-proxy?id=${id}&token=${encodeURIComponent(
    token
  )}&v=${cacheBuster}`;
}
```

Then, inside the object returned by `createSystemSettingsApi()` (after the existing `uploadSampleDocument` block, around line 286), add:

```typescript
    supplementaryDocs: {
      list: async (): Promise<ApiResponse<SupplementaryDoc[]>> => {
        const token =
          typeof localStorage !== "undefined"
            ? localStorage.getItem("auth_token") || ""
            : "";
        const res = await fetch(
          "/api/v1/system-settings/supplementary-docs",
          { headers: { Authorization: `Bearer ${token}` } }
        );
        return (await res.json()) as ApiResponse<SupplementaryDoc[]>;
      },

      upload: async (
        file: File,
        title: string
      ): Promise<ApiResponse<SupplementaryDoc>> => {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("title", title);
        const token =
          typeof localStorage !== "undefined"
            ? localStorage.getItem("auth_token") || ""
            : "";
        const res = await fetch(
          "/api/v1/system-settings/supp-upload-proxy",
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          }
        );
        return (await res.json()) as ApiResponse<SupplementaryDoc>;
      },

      updateTitle: async (
        id: number,
        title: string
      ): Promise<ApiResponse<SupplementaryDoc>> => {
        const token =
          typeof localStorage !== "undefined"
            ? localStorage.getItem("auth_token") || ""
            : "";
        const res = await fetch(
          `/api/v1/system-settings/supplementary-docs/${id}`,
          {
            method: "PATCH",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ title }),
          }
        );
        return (await res.json()) as ApiResponse<SupplementaryDoc>;
      },

      delete: async (
        id: number
      ): Promise<ApiResponse<{ deleted: boolean }>> => {
        const token =
          typeof localStorage !== "undefined"
            ? localStorage.getItem("auth_token") || ""
            : "";
        const res = await fetch(
          `/api/v1/system-settings/supplementary-docs/${id}`,
          {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` },
          }
        );
        return (await res.json()) as ApiResponse<{ deleted: boolean }>;
      },

      reorder: async (
        items: Array<{ id: number; sort_order: number }>
      ): Promise<ApiResponse<{ updated: number }>> => {
        const token =
          typeof localStorage !== "undefined"
            ? localStorage.getItem("auth_token") || ""
            : "";
        const res = await fetch(
          "/api/v1/system-settings/supplementary-docs/reorder",
          {
            method: "PATCH",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ items }),
          }
        );
        return (await res.json()) as ApiResponse<{ updated: number }>;
      },
    },
```

Note: the list/update/delete/reorder calls route directly to the FastAPI backend through the existing Next.js rewrite for `/api/v1/*` paths (no dedicated proxy needed for JSON endpoints — the rewrite passes `Authorization` through). Only `upload` and the `file` streaming endpoint need bespoke proxy routes because the upload uses multipart form data and the file stream requires header preservation (Content-Disposition, Content-Length).

- [ ] **Step 2: Verify the file compiles**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | tail -20
```

Expected: no errors mentioning `system-settings.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api/modules/system-settings.ts
git commit -m "feat: add supplementaryDocs API client + buildSuppDocFileProxyUrl"
```

---

## Task 12: Regenerate OpenAPI Types

**Files:**
- Regenerate: `frontend/lib/api/generated/schema.d.ts`

- [ ] **Step 1: Ensure backend is running**

```bash
docker compose -f docker-compose.dev.yml up -d backend
docker compose -f docker-compose.dev.yml logs backend --tail 20
```

Wait until logs show `Application startup complete.`.

- [ ] **Step 2: Generate**

```bash
cd frontend && npm run api:generate
```

Expected: writes `frontend/lib/api/generated/schema.d.ts` with the new endpoints.

- [ ] **Step 3: Verify the new paths appear**

```bash
grep -c "supplementary-docs" frontend/lib/api/generated/schema.d.ts
```

Expected: a number ≥ 6 (one per endpoint, possibly more).

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore: regenerate openapi types for supplementary-docs"
```

---

## Task 13: Next.js Supp File Proxy

**Files:**
- Create: `frontend/app/api/v1/system-settings/supp-file-proxy/route.ts`

- [ ] **Step 1: Create the route**

```typescript
// frontend/app/api/v1/system-settings/supp-file-proxy/route.ts
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const idParam = searchParams.get("id");
    const id = idParam ? Number.parseInt(idParam, 10) : NaN;
    if (!Number.isInteger(id) || id <= 0) {
      return NextResponse.json({ error: "Invalid id" }, { status: 400 });
    }

    const queryToken = searchParams.get("token");
    const authHeader = request.headers.get("authorization");
    const cookieToken =
      request.cookies.get("access_token")?.value ||
      request.cookies.get("auth_token")?.value;
    const token =
      queryToken || authHeader?.replace("Bearer ", "") || cookieToken;

    if (!token) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const baseUrl =
      process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      return NextResponse.json(
        { error: "Backend not configured" },
        { status: 500 }
      );
    }

    let parsedUrl: URL;
    try {
      parsedUrl = new URL(baseUrl);
    } catch {
      return NextResponse.json(
        { error: "Invalid backend URL" },
        { status: 500 }
      );
    }

    const allowedHostnames = ["backend", "ss.test.nycu.edu.tw"];
    if (!allowedHostnames.includes(parsedUrl.hostname)) {
      return NextResponse.json(
        { error: "Untrusted backend hostname" },
        { status: 500 }
      );
    }

    const backendUrl = new URL(
      `/api/v1/system-settings/supplementary-docs/${id}/file`,
      baseUrl
    ).toString();

    const response = await fetch(backendUrl, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: "Failed to fetch document" },
        { status: response.status }
      );
    }

    const fileBuffer = await response.arrayBuffer();
    const contentType =
      response.headers.get("content-type") || "application/octet-stream";
    const contentDisposition =
      response.headers.get("content-disposition") || "inline";

    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": contentDisposition,
        "Content-Length": fileBuffer.byteLength.toString(),
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Failed to retrieve document" },
      { status: 500 }
    );
  }
}
```

- [ ] **Step 2: Smoke test via curl (requires a doc seeded — skip if none)**

If a supplementary doc exists in the dev DB, sanity-check:

```bash
TOKEN=$(curl -s http://localhost:8000/api/v1/auth/local-login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@nycu.edu.tw","password":"admin123"}' | jq -r .data.access_token)
curl -sSI "http://localhost:3000/api/v1/system-settings/supp-file-proxy?id=1&token=$TOKEN"
```

Expected (if doc id=1 exists): `HTTP/1.1 200 OK` with `Content-Type: application/pdf` (or relevant type).

If id=1 does not exist, skip the smoke test — Task 17's UI flow exercises the path.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/api/v1/system-settings/supp-file-proxy/route.ts
git commit -m "feat: add supp-file-proxy Next.js route"
```

---

## Task 14: Next.js Supp Upload Proxy

**Files:**
- Create: `frontend/app/api/v1/system-settings/supp-upload-proxy/route.ts`

- [ ] **Step 1: Create the route**

```typescript
// frontend/app/api/v1/system-settings/supp-upload-proxy/route.ts
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get("authorization");
    if (!authHeader) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const baseUrl =
      process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      return NextResponse.json(
        { error: "Backend not configured" },
        { status: 500 }
      );
    }

    let parsedUrl: URL;
    try {
      parsedUrl = new URL(baseUrl);
    } catch {
      return NextResponse.json(
        { error: "Invalid backend URL" },
        { status: 500 }
      );
    }

    const allowedHostnames = ["backend", "ss.test.nycu.edu.tw"];
    if (!allowedHostnames.includes(parsedUrl.hostname)) {
      return NextResponse.json(
        { error: "Untrusted backend hostname" },
        { status: 500 }
      );
    }

    const backendUrl = new URL(
      "/api/v1/system-settings/supplementary-docs",
      baseUrl
    ).toString();

    const formData = await request.formData();

    const response = await fetch(backendUrl, {
      method: "POST",
      headers: { Authorization: authHeader },
      body: formData,
    });

    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") || "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Failed to proxy upload" },
      { status: 500 }
    );
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/api/v1/system-settings/supp-upload-proxy/route.ts
git commit -m "feat: add supp-upload-proxy Next.js route"
```

---

## Task 15: AddSupplementaryDocDialog Component

**Files:**
- Create: `frontend/components/admin/system-docs/AddSupplementaryDocDialog.tsx`

- [ ] **Step 1: Create the component**

```typescript
// frontend/components/admin/system-docs/AddSupplementaryDocDialog.tsx
"use client";

import { useRef, useState } from "react";
import { CloudUpload, FileType2, Loader2, X } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import apiClient from "@/lib/api";
import type { SupplementaryDoc } from "@/lib/api/modules/system-settings";

const ACCEPTED = ".pdf,.doc,.docx";
const ACCEPTED_LABEL = "PDF · DOC · DOCX";
const MAX_SIZE_MB = 10;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (doc: SupplementaryDoc) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function AddSupplementaryDocDialog({
  open,
  onOpenChange,
  onCreated,
}: Props) {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setTitle("");
    setFile(null);
    setDragActive(false);
  };

  const validateAndSet = (f: File | null) => {
    if (!f) return;
    const ext = "." + (f.name.toLowerCase().split(".").pop() || "");
    if (!ACCEPTED.split(",").includes(ext)) {
      toast.error(`僅接受 ${ACCEPTED_LABEL}`);
      return;
    }
    if (f.size > MAX_SIZE_MB * 1024 * 1024) {
      toast.error(`檔案大小超過 ${MAX_SIZE_MB} MB`);
      return;
    }
    setFile(f);
  };

  const handleSubmit = async () => {
    const trimmed = title.trim();
    if (!trimmed) {
      toast.error("請輸入標題");
      return;
    }
    if (trimmed.length > 200) {
      toast.error("標題不得超過 200 字");
      return;
    }
    if (!file) {
      toast.error("請選擇檔案");
      return;
    }
    setSubmitting(true);
    try {
      const res = await apiClient.systemSettings.supplementaryDocs.upload(
        file,
        trimmed
      );
      if (res.success && res.data) {
        toast.success("已新增補充參考文件");
        onCreated(res.data);
        reset();
        onOpenChange(false);
      } else {
        toast.error(res.message || "上傳失敗");
      }
    } catch {
      toast.error("上傳失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!submitting) {
          onOpenChange(next);
          if (!next) reset();
        }
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>新增補充參考文件</DialogTitle>
          <DialogDescription>
            上傳後學生即可在申請須知頁面看到此檔案。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label htmlFor="supp-doc-title">標題</Label>
            <Input
              id="supp-doc-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：FAQ"
              maxLength={200}
              disabled={submitting}
            />
            <p className="text-xs text-gray-500 mt-1">
              {title.length}/200
            </p>
          </div>

          {!file ? (
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragActive(false);
                validateAndSet(e.dataTransfer.files?.[0] || null);
              }}
              className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed cursor-pointer py-8 ${
                dragActive
                  ? "border-nycu-blue-500 bg-nycu-blue-50"
                  : "border-gray-300 hover:border-nycu-blue-400 hover:bg-nycu-blue-50/40"
              }`}
            >
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPTED}
                className="sr-only"
                onChange={(e) =>
                  validateAndSet(e.target.files?.[0] || null)
                }
              />
              <CloudUpload className="h-6 w-6 text-nycu-blue-600 mb-2" />
              <p className="text-sm font-medium text-nycu-navy-800">
                拖曳檔案或點擊選擇
              </p>
              <p className="text-xs text-gray-500 mt-1">
                支援 {ACCEPTED_LABEL} · 上限 {MAX_SIZE_MB} MB
              </p>
            </label>
          ) : (
            <div className="rounded-lg border bg-gray-50 p-3 flex items-center gap-3">
              <FileType2 className="h-5 w-5 text-nycu-blue-600 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p
                  className="text-sm font-medium truncate"
                  title={file.name}
                >
                  {file.name}
                </p>
                <p className="text-xs text-gray-500">{formatBytes(file.size)}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setFile(null)}
                disabled={submitting}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => {
                if (!submitting) {
                  reset();
                  onOpenChange(false);
                }
              }}
              disabled={submitting}
            >
              取消
            </Button>
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting && (
                <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
              )}
              {submitting ? "上傳中..." : "上傳"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -i "AddSupplementaryDocDialog" || echo "ok"
```

Expected: `ok` (no compile errors for the new file).

- [ ] **Step 3: Commit**

```bash
git add frontend/components/admin/system-docs/AddSupplementaryDocDialog.tsx
git commit -m "feat: add AddSupplementaryDocDialog component"
```

---

## Task 16: SupplementaryDocsList Component (drag-sort)

**Files:**
- Create: `frontend/components/admin/system-docs/SupplementaryDocsList.tsx`

- [ ] **Step 1: Verify @dnd-kit is installed**

```bash
grep "@dnd-kit/sortable" frontend/package.json
```

Expected: presence of `"@dnd-kit/core"`, `"@dnd-kit/sortable"`, `"@dnd-kit/utilities"`. (Already in package.json as of plan-writing time. If absent, run `cd frontend && bun add @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities` and commit `package.json` + `bun.lockb`.)

- [ ] **Step 2: Create the component**

```typescript
// frontend/components/admin/system-docs/SupplementaryDocsList.tsx
"use client";

import { useEffect, useState } from "react";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  Eye,
  GripVertical,
  Loader2,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import apiClient from "@/lib/api";
import {
  buildSuppDocFileProxyUrl,
  type SupplementaryDoc,
} from "@/lib/api/modules/system-settings";
import { previewMimeType } from "@/lib/utils";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { AddSupplementaryDocDialog } from "./AddSupplementaryDocDialog";

interface SortableRowProps {
  doc: SupplementaryDoc;
  disabled: boolean;
  onPreview: (doc: SupplementaryDoc) => void;
  onEdit: (doc: SupplementaryDoc) => void;
  onDelete: (doc: SupplementaryDoc) => void;
}

function SortableRow({
  doc,
  disabled,
  onPreview,
  onEdit,
  onDelete,
}: SortableRowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: doc.id, disabled });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-3 rounded-md border border-gray-200 bg-white px-3 py-2"
      data-testid={`supp-row-${doc.id}`}
    >
      <button
        type="button"
        aria-label="拖曳排序"
        className="cursor-grab text-gray-400 hover:text-gray-600 disabled:cursor-not-allowed"
        disabled={disabled}
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <div className="flex-1 min-w-0">
        <p
          className="text-sm font-medium text-nycu-navy-900 truncate"
          title={doc.title}
        >
          {doc.title}
        </p>
        <p className="text-xs text-gray-500 truncate" title={doc.original_filename}>
          {doc.original_filename}
        </p>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onPreview(doc)}
        aria-label="預覽"
      >
        <Eye className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onEdit(doc)}
        aria-label="編輯標題"
      >
        <Pencil className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onDelete(doc)}
        aria-label="刪除"
        className="text-red-600 hover:bg-red-50"
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}

export function SupplementaryDocsList() {
  const [docs, setDocs] = useState<SupplementaryDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [reordering, setReordering] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [editingDoc, setEditingDoc] = useState<SupplementaryDoc | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [deletingDoc, setDeletingDoc] = useState<SupplementaryDoc | null>(null);
  const [preview, setPreview] = useState<
    { url: string; filename: string; type: string } | null
  >(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  useEffect(() => {
    apiClient.systemSettings.supplementaryDocs
      .list()
      .then((res) => {
        if (res.success && res.data) setDocs(res.data);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = docs.findIndex((d) => d.id === active.id);
    const newIndex = docs.findIndex((d) => d.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const previous = docs;
    const next = arrayMove(docs, oldIndex, newIndex);
    setDocs(next);
    setReordering(true);

    try {
      const items = next.map((d, idx) => ({ id: d.id, sort_order: idx }));
      const res = await apiClient.systemSettings.supplementaryDocs.reorder(
        items
      );
      if (!res.success) {
        setDocs(previous);
        toast.error(res.message || "排序失敗");
      } else {
        setDocs(
          next.map((d, idx) => ({ ...d, sort_order: idx }))
        );
      }
    } catch {
      setDocs(previous);
      toast.error("排序失敗");
    } finally {
      setReordering(false);
    }
  };

  const handlePreview = (doc: SupplementaryDoc) => {
    const url = buildSuppDocFileProxyUrl(doc.id, doc.object_name);
    setPreview({
      url,
      filename: doc.original_filename,
      type: previewMimeType(doc.original_filename),
    });
  };

  const openEdit = (doc: SupplementaryDoc) => {
    setEditingDoc(doc);
    setEditingTitle(doc.title);
  };

  const saveEdit = async () => {
    if (!editingDoc) return;
    const trimmed = editingTitle.trim();
    if (!trimmed) {
      toast.error("標題不得為空");
      return;
    }
    if (trimmed.length > 200) {
      toast.error("標題不得超過 200 字");
      return;
    }
    const res = await apiClient.systemSettings.supplementaryDocs.updateTitle(
      editingDoc.id,
      trimmed
    );
    if (res.success && res.data) {
      setDocs((prev) =>
        prev.map((d) => (d.id === editingDoc.id ? res.data! : d))
      );
      setEditingDoc(null);
      toast.success("已更新");
    } else {
      toast.error(res.message || "更新失敗");
    }
  };

  const confirmDelete = async () => {
    if (!deletingDoc) return;
    const target = deletingDoc;
    setDeletingDoc(null);
    const previous = docs;
    setDocs((prev) => prev.filter((d) => d.id !== target.id));
    const res = await apiClient.systemSettings.supplementaryDocs.delete(
      target.id
    );
    if (!res.success) {
      setDocs(previous);
      toast.error(res.message || "刪除失敗");
    } else {
      toast.success("已刪除");
    }
  };

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 mt-6">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold text-nycu-navy-900">補充參考文件</h3>
          <p className="text-sm text-gray-500 mt-0.5">
            學生在申請須知頁面會看到此處列出的檔案，可拖曳排序。
          </p>
        </div>
        <Button onClick={() => setAddOpen(true)} size="sm">
          <Plus className="h-4 w-4 mr-1.5" /> 新增
        </Button>
      </header>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" /> 載入中…
        </div>
      ) : docs.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">
          目前尚無補充參考文件，點擊「新增」上傳。
        </p>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={docs.map((d) => d.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-2">
              {docs.map((doc) => (
                <SortableRow
                  key={doc.id}
                  doc={doc}
                  disabled={reordering}
                  onPreview={handlePreview}
                  onEdit={openEdit}
                  onDelete={(d) => setDeletingDoc(d)}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      <AddSupplementaryDocDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onCreated={(doc) => setDocs((prev) => [...prev, doc])}
      />

      {editingDoc && (
        <Dialog
          open
          onOpenChange={(next) => !next && setEditingDoc(null)}
        >
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>編輯標題</DialogTitle>
              <DialogDescription>
                修改此補充參考文件的顯示標題。
              </DialogDescription>
            </DialogHeader>
            <Input
              value={editingTitle}
              onChange={(e) => setEditingTitle(e.target.value)}
              maxLength={200}
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditingDoc(null)}>
                取消
              </Button>
              <Button onClick={saveEdit}>儲存</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {deletingDoc && (
        <Dialog open onOpenChange={(next) => !next && setDeletingDoc(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>確認刪除</DialogTitle>
              <DialogDescription>
                刪除後學生將無法看到「{deletingDoc.title}」這份檔案，確定要刪除嗎？
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setDeletingDoc(null)}
              >
                取消
              </Button>
              <Button
                onClick={confirmDelete}
                className="bg-red-600 hover:bg-red-700 text-white"
              >
                刪除
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      <FilePreviewDialog
        isOpen={preview !== null}
        onClose={() => setPreview(null)}
        file={preview}
        locale="zh"
      />
    </section>
  );
}
```

- [ ] **Step 3: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -i "SupplementaryDocsList" || echo "ok"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/admin/system-docs/SupplementaryDocsList.tsx
git commit -m "feat: add SupplementaryDocsList drag-sort component"
```

---

## Task 17: Wire SupplementaryDocsList into SystemDocsPanel

**Files:**
- Modify: `frontend/components/admin/system-docs/SystemDocsPanel.tsx`

- [ ] **Step 1: Add the import**

At the top of `frontend/components/admin/system-docs/SystemDocsPanel.tsx` (after the existing imports, around line 29):

```typescript
import { SupplementaryDocsList } from "./SupplementaryDocsList";
```

- [ ] **Step 2: Mount the component below the existing 2-slot grid**

Find the closing `</Card>` of the main `<Card>` block (around line 449, before the `<FilePreviewDialog>` and the closing `</>`). Insert AFTER that closing `</Card>` and BEFORE the `<FilePreviewDialog>`:

```typescript
      <SupplementaryDocsList />
```

The result should look like:

```typescript
      </Card>

      <SupplementaryDocsList />

      <FilePreviewDialog
        ...
```

- [ ] **Step 3: Manually verify in the dev environment**

Start the stack (if not running):

```bash
docker compose -f docker-compose.dev.yml up -d
```

Log in to `http://localhost:3000` as `admin@nycu.edu.tw` (password `admin123` in dev), navigate to the system docs admin page, and verify the new "補充參考文件" section renders below the existing two fixed slots. The list should be empty.

Upload one file via the "+ 新增" button; confirm the row appears.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/admin/system-docs/SystemDocsPanel.tsx
git commit -m "feat: mount SupplementaryDocsList in SystemDocsPanel"
```

---

## Task 18: Frontend Tests for SupplementaryDocsList

**Files:**
- Create: `frontend/components/admin/system-docs/__tests__/SupplementaryDocsList.test.tsx`

- [ ] **Step 1: Create the test file**

```typescript
// frontend/components/admin/system-docs/__tests__/SupplementaryDocsList.test.tsx
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SupplementaryDocsList } from "../SupplementaryDocsList";

jest.mock("../../../../lib/api", () => {
  const list = jest.fn();
  const upload = jest.fn();
  const updateTitle = jest.fn();
  const del = jest.fn();
  const reorder = jest.fn();
  return {
    __esModule: true,
    default: {
      systemSettings: {
        supplementaryDocs: {
          list,
          upload,
          updateTitle,
          delete: del,
          reorder,
        },
      },
    },
  };
});

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const apiMock = jest.requireMock("../../../../lib/api") as {
  default: {
    systemSettings: {
      supplementaryDocs: {
        list: jest.Mock;
        upload: jest.Mock;
        updateTitle: jest.Mock;
        delete: jest.Mock;
        reorder: jest.Mock;
      };
    };
  };
};

const fakeDocs = [
  {
    id: 1,
    title: "FAQ",
    object_name: "system-docs/supp_a.pdf",
    original_filename: "faq.pdf",
    content_type: "application/pdf",
    file_size: 100,
    sort_order: 0,
    created_at: "2026-05-27T00:00:00Z",
    updated_at: "2026-05-27T00:00:00Z",
  },
  {
    id: 2,
    title: "範本",
    object_name: "system-docs/supp_b.pdf",
    original_filename: "sample.pdf",
    content_type: "application/pdf",
    file_size: 200,
    sort_order: 1,
    created_at: "2026-05-27T00:00:00Z",
    updated_at: "2026-05-27T00:00:00Z",
  },
];

beforeEach(() => {
  Object.values(apiMock.default.systemSettings.supplementaryDocs).forEach((fn) =>
    fn.mockReset()
  );
});

describe("SupplementaryDocsList", () => {
  it("renders rows from API", async () => {
    apiMock.default.systemSettings.supplementaryDocs.list.mockResolvedValue({
      success: true,
      message: "OK",
      data: fakeDocs,
    });

    render(<SupplementaryDocsList />);

    expect(await screen.findByText("FAQ")).toBeInTheDocument();
    expect(screen.getByText("範本")).toBeInTheDocument();
  });

  it("shows empty state when list is empty", async () => {
    apiMock.default.systemSettings.supplementaryDocs.list.mockResolvedValue({
      success: true,
      message: "OK",
      data: [],
    });

    render(<SupplementaryDocsList />);

    expect(
      await screen.findByText(/目前尚無補充參考文件/)
    ).toBeInTheDocument();
  });

  it("calls delete API after confirm", async () => {
    apiMock.default.systemSettings.supplementaryDocs.list.mockResolvedValue({
      success: true,
      message: "OK",
      data: fakeDocs,
    });
    apiMock.default.systemSettings.supplementaryDocs.delete.mockResolvedValue({
      success: true,
      message: "OK",
      data: { deleted: true },
    });

    render(<SupplementaryDocsList />);

    await screen.findByText("FAQ");
    const deleteBtns = screen.getAllByRole("button", { name: "刪除" });
    fireEvent.click(deleteBtns[0]); // first row delete button

    const confirmBtn = await screen.findByRole("button", { name: "刪除" });
    // findByRole returns the dialog's confirm button (modal). Click it.
    fireEvent.click(confirmBtn);

    await waitFor(() =>
      expect(
        apiMock.default.systemSettings.supplementaryDocs.delete
      ).toHaveBeenCalledWith(1)
    );
  });

  it("calls updateTitle on save edit", async () => {
    apiMock.default.systemSettings.supplementaryDocs.list.mockResolvedValue({
      success: true,
      message: "OK",
      data: fakeDocs,
    });
    apiMock.default.systemSettings.supplementaryDocs.updateTitle.mockResolvedValue({
      success: true,
      message: "OK",
      data: { ...fakeDocs[0], title: "FAQ v2" },
    });

    render(<SupplementaryDocsList />);

    await screen.findByText("FAQ");
    const editBtns = screen.getAllByRole("button", { name: "編輯標題" });
    fireEvent.click(editBtns[0]);

    const input = await screen.findByDisplayValue("FAQ");
    fireEvent.change(input, { target: { value: "FAQ v2" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() =>
      expect(
        apiMock.default.systemSettings.supplementaryDocs.updateTitle
      ).toHaveBeenCalledWith(1, "FAQ v2")
    );
  });
});
```

- [ ] **Step 2: Run the tests**

```bash
cd frontend && npx jest components/admin/system-docs/__tests__/SupplementaryDocsList.test.tsx
```

Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/admin/system-docs/__tests__/SupplementaryDocsList.test.tsx
git commit -m "test: add SupplementaryDocsList component tests"
```

---

## Task 19: Update NoticeAgreementStep — 參考文件 List

**Files:**
- Modify: `frontend/components/student-wizard/steps/NoticeAgreementStep.tsx`

- [ ] **Step 1: Update locale copy**

In the `NOTICES` const at the top of the file (around lines 45–185):

For `zh`:
- **Remove** the `sampleDocumentRow` key
- **Remove** the `sampleDocumentNotProvided` key
- **Add** `referenceDocsHeader: "參考文件"`
- **Add** `referenceDocsEmpty: "目前無參考文件"`

For `en`:
- **Remove** `sampleDocumentRow`
- **Remove** `sampleDocumentNotProvided`
- **Add** `referenceDocsHeader: "Reference Documents"`
- **Add** `referenceDocsEmpty: "No reference documents available"`

(Keep `sampleDocumentLabel` — it is still used as the row label for the fixed sample doc.)

- [ ] **Step 2: Add import + state for supplementary docs**

Update the existing import block:

```typescript
import { api } from "@/lib/api";
import {
  buildFileProxyUrl,
  buildSuppDocFileProxyUrl,
  type SupplementaryDoc,
} from "@/lib/api/modules/system-settings";
import { previewMimeType } from "@/lib/utils";
```

Add state inside `NoticeAgreementStep`, alongside the existing `publicDocs` state (around lines 196–202):

```typescript
const [supplementaryDocs, setSupplementaryDocs] = useState<SupplementaryDoc[]>(
  []
);
```

- [ ] **Step 3: Update the data fetch**

Replace the existing `useEffect` (lines 209–225) with:

```typescript
useEffect(() => {
  Promise.all([
    api.systemSettings.getPublicDocs(),
    api.systemSettings.supplementaryDocs.list(),
  ])
    .then(([docsRes, suppRes]) => {
      if (docsRes.success && docsRes.data) setPublicDocs(docsRes.data);
      if (suppRes.success && suppRes.data) setSupplementaryDocs(suppRes.data);
    })
    .catch((err) => {
      // eslint-disable-next-line no-console
      console.error("[NoticeAgreementStep] doc fetch failed", err);
    })
    .finally(() => {
      setDocsLoaded(true);
    });
}, []);
```

- [ ] **Step 4: Replace the sample-doc row block with the 參考文件 list**

Find the existing block at lines 304–321 (the `<div className="p-4 bg-blue-50 ...">` that currently contains the single sample-doc button). Replace it ENTIRELY with:

```typescript
{(() => {
  const sampleAvailable = Boolean(publicDocs.sample_document_url);
  const hasAnyReferenceDoc = sampleAvailable || supplementaryDocs.length > 0;
  if (!hasAnyReferenceDoc) return null;

  const rows: Array<{
    key: string;
    label: string;
    onClick: () => void;
  }> = [];

  if (sampleAvailable) {
    rows.push({
      key: "fixed-sample",
      label: t.sampleDocumentLabel,
      onClick: () => handleOpenSampleDoc(t.sampleDocumentLabel),
    });
  }

  for (const doc of supplementaryDocs) {
    rows.push({
      key: `supp-${doc.id}`,
      label: doc.title,
      onClick: () => {
        const url = buildSuppDocFileProxyUrl(doc.id, doc.object_name);
        setPreviewFile({
          url,
          filename: doc.original_filename,
          type: previewMimeType(doc.original_filename),
        });
      },
    });
  }

  return (
    <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
      <h4 className="text-sm font-semibold text-blue-900 mb-3">
        {t.referenceDocsHeader}
      </h4>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li
            key={row.key}
            className="flex items-center justify-between gap-3 rounded-md bg-white px-3 py-2"
          >
            <span
              className="text-sm text-nycu-navy-800 truncate"
              title={row.label}
            >
              {row.label}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={row.onClick}
              className="flex items-center gap-2"
            >
              <FileText className="h-4 w-4" /> 預覽
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
})()}
```

- [ ] **Step 5: Verify the file compiles**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -i "NoticeAgreementStep" || echo "ok"
```

Expected: `ok`.

- [ ] **Step 6: Manually verify in the dev environment**

Log in as a student (e.g. `stuunder1`), open a scholarship application, advance to the 申請須知 step. Verify:
- If both `sample_document_url` is unset AND no supplementary docs exist → no 參考文件 section at all (the prior "尚未提供" placeholder is gone).
- If at least one of either exists → 參考文件 section appears with rows in the expected order.
- The "申請文件範例檔" row stays first when present; supplementary docs follow in `sort_order`.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/student-wizard/steps/NoticeAgreementStep.tsx
git commit -m "feat: render 參考文件 list with supplementary docs in NoticeAgreementStep"
```

---

## Task 20: Update notice-agreement-step.test.tsx

**Files:**
- Modify: `frontend/components/__tests__/notice-agreement-step.test.tsx`

- [ ] **Step 1: Extend the existing mock**

At the top of the file, the existing `jest.mock("../../lib/api", ...)` mocks only `getPublicDocs`. Replace it with:

```typescript
jest.mock("../../lib/api", () => {
  const getPublicDocs = jest.fn();
  const list = jest.fn();
  return {
    __esModule: true,
    default: {
      systemSettings: {
        getPublicDocs,
        supplementaryDocs: { list },
      },
    },
    api: {
      systemSettings: {
        getPublicDocs,
        supplementaryDocs: { list },
      },
    },
  };
});

const apiMock = jest.requireMock("../../lib/api") as {
  api: {
    systemSettings: {
      getPublicDocs: jest.Mock;
      supplementaryDocs: { list: jest.Mock };
    };
  };
};

const mockGetPublicDocs = apiMock.api.systemSettings.getPublicDocs;
const mockSuppList = apiMock.api.systemSettings.supplementaryDocs.list;

beforeEach(() => {
  mockGetPublicDocs.mockReset();
  mockSuppList.mockReset();
  // default: no supplementary docs unless overridden
  mockSuppList.mockResolvedValue({ success: true, message: "OK", data: [] });
});
```

(If the existing file already has a `mockGetPublicDocs` const or `beforeEach`, merge — do not duplicate.)

- [ ] **Step 2: Add new test cases**

Append at the end of the existing `describe` block (or top-level if none):

```typescript
describe("NoticeAgreementStep — 參考文件 list", () => {
  it("hides the 參考文件 section when sample doc and supp docs are both empty", async () => {
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      message: "OK",
      data: { regulations_url: "system-docs/x.pdf" },
    });
    mockSuppList.mockResolvedValue({ success: true, message: "OK", data: [] });

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={() => {}}
        onNext={() => {}}
        locale="zh"
      />
    );

    await waitFor(() => expect(mockGetPublicDocs).toHaveBeenCalled());
    expect(screen.queryByText("參考文件")).not.toBeInTheDocument();
  });

  it("shows supplementary docs alongside the fixed sample doc row", async () => {
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      message: "OK",
      data: {
        regulations_url: "system-docs/r.pdf",
        sample_document_url: "system-docs/s.pdf",
        sample_document_url_filename: "sample.pdf",
      },
    });
    mockSuppList.mockResolvedValue({
      success: true,
      message: "OK",
      data: [
        {
          id: 1,
          title: "FAQ",
          object_name: "system-docs/supp_a.pdf",
          original_filename: "faq.pdf",
          content_type: "application/pdf",
          file_size: 10,
          sort_order: 0,
          created_at: "2026-05-27T00:00:00Z",
          updated_at: "2026-05-27T00:00:00Z",
        },
      ],
    });

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={() => {}}
        onNext={() => {}}
        locale="zh"
      />
    );

    expect(await screen.findByText("參考文件")).toBeInTheDocument();
    expect(screen.getByText("申請文件範例檔")).toBeInTheDocument();
    expect(screen.getByText("FAQ")).toBeInTheDocument();
  });

  it("renders only supplementary docs when sample doc is missing", async () => {
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      message: "OK",
      data: { regulations_url: "system-docs/r.pdf" },
    });
    mockSuppList.mockResolvedValue({
      success: true,
      message: "OK",
      data: [
        {
          id: 9,
          title: "範本",
          object_name: "system-docs/supp_x.pdf",
          original_filename: "x.pdf",
          content_type: "application/pdf",
          file_size: 1,
          sort_order: 0,
          created_at: "2026-05-27T00:00:00Z",
          updated_at: "2026-05-27T00:00:00Z",
        },
      ],
    });

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={() => {}}
        onNext={() => {}}
        locale="zh"
      />
    );

    expect(await screen.findByText("參考文件")).toBeInTheDocument();
    expect(screen.queryByText("申請文件範例檔")).not.toBeInTheDocument();
    expect(screen.getByText("範本")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Remove or update assertions that reference removed copy**

If the existing tests reference `sampleDocumentRow` text ("需要參考申請文件格式？") or the `sampleDocumentNotProvided` placeholder, remove or rewrite those assertions — they now will not appear.

Run the existing tests first to see which break:

```bash
cd frontend && npx jest components/__tests__/notice-agreement-step.test.tsx
```

Adjust any failing assertions to match the new copy (the section header is "參考文件" and the placeholder is gone — the section simply does not render when both sources are empty).

- [ ] **Step 4: Run tests until green**

```bash
cd frontend && npx jest components/__tests__/notice-agreement-step.test.tsx
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/__tests__/notice-agreement-step.test.tsx
git commit -m "test: cover 參考文件 list in NoticeAgreementStep"
```

---

## Task 21: Full Suite Run + E2E Sanity

**Files:** (no edits — verification only)

- [ ] **Step 1: Run backend tests**

```bash
cd backend && python -m pytest app/tests/test_supplementary_docs.py app/tests/test_system_settings_upload_doc.py -v
```

Expected: all tests pass (20 new + existing system_settings upload tests still pass).

- [ ] **Step 2: Run frontend tests for both touched components**

```bash
cd frontend && npx jest components/admin/system-docs components/__tests__/notice-agreement-step.test.tsx
```

Expected: all tests pass.

- [ ] **Step 3: Type-check the whole frontend**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json
```

Expected: no errors.

- [ ] **Step 4: End-to-end smoke (manual)**

In a running dev stack:

1. Log in as admin → upload one supplementary doc with title "Smoke Test".
2. Reorder it relative to another (if multiple exist).
3. Log out, log in as a student → open a scholarship application → reach 申請須知 step.
4. Verify the 參考文件 section shows the row labelled "Smoke Test" and preview opens via `FilePreviewDialog`.
5. Log back in as admin → delete the smoke-test doc.
6. Refresh student view → doc gone.

- [ ] **Step 5: Final commit (if any tweaks needed)**

If any small fixes surfaced during the smoke pass, commit them with focused messages. Otherwise, no final commit is required — the previous tasks already committed each component.

---

## Self-Review Notes

- Spec § 3 (data model) → Tasks 1–3
- Spec § 4 (backend API: 6 endpoints) → Tasks 5–10
- Spec § 5 (admin UI) → Tasks 15–17
- Spec § 6 (student UI + 參考文件 list, drop subtitle row) → Task 19
- Spec § 7 (API client + 2 new proxies) → Tasks 11, 13, 14
- Spec § 8 (tests) → Tasks 4–10 (backend), 18, 20 (frontend)
- Spec § 9 (edge cases) → reflected in upload/delete/reorder TDD tests
- Spec § 11 (file touch list) → all paths listed in the file structure section above match

Placeholder scan: no TBDs, no "implement later", every code block contains the actual code or test body.

Type consistency: `SupplementaryDoc` shape consistent across backend response, Pydantic schema, frontend type, and test fixtures (`id, title, object_name, original_filename, content_type, file_size, sort_order, created_at, updated_at`). `reorder` payload shape `[{id, sort_order}]` matches between API client, backend schema (`ReorderItem`), and test JSON.
