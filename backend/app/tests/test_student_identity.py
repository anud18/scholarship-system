"""
Which SIS record answers what:

- 學院 / 系所 (code and name) come from API 1 (std_*); the term row (trm_*) only fills a gap
- StudentService.get_scholarship_term_info is the single rule for which term a scholarship reads
"""

from unittest.mock import AsyncMock

import pytest

from app.core.cache import KEY_PREFIX, invalidate
from app.core.exceptions import ServiceUnavailableError
from app.models.enums import Semester
from app.models.student import Academy, Department
from app.tests.test_cache import fake_redis  # noqa: F401  (fixture)
from app.services.department_names import DEPARTMENT_NAMES_CACHE_KEY, load_department_names
from app.services.student_service import StudentService
from app.utils.application_helpers import (
    get_academy_code_from_data,
    get_academy_name_from_data,
    get_department_code_from_data,
    get_department_name_from_data,
)

# A student who moved 資工 → 電機 after the term row was written: API 1 is current, the term row is not
TRANSFERRED = {
    "std_academyno": "E",
    "std_depno": "1511",
    "trm_academyno": "C",
    "trm_academyname": "資訊學院",
    "trm_depno": "1550",
    "trm_depname": "資工系",
}
DEPARTMENT_NAMES = {"1511": "電機工程學系", "1550": "資訊工程學系"}


def test_codes_come_from_api_1_first():
    assert get_academy_code_from_data(TRANSFERRED) == "E"
    assert get_department_code_from_data(TRANSFERRED) == "1511"


def test_codes_fall_back_to_the_term_row():
    term_only = {"trm_academyno": "C", "trm_depno": "1550"}

    assert get_academy_code_from_data(term_only) == "C"
    assert get_department_code_from_data(term_only) == "1550"
    assert get_academy_code_from_data({}) is None
    assert get_department_code_from_data(None) is None


def test_names_describe_the_same_unit_as_the_api_1_codes():
    assert get_academy_name_from_data(TRANSFERRED) == "電機學院"
    assert get_department_name_from_data(TRANSFERRED, DEPARTMENT_NAMES) == "電機工程學系"


def test_name_falls_back_to_the_term_row_when_the_code_is_unknown():
    unknown = {"std_academyno": "ZZ", "std_depno": "9999", "trm_academyname": "舊學院", "trm_depname": "舊系"}

    assert get_academy_name_from_data(unknown) == "舊學院"
    assert get_department_name_from_data(unknown, DEPARTMENT_NAMES) == "舊系"
    assert get_department_name_from_data(unknown) == "舊系"  # no table passed


def test_the_term_row_lends_its_name_only_when_it_is_about_the_same_unit():
    """An unknown API 1 code must not end up next to the OLD unit's name."""
    transferred = {
        "std_academyno": "ZZ",
        "std_depno": "9999",
        "trm_academyno": "C",
        "trm_academyname": "資訊學院",
        "trm_depno": "1550",
        "trm_depname": "資工系",
    }
    same_unit = {**transferred, "trm_academyno": "ZZ", "trm_depno": "9999"}

    assert get_academy_name_from_data(transferred) is None
    assert get_department_name_from_data(transferred, DEPARTMENT_NAMES) is None
    assert get_academy_name_from_data(same_unit) == "資訊學院"
    assert get_department_name_from_data(same_unit, DEPARTMENT_NAMES) == "資工系"


def test_a_code_with_stray_whitespace_still_finds_its_name():
    assert get_department_name_from_data({"std_depno": "1511 "}, DEPARTMENT_NAMES) == "電機工程學系"
    assert get_academy_name_from_data({"std_academyno": " E"}) == "電機學院"


def test_name_is_none_when_nothing_knows_it():
    assert get_academy_name_from_data({"std_academyno": "ZZ"}) is None
    assert get_department_name_from_data({"std_depno": "9999"}, DEPARTMENT_NAMES) is None


def test_a_retired_academy_code_in_an_old_snapshot_still_resolves():
    assert get_academy_name_from_data({"std_academyno": "Y"}) == get_academy_name_from_data({"std_academyno": "E"})


