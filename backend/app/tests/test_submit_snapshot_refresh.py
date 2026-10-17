"""
ApplicationService._refresh_incomplete_student_snapshot — at submit, a draft whose
SIS term data is missing (status != success) gets its snapshot re-fetched live.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.college_mappings import ORIGINAL_ACADEMY_CODES_KEY
from app.core.exceptions import ServiceUnavailableError
from app.models.application import Application
from app.models.enums import Semester
from app.services.application_service import ApplicationService

DRAFT = {
    "std_stdcode": "411651009",
    "std_cname": "王小明",
    "_term_data_status": "error",
    "_term_error_message": "Student API request timed out",
    "financial_info": {"bank_code": "700"},
}


def _service(snapshot=None, error=None) -> ApplicationService:
    svc = ApplicationService(MagicMock())
    svc.student_service = MagicMock()
    svc.student_service.get_student_snapshot = AsyncMock(return_value=snapshot, side_effect=error)
    return svc


def _application(student_data, semester=None) -> Application:
    return Application(app_id="APP-115-0-00182", academic_year=115, semester=semester, student_data=student_data)


@pytest.mark.asyncio
async def test_successful_snapshot_is_left_alone():
    svc = _service()
    app = _application({**DRAFT, "_term_data_status": "success"})

    await svc._refresh_incomplete_student_snapshot(app)

    svc.student_service.get_student_snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_term_data_is_refetched_live_and_merged():
    refreshed = {"std_stdcode": "411651009", "trm_depname": "電機系", "_term_data_status": "success"}
    svc = _service(snapshot=refreshed)
    app = _application(dict(DRAFT))

    await svc._refresh_incomplete_student_snapshot(app)

    svc.student_service.get_student_snapshot.assert_awaited_once_with(
        "411651009", academic_year="115", semester=None, fresh=True
    )
    assert app.student_data["trm_depname"] == "電機系"
    assert app.student_data["_term_data_status"] == "success"
    assert app.student_data["financial_info"] == {"bank_code": "700"}  # non-SIS keys survive


@pytest.mark.asyncio
async def test_semester_is_passed_as_its_value():
    svc = _service(snapshot={"_term_data_status": "success"})
    app = _application(dict(DRAFT), semester=Semester.first)

    await svc._refresh_incomplete_student_snapshot(app)

    assert svc.student_service.get_student_snapshot.await_args.kwargs["semester"] == "first"


@pytest.mark.asyncio
async def test_partial_snapshot_is_also_refetched():
    svc = _service(snapshot={"trm_term": "2", "_term_data_status": "success"})
    app = _application({**DRAFT, "_term_data_status": "partial", "trm_term": "1"})

    await svc._refresh_incomplete_student_snapshot(app)

    assert app.student_data["trm_term"] == "2"


@pytest.mark.asyncio
async def test_refresh_drops_term_fields_of_the_fallback_term():
    """Term-1 keys that the refreshed term-2 record lacks must not survive into a 'success' snapshot."""
    svc = _service(snapshot={"std_stdcode": "411651009", "trm_term": "2", "_term_data_status": "success"})
    partial = {
        **DRAFT,
        "_term_data_status": "partial",
        "trm_term": "1",
        "trm_placings": "3",
        ORIGINAL_ACADEMY_CODES_KEY: {"trm_academyno": "Y"},
    }
    app = _application(partial)

    await svc._refresh_incomplete_student_snapshot(app)

    assert app.student_data["trm_term"] == "2"
    assert "trm_placings" not in app.student_data
    assert ORIGINAL_ACADEMY_CODES_KEY not in app.student_data
    assert app.student_data["financial_info"] == {"bank_code": "700"}


@pytest.mark.asyncio
async def test_refresh_that_still_has_no_term_data_keeps_the_draft():
    svc = _service(snapshot={"std_stdcode": "411651009", "_term_data_status": "error"})
    draft = dict(DRAFT)
    app = _application(draft)

    await svc._refresh_incomplete_student_snapshot(app)

    assert app.student_data == draft


@pytest.mark.asyncio
async def test_sis_outage_does_not_block_submit():
    svc = _service(error=ServiceUnavailableError("Student API request timed out"))
    draft = dict(DRAFT)
    app = _application(draft)

    await svc._refresh_incomplete_student_snapshot(app)  # does not raise

    assert app.student_data == draft


@pytest.mark.asyncio
async def test_snapshot_without_student_code_is_skipped():
    svc = _service()
    app = _application({"_term_data_status": "error"})

    await svc._refresh_incomplete_student_snapshot(app)

    svc.student_service.get_student_snapshot.assert_not_awaited()
