"""Coercion and rendering helpers for ``Application.student_data`` fields.

``student_data`` is the raw SIS API payload, stored verbatim: nothing in the
write path coerces it (``StudentService`` returns ``result["data"][0]`` as-is and
``StudentSnapshotSchema`` is never used to validate it). The university API
returns its code fields as **strings** (see ``mock-student-api/README.md``), so
every read has to tolerate int, float or numeric-string input.

This is a LEAF module by design: the manual-distribution service and the roster
renderers both need these helpers, and putting them here keeps reportlab and
openpyxl out of the core service's import graph.
"""

from __future__ import annotations

from typing import Any, Optional


def as_int(value: Any) -> Optional[int]:
    """SIS code as an int, or ``None`` when it cannot be read as one.

    Goes via ``float`` so a JSON number that arrived as ``1.0`` (or ``"1.0"``)
    still reads as code 1 — ``int("1.0")`` raises, which would silently downgrade
    a real verdict to "unverifiable". ``bool`` is rejected because ``True`` is not
    a SIS code.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def as_text(value: Any) -> str:
    """Trimmed text for any snapshot value.

    A field the schema documents as a string can arrive as a number (e.g. a
    numeric 系所代碼). Calling ``.strip()`` on that raises AttributeError and
    fails the whole caller, so coerce instead.
    """
    if value is None:
        return ""
    return value.strip() if isinstance(value, str) else str(value)


def format_enrollment_date_roc(student_data: dict) -> str:
    """首次註冊入學日期 as ROC calendar (民國年.月.日).

    Single source of truth for the manual-distribution grid and the 分發名單
    export, so the two can never render the same student differently.

    Semantics: only term 1 is September (a missing term defaults to 1, anything
    else — including an uncoercible value — falls to February), and a
    missing/zero/unreadable year renders "".
    """
    enroll_year = as_int(student_data.get("std_enrollyear"))
    raw_term = student_data.get("std_enrollterm")
    enroll_term = 1 if raw_term is None else as_int(raw_term)
    # Approximate: term 1 = September, term 2 = February
    month = "09" if enroll_term == 1 else "02"
    return f"{enroll_year}.{month}.01" if enroll_year else ""
