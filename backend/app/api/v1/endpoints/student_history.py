"""Shared student scholarship history endpoints (non-admin roles).

- POST /student-history/batch — multi-student lookup for admin, super_admin and
  college users. College users only see students of their own college: the SIS
  ``std_academyno`` must equal the user's ``college_code``.
- GET /student-history/me/months — a student's own 總領月份數. Students get the
  total months only, never amounts or payment details.

The admin single-student lookup lives at /admin/student-history/{student_number}.
"""

import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ScholarshipException
from app.core.security import require_scholarship_manager, require_student
from app.db.deps import get_db
from app.models.user import User
from app.schemas.student_scholarship_history import (
    BatchStudentHistoryRequest,
    StudentScholarshipHistoryData,
)
from app.services.student_scholarship_history_service import (
    StudentScholarshipHistoryService,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_STUDENT_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9]{4,15}$")
MAX_BATCH_SIZE = 50


def _college_scope_error(user: User, data: StudentScholarshipHistoryData) -> Optional[str]:
    """Per-student authorization for college users.

    Returns an error message when the college user may not view this student,
    None when access is allowed. Admin/super_admin are never scoped. A student
    whose college cannot be determined (SIS unavailable) is denied — access
    control must not fail open on an upstream outage.
    """
    if not user.is_college():
        return None
    basic_info = data.academic_info.basic_info if data.academic_info else None
    academy_no = basic_info.std_academyno if basic_info else None
    if not academy_no:
        return "無法確認學生所屬學院，暫時無法查詢此學生"
    if str(academy_no) != str(user.college_code):
        return "僅能查詢本學院學生"
    return None


def _error_result(student_number: str, error: str) -> Dict[str, Any]:
    return {"student_number": student_number, "success": False, "error": error, "data": None}


@router.post("/batch")
async def batch_student_scholarship_history(
    request: BatchStudentHistoryRequest,
    current_user: User = Depends(require_scholarship_manager),
    db: AsyncSession = Depends(get_db),
):
    """Multi-student history lookup. Per-student failures (not found, out of
    college scope) are reported inside data.results, not as an HTTP error, so
    one bad 學號 doesn't sink the rest of the batch."""
    student_numbers = list(dict.fromkeys(number.strip() for number in request.student_numbers if number.strip()))
    if not student_numbers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="請輸入至少一個學號")
    if len(student_numbers) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"一次最多查詢 {MAX_BATCH_SIZE} 位學生",
        )
    invalid = [number for number in student_numbers if not _STUDENT_NUMBER_PATTERN.match(number)]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"學號格式不正確: {', '.join(invalid)}",
        )
    if current_user.is_college() and not current_user.college_code:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="帳號未設定學院代碼，無法查詢學生領獎紀錄",
        )

    service = StudentScholarshipHistoryService()
    results = []
    # Sequential on purpose: every lookup shares this request's AsyncSession,
    # which does not support concurrent statements on one connection.
    for student_number in student_numbers:
        try:
            data = await service.get_history(db, student_number)
        except ScholarshipException as exc:
            if exc.status_code != status.HTTP_404_NOT_FOUND:
                raise
            results.append(_error_result(student_number, exc.message))
            continue

        scope_error = _college_scope_error(current_user, data)
        if scope_error:
            results.append(_error_result(student_number, scope_error))
            continue

        results.append(
            {
                "student_number": student_number,
                "success": True,
                "error": None,
                "data": data.model_dump(mode="json"),
            }
        )

    return {
        "success": True,
        "message": "Student histories retrieved",
        "data": {"results": results},
    }


@router.get("/me/months")
async def get_my_received_months(
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """A student's own 總領月份數 (匯入 + 系統, summed across every scholarship
    type). No SIS data and no payment records is a valid "0 months" state for a
    student viewing their own history, not a 404."""
    student_number = current_user.nycu_id
    service = StudentScholarshipHistoryService()
    try:
        data = await service.get_history(db, student_number)
        total_received_months = data.summary.total_received_months
    except ScholarshipException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise
        total_received_months = 0

    return {
        "success": True,
        "message": "Received months retrieved",
        "data": {
            "student_number": student_number,
            "total_received_months": total_received_months,
        },
    }
