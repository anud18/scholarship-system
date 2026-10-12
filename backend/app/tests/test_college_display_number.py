"""學院顯示編號: numbered college names in the 學生資料彙整表 學院 column."""

from types import SimpleNamespace

import pytest

from app.services.college_ranking_export_service import STATIC_HEADERS, CollegeRankingExportService, ExportRow
from app.utils.college_display_number import (
    COLLEGE_DISPLAY_NUMBERS,
    format_college_name,
    format_student_college,
)


def test_mapping_numbers_are_1_to_19_unique():
    assert sorted(COLLEGE_DISPLAY_NUMBERS.values()) == list(range(1, 20))


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


def test_format_student_college_prefers_std_academyno():
    sd = {"std_academyno": "C", "trm_academyno": "E", "trm_academyname": "資訊學院"}
    assert format_student_college(sd) == "6. 資訊學院"


def test_format_student_college_falls_back_to_trm_academyno():
    assert format_student_college({"trm_academyno": "E", "trm_academyname": "電機學院"}) == "7. 電機學院"


def test_summary_table_college_column_is_numbered():
    app = SimpleNamespace(
        student_data={"std_academyno": "C", "trm_academyname": "資訊學院", "trm_depname": "資訊工程學系"},
        submitted_form_data={},
        sub_type_preferences=[],
        sub_scholarship_type=None,
    )
    row = ExportRow(rank_position=1, application=app, bank_account="", advisor_names="")
    values = CollegeRankingExportService()._static_values(row, 1, {})
    assert values[STATIC_HEADERS.index("學院")] == "6. 資訊學院"
    assert values[STATIC_HEADERS.index("系所")] == "資訊工程學系"
