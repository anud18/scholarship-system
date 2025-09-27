from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from minio.error import S3Error

from app.services.minio_service import MinIOService

BASE_CONFIG = dict(
    max_file_size=1024,
    allowed_file_types_list=["pdf", "jpg"],
    minio_endpoint="",
    minio_access_key="",
    minio_secret_key="",
    minio_secure=False,
    minio_bucket="test-bucket",
    testing=True,
)


def _make_settings(**overrides):
    data = BASE_CONFIG.copy()
    data.update(overrides)
    return SimpleNamespace(**data)


def _build_upload_file(filename: str, content: bytes, content_type: str = "application/pdf"):
    class FakeUploadFile:
        def __init__(self):
            self.filename = filename
            self._content = content
            self.content_type = content_type

        async def read(self):
            return self._content

    return FakeUploadFile()


@pytest.fixture
def minio_service(monkeypatch):
    service = MinIOService.__new__(MinIOService)
    service.client = MagicMock()
    service.bucket_name = BASE_CONFIG["minio_bucket"]
    monkeypatch.setattr("app.services.minio_service.settings", SimpleNamespace(**BASE_CONFIG))
    return service


@pytest.mark.asyncio
async def test_upload_file_success(minio_service, monkeypatch):
    monkeypatch.setattr("app.services.minio_service.settings", _make_settings())

    upload = _build_upload_file("transcript.pdf", b"fake-bytes")
    minio_service.client.put_object.return_value = None

    object_name, size = await MinIOService.upload_file(minio_service, upload, application_id=1, file_type="doc")

    assert object_name.startswith("applications/1/documents/")
    assert object_name.endswith(".pdf")
    assert size == len(b"fake-bytes")
    minio_service.client.put_object.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_rejects_large_file(minio_service, monkeypatch):
    monkeypatch.setattr("app.services.minio_service.settings", _make_settings(max_file_size=5))

    upload = _build_upload_file("large.pdf", b"too-large-bytes")

    with pytest.raises(HTTPException) as exc:
        await MinIOService.upload_file(minio_service, upload, application_id=1, file_type="doc")

    assert exc.value.status_code == 500  # currently wrapped inside generic handler
    minio_service.client.put_object.assert_not_called()


@pytest.mark.asyncio
async def test_upload_file_invalid_extension(minio_service, monkeypatch):
    monkeypatch.setattr("app.services.minio_service.settings", _make_settings(allowed_file_types_list=["pdf"]))

    upload = _build_upload_file("image.bmp", b"data")

    with pytest.raises(HTTPException) as exc:
        await MinIOService.upload_file(minio_service, upload, application_id=1, file_type="doc")

    assert exc.value.status_code == 500  # currently wrapped inside generic handler
    minio_service.client.put_object.assert_not_called()


@pytest.mark.asyncio
async def test_upload_file_s3_error(minio_service, monkeypatch):
    monkeypatch.setattr("app.services.minio_service.settings", _make_settings())

    upload = _build_upload_file("doc.pdf", b"data")
    minio_service.client.put_object.side_effect = S3Error(
        "code", "msg", "resource", "request_id", "host_id", "response"
    )

    with pytest.raises(HTTPException) as exc:
        await MinIOService.upload_file(minio_service, upload, application_id=2, file_type="doc")

    assert exc.value.status_code == 500


def test_get_file_stream_success(minio_service):
    response = minio_service.get_file_stream("path/to/file")
    minio_service.client.get_object.assert_called_once_with("test-bucket", "path/to/file")
    assert response == minio_service.client.get_object.return_value


def test_get_file_stream_not_found(minio_service):
    minio_service.client.get_object.side_effect = S3Error(
        "code", "msg", "resource", "request_id", "host_id", "response"
    )

    with pytest.raises(HTTPException) as exc:
        minio_service.get_file_stream("missing")

    assert exc.value.status_code == 404


def test_delete_file_success(minio_service):
    assert minio_service.delete_file("file") is True
    minio_service.client.remove_object.assert_called_once_with("test-bucket", "file")


def test_delete_file_failure(minio_service):
    minio_service.client.remove_object.side_effect = S3Error(
        "code", "msg", "resource", "request_id", "host_id", "response"
    )

    assert minio_service.delete_file("file") is False


def test_clone_file_to_application_success(minio_service, monkeypatch):
    monkeypatch.setattr(
        "app.services.minio_service.uuid", SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="abcd1234"))
    )

    new_name = minio_service.clone_file_to_application("user-profiles/1/file.pdf", application_id="APP-1")

    minio_service.client.copy_object.assert_called_once()
    assert new_name.startswith("applications/APP-1/documents/")
    assert new_name.endswith(".pdf")


def test_clone_file_to_application_creates_placeholder(minio_service, monkeypatch):
    monkeypatch.setattr("app.services.minio_service.uuid", SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="xyz987")))

    minio_service.client.copy_object.side_effect = Exception("not found")

    new_name = minio_service.clone_file_to_application("user-profiles/1/missing.jpg", application_id="APP-2")

    minio_service.client.put_object.assert_called_once()
    assert new_name.startswith("applications/APP-2/documents/")
    assert new_name.endswith(".jpg")


@pytest.mark.asyncio
async def test_upload_file_unexpected_error(minio_service, monkeypatch):
    monkeypatch.setattr("app.services.minio_service.settings", _make_settings())

    upload = _build_upload_file("doc.pdf", b"data")
    minio_service.client.put_object.side_effect = ValueError("boom")

    with pytest.raises(HTTPException) as exc:
        await MinIOService.upload_file(minio_service, upload, application_id=3, file_type="doc")

    assert exc.value.status_code == 500


def test_clone_file_to_application_placeholder_failure(minio_service, monkeypatch):
    monkeypatch.setattr("app.services.minio_service.uuid", SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="abcd")))

    minio_service.client.copy_object.side_effect = Exception("missing")
    minio_service.client.put_object.side_effect = S3Error("code", "msg", "resource", "request", "host", "response")

    with pytest.raises(HTTPException) as exc:
        minio_service.clone_file_to_application("user-profiles/1/placeholder.pdf", application_id="APP-3")

    assert exc.value.status_code == 500


def test_extract_object_name_from_url_variants(minio_service):
    service = minio_service

    extracted = service.extract_object_name_from_url(
        "/api/v1/user-profiles/files/bank_documents/bankbook.pdf?token=abc"
    )
    assert extracted.endswith("bankbook.pdf")

    assert service.extract_object_name_from_url("/some/other/path.pdf") is None
