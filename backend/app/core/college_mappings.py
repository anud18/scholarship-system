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
assigning the 學院 role or labelling a quota row. Code 8 (人社院) is excluded
too: the same college is already code A (人社院), so listing both offered a
duplicate 人社院 option. Code Y (電資學院) is excluded as well: the college no
longer exists — see ``MERGED_ACADEMY_CODES``.
"""

from typing import Any, Dict, List, Optional, Tuple

# (code, zh short name, en name) — verbatim from 學院代碼表.xlsx.
# ``en`` is ``aca_ename`` falling back to ``aca_esname``.
ACADEMY_TABLE: Tuple[Tuple[str, str, str], ...] = (
    ("E", "電機學院", "College of Electrical and Computer Engineering"),
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

# Retired SIS academy code -> the college that now owns its students.
# 電資學院 (Y) no longer exists, but SIS still files the 電資博學程 under Y. 電機學院
# (E) manages the programme and is the only one of the two that receives quota,
# so Y students are reviewed, ranked and distributed as E students.
MERGED_ACADEMY_CODES: Dict[str, str] = {"Y": "E"}

# Keys of a SIS student / term record (and the legacy fallback keys read by
# get_college_code_from_data) that carry an academy code or an academy name.
ACADEMY_CODE_KEYS: Tuple[str, ...] = ("std_academyno", "trm_academyno", "academy_code", "college_code", "std_college")
# academy-name key -> the code key it names (the name follows only its own code)
ACADEMY_NAME_KEYS: Dict[str, str] = {"trm_academyname": "trm_academyno"}
# Snapshot metadata key keeping the raw SIS codes that normalization replaced.
ORIGINAL_ACADEMY_CODES_KEY = "_sis_academy_codes_original"


def normalize_academy_code(code: Optional[str]) -> Optional[str]:
    """Map a retired academy code to its surviving college; other values pass through."""
    if not isinstance(code, str):
        return code
    return MERGED_ACADEMY_CODES.get(code.strip(), code)


def normalize_student_academy(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a copy of a SIS student/term record with retired academy codes remapped.

    Every key in ``ACADEMY_CODE_KEYS`` holding a retired code is rewritten to the
    surviving college, an academy name follows only its own code key (a term
    record's name never changes because the *basic* record's code did), and the replaced raw values
    are kept under ``ORIGINAL_ACADEMY_CODES_KEY`` so the SIS value stays auditable.
    A record without retired codes is returned unchanged (same object).
    """
    if not isinstance(record, dict):
        return record

    replaced = {
        key: record[key]
        for key in ACADEMY_CODE_KEYS
        if isinstance(record.get(key), str) and record[key].strip() in MERGED_ACADEMY_CODES
    }
    if not replaced:
        return record

    new_codes = {key: MERGED_ACADEMY_CODES[value.strip()] for key, value in replaced.items()}
    new_names = {
        name_key: COLLEGE_MAPPINGS[new_codes[code_key]]
        for name_key, code_key in ACADEMY_NAME_KEYS.items()
        if code_key in new_codes and new_codes[code_key] in COLLEGE_MAPPINGS
    }
    originals = {**(record.get(ORIGINAL_ACADEMY_CODES_KEY) or {}), **replaced}
    return {**record, **new_codes, **new_names, ORIGINAL_ACADEMY_CODES_KEY: originals}


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
