"""
Tests for received_months_parser — 國科會 獲獎生已領月份統計表 parsing.

Pinned behaviour:
- the header row is found by content, not position
- the 範例 demo row and blank-學號 rows are skipped
- months come from the inclusive F→G span, never from 合計目前領獎月份數
- 合計 disagreeing produces a warning, not an error, and F/G still wins
- unparseable/blank F or G, and G < F, are row errors
"""

from datetime import datetime

import pytest

from app.services.received_months_parser import (
    MonthParseError,
    format_roc_month,
    month_span_inclusive,
    parse_month_cell,
    parse_received_months_workbook,
)

HEADER = (
    "NO",
    "學院",
    "系所",
    "學號",
    "學生姓名",
    "領獎起始月份",
    "目前領獎月份",
    "領獎結束月份",
    "合計目前領獎月份數",
    "休學/退學/畢業",
    "備註",
)
TITLE = ("國科會博士生獎學金-獲獎生已領月份統計表", None, None, None, None, None, None, None, None, None, None)
EXAMPLE = (
    "範例",
    "人文藝術與社會學院",
    "應用藝術研究所",
    "412262001",
    "王美美",
    "113年9月",
    "115年8月",
    "116年8月",
    "24",
    "115年9月休學",
    "",
)


def _row(no, student_number, start, current, stated=None, **extra):
    return (
        no,
        extra.get("college", "電機學院"),
        extra.get("dept", "電機工程學系"),
        student_number,
        extra.get("name", "測試生"),
        start,
        current,
        extra.get("end", ""),
        stated,
        extra.get("status", ""),
        extra.get("remark", ""),
    )


class TestParseMonthCell:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("113年9月", 11309),
            ("113年09月", 11309),
            ("113/9", 11309),
            ("113-09", 11309),
            ("113.9", 11309),
            ("11309", 11309),
            ("　113年9月　", 11309),
            ("202409", 11309),
            ("2024-09", 11309),
            (datetime(2024, 9, 1), 11309),
        ],
    )
    def test_accepted_formats(self, value, expected):
        assert parse_month_cell(value) == expected

    @pytest.mark.parametrize("value", [None, "", "   ", "第九個月", "113年13月", "abc"])
    def test_rejected_formats(self, value):
        with pytest.raises(MonthParseError):
            parse_month_cell(value)

    def test_format_roundtrip(self):
        assert format_roc_month(parse_month_cell("113年9月")) == "113年9月"


class TestMonthSpan:
    def test_span_is_inclusive_of_both_endpoints(self):
        # 113年9月 → 115年8月 is the 24 國科會 states in the sample file.
        assert month_span_inclusive(11309, 11508) == 24

    def test_same_month_is_one(self):
        assert month_span_inclusive(11309, 11309) == 1

    def test_single_year_boundary(self):
        assert month_span_inclusive(11309, 11408) == 12


class TestWorkbookParsing:
    def test_finds_header_below_title_and_skips_example(self):
        rows = [TITLE, HEADER, EXAMPLE, _row(1, "310460031", "113年9月", "115年8月", 24)]
        result = parse_received_months_workbook(rows)

        assert len(result.rows) == 1
        parsed = result.rows[0]
        assert parsed.student_number == "310460031"
        assert parsed.months == 24
        assert parsed.error is None
        assert parsed.warning is None

    def test_blank_student_number_rows_are_skipped(self):
        # The real template ships pre-numbered but empty rows 1..N.
        rows = [
            TITLE,
            HEADER,
            EXAMPLE,
            _row(1, "310460031", "113年9月", "113年10月", 2),
            _row(2, "", "", "", None),
            _row(3, None, None, None, None),
        ]
        result = parse_received_months_workbook(rows)
        assert [r.student_number for r in result.rows] == ["310460031"]

    def test_stated_total_disagreeing_warns_but_keeps_derived_value(self):
        rows = [TITLE, HEADER, _row(1, "310460031", "113年9月", "115年8月", 22)]
        result = parse_received_months_workbook(rows)

        parsed = result.rows[0]
        assert parsed.months == 24, "F→G must win over 合計目前領獎月份數"
        assert parsed.is_valid
        assert parsed.warning is not None
        assert "22" in parsed.warning and "24" in parsed.warning
        assert result.warning_count == 1
        assert result.error_count == 0

    def test_stated_total_absent_is_not_a_warning(self):
        rows = [TITLE, HEADER, _row(1, "310460031", "113年9月", "115年8月", None)]
        result = parse_received_months_workbook(rows)
        assert result.rows[0].warning is None

    def test_blank_start_month_is_a_row_error(self):
        rows = [TITLE, HEADER, _row(1, "310460031", "", "115年8月", 24)]
        result = parse_received_months_workbook(rows)

        parsed = result.rows[0]
        assert not parsed.is_valid
        assert parsed.months is None
        assert "領獎起始月份" in parsed.error
        assert result.error_count == 1

    def test_current_before_start_is_a_row_error(self):
        rows = [TITLE, HEADER, _row(1, "310460031", "115年8月", "113年9月", 24)]
        result = parse_received_months_workbook(rows)

        parsed = result.rows[0]
        assert not parsed.is_valid
        assert "早於" in parsed.error

    def test_raw_row_keeps_every_column_verbatim(self):
        rows = [
            TITLE,
            HEADER,
            _row(1, "310460031", "113年9月", "115年8月", 24, status="115年9月休學", remark="備註內容"),
        ]
        result = parse_received_months_workbook(rows)

        raw = result.rows[0].raw_row
        assert raw["學號"] == "310460031"
        assert raw["領獎起始月份"] == "113年9月"
        assert raw["目前領獎月份"] == "115年8月"
        assert raw["休學/退學/畢業"] == "115年9月休學"
        assert raw["備註"] == "備註內容"
        assert raw["學生姓名"] == "測試生"

    def test_columns_are_mapped_by_header_not_position(self):
        # 國科會 inserting a column must not shift the derivation.
        shifted_header = ("NO", "新欄位", "學號", "領獎起始月份", "目前領獎月份")
        rows = [TITLE, shifted_header, ("1", "x", "310460031", "113年9月", "113年12月")]
        result = parse_received_months_workbook(rows)

        assert result.rows[0].student_number == "310460031"
        assert result.rows[0].months == 4

    def test_missing_header_row_raises(self):
        with pytest.raises(ValueError, match="表頭"):
            parse_received_months_workbook([TITLE, ("a", "b", "c")])

    def test_no_data_rows_raises(self):
        # The blank template: header + 範例 + empty numbered rows only.
        rows = [TITLE, HEADER, EXAMPLE] + [_row(n, "", "", "", None) for n in range(1, 10)]
        with pytest.raises(ValueError, match="沒有可匯入的資料列"):
            parse_received_months_workbook(rows)

    def test_row_number_points_at_the_sheet_row(self):
        rows = [TITLE, HEADER, EXAMPLE, _row(1, "310460031", "", "", None)]
        result = parse_received_months_workbook(rows)
        # TITLE=1, HEADER=2, EXAMPLE=3, data=4
        assert result.rows[0].row_number == 4
