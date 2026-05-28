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


class TestListSupplementaryDocs:
    @pytest.mark.asyncio
    async def test_list_empty(self, admin_client: AsyncClient):
        response = await admin_client.get("/api/v1/system-settings/supplementary-docs")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_list_sorted_by_sort_order_then_id(self, admin_client: AsyncClient, db: AsyncSession):
        from app.models.supplementary_doc import SupplementaryDoc

        db.add_all(
            [
                SupplementaryDoc(
                    title="C",
                    object_name="system-docs/c.pdf",
                    original_filename="c.pdf",
                    content_type="application/pdf",
                    file_size=10,
                    sort_order=2,
                ),
                SupplementaryDoc(
                    title="A",
                    object_name="system-docs/a.pdf",
                    original_filename="a.pdf",
                    content_type="application/pdf",
                    file_size=10,
                    sort_order=0,
                ),
                SupplementaryDoc(
                    title="B",
                    object_name="system-docs/b.pdf",
                    original_filename="b.pdf",
                    content_type="application/pdf",
                    file_size=10,
                    sort_order=1,
                ),
            ]
        )
        await db.commit()

        response = await admin_client.get("/api/v1/system-settings/supplementary-docs")
        body = response.json()
        titles = [item["title"] for item in body["data"]]
        assert titles == ["A", "B", "C"]


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
    async def test_rejects_disallowed_extension(self, admin_client: AsyncClient, fake_minio):
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


