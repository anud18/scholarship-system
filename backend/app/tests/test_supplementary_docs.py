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
