"""電資學院 (Y) is retired: SIS records filed under Y are treated as 電機學院 (E).

SIS still files the 電資博學程 under academy code Y, but 電機學院 manages it and
is the only one of the two that receives quota. Every SIS record is remapped at
the boundary (StudentService + StudentVerificationService), so the ~25 college
read sites — which all key on ``student_data.std_academyno`` — see E.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.college_mappings import (
    COLLEGE_MAPPINGS,
    MERGED_ACADEMY_CODES,
    ORIGINAL_ACADEMY_CODES_KEY,
    normalize_academy_code,
    normalize_student_academy,
)
from app.models.payment_roster import StudentVerificationStatus
from app.services.student_service import StudentService
from app.services.student_verification_service import StudentVerificationService
from app.utils.application_helpers import get_college_code_from_data

EECS_PHD_BASIC = {"std_stdcode": "314540001", "std_academyno": "Y", "std_depno": "4540"}
EECS_PHD_TERM = {"trm_academyno": "Y", "trm_academyname": "電資學院", "trm_depno": "4540"}


class TestNormalizeAcademyCode:
    def test_retired_code_maps_to_surviving_college(self) -> None:
        assert MERGED_ACADEMY_CODES == {"Y": "E"}
        assert normalize_academy_code("Y") == "E"
        assert normalize_academy_code(" Y ") == "E"

    def test_other_values_pass_through(self) -> None:
        assert normalize_academy_code("C") == "C"
        assert normalize_academy_code("") == ""
        assert normalize_academy_code(None) is None

    def test_retired_code_is_not_a_listed_college(self) -> None:
        assert "Y" not in COLLEGE_MAPPINGS
        assert COLLEGE_MAPPINGS["E"] == "電機學院"


class TestNormalizeStudentAcademy:
    def test_basic_record_is_remapped_and_original_kept(self) -> None:
        result = normalize_student_academy(EECS_PHD_BASIC)

        assert result["std_academyno"] == "E"
        assert result["std_depno"] == "4540"
        assert result[ORIGINAL_ACADEMY_CODES_KEY] == {"std_academyno": "Y"}
        assert get_college_code_from_data(result) == "E"

    def test_term_record_name_follows_code(self) -> None:
        result = normalize_student_academy(EECS_PHD_TERM)

        assert result["trm_academyno"] == "E"
        assert result["trm_academyname"] == "電機學院"
        assert result[ORIGINAL_ACADEMY_CODES_KEY] == {"trm_academyno": "Y"}

    def test_name_follows_only_its_own_code(self) -> None:
        """A term spent in another college keeps that college's name."""
        record = {"std_academyno": "Y", "trm_academyno": "C", "trm_academyname": "資訊學院"}
        result = normalize_student_academy(record)

        assert result["std_academyno"] == "E"
        assert result["trm_academyno"] == "C"
        assert result["trm_academyname"] == "資訊學院"

    def test_legacy_fallback_keys_are_remapped(self) -> None:
        result = normalize_student_academy({"college_code": "Y"})
        assert result["college_code"] == "E"

    def test_does_not_mutate_input(self) -> None:
        record = dict(EECS_PHD_BASIC)
        normalize_student_academy(record)
        assert record == EECS_PHD_BASIC

    def test_unaffected_record_returned_unchanged(self) -> None:
        record = {"std_academyno": "C", "trm_academyname": "資訊學院"}
        assert normalize_student_academy(record) is record

    @pytest.mark.parametrize("value", [None, {}, []])
    def test_non_records_pass_through(self, value) -> None:
        assert normalize_student_academy(value) == value

    def test_is_idempotent(self) -> None:
        once = normalize_student_academy(EECS_PHD_TERM)
        assert normalize_student_academy(once) is once


def _api_service() -> StudentService:
    svc = StudentService()
    svc.api_enabled = True
    svc.api_base_url = "http://fake-sis-api"
    svc.api_timeout = 5.0
    return svc


def _mock_sis(record):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"code": "200", "data": [record]}
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    patcher = patch("app.services.student_service._get_http_client", return_value=mock_client)
    patcher.start()
    return patcher


@pytest.mark.asyncio
async def test_basic_info_is_normalized_at_sis_boundary():
    patcher = _mock_sis(EECS_PHD_BASIC)
    try:
        result = await _api_service().get_student_basic_info("314540001")
    finally:
        patcher.stop()

    assert result["std_academyno"] == "E"
    assert result[ORIGINAL_ACADEMY_CODES_KEY] == {"std_academyno": "Y"}


@pytest.mark.asyncio
async def test_snapshot_attributes_eecs_phd_to_ece():
    """A new application's snapshot (basic + term) lands in 電機學院."""
    svc = _api_service()
    with (
        patch.object(svc, "get_student_basic_info", AsyncMock(return_value=normalize_student_academy(EECS_PHD_BASIC))),
        patch.object(svc, "get_student_term_info", AsyncMock(return_value=normalize_student_academy(EECS_PHD_TERM))),
    ):
        snapshot = await svc.get_student_snapshot("314540001", academic_year="114", semester="first")

    assert snapshot["std_academyno"] == "E"
    assert snapshot["trm_academyno"] == "E"
    assert snapshot["trm_academyname"] == "電機學院"
    assert get_college_code_from_data(snapshot) == "E"
    # basic + term records each replaced a raw Y; the snapshot keeps both
    assert snapshot[ORIGINAL_ACADEMY_CODES_KEY] == {"std_academyno": "Y", "trm_academyno": "Y"}


@pytest.mark.asyncio
async def test_term_info_is_normalized_at_sis_boundary():
    patcher = _mock_sis(EECS_PHD_TERM)
    try:
        result = await _api_service().get_student_term_info("314540001", "114", "1")
    finally:
        patcher.stop()

    assert result["trm_academyno"] == "E"
    assert result["trm_academyname"] == "電機學院"


def test_roster_verification_student_info_is_normalized(monkeypatch):
    """Roster generation merges verification student_info back into student_data;
    a raw Y there would undo the migration on every roster run."""
    service = StudentVerificationService()
    monkeypatch.setattr(service, "mock_mode", True)
    monkeypatch.setattr(
        service,
        "_mock_verification",
        lambda *a: {
            "status": StudentVerificationStatus.VERIFIED,
            "message": "ok",
            "student_info": dict(EECS_PHD_BASIC),
            "verified_at": None,
            "api_response": {},
        },
    )

    result = service.verify_student("A123456789", "測試生")

    assert result["status"] == StudentVerificationStatus.VERIFIED
    assert result["student_info"]["std_academyno"] == "E"
    # provenance stays out, or each roster run would clobber the snapshot's basic+term union
    assert ORIGINAL_ACADEMY_CODES_KEY not in result["student_info"]
