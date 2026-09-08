"""Endpoint contract for GET /college-review/export-package after the move to
true streaming (issue #1376): every rejection is decided before the response
starts (400/500 from prepare_export, 403 from the permission helpers), the
success path is a chunked StreamingResponse with no Content-Length, and
``dry_run=true`` answers with an ApiResponse without touching the archive.

The handler is called directly with stubbed collaborators — the real service
needs MinIO and a DB — so these are plain async unit tests.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import quote

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

import app.api.v1.endpoints.college_review.export_package as ep
from app.models.user import UserRole
from app.services.export_package_service import ExportPlan

_FILENAME = "博士生獎學金_申請資料_114_0_資訊學院.zip"


def _plan(count_per_dept=(2, 1)):
    return ExportPlan(
        scholarship_name="博士生獎學金",
        academic_year=114,
        semester=None,
        college_name="資訊學院",
        dept_groups={f"{i}_系{i}": [object()] * n for i, n in enumerate(count_per_dept, start=1)},
        field_labels={},
        summary_tables={},
        zip_filename=_FILENAME,
    )


class _StubService:
    def __init__(self, plan=None, error=None, chunks=(b"PK\x03\x04", b"middle", b"tail")):
        self.plan = plan
        self.error = error
        self.chunks = chunks
        self.prepare_kwargs = None
        self.iter_calls = 0

    async def prepare_export(self, **kwargs):
        self.prepare_kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.plan

    async def iter_export_zip(self, plan):
        self.iter_calls += 1
        for chunk in self.chunks:
            yield chunk


async def _allow(*args, **kwargs):
    return True


async def _deny(*args, **kwargs):
    return False


@pytest.fixture
def college_user():
    return SimpleNamespace(id=5, role=UserRole.college, college_code="C")


@pytest.fixture
def wire(monkeypatch):
    """Install a stub service behind permissive permission helpers; returns the stub."""

    def _wire(stub):
        monkeypatch.setattr(ep, "_check_scholarship_permission", _allow)
        monkeypatch.setattr(ep, "_check_academic_year_permission", _allow)
        monkeypatch.setattr(ep, "MinIOService", lambda: None)
        monkeypatch.setattr(ep, "ExportPackageService", lambda db, minio: stub)
        return stub

    return _wire


@pytest.fixture
def fake_logger(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(ep, "logger", logger)
    return logger


async def _call(user, db=None, **overrides):
    params = dict(
        scholarship_type_id=2,
        academic_year=114,
        semester=None,
        dry_run=False,
        current_user=user,
        db=db if db is not None else AsyncMock(),
    )
    return await ep.export_application_package(**{**params, **overrides})


def _ended_extra(fake_logger):
    ended = [call for call in fake_logger.info.call_args_list if "stream ended" in call.args[0]]
    assert len(ended) == 1
    return ended[0].kwargs["extra"]


@pytest.mark.asyncio
async def test_dry_run_returns_api_response_without_building_the_archive(wire, college_user, fake_logger):
    stub = wire(_StubService(plan=_plan()))
    db = AsyncMock()

    result = await _call(college_user, db=db, dry_run=True)

    assert result == {
        "success": True,
        "message": "可匯出",
        "data": {"filename": _FILENAME, "application_count": 3},
    }
    assert stub.iter_calls == 0
    db.close.assert_not_awaited()  # nothing streams; the dependency teardown follows at once
    # Still an audited bulk-PII access, flagged as the precheck.
    issued = fake_logger.info.call_args_list[0]
    assert issued.args[1] == "precheck passed"
    assert issued.kwargs["extra"]["actor_user_id"] == 5
    assert issued.kwargs["extra"]["application_count"] == 3


@pytest.mark.asyncio
async def test_download_is_a_chunked_stream_without_content_length(wire, college_user, fake_logger):
    stub = wire(_StubService(plan=_plan()))
    db = AsyncMock()

    response = await _call(college_user, db=db)

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "application/zip"
    # The pooled connection is released before the client-paced transfer
    # starts; FastAPI's own teardown would only run after the last byte.
    db.close.assert_awaited_once()
    # The size is unknown up front; the ASGI server sends chunked encoding.
    assert "content-length" not in response.headers
    assert response.headers["content-disposition"] == f"attachment; filename*=UTF-8''{quote(_FILENAME)}"

    body = b"".join([chunk async for chunk in response.body_iterator])
    assert body == b"".join(stub.chunks)
    assert stub.iter_calls == 1

    issued = fake_logger.info.call_args_list[0]
    assert issued.args[1] == "issued"
    ended = _ended_extra(fake_logger)
    assert ended["completed"] is True
    assert ended["size_bytes"] == len(body)
    assert ended["actor_user_id"] == 5
    assert ended["export_filename"] == _FILENAME


@pytest.mark.asyncio
async def test_client_disconnect_is_logged_as_incomplete(wire, college_user, fake_logger):
    wire(_StubService(plan=_plan()))

    response = await _call(college_user)
    iterator = response.body_iterator
    first = await iterator.__anext__()
    await iterator.aclose()  # what Starlette does when the client goes away

    ended = _ended_extra(fake_logger)
    assert ended["completed"] is False
    assert ended["size_bytes"] == len(first)


@pytest.mark.asyncio
async def test_rejections_become_400_before_any_byte_is_sent(wire, college_user):
    stub = wire(_StubService(error=ValueError("無申請資料可匯出")))

    with pytest.raises(HTTPException) as exc:
        await _call(college_user)

    assert exc.value.status_code == 400
    assert exc.value.detail == "無申請資料可匯出"
    assert stub.iter_calls == 0


@pytest.mark.asyncio
async def test_unexpected_preparation_failure_becomes_500(wire, college_user):
    wire(_StubService(error=RuntimeError("minio down")))

    with pytest.raises(HTTPException) as exc:
        await _call(college_user)

    assert exc.value.status_code == 500
    assert exc.value.detail == "匯出檔案產生失敗"


@pytest.mark.asyncio
async def test_college_scope_and_semester_normalisation_reach_the_service(wire, college_user):
    stub = wire(_StubService(plan=_plan()))

    await _call(college_user, semester="yearly", dry_run=True)

    assert stub.prepare_kwargs == {
        "scholarship_type_id": 2,
        "academic_year": 114,
        "semester": None,
        "college_code": "C",
        # dry_run skips the workbook build — only filename + count are needed
        "include_summary_tables": False,
    }


@pytest.mark.asyncio
async def test_real_download_builds_the_summary_tables(wire, college_user, fake_logger):
    stub = wire(_StubService(plan=_plan()))

    await _call(college_user)

    assert stub.prepare_kwargs["include_summary_tables"] is True


@pytest.mark.asyncio
async def test_admin_is_not_college_scoped(wire):
    stub = wire(_StubService(plan=_plan()))
    admin = SimpleNamespace(id=1, role=UserRole.admin, college_code=None)

    await _call(admin, dry_run=True)

    assert stub.prepare_kwargs["college_code"] is None


@pytest.mark.asyncio
async def test_permission_denial_is_403_and_never_reaches_the_service(monkeypatch, college_user):
    monkeypatch.setattr(ep, "_check_scholarship_permission", _deny)
    service_factory = MagicMock()
    monkeypatch.setattr(ep, "ExportPackageService", service_factory)

    with pytest.raises(HTTPException) as exc:
        await _call(college_user)

    assert exc.value.status_code == 403
    service_factory.assert_not_called()
