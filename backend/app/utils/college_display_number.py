"""學院顯示編號 (各學院編號對照表).

Display-only numbering admins use to refer to colleges, keyed by the SIS academy
code. It does NOT replace the SIS code mapping — codes stay the identity
everywhere; the number is only prefixed onto rendered college names.

Mirrored in ``frontend/lib/college-display-number.ts`` — keep the two in sync.
Every key must be a code in ``app.core.college_mappings.ACADEMY_TABLE`` (or a
documented SIS alias of one); ``test_college_display_number.py`` enforces it.
Comments carry the 對照表's full names; the system shows the short SIS names.
"""

from typing import Any, Mapping, Optional

from app.core.college_mappings import COLLEGE_MAPPINGS

COLLEGE_DISPLAY_NUMBERS: dict[str, int] = {
    "A": 1,  # 人文藝術與社會學院
    "8": 1,  # legacy SIS alias of A (人社院), see college_mappings.py
    "I": 2,  # 工學院
    "B": 3,  # 工程生物科學學院
    "K": 4,  # 客家文化學院
    "S": 5,  # 理學院
    "C": 6,  # 資訊學院
    "E": 7,  # 電機學院
    "M": 8,  # 管理學院
    "O": 9,  # 光電學院
    "L": 10,  # 科技法律學院
    "D": 11,  # 國際半導體產業學院
    "G": 12,  # 智慧科學暨綠能學院
    "2": 13,  # 牙醫學院
    "7": 14,  # 生命科學院
    "6": 15,  # 生物醫學暨工程學院
    "1": 16,  # 醫學院
    "5": 17,  # 藥物科學院
    "3": 18,  # 護理學院
    "F": 19,  # 產學創新研究學院
}


def format_college_name(code: Optional[str], name: Optional[str]) -> str:
    """Prefix ``name`` with its display number ("6. 資訊學院").

    Unnumbered codes and missing codes return the name unchanged; a missing name
    returns "" (never a bare number).
    """
    if not name:
        return ""
    number = COLLEGE_DISPLAY_NUMBERS.get(str(code).strip()) if code is not None else None
    if number is None:
        return name
    return f"{number}. {name}"


def format_student_college(student_data: Mapping[str, Any]) -> str:
    """Numbered 學院 label for an application's SIS snapshot (``student_data``).

    The number and the name must describe the same college, so the code is paired
    with the name it came with: the term row (trm_academyno + trm_academyname)
    first, else the base row's std_academyno with its COLLEGE_MAPPINGS name.
    std_academyno only fills in for a term row that carries a name but no code.
    """
    term_name = student_data.get("trm_academyname")
    if term_name:
        return format_college_name(student_data.get("trm_academyno") or student_data.get("std_academyno"), term_name)
    code = student_data.get("std_academyno") or student_data.get("trm_academyno")
    return format_college_name(code, COLLEGE_MAPPINGS.get(str(code).strip()) if code else None)
