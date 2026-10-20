"""
學院/系所 on application responses and the college distribution view follow API 1 (std_*):
the code comes from std_* first, the name is resolved from that code, and the term row
(trm_*) only fills a gap — see app.utils.application_helpers.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.endpoints.college_review._helpers import _group_items_by_sub_type
from app.models.application import Application, ApplicationStatus
from app.models.user import User, UserRole
from app.services.application_service import ApplicationService

DEPARTMENT_NAMES = {"1511": "電機工程學系", "1550": "資訊工程學系"}

# Term lookup failed (SIS timeout): API 1 only, no trm_* keys at all
API_1_ONLY = {"std_stdcode": "311551001", "std_cname": "王小明", "std_academyno": "E", "std_depno": "1511"}

# Moved 資工 → 電機 after the term row was written
TRANSFERRED = {
    "std_stdcode": "311551002",
    "std_cname": "陳小美",
    "std_academyno": "E",
    "std_depno": "1511",
    "trm_academyno": "C",
    "trm_academyname": "資訊學院",
    "trm_depno": "1550",
    "trm_depname": "資工系",
}

# Department code missing from the departments table: the term row's name is all we have
UNKNOWN_CODE = {"std_stdcode": "311551003", "std_cname": "張三", "std_depno": "9999", "trm_depname": "舊系所"}


# ---------- ApplicationService._extract_student_fields ----------


@pytest.fixture
def service():
    return ApplicationService(MagicMock())


def test_extract_fields_names_come_from_api_1_when_term_lookup_failed(service):
    fields = service._extract_student_fields(API_1_ONLY, DEPARTMENT_NAMES)

    assert fields["academy_code"] == "E"
    assert fields["academy_name"] == "電機學院"
    assert fields["department_code"] == "1511"
    assert fields["department_name"] == "電機工程學系"


def test_extract_fields_transferred_student_gets_the_api_1_unit(service):
    fields = service._extract_student_fields(TRANSFERRED, DEPARTMENT_NAMES)

    assert fields["academy_code"] == "E"
    assert fields["academy_name"] == "電機學院"
    assert fields["department_code"] == "1511"
    assert fields["department_name"] == "電機工程學系"


def test_extract_fields_unknown_department_code_falls_back_to_trm_depname(service):
    fields = service._extract_student_fields(UNKNOWN_CODE, DEPARTMENT_NAMES)

    assert fields["department_code"] == "9999"
    assert fields["department_name"] == "舊系所"


def test_extract_fields_term_only_data_still_reads_the_term_row(service):
    fields = service._extract_student_fields(
        {**TRANSFERRED, "trm_termcount": 3, "std_termcount": 5, "trm_ascore_gpa": 3.9}, DEPARTMENT_NAMES
    )

    assert fields["term_count"] == 3
    assert fields["gpa"] == 3.9


@pytest.mark.asyncio
async def test_build_application_response_resolves_department_name_from_the_table():
    now = datetime.now(timezone.utc)
    application = Application(
        id=1,
        app_id="APP-113-1-00001",
        user_id=7,
        scholarship_type_id=1,
        status=ApplicationStatus.submitted,
        is_renewal=False,
        application_round=1,
        academic_year=113,
        student_data=TRANSFERRED,
        submitted_form_data={},
        created_at=now,
        updated_at=now,
    )
    user = User(id=7, nycu_id="311551002", role=UserRole.student)
    service = ApplicationService(MagicMock())

    loader = AsyncMock(return_value=DEPARTMENT_NAMES)
    with patch("app.services.application_service.load_department_names", loader):
        response = await service._build_application_response(application, user)

    loader.assert_awaited_once()
    assert response.department_code == "1511"
    assert response.department_name == "電機工程學系"
    assert response.academy_name == "電機學院"


# ---------- college distribution view: _group_items_by_sub_type ----------


def _item(student_data: dict, rank: int) -> SimpleNamespace:
    return SimpleNamespace(
        application=SimpleNamespace(student_data=student_data, scholarship_subtype_list=["nstc"]),
        ranking_id=1,
        rank_position=rank,
        is_allocated=True,
        allocated_sub_type="nstc",
        backup_allocations=None,
    )


def _departments_by_student(items, department_names=None) -> dict:
    groups = _group_items_by_sub_type(items, {1: "nstc"}, {}, department_names)
    nstc = next(g for g in groups if g["code"] == "nstc")
    return {s["student_number"]: s["department"] for s in nstc["admitted"]}


def test_distribution_department_names_follow_api_1():
    departments = _departments_by_student(
        [_item(API_1_ONLY, 1), _item(TRANSFERRED, 2), _item(UNKNOWN_CODE, 3)], DEPARTMENT_NAMES
    )

    assert departments == {
        "311551001": "電機工程學系",  # term lookup failed: no longer blank
        "311551002": "電機工程學系",  # transferred: the std_depno department, not 資工系
        "311551003": "舊系所",  # unknown code: term row's name
    }


def test_distribution_department_without_table_or_term_name_is_empty_string():
    assert _departments_by_student([_item(API_1_ONLY, 1)]) == {"311551001": ""}
