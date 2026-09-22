"""
The college 申請審核 page tabs by scholarship code and sends ``scholarship_type``
to ``GET /college-review/applications``. ``CollegeReviewService`` used to ignore
that parameter, so every tab loaded (and SIS-enriched) all scholarships'
applications for the year — slow, and other scholarships leaked into the tab.
"""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import ApplicationStatus
from app.models.user import UserRole
from app.services.college_review_service import CollegeReviewService
from app.tests.test_get_applications_for_review_deep import _seed_app, _seed_config, _seed_user


async def _register_json_extract_path_text(db: AsyncSession) -> None:
    """The college scope filter uses the Postgres-only json_extract_path_text."""

    def json_extract_path_text(raw, key):
        value = json.loads(raw).get(key) if raw else None
        return None if value is None else str(value)

    connection = await db.connection()
    raw_connection = await connection.get_raw_connection()
    await raw_connection.driver_connection.create_function("json_extract_path_text", 2, json_extract_path_text)


@pytest.mark.asyncio
async def test_college_list_filters_by_scholarship_code(db: AsyncSession):
    await _register_json_extract_path_text(db)
    college = await _seed_user(db, role=UserRole.college, nycu_id="crlist_college")
    student = await _seed_user(db, role=UserRole.student, nycu_id="crlist_stu")
    cfg_a = await _seed_config(db, suffix="crlist_a")
    cfg_b = await _seed_config(db, suffix="crlist_b")
    app_a = await _seed_app(db, student=student, config=cfg_a, status=ApplicationStatus.submitted.value, suffix="cra")
    await _seed_app(db, student=student, config=cfg_b, status=ApplicationStatus.submitted.value, suffix="crb")

    service = CollegeReviewService(db)
    filtered = await service.get_applications_for_review(
        scholarship_type="forrev_crlist_a", academic_year=114, college_code=college.college_code
    )
    unfiltered = await service.get_applications_for_review(academic_year=114, college_code=college.college_code)

    assert [row["id"] for row in filtered] == [app_a.id]
    assert len(unfiltered) == 2
