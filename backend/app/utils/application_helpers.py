"""
學生資料存取 Helper 函數

資料來源說明：
1. 快照資料 (application.student_data)
   - 用途：歷史紀錄查看
   - 特性：申請時的資料快照，不會改變

2. 獎學金期間資料 (StudentService.get_student_term_info)
   - 用途：造冊、分配、資格檢查
   - 特性：該獎學金 config 學年學期的最新狀態
   - 查詢規則：
     * 學期制 (Semester.first/second): 只查指定學期
     * 學年制 (None): 先查第二學期，無資料再查第一學期

3. 當前資料 (StudentService.get_student_basic_info)
   - 用途：顯示用戶目前狀態
   - 特性：當前學年學期的最新資料

錯誤處理原則：
- API 呼叫失敗時直接拋出錯誤
- 不提供 fallback 或 mock 資料
- 符合 CLAUDE.md 錯誤處理標準
"""

import logging
from typing import Any, Dict, Optional

from app.core.exceptions import NotFoundError
from app.models.application import Application
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration
from app.services.student_service import StudentService

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
# 獎學金期間資料存取函數（用於造冊、分配、資格檢查）
# ============================================================================


async def get_scholarship_period_student_data(
    student_code: str,
    scholarship_config: ScholarshipConfiguration,
    student_service: StudentService,
) -> Dict[str, Any]:
    """
    取得獎學金 config 學年學期的最新學生資料

    查詢邏輯：
    1. Semester.first → 只查 term="1"，無資料則報錯
    2. Semester.second → 只查 term="2"，無資料則報錯
    3. None (學年制) → 先查 term="2"，403 則查 term="1"，都無資料則報錯

    Args:
        student_code: 學號
        scholarship_config: 獎學金配置
        student_service: StudentService 實例

    Returns:
        學生資料字典

    Raises:
        ServiceUnavailableError: API 呼叫失敗 (非 403/404)
        NotFoundError: 無學生資料
    """
    academic_year = str(scholarship_config.academic_year)
    semester = scholarship_config.semester

    if semester == Semester.first:
        # 學期制 - 只查第一學期
        logger.info(f"查詢學生 {student_code} 在 {academic_year} 學年度第一學期的資料")
        data = await student_service.get_student_term_info(student_code, academic_year, "1")
        if not data:
            raise NotFoundError(f"學生 {student_code} 在 {academic_year} 學年度第一學期無資料")
        return data

    elif semester == Semester.second:
        # 學期制 - 只查第二學期
        logger.info(f"查詢學生 {student_code} 在 {academic_year} 學年度第二學期的資料")
        data = await student_service.get_student_term_info(student_code, academic_year, "2")
        if not data:
            raise NotFoundError(f"學生 {student_code} 在 {academic_year} 學年度第二學期無資料")
        return data

    else:  # 學年制 (semester is None)
        # 先查第二學期
        logger.info(f"查詢學生 {student_code} 在 {academic_year} 學年度的資料（學年制，先查第二學期）")
        data = await student_service.get_student_term_info(student_code, academic_year, "2")
        if data:
            logger.info(f"學生 {student_code} 在第二學期有資料")
            return data

        # 第二學期無資料，查第一學期
        logger.info(f"學生 {student_code} 第二學期無資料，嘗試查詢第一學期")
        data = await student_service.get_student_term_info(student_code, academic_year, "1")
        if data:
            logger.info(f"學生 {student_code} 在第一學期有資料")
            return data

        # 兩個學期都無資料
        raise NotFoundError(f"學生 {student_code} 在 {academic_year} 學年度兩個學期都無資料")


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
    if not student_data or not isinstance(student_data, dict):
        return None

    return student_data.get("dept_code")


def get_academy_code_from_data(student_data: Dict[str, Any]) -> Optional[str]:
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
    return student_data.get("std_academyno") or student_data.get("academy_code") or student_data.get("college_code")


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


# ============================================================================
# 當前資料存取函數（用於顯示用戶狀態）
# ============================================================================


async def get_current_student_data(
    student_code: str,
    student_service: StudentService,
) -> Dict[str, Any]:
    """
    取得當前學年學期的學生資料

    Args:
        student_code: 學號
        student_service: StudentService 實例

    Returns:
        學生資料字典

    Raises:
        ServiceUnavailableError: API 呼叫失敗
        NotFoundError: 學生不存在
    """
    logger.info(f"查詢學生 {student_code} 的當前資料")
    data = await student_service.get_student_basic_info(student_code)
    if not data:
        raise NotFoundError(f"學生 {student_code} 不存在")
    return data
