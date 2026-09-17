"""
The college 申請審核 list shows each student's 學期狀態/GPA for the application's
academic year. It used to call the live SIS term API once per application (twice
for yearly scholarships), which made the list slow for colleges with many
applicants. The same term data is already in the ``student_data`` snapshot
(captured at submission with the identical term rule), so the enricher must read
it from there and only fall back to SIS — with bounded concurrency — when the
snapshot lacks the matching term.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import application_enricher_service as enricher_module
from app.services.application_enricher_service import ApplicationEnricherService


@pytest.fixture
def service():
    svc = ApplicationEnricherService(db=None)  # type: ignore[arg-type]
    svc.student_service.get_student_term_info = AsyncMock(return_value={"trm_studystatus": 9, "trm_ascore_gpa": 2.0})
    return svc


def _app(app_id, academic_year=114, semester=None, **snapshot):
    return {
        "id": app_id,
        "academic_year": academic_year,
        "semester": semester,
        "student_data": {"std_stdcode": f"S{app_id}", "std_cname": "王", **snapshot},
    }


async def test_yearly_snapshot_term_data_skips_sis(service):
    apps = [_app(i, trm_year=114, trm_term=2, trm_studystatus=1, trm_ascore_gpa=3.9) for i in range(20)]

    period_map = await service._fetch_scholarship_period_data(apps)

    service.student_service.get_student_term_info.assert_not_called()
    assert period_map[0]["trm_studystatus"] == 1
    formatted = service._format_applications(apps, period_map)
    assert formatted[0]["scholarship_period_status"] == 1
    assert formatted[0]["scholarship_period_gpa"] == 3.9


async def test_snapshot_from_other_year_falls_back_to_sis(service):
    apps = [_app(1, academic_year=114, trm_year=113, trm_term=2, trm_studystatus=1)]

    period_map = await service._fetch_scholarship_period_data(apps)

    service.student_service.get_student_term_info.assert_awaited_once_with("S1", "114", "2")
    assert period_map[1]["trm_studystatus"] == 9


async def test_semester_app_requires_matching_term(service):
    matching = _app(1, semester="first", trm_year=114, trm_term=1, trm_studystatus=1)
    wrong_term = _app(2, semester="second", trm_year=114, trm_term=1, trm_studystatus=1)

    period_map = await service._fetch_scholarship_period_data([matching, wrong_term])

    service.student_service.get_student_term_info.assert_awaited_once_with("S2", "114", "2")
    assert period_map[1]["trm_studystatus"] == 1
    assert period_map[2]["trm_studystatus"] == 9


async def test_snapshot_without_term_data_falls_back_to_sis(service):
    period_map = await service._fetch_scholarship_period_data([_app(1, semester="first")])

    service.student_service.get_student_term_info.assert_awaited_once_with("S1", "114", "1")
    assert period_map[1]["trm_studystatus"] == 9


async def test_live_fallback_concurrency_is_bounded(service, monkeypatch):
    monkeypatch.setattr(enricher_module, "MAX_CONCURRENT_PERIOD_LOOKUPS", 3)
    in_flight = 0
    peak = 0

    async def slow_lookup(*_args):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return {"trm_studystatus": 1}

    service.student_service.get_student_term_info = slow_lookup

    period_map = await service._fetch_scholarship_period_data([_app(i, semester="first") for i in range(12)])

    assert peak == 3
    assert len(period_map) == 12


async def test_live_fallback_failure_maps_to_none(service):
    service.student_service.get_student_term_info = AsyncMock(side_effect=RuntimeError("SIS down"))

    period_map = await service._fetch_scholarship_period_data([_app(1, semester="first")])

    assert period_map == {1: None}