class TestUpdateSupplementaryDocTitle:
    @pytest.mark.asyncio
    async def test_admin_updates_title(self, admin_client: AsyncClient, db: AsyncSession):
        doc = SupplementaryDoc(
            title="Old",
            object_name="system-docs/x.pdf",
            original_filename="x.pdf",
            content_type="application/pdf",
            file_size=10,
            sort_order=0,
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
            title="Old",
            object_name="system-docs/x.pdf",
            original_filename="x.pdf",
            content_type="application/pdf",
            file_size=10,
            sort_order=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        response = await admin_client.patch(
            f"/api/v1/system-settings/supplementary-docs/{doc.id}",
            json={"title": "   "},
        )
        assert response.status_code == 422


class TestDeleteSupplementaryDoc:
    @pytest.mark.asyncio
    async def test_admin_deletes(self, admin_client: AsyncClient, fake_minio, db: AsyncSession):
        doc = SupplementaryDoc(
            title="X",
            object_name="system-docs/x.pdf",
            original_filename="x.pdf",
            content_type="application/pdf",
            file_size=10,
            sort_order=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        doc_id = doc.id

        response = await admin_client.delete(f"/api/v1/system-settings/supplementary-docs/{doc_id}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        fake_minio.client.remove_object.assert_called_once_with("scholarship-system", "system-docs/x.pdf")

        from sqlalchemy import select

        rows = (await db.execute(select(SupplementaryDoc).where(SupplementaryDoc.id == doc_id))).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_delete_missing_returns_404(self, admin_client: AsyncClient, fake_minio):
        response = await admin_client.delete("/api/v1/system-settings/supplementary-docs/99999")
        assert response.status_code == 404
        fake_minio.client.remove_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_succeeds_even_when_minio_fails(self, admin_client: AsyncClient, fake_minio, db: AsyncSession):
        doc = SupplementaryDoc(
            title="X",
            object_name="system-docs/x.pdf",
            original_filename="x.pdf",
            content_type="application/pdf",
            file_size=10,
            sort_order=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        fake_minio.client.remove_object.side_effect = RuntimeError("boom")

        response = await admin_client.delete(f"/api/v1/system-settings/supplementary-docs/{doc.id}")
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True


class TestReorderSupplementaryDocs:
    @pytest.mark.asyncio
    async def test_admin_reorders(self, admin_client: AsyncClient, db: AsyncSession):
        a = SupplementaryDoc(
            title="A",
            object_name="system-docs/a.pdf",
            original_filename="a.pdf",
            content_type="application/pdf",
            file_size=10,
            sort_order=0,
        )
        b = SupplementaryDoc(
            title="B",
            object_name="system-docs/b.pdf",
            original_filename="b.pdf",
            content_type="application/pdf",
            file_size=10,
            sort_order=1,
        )
        db.add_all([a, b])
        await db.commit()
        await db.refresh(a)
        await db.refresh(b)

        response = await admin_client.patch(
            "/api/v1/system-settings/supplementary-docs/reorder",
            json={
                "items": [
                    {"id": a.id, "sort_order": 1},
                    {"id": b.id, "sort_order": 0},
                ]
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["updated"] == 2

        list_response = await admin_client.get("/api/v1/system-settings/supplementary-docs")
        titles = [item["title"] for item in list_response.json()["data"]]
        assert titles == ["B", "A"]

    @pytest.mark.asyncio
    async def test_reorder_with_missing_id_400_and_no_changes(self, admin_client: AsyncClient, db: AsyncSession):
        a = SupplementaryDoc(
            title="A",
            object_name="system-docs/a.pdf",
            original_filename="a.pdf",
            content_type="application/pdf",
            file_size=10,
            sort_order=0,
        )
        db.add(a)
        await db.commit()
        await db.refresh(a)

        response = await admin_client.patch(
            "/api/v1/system-settings/supplementary-docs/reorder",
            json={
                "items": [
                    {"id": a.id, "sort_order": 5},
                    {"id": 99999, "sort_order": 6},
                ]
            },
        )
        assert response.status_code == 400

        await db.refresh(a)
        assert a.sort_order == 0  # unchanged

    @pytest.mark.asyncio
    async def test_reorder_duplicate_sort_orders_422(self, admin_client: AsyncClient, db: AsyncSession):
        a = SupplementaryDoc(
            title="A",
            object_name="system-docs/a.pdf",
            original_filename="a.pdf",
            content_type="application/pdf",
            file_size=10,
            sort_order=0,
        )
        b = SupplementaryDoc(
            title="B",
            object_name="system-docs/b.pdf",
            original_filename="b.pdf",
            content_type="application/pdf",
            file_size=10,
            sort_order=1,
        )
        db.add_all([a, b])
        await db.commit()
        await db.refresh(a)
        await db.refresh(b)

        response = await admin_client.patch(
            "/api/v1/system-settings/supplementary-docs/reorder",
            json={
                "items": [
                    {"id": a.id, "sort_order": 0},
                    {"id": b.id, "sort_order": 0},
                ]
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reorder_empty_payload_422(self, admin_client: AsyncClient):
        response = await admin_client.patch(
            "/api/v1/system-settings/supplementary-docs/reorder",
            json={"items": []},
        )
        assert response.status_code == 422


class TestStreamSupplementaryDocFile:
    @pytest.mark.asyncio
    async def test_streams_file_for_authenticated_user(self, student_client: AsyncClient, fake_minio, db: AsyncSession):
        doc = SupplementaryDoc(
            title="X",
            object_name="system-docs/x.pdf",
            original_filename="說明.pdf",
            content_type="application/pdf",
            file_size=10,
            sort_order=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        fake_response = MagicMock()
        fake_response.read.return_value = b"%PDF-1.4 data"
        fake_minio.client.get_object.return_value = fake_response

        response = await student_client.get(f"/api/v1/system-settings/supplementary-docs/{doc.id}/file")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        # filename* must be encoded per RFC 5987
        assert "filename*=UTF-8''" in response.headers["content-disposition"]
        assert response.content == b"%PDF-1.4 data"

    @pytest.mark.asyncio
    async def test_file_404_for_missing_id(self, student_client: AsyncClient, fake_minio):
        response = await student_client.get("/api/v1/system-settings/supplementary-docs/9999/file")
        assert response.status_code == 404
        fake_minio.client.get_object.assert_not_called()
