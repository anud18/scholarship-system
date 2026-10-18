"""學院顯示編號: numbered college names in the 學生資料彙整表 學院 column."""

from types import SimpleNamespace

import pytest

from app.core.college_mappings import COLLEGE_MAPPINGS
from app.services.college_ranking_export_service import STATIC_HEADERS, CollegeRankingExportService, ExportRow
from app.utils.college_display_number import (
    COLLEGE_DISPLAY_NUMBERS,
    format_college_name,
    format_student_college,
)


def test_mapping_numbers_cover_1_to_19():
    assert sorted(set(COLLEGE_DISPLAY_NUMBERS.values())) == list(range(1, 20))


def test_only_legacy_alias_8_shares_a_number():
    # 8 is the legacy SIS code for the same college as A (人社院).
    assert COLLEGE_DISPLAY_NUMBERS["8"] == COLLEGE_DISPLAY_NUMBERS["A"]
    rest = {k: v for k, v in COLLEGE_DISPLAY_NUMBERS.items() if k != "8"}
    assert len(set(rest.values())) == len(rest)


def test_every_numbered_code_is_a_known_academy():
    assert set(COLLEGE_DISPLAY_NUMBERS) - {"8"} <= set(COLLEGE_MAPPINGS)


@pytest.mark.parametrize(
    "code, name, expected",
    [
        ("C", "資訊學院", "6. 資訊學院"),
        ("A", "人社院", "1. 人社院"),
        ("F", "產創學院", "19. 產創學院"),
        ("2", "牙醫學院", "13. 牙醫學院"),
        (" C ", "資訊學院", "6. 資訊學院"),
        ("Y", "電資學院", "電資學院"),  # not in the 對照表 → unnumbered
        (None, "資訊學院", "資訊學院"),
        ("C", None, ""),  # never a bare number
        ("C", "", ""),
    ],
)
def test_format_college_name(code, name, expected):
    assert format_college_name(code, name) == expected


def test_format_student_college_transferred_student_is_labelled_with_the_api_1_college():
    # Changed college: API 1 (current record) says C, the term row still says E/電機學院.
    # API 1 decides, and the number and the name both describe C.
    sd = {"std_academyno": "C", "trm_academyno": "E", "trm_academyname": "電機學院"}
    assert format_student_college(sd) == "6. 資訊學院"


def test_format_student_college_without_term_name_resolves_from_code():
    assert format_student_college({"std_academyno": "C"}) == "6. 資訊學院"


def test_format_student_college_term_lookup_failed_uses_api_1_only():
    # SIS timed out on the term lookup: only std_* is in the snapshot.
    assert format_student_college({"std_academyno": "E", "std_depno": "1511"}) == "7. 電機學院"


def test_format_student_college_unknown_api_1_code_falls_back_to_the_term_pair():
    # API 1's code is not in the academy table → the term row speaks, as a pair.
    sd = {"std_academyno": "ZZ", "trm_academyno": "E", "trm_academyname": "電機學院"}
    assert format_student_college(sd) == "7. 電機學院"


def test_format_student_college_unknown_codes_fall_back_to_the_term_name_unnumbered():
    sd = {"std_academyno": "ZZ", "trm_academyname": "舊學院"}
    assert format_student_college(sd) == "舊學院"


def test_format_student_college_term_row_without_name_resolves_from_its_code():
    assert format_student_college({"trm_academyno": "C"}) == "6. 資訊學院"


def test_format_student_college_retired_code_is_normalised():
    # Y (電資學院) was merged into E; an old snapshot still gets E's number and name.
    assert format_student_college({"std_academyno": "Y"}) == format_student_college({"std_academyno": "E"})


def test_format_student_college_legacy_code_8():
    assert format_student_college({"trm_academyno": "8", "trm_academyname": "人社院"}) == "1. 人社院"


def test_format_student_college_empty_snapshot():
    assert format_student_college({}) == ""


def test_summary_table_college_column_is_numbered():
    app = SimpleNamespace(
        student_data={"trm_academyno": "C", "trm_academyname": "資訊學院", "trm_depname": "資訊工程學系"},
        submitted_form_data={},
        sub_type_preferences=[],
        sub_scholarship_type=None,
    )
    row = ExportRow(rank_position=1, application=app, bank_account="", advisor_names="")
    values = CollegeRankingExportService()._static_values(row, 1, {})
    assert values[STATIC_HEADERS.index("學院")] == "6. 資訊學院"
    assert values[STATIC_HEADERS.index("系所")] == "資訊工程學系"
