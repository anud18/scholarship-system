"""
Centralized college mappings for the scholarship system
"""

from typing import Dict, List, Optional

# College code to name mappings
COLLEGE_MAPPINGS = {
    "E": "電機學院",
    "C": "資訊學院", 
    "I": "工學院",
    "S": "理學院",
    "B": "工程生物學院",
    "O": "光電學院",
    "D": "半導體學院",
    "1": "醫學院",
    "6": "生醫工學院",
    "7": "生命科學院",
    "M": "管理學院",
    "A": "人社院",
    "K": "客家學院"
}

# English mappings for internationalization
COLLEGE_MAPPINGS_EN = {
    "E": "College of Electrical and Computer Engineering",
    "C": "College of Computer Science", 
    "I": "College of Engineering",
    "S": "College of Science",
    "B": "College of Biological Science and Technology",
    "O": "College of Photonics",
    "D": "College of Semiconductor Research",
    "1": "College of Medicine",
    "6": "College of Biomedical Engineering",
    "7": "College of Life Science",
    "M": "College of Management",
    "A": "College of Humanities and Social Sciences",
    "K": "College of Hakka Studies"
}


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
        colleges.append({
            "code": code,
            "name": COLLEGE_MAPPINGS.get(code, ""),
            "name_en": COLLEGE_MAPPINGS_EN.get(code, "")
        })
    
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