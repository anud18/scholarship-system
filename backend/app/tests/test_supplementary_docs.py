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
    async def test_list_sorted_by_sort_order_then_id(
        self, admin_client: AsyncClient, db: AsyncSession
    ):
        from app.models.supplementary_doc import SupplementaryDoc

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
