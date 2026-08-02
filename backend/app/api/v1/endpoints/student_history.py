"""Shared student scholarship history endpoints (non-admin roles).

- POST /student-history/batch — multi-student lookup for admin, super_admin and
  college users. College users only see students of their own college; scope is
  decided snapshot-first (application ``student_data.std_academyno``) with live
  SIS as a secondary signal, so a SIS outage cannot lock colleges out of their
  own students' records.
- GET /student-history/me/months — a student's own 總領月份數. Students get the
  total months only, never amounts or payment details.
- GET/PUT /student-history/visibility — the two admin switches that decide
  whether the student and college views above are open at all.

The admin single-student lookup lives at /admin/student-history/{student_number}.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ScholarshipException
from app.core.security import get_current_user, require_admin, require_scholarship_manager, require_student
from app.db.deps import get_db
from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User
from app.schemas.student_scholarship_history import (
    STUDENT_NUMBER_PATTERN,
    BatchStudentHistoryRequest,
    StudentHistoryVisibilityUpdate,
    StudentScholarshipHistoryData,
)
from app.services.student_history_visibility import (
    COLLEGE_DISABLED_MESSAGE,
    STUDENT_DISABLED_MESSAGE,
    get_student_history_visibility,
    set_student_history_visibility,
)
from app.services.student_scholarship_history_service import (
    StudentScholarshipHistoryService,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_BATCH_SIZE = 20

# One message for BOTH "student does not exist" and "student is outside your
# college": distinguishable errors would let a college account enumerate which
# student numbers exist university-wide (existence oracle).
_COLLEGE_NOT_VISIBLE = "查無符合條件的學生資料"

# Admin-authored content that must not reach college users: free-text
# revocation/suspension notes, and the verbatim rows/provenance of the
# admin-uploaded 已領月份數 import file.
_COLLEGE_HIDDEN_RECORD_FIELDS = ("revoke_reason", "suspend_reason")
_COLLEGE_HIDDEN_MONTHS_FIELDS = ("raw_row", "file_name", "imported_at")


async def _is_college_visible(
    db: AsyncSession,
    service: StudentScholarshipHistoryService,
    college_code: str,
    data: StudentScholarshipHistoryData,
) -> bool:
    """May a college user with ``college_code`` view this student?

    Snapshot-first: the frozen application ``std_academyno`` is the same
    source every other college gate in the repo scopes by, and it keeps the
    awarding college's access alive through SIS outages and student
    transfers. Live SIS additionally admits the student's *current* college
    (e.g. record-less students, post-transfer college). Both sides are
    stripped — ``users.college_code`` is stored unvalidated.
    """
    code = (college_code or "").strip()
    basic_info = data.academic_info.basic_info if data.academic_info else None
    sis_code = str(basic_info.std_academyno).strip() if basic_info and basic_info.std_academyno is not None else ""
    if code and sis_code == code:
        return True
    snapshot_codes = await service.get_snapshot_academy_codes(db, data.student_number)
    return code in snapshot_codes


def _project_payload(data: StudentScholarshipHistoryData, for_college: bool) -> Dict[str, Any]:
    """Serialize history; for college users, blank out admin-only fields."""
    payload = data.model_dump(mode="json")
    if not for_college:
        return payload
    for record in payload["payment_records"]:
        for field in _COLLEGE_HIDDEN_RECORD_FIELDS:
            record[field] = None
    for breakdown in payload["received_months"]:
        for field in _COLLEGE_HIDDEN_MONTHS_FIELDS:
            breakdown[field] = None
    return payload


def _error_result(student_number: str, error: str) -> Dict[str, Any]:
    return {"student_number": student_number, "success": False, "error": error, "data": None}


@router.post("/batch")
async def batch_student_scholarship_history(
    request: BatchStudentHistoryRequest,
    current_user: User = Depends(require_scholarship_manager),
    db: AsyncSession = Depends(get_db),
):
    """Multi-student history lookup. Failures are strictly per-student
    (not found, out of college scope, lookup error) inside data.results —
    one bad 學號 or one failed lookup never sinks the rest of the batch."""
    student_numbers = list(dict.fromkeys(number.strip() for number in request.student_numbers if number.strip()))
    if not student_numbers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="請輸入至少一個學號")
    if len(student_numbers) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"一次最多查詢 {MAX_BATCH_SIZE} 位學生",
        )
    invalid = [number for number in student_numbers if not STUDENT_NUMBER_PATTERN.match(number)]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"學號格式不正確: {', '.join(invalid)}",
        )
    is_college = current_user.is_college()
    if is_college:
        # Admin switch, checked before any lookup work: when 學院查詢 is closed
        # a college account has no access at all, not a narrower one.
        visibility = await get_student_history_visibility(db)
        if not visibility.college_enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=COLLEGE_DISABLED_MESSAGE)
        if not (current_user.college_code or "").strip():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="帳號未設定學院代碼，無法查詢學生領獎紀錄",
            )

    service = StudentScholarshipHistoryService()
    # SIS lookups run as one concurrent wave up front; the per-student loop
    # below stays sequential because every DB statement shares this request's
    # AsyncSession, which does not support concurrent use.
    sis_lookups = await service.fetch_sis_lookups(student_numbers)

    results = []
    for student_number in student_numbers:
        try:
            data = await service.get_history(db, student_number, prefetched_sis=sis_lookups.get(student_number))
            if is_college and not await _is_college_visible(db, service, current_user.college_code, data):
                results.append(_error_result(student_number, _COLLEGE_NOT_VISIBLE))
                continue
        except Exception as exc:
            if isinstance(exc, ScholarshipException) and exc.status_code == status.HTTP_404_NOT_FOUND:
                results.append(_error_result(student_number, _COLLEGE_NOT_VISIBLE if is_college else exc.message))
                continue
            # Per-student contract: report and move on. Roll back so the
            # shared session is usable for the remaining students.
            await db.rollback()
            logger.error("Student history lookup failed for %s", student_number, exc_info=True)
            results.append(_error_result(student_number, "查詢失敗，請稍後再試"))
            continue

        results.append(
            {
                "student_number": student_number,
                "success": True,
                "error": None,
                "data": _project_payload(data, for_college=is_college),
            }
        )

    # Privileged bulk read of payment data — leave an audit trail of who
    # queried whom (the admin single-lookup predates this and has none).
    db.add(
        AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.view.value,
            resource_type="student_history",
            description=f"student history batch lookup ({len(student_numbers)} students)",
            new_values={
                "student_numbers": student_numbers,
                "returned": [r["student_number"] for r in results if r["success"]],
            },
        )
    )
    await db.commit()

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
    type). DB-only — no SIS round trip — and an empty history is a valid
    0-month state, not an error."""
    visibility = await get_student_history_visibility(db)
    if not visibility.student_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=STUDENT_DISABLED_MESSAGE)

    student_number = current_user.nycu_id
    service = StudentScholarshipHistoryService()
    total_received_months = await service.get_total_received_months(db, student_number)

    return {
        "success": True,
        "message": "Received months retrieved",
        "data": {
            "student_number": student_number,
            "total_received_months": total_received_months,
        },
    }


@router.get("/visibility")
async def get_visibility(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Read both switches. Open to any authenticated user on purpose: the
    student card and the college tab hide themselves when their switch is off,
    which needs the flag BEFORE the gated request is attempted. The payload is
    two booleans about the system, never about a person."""
    visibility = await get_student_history_visibility(db)
    return {
        "success": True,
        "message": "Student history visibility retrieved",
        "data": visibility.to_dict(),
    }


@router.put("/visibility")
async def update_visibility(
    request: StudentHistoryVisibilityUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only. Each audience is decided separately — an omitted field keeps
    its current value rather than being reset."""
    try:
        visibility = await set_student_history_visibility(
            db,
            user_id=current_user.id,
            student_enabled=request.student_enabled,
            college_enabled=request.college_enabled,
        )
    except ValueError as exc:
        # Rejected before anything was written (readonly row) — a 400 with the
        # reason, not an opaque 500 from the catch-all handler.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "success": True,
        "message": "Student history visibility updated",
        "data": visibility.to_dict(),
    }
