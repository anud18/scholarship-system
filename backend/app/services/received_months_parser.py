"""
Parser for 國科會's 「獲獎生已領月份統計表」 workbook.

The file is a human-maintained report, not an export, so the parser is
deliberately tolerant of its shape:

* The header row is located by content (a row carrying both 學號 and
  領獎起始月份), not by position — the real file has a merged title above it.
* Columns are mapped by header text, so 國科會 can add, drop or reorder columns
  without breaking the import. Everything on the row is kept verbatim.
* A demo row (學號 column reading 範例) and rows with no 學號 are skipped.

The month count is derived from the inclusive span 領獎起始月份 → 目前領獎月份.
Column 合計目前領獎月份數 is NEVER used as the value; when present and
disagreeing it produces a warning so the admin can eyeball the source data.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

# Header cells that identify the header row and the two columns we derive from.
HEADER_STUDENT_NUMBER = "學號"
HEADER_START_MONTH = "領獎起始月份"
HEADER_CURRENT_MONTH = "目前領獎月份"
HEADER_STATED_TOTAL = "合計目前領獎月份數"

# Rows whose 學號 (or leading NO cell) is this are 國科會's illustrative example.
EXAMPLE_ROW_MARKER = "範例"

# How far down to look for the header before giving up.
MAX_HEADER_SCAN_ROWS = 10

# Gregorian-to-ROC offset. A four-digit year in a month cell is Gregorian.
ROC_YEAR_OFFSET = 1911

# Sanity bounds for a ROC year, guarding against a stray number being read as a
# date (e.g. a sequence number in the wrong column).
MIN_ROC_YEAR = 1
MAX_ROC_YEAR = 999

_MONTH_PATTERNS = (
    # 113年9月 / 113年09月
    re.compile(r"^(?P<year>\d{2,4})\s*年\s*(?P<month>\d{1,2})\s*月?$"),
    # 113/9  113-9  113.9
    re.compile(r"^(?P<year>\d{2,4})\s*[/\-.]\s*(?P<month>\d{1,2})$"),
    # 11309 — six digits would be a Gregorian yyyymm, handled below
    re.compile(r"^(?P<year>\d{3})(?P<month>\d{2})$"),
    re.compile(r"^(?P<year>\d{4})(?P<month>\d{2})$"),
)


class MonthParseError(ValueError):
    """A month cell could not be understood."""


@dataclass
class ParsedRow:
    """One data row from the workbook.

    ``months`` is None exactly when ``error`` is set — an errored row is
    reported to the admin but never written to the ledger.
    """

    row_number: int
    student_number: str
    raw_row: Dict[str, Any]
    months: Optional[int] = None
    award_start_month: Optional[int] = None
    award_current_month: Optional[int] = None
    warning: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.error is None


@dataclass
class ParseResult:
    rows: List[ParsedRow] = field(default_factory=list)
    headers: List[str] = field(default_factory=list)

    @property
    def valid_rows(self) -> List[ParsedRow]:
        return [r for r in self.rows if r.is_valid]

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.rows if r.is_valid and r.warning)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.rows if not r.is_valid)


def _cell_to_text(value: Any) -> str:
    """Normalise a cell to trimmed text, without mangling dates."""
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _to_roc_code(year: int, month: int) -> int:
    """Pack a ROC year/month into a sortable yyyymm integer (113年9月 -> 11309)."""
    return year * 100 + month


def parse_month_cell(value: Any) -> int:
    """Parse a month cell into a ROC yyyymm code.

    Accepts 113年9月, 113年09月, 113/9, 113-09, 11309, a Gregorian 2024-09 /
    202409, and real Excel date cells. Raises MonthParseError otherwise.
    """
    if value is None:
        raise MonthParseError("空白")

    if isinstance(value, (datetime, date)):
        return _to_roc_code(value.year - ROC_YEAR_OFFSET, value.month)

    text = _cell_to_text(value)
    if not text:
        raise MonthParseError("空白")

    # Strip full-width spaces the report tends to carry.
    text = text.replace("　", "").strip()

    for pattern in _MONTH_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        year = int(match.group("year"))
        month = int(match.group("month"))
        if not 1 <= month <= 12:
            raise MonthParseError(f"月份 {month} 不在 1-12 範圍")
        # A four-digit year is Gregorian; anything shorter is already ROC.
        if year >= 1000:
            year -= ROC_YEAR_OFFSET
        if not MIN_ROC_YEAR <= year <= MAX_ROC_YEAR:
            raise MonthParseError(f"民國年 {year} 不合理")
        return _to_roc_code(year, month)

    raise MonthParseError(f"無法解析月份格式: {text}")


def month_span_inclusive(start_code: int, end_code: int) -> int:
    """Inclusive month count between two ROC yyyymm codes.

    113年9月 → 115年8月 is 24 months: both endpoints count, because 目前領獎月份
    is a month the student has already been paid for.
    """
    start_year, start_month = divmod(start_code, 100)
    end_year, end_month = divmod(end_code, 100)
    return (end_year - start_year) * 12 + (end_month - start_month) + 1


def format_roc_month(code: Optional[int]) -> Optional[str]:
    """Render a ROC yyyymm code back as 113年9月 for display."""
    if code is None:
        return None
    year, month = divmod(code, 100)
    return f"{year}年{month}月"


def _find_header_row(rows: List[Tuple[Any, ...]]) -> Tuple[int, List[str]]:
    """Locate the header row by content and return (index, header texts)."""
    for index, row in enumerate(rows[:MAX_HEADER_SCAN_ROWS]):
        texts = [_cell_to_text(cell) for cell in row]
        if HEADER_STUDENT_NUMBER in texts and HEADER_START_MONTH in texts:
            return index, texts
    raise ValueError(f"找不到表頭列（需同時包含「{HEADER_STUDENT_NUMBER}」與「{HEADER_START_MONTH}」）")


def _build_raw_row(headers: List[str], row: Tuple[Any, ...]) -> Dict[str, Any]:
    """Keep every cell, keyed by its header text.

    Unlabelled columns fall back to a positional key so nothing is silently
    dropped; duplicate headers are suffixed for the same reason.
    """
    raw: Dict[str, Any] = {}
    for position, cell in enumerate(row):
        header = headers[position] if position < len(headers) else ""
        key = header or f"欄位{position + 1}"
        if key in raw:
            key = f"{key}_{position + 1}"
        raw[key] = _cell_to_text(cell)
    return raw


def _is_example_row(raw_row: Dict[str, Any], student_number: str) -> bool:
    if student_number == EXAMPLE_ROW_MARKER:
        return True
    # 國科會's template puts 範例 in the NO column with the rest of the row filled in.
    return any(_cell_to_text(v) == EXAMPLE_ROW_MARKER for v in raw_row.values())


def _derive_months(raw_row: Dict[str, Any]) -> Tuple[int, int, int, Optional[str]]:
    """Return (months, start_code, current_code, warning). Raises MonthParseError."""
    try:
        start_code = parse_month_cell(raw_row.get(HEADER_START_MONTH))
    except MonthParseError as exc:
        raise MonthParseError(f"「{HEADER_START_MONTH}」{exc}") from exc

    try:
        current_code = parse_month_cell(raw_row.get(HEADER_CURRENT_MONTH))
    except MonthParseError as exc:
        raise MonthParseError(f"「{HEADER_CURRENT_MONTH}」{exc}") from exc

    if current_code < start_code:
        raise MonthParseError(
            f"「{HEADER_CURRENT_MONTH}」{format_roc_month(current_code)} 早於"
            f"「{HEADER_START_MONTH}」{format_roc_month(start_code)}"
        )

    months = month_span_inclusive(start_code, current_code)

    warning = None
    stated = _cell_to_text(raw_row.get(HEADER_STATED_TOTAL))
    if stated:
        try:
            stated_value = int(float(stated))
        except (TypeError, ValueError):
            warning = f"「{HEADER_STATED_TOTAL}」無法解析為數字: {stated}"
        else:
            if stated_value != months:
                warning = f"「{HEADER_STATED_TOTAL}」為 {stated_value}，與 F→G 推算的 {months} 不一致（採用 {months}）"

    return months, start_code, current_code, warning


def parse_received_months_workbook(rows: List[Tuple[Any, ...]]) -> ParseResult:
    """Parse worksheet rows (as returned by ``ws.iter_rows(values_only=True)``).

    Raises ValueError when the header row cannot be found or the sheet holds no
    data rows at all — those are file-level problems, not row-level ones.
    """
    header_index, headers = _find_header_row(rows)
    result = ParseResult(headers=[h for h in headers if h])

    for offset, row in enumerate(rows[header_index + 1 :]):
        # 1-based sheet row number, for error messages the admin can act on.
        row_number = header_index + offset + 2
        raw_row = _build_raw_row(headers, row)
        student_number = _cell_to_text(raw_row.get(HEADER_STUDENT_NUMBER))

        if not student_number or _is_example_row(raw_row, student_number):
            continue

        try:
            months, start_code, current_code, warning = _derive_months(raw_row)
        except MonthParseError as exc:
            result.rows.append(
                ParsedRow(
                    row_number=row_number,
                    student_number=student_number,
                    raw_row=raw_row,
                    error=str(exc),
                )
            )
            continue

        result.rows.append(
            ParsedRow(
                row_number=row_number,
                student_number=student_number,
                raw_row=raw_row,
                months=months,
                award_start_month=start_code,
                award_current_month=current_code,
                warning=warning,
            )
        )

    if not result.rows:
        raise ValueError("檔案中沒有可匯入的資料列")

    return result
