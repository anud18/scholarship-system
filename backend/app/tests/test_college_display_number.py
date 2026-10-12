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


def test_format_student_college_pairs_number_with_term_name():
    # Changed college: base row says C, term row says E/電機學院 → number follows the name.
    sd = {"std_academyno": "C", "trm_academyno": "E", "trm_academyname": "電機學院"}
    assert format_student_college(sd) == "7. 電機學院"


def test_format_student_college_without_term_name_resolves_from_code():
    assert format_student_college({"std_academyno": "C"}) == "6. 資訊學院"


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
