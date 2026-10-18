"""
學生資料存取 Helper 函數

資料來源說明：
快照資料 (application.student_data) 是申請時 SIS 兩支 API 的快照，不會改變：
1. API 1 (ScholarshipStudent, std_* / com_*)：學生本人的學籍 —— 學院、系所的代碼與歸屬以它為準
2. API 2 (ScholarshipStudentTerm, trm_*)：該獎學金學年學期的紀錄 —— GPA、排名、學期數；
   只在 API 1 沒有時補位（名稱類欄位）
   學期選擇規則集中在 StudentService.get_scholarship_term_info：
     * 學期制 (Semester.first/second): 只查指定學期
     * 學年制 (None / yearly): 先查第二學期，無資料再查第一學期

錯誤處理原則：
- API 呼叫失敗時直接拋出錯誤
- 不提供 fallback 或 mock 資料
- 符合 CLAUDE.md 錯誤處理標準
"""

import logging
from typing import Any, Dict, Mapping, Optional

from app.core.college_mappings import COLLEGE_MAPPINGS, normalize_academy_code
from app.models.application import Application

logger = logging.getLogger(__name__)


# ============================================================================
# 快照資料存取函數（用於歷史查看）
# ============================================================================


def get_snapshot_student_name(application: Application) -> str:
    """
    從申請快照中提取學生姓名（用於歷史紀錄顯示）

    Args:
        application: Application 物件

    Returns:
        學生姓名，無資料時返回 "Unknown"
    """
    if not application.student_data or not isinstance(application.student_data, dict):
        return "Unknown"

    return (
        application.student_data.get("std_cname")
        or application.student_data.get("name")
        or application.student_data.get("student_name")
        or "Unknown"
    )


def get_snapshot_college_code(application: Application) -> Optional[str]:
    """
    從申請快照中提取學院代碼（用於歷史紀錄顯示）

    Args:
        application: Application 物件

    Returns:
        學院代碼，無資料時返回 None
    """
    if not application.student_data or not isinstance(application.student_data, dict):
        return None

    # std_academyno is the correct field from API, prioritize it
    return (
        application.student_data.get("std_academyno")
        or application.student_data.get("academy_code")
        or application.student_data.get("college_code")
        or application.student_data.get("std_college")
    )


def get_snapshot_nycu_id(application: Application) -> Optional[str]:
    """
    從申請快照中提取學號（用於歷史紀錄顯示）

    Args:
        application: Application 物件

    Returns:
        學號，無資料時返回 None
    """
    if not application.student_data or not isinstance(application.student_data, dict):
        return None

    return (
        application.student_data.get("std_stdcode")
        or application.student_data.get("nycu_id")
        or application.student_data.get("student_id")
    )


def get_snapshot_email(application: Application) -> Optional[str]:
    """
    從申請快照中提取 Email（用於歷史紀錄顯示）

    Args:
        application: Application 物件

    Returns:
        Email，無資料時返回 None
    """
    if not application.student_data or not isinstance(application.student_data, dict):
        return None

    return application.student_data.get("com_email") or application.student_data.get("email")


# ============================================================================
# 學生資料欄位存取（來自 student_data 快照 / SIS 回應）
# ============================================================================


def get_student_name_from_data(student_data: Dict[str, Any]) -> str:
    """
    從學生資料字典中提取姓名

    Args:
        student_data: 學生資料字典（來自 API）

    Returns:
        學生姓名，無資料時返回 "Unknown"
    """
    if not student_data or not isinstance(student_data, dict):
        return "Unknown"

    return student_data.get("std_cname") or student_data.get("name") or student_data.get("student_name") or "Unknown"


def get_college_code_from_data(student_data: Dict[str, Any]) -> Optional[str]:
    """
    從學生資料字典中提取學院代碼

    Args:
        student_data: 學生資料字典（來自 API）

    Returns:
        學院代碼，無資料時返回 None
    """
    if not student_data or not isinstance(student_data, dict):
        return None

    # std_academyno is the correct field from API, prioritize it
    return (
        student_data.get("std_academyno")
        or student_data.get("academy_code")
        or student_data.get("college_code")
        or student_data.get("std_college")
    )


def get_nycu_id_from_data(student_data: Dict[str, Any]) -> Optional[str]:
    """
    從學生資料字典中提取學號

    Args:
        student_data: 學生資料字典（來自 API）

    Returns:
        學號，無資料時返回 None
    """
    if not student_data or not isinstance(student_data, dict):
        return None

    return student_data.get("std_stdcode") or student_data.get("nycu_id") or student_data.get("student_id")


