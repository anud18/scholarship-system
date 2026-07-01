"""
Shared helper for preventing spreadsheet formula injection (CWE-1236) when
writing untrusted values into openpyxl workbook cells.
"""

from typing import Any

# Leading characters spreadsheet applications treat as the start of a formula.
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def excel_safe_cell_value(value: Any) -> Any:
    """Neutralize spreadsheet formula injection before an untrusted string
    reaches an xlsx cell.

    openpyxl promotes any string starting with ``=`` to a live formula cell.
    If the value originates from student- or otherwise low-privilege-supplied
    input (form fields, whitelist notes, imported names/addresses) and ends
    up in a workbook a higher-privilege reviewer opens, a malicious value
    could exfiltrate adjacent cell data or worse. Prefixing the value with an
    apostrophe forces spreadsheet applications to treat it as literal text --
    the standard CSV/Excel-injection mitigation (OWASP). Non-string values
    (row numbers, ranks, None) pass through unchanged; ordinary text without
    a leading trigger character is unaffected.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGER_CHARS):
        return "'" + value
    return value
