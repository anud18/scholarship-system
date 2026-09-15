"""
Centralized college (academy) mappings for the scholarship system.

Source of truth: the SIS academy code table (學院代碼表 — ``aca_academyno`` /
``aca_cname`` / ``aca_ename``). ``ACADEMY_TABLE`` below is a verbatim copy of
that sheet; every other structure in this module is derived from it so the
static fallback map, the ``academies`` DB table (see the
``align_academy_names_*`` migrations) and the reference-data dropdowns can
never disagree with each other.

Numeric codes are the SIS 陽明-campus academy codes (std_academyno). The
sheet's three placeholder rows (4=選讀生, *=外校生, ^=校內其他單位) are
deliberately excluded: they are not colleges and must never be offered when
assigning the 學院 role or labelling a quota row.
"""

from typing import Dict, List, Optional, Tuple

# (code, zh short name, en name) — verbatim from 學院代碼表.xlsx.
# ``en`` is ``aca_ename`` falling back to ``aca_esname``.
ACADEMY_TABLE: Tuple[Tuple[str, str, str], ...] = (
    ("E", "電機學院", "College of Electrical and Computer Engineering"),
    ("Y", "電資學院", "Electrical Engineering and Computer Science"),
    ("C", "資訊學院", "College of Computer Science"),
    ("B", "工程生物學院", "College of Engineering Bioscience"),
    ("M", "管理學院", "College of Management"),
    ("I", "工學院", "College of Engineering"),
    ("S", "理學院", "College of Science"),
    ("A", "人社院", "College of Humanities Arts and Social Sciences"),
    ("K", "客家學院", "College of Hakka Studies"),
    ("X", "電機資訊學院", "Electrical Engineering and Computer Science"),
    ("O", "光電學院", "College of Photonics"),
    ("L", "科技法律學院", "School of Law"),
    ("D", "半導體學院", "International College of Semiconductor Technology"),
    ("G", "綠能學院", "College of Artificial Intelligence"),
    ("Z", "國防中心", "CeNDER"),
    ("8", "人社院", "College of Humanities and Social Sciences"),
    ("1", "醫學院", "College of Medicine"),
    ("2", "牙醫學院", "College of Dentistry"),
    ("3", "護理學院", "College of Nursing"),
    ("5", "藥物科學院", "College of Pharmaceutical Sciences"),
    ("6", "生醫工學院", "College of Biomedical Science and Engineering"),
    ("7", "生命科學院", "College of Life Sciences"),
    ("0", "校級", "School Level"),
    ("F", "產創學院", "Industry Academia Innovation School"),
    ("P", "跨院", "Cross-Domain Integration Promoting Office"),
    ("J", "博雅書苑", "Liberal Arts College"),
)

# College code to name mappings
COLLEGE_MAPPINGS: Dict[str, str] = {code: name for code, name, _ in ACADEMY_TABLE}

# English mappings for internationalization
COLLEGE_MAPPINGS_EN: Dict[str, str] = {code: name_en for code, _, name_en in ACADEMY_TABLE}


def get_college_name(code: str, lang: str = "zh") -> Optional[str]:
    """
    Get college name by code

    Args:
        code: College code (e.g., "E", "C", "I")
        lang: Language code ("zh" for Chinese, "en" for English)

    Returns:
        College name or None if code not found
    """
    if lang == "en":
        return COLLEGE_MAPPINGS_EN.get(code)
    return COLLEGE_MAPPINGS.get(code)


def get_all_colleges(lang: str = "zh") -> List[Dict[str, str]]:
    """
    Get all colleges as a list of dictionaries

    Args:
        lang: Language code ("zh" for Chinese, "en" for English)

    Returns:
        List of college dictionaries with code, name, and name_en
    """
    colleges = []
    mappings = COLLEGE_MAPPINGS_EN if lang == "en" else COLLEGE_MAPPINGS

    for code in sorted(mappings.keys()):
        colleges.append(
            {
                "code": code,
                "name": COLLEGE_MAPPINGS.get(code, ""),
                "name_en": COLLEGE_MAPPINGS_EN.get(code, ""),
            }
        )

    return colleges


def is_valid_college_code(code: str) -> bool:
    """
    Check if a college code is valid

    Args:
        code: College code to validate

    Returns:
        True if valid, False otherwise
    """
    return code in COLLEGE_MAPPINGS


def get_college_codes() -> List[str]:
    """
    Get all valid college codes

    Returns:
        Sorted list of college codes
    """
    return sorted(COLLEGE_MAPPINGS.keys())