def get_email_from_data(student_data: Dict[str, Any]) -> Optional[str]:
    """
    從學生資料字典中提取 Email

    Args:
        student_data: 學生資料字典（來自 API）

    Returns:
        Email，無資料時返回 None
    """
    if not student_data or not isinstance(student_data, dict):
        return None

    return student_data.get("com_email") or student_data.get("email")


def get_department_code_from_data(student_data: Dict[str, Any]) -> Optional[str]:
    """
    從學生資料字典中提取部門代碼

    Args:
        student_data: 學生資料字典（來自 API）

    Returns:
        部門代碼，無資料時返回 None
    """
    if not student_data or not isinstance(student_data, Mapping):
        return None

    # API 1 (std_*) is the student's own record; the term row only fills a gap
    return student_data.get("std_depno") or student_data.get("trm_depno")


def get_academy_code_from_data(student_data: Dict[str, Any]) -> Optional[str]:
    """
    從學生資料字典中提取學院代碼

    Args:
        student_data: 學生資料字典（來自 API）

    Returns:
        學院代碼，無資料時返回 None
    """
    if not student_data or not isinstance(student_data, Mapping):
        return None

    # API 1 (std_*) first — the same field get_college_code_from_data scopes colleges by
    return student_data.get("std_academyno") or student_data.get("trm_academyno")


def _term_row_describes(student_data: Mapping[str, Any], term_code_key: str, code: Any, normalize=str) -> bool:
    """The term row may lend its NAME only if it is about the same unit as ``code``
    (or names no unit of its own) — otherwise a transferred student would get the new
    code next to the old unit's name."""
    term_code = student_data.get(term_code_key)
    return not term_code or normalize(str(term_code).strip()) == normalize(str(code).strip())


def get_academy_name_from_data(student_data: Mapping[str, Any]) -> Optional[str]:
    """
    學院名稱：以 API 1 的學院代碼（std_academyno）對應學院表

    查不到時才用學期資料的名稱，而且只在學期資料指的是同一個學院時 ——
    代碼與名稱因此永遠描述同一個學院（學期資料的學院可能是轉院前的）。
    """
    if not student_data or not isinstance(student_data, Mapping):
        return None

    code = normalize_academy_code(get_academy_code_from_data(student_data))
    if code and COLLEGE_MAPPINGS.get(str(code).strip()):
        return COLLEGE_MAPPINGS[str(code).strip()]
    if not code or _term_row_describes(student_data, "trm_academyno", code, normalize_academy_code):
        return student_data.get("trm_academyname") or None
    return None


def get_department_name_from_data(
    student_data: Mapping[str, Any], department_names: Optional[Mapping[str, str]] = None
) -> Optional[str]:
    """
    系所名稱：以 API 1 的系所代碼（std_depno）查系所表（``department_names``：代碼 → 名稱，
    見 app.services.department_names.load_department_names）

    查不到時才用學期資料的名稱，而且只在學期資料指的是同一個系所時（同 get_academy_name_from_data）。
    """
    if not student_data or not isinstance(student_data, Mapping):
        return None

    code = get_department_code_from_data(student_data)
    if code and department_names and department_names.get(str(code).strip()):
        return department_names[str(code).strip()]
    if not code or _term_row_describes(student_data, "trm_depno", code):
        return student_data.get("trm_depname") or None
    return None


def get_term_count_from_data(student_data: Dict[str, Any]) -> Optional[str]:
    """
    從學生資料字典中提取學期數

    優先使用申請當下學期資料 (trm_termcount)，其次使用基本資料 (std_termcount)

    Args:
        student_data: 學生資料字典（來自 API）

    Returns:
        學期數，無資料時返回 None
    """
    if not student_data or not isinstance(student_data, dict):
        return None

    # Priority: trm_termcount (term data) > std_termcount (basic data) > term_count (legacy)
    return student_data.get("trm_termcount") or student_data.get("std_termcount") or student_data.get("term_count")


def get_enrollment_info_from_data(student_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    從學生資料字典中提取入學資訊（用於 PhD cohort matching）

    Args:
        student_data: 學生資料字典（來自 API）

    Returns:
        包含 enrollyear, enrollterm 的字典
    """
    if not student_data or not isinstance(student_data, dict):
        return {"enrollyear": None, "enrollterm": None}

    return {
        "enrollyear": student_data.get("std_enrollyear"),
        "enrollterm": student_data.get("std_enrollterm"),
    }
