"""
Tests for upload_system_doc in
backend/app/api/v1/endpoints/system_settings.py.

Pins the policy that regulations_url accepts ONLY .pdf
(rejects .docx, rejects mismatched MIME), while sample_document_url
continues to accept .pdf / .doc / .docx.
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
        nycu_id="docupload_admin",
        name="Doc Upload Admin",
        email="docupload_admin@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def admin_client(
    db: AsyncSession, admin_user: User
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db

    async def override_get_current_user():
        return admin_user

    async def override_require_admin():
        return admin_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_admin] = override_require_admin

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def fake_minio():
    """Patch minio_service so the test never touches MinIO."""
    with patch(
        "app.services.minio_service.minio_service"
    ) as mock_service:
        mock_service.default_bucket = "test-bucket"
        mock_service.client = MagicMock()
        mock_service.client.put_object = MagicMock()
        mock_service.client.remove_object = MagicMock()
        yield mock_service


async def _post_upload(
    client: AsyncClient,
    doc_key: str,
    filename: str,
    content_type: str,
    body: bytes = b"%PDF-1.4 minimal",
):
    files = {"file": (filename, BytesIO(body), content_type)}
    return await client.post(
        f"/api/v1/system-settings/upload/{doc_key}",
        files=files,
    )


@pytest.mark.asyncio
class TestRegulationsUploadValidation:
    async def test_rejects_docx_for_regulations_url(
        self, admin_client: AsyncClient, fake_minio
    ):
        res = await _post_upload(
            admin_client,
            "regulations_url",
            filename="rules.docx",
            content_type=(
                "application/vnd.openxmlformats-"
                "officedocument.wordprocessingml.document"
            ),
        )
        assert res.status_code == 400
        body = res.json()
        # The app wraps HTTPException.detail into a standardized envelope
        # (`{success, message, trace_id}`) via an exception handler — check
        # both shapes to stay compatible with either.
        error_text = body.get("detail") or body.get("message") or ""
        assert "PDF" in error_text
        fake_minio.client.put_object.assert_not_called()

    async def test_rejects_pdf_extension_with_mismatched_mime(
        self, admin_client: AsyncClient, fake_minio
    ):
        res = await _post_upload(
            admin_client,
            "regulations_url",
            filename="rules.pdf",
            content_type="application/octet-stream",
        )
        assert res.status_code == 400
        fake_minio.client.put_object.assert_not_called()

    async def test_accepts_pdf_with_pdf_mime(
        self, admin_client: AsyncClient, fake_minio
    ):
        res = await _post_upload(
            admin_client,
            "regulations_url",
            filename="rules.pdf",
            content_type="application/pdf",
        )
        assert res.status_code == 200
        fake_minio.client.put_object.assert_called_once()

    async def test_rejects_non_pdf_bytes_even_when_extension_and_mime_say_pdf(
        self, admin_client: AsyncClient, fake_minio
    ):
        # Defense in depth: a malicious admin can spoof Content-Type and
        # filename. Magic-byte sniff catches the content itself.
        res = await _post_upload(
            admin_client,
            "regulations_url",
            filename="rules.pdf",
            content_type="application/pdf",
            body=b"PK\x03\x04 docx bytes pretending to be PDF",
        )
        assert res.status_code == 400
        fake_minio.client.put_object.assert_not_called()


@pytest.mark.asyncio
class TestSampleDocumentUploadStillAcceptsDocx:
    async def test_accepts_docx_for_sample_document_url(
        self, admin_client: AsyncClient, fake_minio
    ):
        res = await _post_upload(
            admin_client,
            "sample_document_url",
            filename="sample.docx",
            content_type=(
                "application/vnd.openxmlformats-"
                "officedocument.wordprocessingml.document"
            ),
        )
        assert res.status_code == 200
        fake_minio.client.put_object.assert_called_once()