@pytest.mark.asyncio
async def test_load_department_names_maps_code_to_name(db):
    await invalidate("refdata:department-names")
    db.add(Academy(code="E", name="電機學院"))
    await db.flush()
    db.add_all(
        [
            Department(code="1511", name="電機工程學系", academy_code="E"),
            Department(code="1512", name="電子研究所", academy_code="E"),
        ]
    )
    await db.flush()

    names = await load_department_names(db)
    await invalidate("refdata:department-names")

    assert names["1511"] == "電機工程學系"
    assert names["1512"] == "電子研究所"


# ---------- the term a scholarship reads ----------


def _service(by_term: dict) -> StudentService:
    """StudentService whose term lookups answer from ``by_term`` ({"1": record|None|Exception, ...})."""
    service = StudentService()

    async def lookup(code, year, term, fresh=False):
        answer = by_term[term]
        if isinstance(answer, Exception):
            raise answer
        return answer

    service.get_student_term_info = AsyncMock(side_effect=lookup)
    return service


def _terms_asked(service: StudentService) -> list:
    return [call.args[2] for call in service.get_student_term_info.await_args_list]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "semester, term", [("first", "1"), (Semester.first, "1"), ("second", "2"), (Semester.second, "2")]
)
async def test_semester_scholarship_reads_only_its_own_term(semester, term):
    service = _service({"1": {"trm_term": 1}, "2": {"trm_term": 2}})

    data, status, message = await service.get_scholarship_term_info("411651009", "114", semester)

    assert data == {"trm_term": int(term)}
    assert (status, message) == ("success", None)
    assert _terms_asked(service) == [term]


@pytest.mark.asyncio
async def test_semester_scholarship_without_that_term_is_an_error():
    service = _service({"1": None, "2": {"trm_term": 2}})

    data, status, message = await service.get_scholarship_term_info("411651009", "114", "first")

    assert data is None
    assert status == "error"
    assert "114" in message


@pytest.mark.asyncio
@pytest.mark.parametrize("yearly", [None, "yearly", Semester.yearly])
async def test_yearly_scholarship_prefers_term_2(yearly):
    service = _service({"1": {"trm_term": 1}, "2": {"trm_term": 2}})

    data, status, _ = await service.get_scholarship_term_info("411651009", "114", yearly)

    assert data == {"trm_term": 2}
    assert status == "success"
    assert _terms_asked(service) == ["2"]


@pytest.mark.asyncio
async def test_yearly_scholarship_uses_term_1_when_term_2_is_empty():
    service = _service({"1": {"trm_term": 1}, "2": None})

    data, status, _ = await service.get_scholarship_term_info("411651009", "114", None)

    assert data == {"trm_term": 1}
    assert status == "success"
    assert _terms_asked(service) == ["2", "1"]


@pytest.mark.asyncio
async def test_yearly_scholarship_raises_when_term_2_failed_and_term_1_is_empty():
    """A SIS outage must not read as 'this student has no term data'."""
    service = _service({"1": None, "2": ServiceUnavailableError("timed out")})

    with pytest.raises(ServiceUnavailableError, match="timed out"):
        await service.get_scholarship_term_info("411651009", "114", None)


@pytest.mark.asyncio
async def test_yearly_scholarship_marks_term_1_partial_when_term_2_failed():
    service = _service({"1": {"trm_term": 1}, "2": ServiceUnavailableError("timed out")})

    data, status, message = await service.get_scholarship_term_info("411651009", "114", None)

    assert data == {"trm_term": 1}
    assert status == "partial"
    assert "timed out" in message


@pytest.mark.asyncio
async def test_department_names_are_cached_but_an_empty_table_is_not(db, fake_redis):
    """An empty mapping (read before seeding / after a rebuild) must not stay in Redis for an hour."""
    key = (KEY_PREFIX + DEPARTMENT_NAMES_CACHE_KEY).encode()

    assert await load_department_names(db) == {}
    assert await fake_redis.get(key) is None

    db.add(Academy(code="E", name="電機學院"))
    await db.flush()
    db.add(Department(code="1511", name="電機工程學系", academy_code="E"))
    await db.flush()

    assert await load_department_names(db) == {"1511": "電機工程學系"}
    assert await fake_redis.get(key) is not None
